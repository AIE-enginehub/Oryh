"""OAuth 2.1, the second door's lock: discovery documents, authorization
code + PKCE in the person's browser, the token endpoint's three grants
(code, refresh, device), and the refusals — a redirect that is not the
client's own host, a wrong verifier, a spent code."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from conftest import make_client, provision_tenant

CLIENT_ID = "https://agent.example.com/client"
REDIRECT = "http://127.0.0.1:53421/callback"


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _person(client: TestClient) -> dict:
    t = provision_tenant(client, company_name="OAuth Co", email="admin@oauth-co.example", password="admin-pass1")
    return {"service": {"X-API-Key": t["plain_text_api_key"]}, "email": "admin@oauth-co.example", "password": "admin-pass1"}


def _login(client: TestClient, email: str, password: str) -> None:
    r = client.post("/web/login", data={"email": email, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text


def _authorize(client: TestClient, challenge: str, *, decision: str = "approve", state: str = "xyz") -> dict[str, list[str]]:
    params = {
        "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
        "resource": "http://testserver/mcp",
    }
    page = client.get("/oauth/authorize", params=params)
    assert page.status_code == 200 and "agent.example.com" in page.text, page.text[:300]
    consent = re.search(r'name="consent" value="([^"]+)"', page.text).group(1)
    decided = client.post("/oauth/authorize", data={**params, "decision": decision, "consent": consent}, follow_redirects=False)
    assert decided.status_code == 303, decided.text
    location = decided.headers["location"]
    assert location.startswith(REDIRECT + "?")
    return parse_qs(urlsplit(location).query)


def test_discovery_documents_point_at_this_server() -> None:
    with make_client([]) as client:
        meta = client.get("/.well-known/oauth-authorization-server").json()
        assert meta["authorization_endpoint"].endswith("/oauth/authorize")
        assert meta["token_endpoint"].endswith("/oauth/token")
        assert meta["code_challenge_methods_supported"] == ["S256"]
        assert "urn:ietf:params:oauth:grant-type:device_code" in meta["grant_types_supported"]
        resource = client.get("/.well-known/oauth-protected-resource/mcp").json()
        assert resource["resource"].endswith("/mcp") and resource["authorization_servers"] == [meta["issuer"]]


def test_authorization_code_with_pkce_mints_the_interactive_key_pair() -> None:
    with make_client([]) as client:
        person = _person(client)
        verifier, challenge = _pkce()
        anonymous = client.get("/oauth/authorize", params={
            "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT,
            "code_challenge": challenge, "code_challenge_method": "S256"}, follow_redirects=False)
        assert anonymous.status_code == 303 and "/web/login?next=" in anonymous.headers["location"], \
            "consent needs the person: the browser goes to login and comes back"
        _login(client, person["email"], person["password"])
        query = _authorize(client, challenge)
        assert query["state"] == ["xyz"] and query["iss"], "state echoed, issuer named (RFC 9207)"
        code = query["code"][0]

        wrong = client.post("/oauth/token", data={
            "grant_type": "authorization_code", "code": code, "code_verifier": "not-the-verifier",
            "client_id": CLIENT_ID, "redirect_uri": REDIRECT})
        assert wrong.status_code == 400 and wrong.json()["error"] == "invalid_grant"

        exchanged = client.post("/oauth/token", data={
            "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
            "client_id": CLIENT_ID, "redirect_uri": REDIRECT})
        assert exchanged.status_code == 200, exchanged.text
        tokens = exchanged.json()
        assert tokens["token_type"] == "Bearer" and tokens["expires_in"] > 0 and tokens["refresh_token"]

        client.cookies.clear()
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert me.status_code == 200, "the access token is the interactive api key, presented as a bearer"

        again = client.post("/oauth/token", data={
            "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
            "client_id": CLIENT_ID, "redirect_uri": REDIRECT})
        assert again.status_code == 400, "a code is spent once"

        refreshed = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200 and refreshed.json()["access_token"] != tokens["access_token"], \
            "the refresh grant rotates the pair, same as /auth/token/refresh"


def test_the_redirect_must_be_the_clients_own_host_or_loopback() -> None:
    with make_client([]) as client:
        person = _person(client)
        _login(client, person["email"], person["password"])
        _verifier, challenge = _pkce()
        foreign = client.get("/oauth/authorize", params={
            "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": "https://evil.example.net/cb",
            "code_challenge": challenge, "code_challenge_method": "S256"})
        assert foreign.status_code == 400, "never redirect a code to a host that is not the client's"
        own = client.get("/oauth/authorize", params={
            "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": "https://agent.example.com/cb",
            "code_challenge": challenge, "code_challenge_method": "S256"})
        assert own.status_code == 200
        no_pkce = client.get("/oauth/authorize", params={
            "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT}, follow_redirects=False)
        assert no_pkce.status_code == 303 and "error=invalid_request" in no_pkce.headers["location"]
        denied = _authorize(client, challenge, decision="deny", state="s1")
        assert denied["error"] == ["access_denied"] and denied["state"] == ["s1"]


def test_the_device_grant_is_the_existing_device_flow_under_its_rfc_name() -> None:
    with make_client([]) as client:
        person = _person(client)
        started = client.post("/oauth/device_authorization", data={"client_id": CLIENT_ID}).json()
        assert started["user_code"] and started["verification_uri"].endswith("/web/device")
        pending = client.post("/oauth/token", data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": started["device_code"]})
        assert pending.status_code == 400 and pending.json()["error"] == "authorization_pending"
        _login(client, person["email"], person["password"])
        approved = client.post("/web/device/approve", data={"code": started["user_code"]})
        assert approved.status_code == 200
        tokens = client.post("/oauth/token", data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": started["device_code"]})
        assert tokens.status_code == 200 and tokens.json()["token_type"] == "Bearer", tokens.text


def test_the_consent_is_a_nonce_shown_to_this_session_and_spent_once() -> None:
    """Review R08: a logged-in browser could be made to approve without ever
    seeing the consent page. The consent is now a nonce minted for the
    session that loaded the page, bound to the request's parameters, spent
    once, and the POST must come from this site."""
    with make_client([]) as client:
        person = _person(client)
        _login(client, person["email"], person["password"])
        _verifier, challenge = _pkce()
        params = {
            "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT,
            "code_challenge": challenge, "code_challenge_method": "S256", "state": "n1",
        }
        blind = client.post("/oauth/authorize", data={**params, "decision": "approve"}, follow_redirects=False)
        assert blind.status_code == 403, "no consent page seen, no code"

        page = client.get("/oauth/authorize", params=params)
        consent = re.search(r'name="consent" value="([^"]+)"', page.text).group(1)
        foreign = client.post("/oauth/authorize", data={**params, "decision": "approve", "consent": consent},
                              headers={"Origin": "https://evil.example.net"}, follow_redirects=False)
        assert foreign.status_code == 403, "a consent posted from another origin is refused"
        swapped = client.post("/oauth/authorize", data={**params, "redirect_uri": "http://127.0.0.1:9/cb",
                                                        "decision": "approve", "consent": consent}, follow_redirects=False)
        assert swapped.status_code == 400 or swapped.status_code == 403, "the nonce is bound to the parameters it was shown for"
        ok = client.post("/oauth/authorize", data={**params, "decision": "approve", "consent": consent}, follow_redirects=False)
        assert ok.status_code == 303 and "code=" in ok.headers["location"]
        again = client.post("/oauth/authorize", data={**params, "decision": "approve", "consent": consent}, follow_redirects=False)
        assert again.status_code == 403, "a consent is spent once"
