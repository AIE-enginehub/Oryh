"""Synthetic OAuth client registration; no production data or network."""
import re
from urllib.parse import parse_qs, urlsplit
import pytest
from conftest import make_client
from test_oauth import _person, _login, _pkce
from app.core.config import settings

CALLBACK = "workbuddy://workbuddy/mcp/connector%3Aoryh/oauth/callback"
CLOUD_CALLBACK = "https://open.workbuddy.cn/oauth/callback/connectivity"
QUALITY_CALLBACK = "https://www.workbuddy.cn/console/as/p/connector/oauth/oryh/connect"


def test_registration_is_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "oauth_dynamic_registration_enabled", False)
    with make_client() as client:
        assert "registration_endpoint" not in client.get('/.well-known/oauth-authorization-server').json()
        assert client.post('/oauth/register', json={'redirect_uris': [CALLBACK]}).status_code == 404


@pytest.mark.parametrize('uri', [CALLBACK, 'http://127.0.0.1:53421/oauth/callback', CLOUD_CALLBACK, QUALITY_CALLBACK])
def test_registered_client_pkce_consent_and_tool_discovery(monkeypatch, uri):
    monkeypatch.setattr(settings, "oauth_dynamic_registration_enabled", True)
    monkeypatch.setattr(settings, "oauth_workbuddy_connectivity_callback_enabled", uri == CLOUD_CALLBACK)
    monkeypatch.setattr(settings, "oauth_workbuddy_quality_evaluation_callback_enabled", uri == QUALITY_CALLBACK)
    with make_client() as client:
        assert client.get('/.well-known/oauth-authorization-server').json()['registration_endpoint'].endswith('/oauth/register')
        r = client.post('/oauth/register', json={'redirect_uris': [uri], 'client_name': 'Synthetic WorkBuddy', 'grant_types': ['authorization_code', 'refresh_token'], 'token_endpoint_auth_method': 'none'})
        assert r.status_code == 201, r.text
        registration = r.json()
        assert registration['redirect_uris'] == [uri]
        assert 'client_secret' not in registration
        person = _person(client)
        _login(client, person['email'], person['password'])
        verifier, challenge = _pkce()
        params = {'client_id': registration['client_id'], 'redirect_uri': uri, 'response_type': 'code', 'code_challenge': challenge, 'code_challenge_method': 'S256', 'state': 'synthetic', 'resource': 'http://testserver/mcp'}
        assert client.get('/oauth/authorize', params={**params, 'redirect_uri': uri + '?changed=true'}, follow_redirects=False).status_code == 400
        assert client.get('/oauth/authorize', params={**params, 'client_id': 'urn:oryh:oauth-client:invalid'}, follow_redirects=False).status_code == 400
        page = client.get('/oauth/authorize', params=params)
        assert page.status_code == 200, page.text
        consent = re.search(r'name="consent" value="([^"]+)"', page.text).group(1)
        approved = client.post('/oauth/authorize', data={**params, 'decision': 'approve', 'consent': consent}, follow_redirects=False)
        assert approved.status_code == 303, approved.text
        code = parse_qs(urlsplit(approved.headers['location']).query)['code'][0]
        exchange = {'grant_type': 'authorization_code', 'client_id': registration['client_id'], 'redirect_uri': uri, 'code': code, 'code_verifier': verifier}
        assert client.post('/oauth/token', data={**exchange, 'code_verifier': 'wrong'}).status_code == 400
        result = client.post('/oauth/token', data=exchange)
        assert result.status_code == 200, result.text
        assert client.post('/oauth/token', data=exchange).status_code == 400
        client.cookies.clear()
        headers = {'Authorization': 'Bearer ' + result.json()['access_token']}
        for method, params in [('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'synthetic', 'version': '1'}}), ('tools/list', {})]:
            response = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
            assert response.status_code == 200, response.text
            assert 'error' not in response.json(), response.text
            if method == 'initialize':
                assert response.json()['result']['protocolVersion'] == '2025-11-25'
                headers['MCP-Protocol-Version'] = '2025-11-25'
            else:
                assert len(response.json()['result']['tools']) == 8
        assert client.post('/mcp', json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}).status_code == 401


@pytest.mark.parametrize('uri', ['https://evil.example/callback', 'http://localhost:1234/oauth/callback', 'http://127.0.0.1.evil.example:1234/oauth/callback', 'http://user@127.0.0.1:1234/oauth/callback', 'http://127.0.0.1:1234/oauth/callback#fragment', 'workbuddy://evil/mcp/a/oauth/callback', 'javascript:alert(1)', 'http://127.0.0.1:99999/oauth/callback'])
def test_unsafe_callback_rejected(monkeypatch, uri):
    monkeypatch.setattr(settings, 'oauth_dynamic_registration_enabled', True)
    with make_client() as client:
        response = client.post('/oauth/register', json={'redirect_uris': [uri]})
        assert response.status_code == 400
        assert response.json()['error'] == 'invalid_redirect_uri'


def test_rejected_callback_audit_log_contains_only_redirect_metadata(monkeypatch, caplog):
    monkeypatch.setattr(settings, 'oauth_dynamic_registration_enabled', True)
    uri = 'https://quality.example.test/oauth/callback'
    with caplog.at_level('WARNING', logger='oryh.oauth'), make_client() as client:
        response = client.post('/oauth/register', json={
            'redirect_uris': [uri],
            'client_name': 'must-not-appear-in-the-audit-log',
        })
    assert response.status_code == 400
    assert caplog.messages == [
        f"OAuth client registration rejected redirect_uris={[uri]!r}",
    ]
    assert 'must-not-appear-in-the-audit-log' not in caplog.text


@pytest.mark.parametrize(('enabled', 'uri'), [
    (False, CLOUD_CALLBACK),
    (True, CLOUD_CALLBACK + '?other=true'),
    (True, CLOUD_CALLBACK + '#fragment'),
    (True, CLOUD_CALLBACK + '/'),
    (True, CLOUD_CALLBACK.replace('open.workbuddy.cn', 'other.workbuddy.cn')),
    (True, CLOUD_CALLBACK.replace('open.workbuddy.cn', 'open.workbuddy.cn.example.test')),
])
def test_cloud_registration_requires_the_enabled_exact_callback(monkeypatch, enabled, uri):
    monkeypatch.setattr(settings, "oauth_dynamic_registration_enabled", True)
    monkeypatch.setattr(settings, "oauth_workbuddy_connectivity_callback_enabled", enabled)
    with make_client() as client:
        response = client.post('/oauth/register', json={'redirect_uris': [uri]})
        assert response.status_code == 400
        assert response.json()['error'] == 'invalid_redirect_uri'


@pytest.mark.parametrize(('enabled', 'uri'), [
    (False, QUALITY_CALLBACK),
    (True, QUALITY_CALLBACK + '?other=true'),
    (True, QUALITY_CALLBACK + '#fragment'),
    (True, QUALITY_CALLBACK + '/'),
    (True, QUALITY_CALLBACK.replace('www.workbuddy.cn', 'open.workbuddy.cn')),
    (True, QUALITY_CALLBACK.replace('www.workbuddy.cn', 'www.workbuddy.cn.example.test')),
])
def test_quality_registration_requires_the_enabled_exact_callback(monkeypatch, enabled, uri):
    monkeypatch.setattr(settings, "oauth_dynamic_registration_enabled", True)
    monkeypatch.setattr(settings, "oauth_workbuddy_quality_evaluation_callback_enabled", enabled)
    with make_client() as client:
        response = client.post('/oauth/register', json={'redirect_uris': [uri]})
        assert response.status_code == 400
        assert response.json()['error'] == 'invalid_redirect_uri'


@pytest.mark.parametrize(('connectivity_enabled', 'quality_enabled', 'rejected_uri'), [
    (True, False, QUALITY_CALLBACK),
    (False, True, CLOUD_CALLBACK),
])
def test_workbuddy_callback_switches_are_independent(
    monkeypatch, connectivity_enabled, quality_enabled, rejected_uri
):
    monkeypatch.setattr(settings, "oauth_dynamic_registration_enabled", True)
    monkeypatch.setattr(
        settings, "oauth_workbuddy_connectivity_callback_enabled", connectivity_enabled
    )
    monkeypatch.setattr(
        settings, "oauth_workbuddy_quality_evaluation_callback_enabled", quality_enabled
    )
    with make_client() as client:
        response = client.post('/oauth/register', json={'redirect_uris': [rejected_uri]})
        assert response.status_code == 400
        assert response.json()['error'] == 'invalid_redirect_uri'


@pytest.mark.parametrize('extra', [{'token_endpoint_auth_method': 'client_secret_post'}, {'grant_types': ['client_credentials']}, {'scope': 'admin'}, {'client_name': ['bad']}, {'response_types': ['token']}])
def test_unsupported_metadata_rejected(monkeypatch, extra):
    monkeypatch.setattr(settings, 'oauth_dynamic_registration_enabled', True)
    with make_client() as client:
        assert client.post('/oauth/register', json={'redirect_uris': [CALLBACK], **extra}).status_code == 400


def test_invalid_and_oversized_registration_bodies(monkeypatch):
    monkeypatch.setattr(settings, 'oauth_dynamic_registration_enabled', True)
    with make_client() as client:
        for body in [b'{', b'[]', b'x' * 16385]:
            assert client.post('/oauth/register', content=body).status_code == 400
