"""Geos and territories: places in a hierarchy, territories as sets of
places with people, and a customer's territory resolved from where it is.

Pinned: the hierarchy cannot loop; the China template loads once and is
harmless to repeat; coverage is by containment (a territory covering the
province covers the city); the most specific coverage wins; two territories
at the same level make the answer ambiguous and the customer's territory
stays empty for a person to set; a lead's geo and owner ride the conversion
bridge into the customer; and a geo change on a customer re-resolves.
"""

from __future__ import annotations

import pytest

from conftest import make_client, provision_tenant


@pytest.fixture()
def desk():
    with make_client([]) as client:
        t = provision_tenant(client, company_name="Geo Co", email="admin@geo.example")
        admin = {"X-API-Key": t["plain_text_api_key"]}
        yield {"client": client, "admin": admin}


def _geo(client, admin, code, name, geo_type, parent=None):
    made = client.post("/api/v1/geos", headers=admin,
                       json={"geo_code": code, "name": name, "geo_type": geo_type, "parent_geo_id": parent})
    assert made.status_code == 201, made.text
    return made.json()["data"]


def test_places_form_a_hierarchy_and_the_template_loads_once(desk) -> None:
    client, admin = desk["client"], desk["admin"]
    first = client.post("/api/v1/geos/seed-template", headers=admin, json={"template": "cn_provinces"})
    assert first.status_code == 201, first.text
    assert first.json()["created"] == 35 and first.json()["existing"] == 0
    again = client.post("/api/v1/geos/seed-template", headers=admin, json={"template": "cn_provinces"})
    assert again.json()["created"] == 0 and again.json()["existing"] == 35

    zhejiang = client.get("/api/v1/geos?geo_code=330000", headers=admin).json()["data"][0]
    cn = client.get("/api/v1/geos?geo_code=CN", headers=admin).json()["data"][0]
    assert zhejiang["parent_geo_id"] == cn["id"] and zhejiang["geo_type"] == "province"
    hangzhou = _geo(client, admin, "3301", "杭州市", "city", zhejiang["id"])
    xihu = _geo(client, admin, "330106", "西湖区", "district", hangzhou["id"])
    path = client.get(f"/api/v1/geos/{xihu['id']}/path", headers=admin).json()["data"]
    assert [g["name"] for g in path][2:] == ["杭州市", "西湖区"]
    # the template's own rows are named by the seed locale: Chinese in the
    # cloud assembly, English in the standalone one
    assert [g["name"] for g in path][:2] in (["中国", "浙江省"], ["China", "Zhejiang"])

    assert client.post("/api/v1/geos", headers=admin,
                       json={"geo_code": "x", "name": "x", "geo_type": "planet"}).status_code == 422
    loop = client.patch(f"/api/v1/geos/{zhejiang['id']}", headers=admin, json={"parent_geo_id": xihu["id"]})
    assert loop.status_code == 422, "a parent below the geo would loop"
    assert client.post("/api/v1/geos", headers=admin,
                       json={"geo_code": "3301", "name": "again", "geo_type": "city"}).status_code == 409
    provinces = client.get("/api/v1/geos?geo_type=province&page=1&size=5", headers=admin).json()
    assert provinces["meta"]["total"] == 34


def test_coverage_is_by_containment_and_ambiguity_is_a_persons_call(desk) -> None:
    client, admin = desk["client"], desk["admin"]
    cn = _geo(client, admin, "CN", "中国", "country")
    zhejiang = _geo(client, admin, "33", "浙江省", "province", cn["id"])
    jiangsu = _geo(client, admin, "32", "江苏省", "province", cn["id"])
    hangzhou = _geo(client, admin, "3301", "杭州市", "city", zhejiang["id"])
    ningbo = _geo(client, admin, "3302", "宁波市", "city", zhejiang["id"])
    xihu = _geo(client, admin, "330106", "西湖区", "district", hangzhou["id"])

    manager = client.post("/api/v1/employees", json={"name": "东区经理"}, headers=admin).json()["data"]["id"]
    east = client.post("/api/v1/territories", headers=admin,
                       json={"territory_code": "EAST", "name": "华东区", "manager_employee_id": manager}).json()["data"]
    zj = client.post("/api/v1/territories", headers=admin,
                     json={"territory_code": "ZJ", "name": "浙江区", "parent_territory_id": east["id"]}).json()["data"]
    hz = client.post("/api/v1/territories", headers=admin,
                     json={"territory_code": "HZ", "name": "杭州区", "parent_territory_id": zj["id"]}).json()["data"]
    for territory, geo in ((east, zhejiang), (east, jiangsu), (zj, zhejiang), (hz, hangzhou)):
        cover = client.post("/api/v1/territory-geos", headers=admin,
                            json={"territory_id": territory["id"], "geo_id": geo["id"]})
        assert cover.status_code == 201, cover.text
    assert client.post("/api/v1/territory-geos", headers=admin,
                       json={"territory_id": hz["id"], "geo_id": hangzhou["id"]}).status_code == 409

    # a district in Hangzhou: the city territory is the most specific answer
    resolved = client.get(f"/api/v1/territory-resolution?geo_id={xihu['id']}", headers=admin).json()["data"]
    assert [g["name"] for g in resolved["geo_path"]] == ["西湖区", "杭州市", "浙江省", "中国"]
    assert resolved["territory"]["territory_code"] == "HZ" and resolved["ambiguous"] is False
    assert [(m["territory"]["territory_code"], m["depth"]) for m in resolved["matches"]] == [("HZ", 1), ("EAST", 2), ("ZJ", 2)]
    # Ningbo: nothing covers the city; the province is covered by two territories at the same depth
    resolved = client.get(f"/api/v1/territory-resolution?geo_id={ningbo['id']}", headers=admin).json()["data"]
    assert resolved["territory"] is None and resolved["ambiguous"] is True
    assert {m["territory"]["territory_code"] for m in resolved["matches"]} == {"EAST", "ZJ"}

    # a customer in Xihu gets HZ on its own; one in Ningbo gets nothing until a person decides
    xihu_customer = client.post("/api/v1/customers", headers=admin,
                                json={"name": "西湖客户", "geo_id": xihu["id"], "payment_terms": "月结 30 天"}).json()["data"]
    assert xihu_customer["territory_id"] == hz["id"] and xihu_customer["payment_terms"] == "月结 30 天"
    ningbo_customer = client.post("/api/v1/customers", headers=admin,
                                  json={"name": "宁波客户", "geo_id": ningbo["id"]}).json()["data"]
    assert ningbo_customer["territory_id"] is None
    assigned = client.patch(f"/api/v1/customers/{ningbo_customer['id']}", headers=admin,
                            json={"territory_id": zj["id"], "owner_employee_id": manager})
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["data"]["territory_id"] == zj["id"] and assigned.json()["data"]["owner_employee_id"] == manager
    # moving the customer re-resolves
    moved = client.patch(f"/api/v1/customers/{ningbo_customer['id']}", headers=admin, json={"geo_id": hangzhou["id"]})
    assert moved.json()["data"]["territory_id"] == hz["id"]
    by_territory = client.get(f"/api/v1/customers?territory_id={hz['id']}", headers=admin).json()["data"]
    assert {c["name"] for c in by_territory} == {"西湖客户", "宁波客户"}

    member = client.post("/api/v1/territory-members", headers=admin,
                         json={"territory_id": hz["id"], "employee_id": manager, "role": "manager"})
    assert member.status_code == 201, member.text
    assert client.post("/api/v1/territory-members", headers=admin,
                       json={"territory_id": hz["id"], "employee_id": manager, "role": "rep"}).status_code == 409
    assert client.post("/api/v1/territory-members", headers=admin,
                       json={"territory_id": hz["id"], "employee_id": manager, "role": "mascot"}).status_code == 422


def test_a_leads_place_and_owner_ride_the_bridge(desk) -> None:
    client, admin = desk["client"], desk["admin"]
    cn = _geo(client, admin, "CN", "中国", "country")
    zhejiang = _geo(client, admin, "33", "浙江省", "province", cn["id"])
    zj = client.post("/api/v1/territories", headers=admin, json={"territory_code": "ZJ", "name": "浙江区"}).json()["data"]
    client.post("/api/v1/territory-geos", headers=admin, json={"territory_id": zj["id"], "geo_id": zhejiang["id"]})
    rep = client.post("/api/v1/employees", json={"name": "小张"}, headers=admin).json()["data"]["id"]

    ghost = client.post("/api/v1/leads", headers=admin, json={"employee_id": rep, "company_name": "x",
                                                                "geo_id": "00000000-0000-0000-0000-000000000000"})
    assert ghost.status_code == 404
    lead = client.post("/api/v1/leads", headers=admin,
                       json={"employee_id": rep, "company_name": "泵业公司", "geo_id": zhejiang["id"]}).json()["data"]
    assert lead["geo_id"] == zhejiang["id"]
    client.patch(f"/api/v1/leads/{lead['id']}", headers=admin, json={"status": "qualified"})
    converted = client.post(f"/api/v1/leads/{lead['id']}/convert", headers=admin, json={})
    assert converted.status_code in (200, 201), converted.text
    customer_id = client.get(f"/api/v1/leads/{lead['id']}", headers=admin).json()["data"]["converted_customer_id"]
    customer = client.get(f"/api/v1/customers/{customer_id}", headers=admin).json()["data"]
    assert customer["geo_id"] == zhejiang["id"]
    assert customer["territory_id"] == zj["id"]
    assert customer["owner_employee_id"] == rep
    mine = client.get(f"/api/v1/customers?owner_employee_id={rep}", headers=admin).json()["data"]
    assert [c["id"] for c in mine] == [customer_id]
