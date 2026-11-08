import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.agent import Session


def config(tmp_path):
    return Settings(_env_file=None, model_api_key='env-secret', search_api_key='search-secret',
                    answer_review_enabled=False, campus_auth_file=tmp_path / 'no-auth')


def test_settings_are_write_only_persistent_and_take_effect(tmp_path):
    path = tmp_path / 'private/settings.json'
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': '合成回答'}, 'finish_reason': 'stop'}]})

    with TestClient(create_app(config(tmp_path), httpx.MockTransport(upstream), settings_file=path)) as client:
        read = client.get('/api/settings')
        assert read.headers['cache-control'] == 'no-store'
        assert read.json()['model_api_key_configured']
        assert 'env-secret' not in read.text and 'search-secret' not in read.text
        response = client.patch('/api/settings', json={'model_api_key': ' new-secret ', 'model_base_url': 'https://example.org/v1',
                                                     'model_name': 'new-model', 'model_max_tokens': 800})
        assert response.status_code == 200
        assert 'new-secret' not in response.text
        assert response.json()['model_name'] == 'new-model'
        sid = client.post('/api/sessions').json()['session_id']
        client.post(f'/api/sessions/{sid}/chat', json={'message': '你好', 'source_mode': 'web'})
        assert calls[-1].url == 'https://example.org/v1/chat/completions'
        assert calls[-1].headers['authorization'] == 'Bearer new-secret'
        assert json.loads(calls[-1].content)['max_tokens'] == 800
        assert client.patch('/api/settings', json={'model_name': 'another-model'}).json()['model_api_key_configured']
    assert json.loads(path.read_text())['model_api_key'] == 'new-secret'
    assert json.loads(path.read_text())['search_api_key'] == 'search-secret'
    with TestClient(create_app(config(tmp_path), settings_file=path)) as client:
        assert client.get('/api/health').json()['model']['name'] == 'another-model'
        assert client.patch('/api/settings', json={'model_api_key': ''}).json()['model_api_key_configured'] is False
        assert client.get('/api/health').json()['model']['configured'] is False
    with TestClient(create_app(config(tmp_path), settings_file=path)) as client:
        assert client.get('/api/settings').json()['model_api_key_configured'] is False


def test_restart_uses_saved_settings_even_with_conflicting_environment(tmp_path, monkeypatch):
    path = tmp_path / 'settings.json'
    monkeypatch.setenv('MODEL_API_KEY', 'must-never-be-used')
    monkeypatch.setenv('SEARCH_PROVIDER', 'invalid-old-value')
    base = Settings(_env_file=None, campus_auth_file=tmp_path / 'no-auth')
    with TestClient(create_app(base, settings_file=path)) as client:
        assert not client.get('/api/settings').json()['model_api_key_configured']
        result = client.patch('/api/settings', json={'model_api_key': 'saved-key', 'model_name': 'saved-model',
                                                    'model_max_tokens': 1024, 'request_budget_seconds': 90})
        assert result.status_code == 200
        expected = result.json()
    with TestClient(create_app(base, settings_file=path)) as client:
        assert client.get('/api/settings').json() == expected
        client.patch('/api/settings', json={'model_api_key': ''})
    with TestClient(create_app(base, settings_file=path)) as client:
        assert not client.get('/api/health').json()['model']['configured']


def test_legacy_migration_preserves_saved_values_and_archives_secrets(tmp_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('migrate_settings', Path(__file__).resolve().parents[1] / 'scripts/migrate_settings.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    folder = tmp_path / '.private'
    folder.mkdir()
    (folder / 'settings.json').write_text(json.dumps({'model_api_key': 'saved-key', 'model_name': 'saved-model'}))
    legacy = tmp_path / '.env'
    original = 'MODEL_API_KEY=old-key\nMODEL_NAME=old-model\nSEARCH_API_KEY=search-key\nSEARCH_PROVIDER=tavily\nBACKEND_PORT=8123\n'
    legacy.write_text(original)
    count, backup, deployment = migration.migrate(tmp_path)
    assert count == 2 and deployment == ['BACKEND_PORT']
    assert not legacy.exists()
    assert backup.read_text() == original
    saved = json.loads((folder / 'settings.json').read_text())
    assert saved['model_api_key'] == 'saved-key' and saved['model_name'] == 'saved-model'
    assert saved['search_api_key'] == 'search-key' and saved['search_provider'] == 'tavily'
    assert 'backend_port' not in saved
    assert migration.migrate(tmp_path) == (0, None, [])


@pytest.mark.parametrize('payload', [
    {'model_max_tokens': 0, 'model_api_key': 'never-echo'},
    {'model_api_key': None}, {'model_api_key': 'a' * 8193},
    {'model_base_url': 'https://user:never-echo@example.org'},
    {'model_base_url': 'https://example.org/?key=never-echo'},
    {'model_name': '   '}, {'backend_port': 9999}, {'search_provider': 'unknown'},
])
def test_invalid_settings_do_not_echo_secrets_or_change_config(tmp_path, payload):
    path = tmp_path / 'settings.json'
    with TestClient(create_app(config(tmp_path), settings_file=path)) as client:
        before = client.get('/api/settings').json()
        result = client.patch('/api/settings', json=payload)
        assert result.status_code == 422
        assert 'never-echo' not in result.text
        assert client.get('/api/settings').json() == before
        assert not path.exists()


def test_settings_failure_busy_and_cross_site_guards(tmp_path, monkeypatch):
    path = tmp_path / 'settings.json'
    with TestClient(create_app(config(tmp_path), settings_file=path)) as client:
        original = client.get('/api/settings').json()
        session = Session(busy=True)
        client.app.state.sessions[session.id] = session
        assert client.patch('/api/settings', json={'model_name': 'changed'}).status_code == 409
        session.busy = False
        assert client.patch('/api/settings', json={}, headers={'Origin': 'https://foreign.example'}).status_code == 403
        assert client.patch('/api/settings', json={}, headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
        assert client.patch('/api/settings', content='model_name=x', headers={'Content-Type': 'text/plain'}).status_code == 415
        malformed = client.patch('/api/settings', content='{"model_api_key":"never-echo",', headers={'Content-Type': 'application/json'})
        assert malformed.status_code == 422 and 'never-echo' not in malformed.text
        monkeypatch.setattr('app.runtime_settings.os.replace', lambda *args: (_ for _ in ()).throw(OSError('private-path-secret')))
        result = client.patch('/api/settings', json={'model_api_key': 'never-echo'})
        assert result.status_code == 503 and 'never-echo' not in result.text and 'private-path-secret' not in result.text
        assert client.get('/api/settings').json() == original
        assert not path.exists()
        assert not list(tmp_path.glob('.settings-*.tmp'))
