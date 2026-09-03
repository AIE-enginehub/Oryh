"""Product images: the catalog's pictures, bytes in the attachment store.

What is pinned: the catalog desk may upload (master_data.manage now counts
as a filing capability) and only image/* attachments become pictures; one
primary per product with promotion demoting the old in the same write; the
gallery lists primary-first then curated order; the bytes are read through
the product that carries them, by everyone, and an image id that is real
but another product's is a 404 like one that is not real; removing a
picture removes the link and keeps the bytes; product reads carry
primary_image_id so a list can show thumbnails without a query per row.
"""

from __future__ import annotations

import base64

import pytest

from app.services.emails import outbox

from conftest import make_client, provision_tenant

# a valid 1×1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@pytest.fixture()
def gallery():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Pic Co", email="admin@pic.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}

        def desk(name: str, permissions: list[str]) -> dict:
            client.post("/api/v1/roles", json={"name": name, "permissions": permissions},
                        headers=admin)
            uid = client.post("/api/v1/auth/invitations",
                              json={"email": f"{name}@pic.example", "role": name},
                              headers=admin).json()["data"]["id"]
            token = next(l.rsplit("token=", 1)[1].strip()
                         for l in outbox.messages[-1].body.splitlines() if "token=" in l)
            client.post("/api/v1/auth/invitations/accept",
                        json={"token": token, "password": "invitee-pass1"})
            return {"X-API-Key": client.post(
                "/api/v1/tenant/api-keys", json={"label": name, "user_id": uid},
                headers=admin).json()["data"]["plain_text_api_key"]}

        curator = desk("curator", ["master_data.manage"])
        member = desk("nobody", [])
        product = client.post("/api/v1/products", json={"name": "工业阀门"},
                              headers=curator).json()["data"]["id"]

        def upload(filename: str, content_type: str, raw: bytes = PNG, headers=None) -> object:
            return client.post("/api/v1/attachments", headers=headers or curator, json={
                "filename": filename, "content_type": content_type,
                "content_base64": base64.b64encode(raw).decode()})

        def picture(attachment_id: str, **extra) -> dict:
            r = client.post("/api/v1/product-images", headers=curator,
                            json={"product_id": product, "attachment_id": attachment_id, **extra})
            assert r.status_code == 201, r.text
            return r.json()["data"]

        yield {"client": client, "admin": admin, "curator": curator, "member": member,
               "product": product, "upload": upload, "picture": picture}


def test_the_catalog_desk_uploads_and_only_images_become_pictures(gallery) -> None:
    client, curator = gallery["client"], gallery["curator"]
    uploaded = gallery["upload"]("valve.png", "image/png")
    assert uploaded.status_code == 201, "master_data.manage now files attachment-backed records"
    sheet = gallery["upload"]("spec.xlsx",
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              b"PK fake sheet")
    not_a_picture = client.post("/api/v1/product-images", headers=curator, json={
        "product_id": gallery["product"], "attachment_id": sheet.json()["data"]["id"]})
    assert not_a_picture.status_code == 422, "a spec sheet is a document, not a picture"
    refused = gallery["upload"]("x.png", "image/png", headers=gallery["member"])
    assert refused.status_code == 403


def test_one_primary_and_the_gallery_order(gallery) -> None:
    client, curator = gallery["client"], gallery["curator"]
    a = gallery["upload"]("a.png", "image/png").json()["data"]["id"]
    b = gallery["upload"]("b.png", "image/png", PNG + b"\n").json()["data"]["id"]
    c = gallery["upload"]("c.png", "image/png", PNG + b"\n\n").json()["data"]["id"]
    first = gallery["picture"](a, is_primary=True, sort_order=2)
    second = gallery["picture"](b, sort_order=1)
    third = gallery["picture"](c, is_primary=True, caption="细节")
    assert third["is_primary"]
    rows = client.get("/api/v1/product-images", headers=gallery["member"],
                      params={"product_id": gallery["product"]}).json()["data"]
    assert [r["attachment_id"] for r in rows] == [c, b, a], \
        "primary first, then the curated order — and the old primary was demoted"
    assert sum(1 for r in rows if r["is_primary"]) == 1

    promoted = client.patch(f"/api/v1/product-images/{second['id']}", headers=curator,
                            json={"is_primary": True})
    assert promoted.status_code == 200
    rows = client.get("/api/v1/product-images", headers=curator,
                      params={"product_id": gallery["product"]}).json()["data"]
    assert [r["id"] for r in rows if r["is_primary"]] == [second["id"]]

    doubled = client.post("/api/v1/product-images", headers=curator, json={
        "product_id": gallery["product"], "attachment_id": a})
    assert doubled.status_code == 409, "the same picture twice on one product is one row"
    del first


def test_bytes_are_read_through_the_product_and_only_its_own(gallery) -> None:
    client, curator = gallery["client"], gallery["curator"]
    a = gallery["upload"]("valve.png", "image/png").json()["data"]["id"]
    image = gallery["picture"](a, is_primary=True)
    read = client.get(f"/api/v1/products/{gallery['product']}/attachments/{a}/content",
                      headers=gallery["member"])
    assert read.status_code == 200, "everyone reads the catalog, so everyone reads its pictures"
    assert read.headers["content-type"].startswith("image/png") and read.content == PNG

    other = client.post("/api/v1/products", json={"name": "别的产品"},
                        headers=curator).json()["data"]["id"]
    crossed = client.get(f"/api/v1/products/{other}/attachments/{a}/content",
                         headers=gallery["member"])
    assert crossed.status_code == 404, "a real attachment on the wrong product reads as not found"

    listed = client.get("/api/v1/products", headers=gallery["member"],
                        params={"keyword": "工业阀门"}).json()["data"][0]
    assert listed["primary_image_id"] == image["id"], "lists can show thumbnails without a query per row"

    removed = client.delete(f"/api/v1/product-images/{image['id']}", headers=curator)
    assert removed.status_code == 204
    kept = client.get(f"/api/v1/attachments/{a}", headers=gallery["admin"])
    assert kept.status_code == 200, "the link goes, the bytes stay in the store"


def test_a_picture_says_what_kind_it_is(gallery) -> None:
    """The kind is the tenant's vocabulary, orthogonal to the primary: a
    design draft is usually not the primary, a detail shot never is by
    default, and the e-commerce sync asks for every detail shot at once."""
    client, curator = gallery["client"], gallery["curator"]
    hero = gallery["upload"]("hero.png", "image/png").json()["data"]["id"]
    detail = gallery["upload"]("detail.png", "image/png", PNG + b"\n").json()["data"]["id"]
    draft = gallery["upload"]("draft.pdf", "application/pdf", b"%PDF-1.4 design").json()["data"]["id"]
    sheet = gallery["upload"]("sizes.xlsx",
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                              b"PK fake").json()["data"]["id"]

    bent = client.post("/api/v1/product-images", headers=curator, json={
        "product_id": gallery["product"], "attachment_id": hero, "image_type": "hologram"})
    assert bent.status_code == 422 and "detail" in bent.json()["detail"], \
        "an unknown kind is refused with the vocabulary"

    gallery["picture"](hero, is_primary=True, image_type="main")
    gallery["picture"](detail, image_type="detail")
    design = gallery["picture"](draft, image_type="design", caption="V3 效果图")
    assert design["content_type"] == "application/pdf", "a PDF design draft belongs in the gallery"
    refused = client.post("/api/v1/product-images", headers=curator, json={
        "product_id": gallery["product"], "attachment_id": sheet, "image_type": "dimension"})
    assert refused.status_code == 422, "a spreadsheet is a document, not a picture"

    details = client.get("/api/v1/product-images", headers=gallery["member"],
                         params={"product_id": gallery["product"], "image_type": "detail"}
                         ).json()["data"]
    assert [r["attachment_id"] for r in details] == [detail], "the sync asks by kind"
    retyped = client.patch(f"/api/v1/product-images/{design['id']}", headers=curator,
                           json={"image_type": "dimension"})
    assert retyped.status_code == 200 and retyped.json()["data"]["image_type"] == "dimension"
    mistyped = client.patch(f"/api/v1/product-images/{design['id']}", headers=curator,
                            json={"image_type": "hologram"})
    assert mistyped.status_code == 422, "the vocabulary holds on PATCH as it does on POST"
