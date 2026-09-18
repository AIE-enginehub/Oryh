"""Aggregate editing: atomic write, dry run, stale version, stable row ids."""
from test_inline_lines import provision, employee


def setup_document(client):
    auth = provision(client)
    emp = employee(client, auth)
    response = client.post('/api/v1/timesheet-headers', headers=auth, json={
        'employee_id': emp, 'period_start': '2026-06-01', 'period_end': '2026-06-07',
        'entries': [{'work_date': '2026-06-01', 'hours': 8, 'task': 'original'},
                    {'work_date': '2026-06-02', 'hours': 4}],
    })
    assert response.status_code == 201, response.text
    url = '/api/v1/timesheet-headers/' + response.json()['data']['id']
    before = client.get(url + '/detail', headers=auth).json()['data']
    payload = {'expected_revision': before['revision'], 'intent_id': 'test-save',
               'period_start': '2026-06-01', 'period_end': '2026-06-07',
               'source_report_text': 'revised', 'entries': [
                   {'id': before['entries'][0]['id'], 'work_date': '2026-06-03', 'hours': 6, 'task': 'edited'},
                   {'work_date': '2026-06-04', 'hours': 3},
               ]}
    return auth, url, before, payload


def test_save_all_preserves_id_removes_and_adds_in_one_write(client):
    auth, url, before, payload = setup_document(client)
    dry = client.post(url + '/save?validate_only=true', headers=auth, json=payload)
    assert dry.status_code == 200, dry.text
    assert dry.json()['meta'] == {'validate_only': True, 'written': False}
    assert client.get(url + '/detail', headers=auth).json()['data'] == before
    saved = client.post(url + '/save', headers=auth, json=payload)
    assert saved.status_code == 200, saved.text
    after = client.get(url + '/detail', headers=auth).json()['data']
    assert after['header']['source_report_text'] == 'revised'
    assert [(r['work_date'], r['hours']) for r in after['entries']] == [('2026-06-03', 6), ('2026-06-04', 3)]
    assert after['entries'][0]['id'] == before['entries'][0]['id']
    assert before['entries'][1]['id'] not in [r['id'] for r in after['entries']]
    assert client.post(url + '/save', headers=auth, json=payload).status_code == 409


def test_bad_last_row_rolls_back_header_and_prior_rows(client):
    auth, url, before, payload = setup_document(client)
    payload['entries'][-1]['project_id'] = 'missing-project'
    result = client.post(url + '/save', headers=auth, json=payload)
    assert result.status_code in (400, 404, 422), result.text
    assert client.get(url + '/detail', headers=auth).json()['data'] == before


def test_unknown_or_duplicate_ids_and_daily_overflow_rejected(client):
    auth, url, before, payload = setup_document(client)
    payload['entries'][1]['id'] = payload['entries'][0]['id']
    assert client.post(url + '/save', headers=auth, json=payload).status_code == 422
    payload['entries'][1]['id'] = 'foreign-id'
    assert client.post(url + '/save', headers=auth, json=payload).status_code == 422
    del payload['entries'][1]['id']
    for r in payload['entries']:
        r['hours'], r['work_date'] = 16, '2026-06-03'
    assert client.post(url + '/save', headers=auth, json=payload).status_code == 422
    assert client.get(url + '/detail', headers=auth).json()['data'] == before


def test_submitted_sheet_cannot_be_saved(client):
    auth, url, before, payload = setup_document(client)
    assert client.post(url + '/submit', headers=auth, json={}).status_code == 200
    payload['expected_revision'] = client.get(url + '/detail', headers=auth).json()['data']['revision']
    assert client.post(url + '/save', headers=auth, json=payload).status_code == 409


def test_other_tenant_cannot_write_document(client):
    from conftest import provision_tenant
    auth, url, before, payload = setup_document(client)
    other = provision_tenant(client, company_name='Other Save Co', email='admin@other-save.example', password='test-only-pass')
    result = client.post(url + '/save', headers={'X-API-Key': other['plain_text_api_key']}, json=payload)
    assert result.status_code == 404
    assert client.get(url + '/detail', headers=auth).json()['data'] == before
