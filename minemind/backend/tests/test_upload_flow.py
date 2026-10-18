from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from main import app
from services import auth_service as auth, document_lifecycle as lifecycle


def test_upload_idempotency_and_indexing_status(user):
    headers = {'Authorization': 'Bearer ' + auth.create_token(user['id']), 'Idempotency-Key': 'upload-one'}
    with TestClient(app) as client, patch.object(lifecycle, 'ingest_document', AsyncMock(return_value=1)) as ingest:
        first = client.post('/api/upload', headers=headers, files={'file': ('sample.txt', b'Pump pressure must not exceed 42 kPa.', 'text/plain')})
        assert first.status_code == 200, first.text
        second = client.post('/api/upload', headers=headers, files={'file': ('sample.txt', b'Pump pressure must not exceed 42 kPa.', 'text/plain')})
        assert second.status_code == 200, second.text
        assert first.json()['id'] == second.json()['id']
        assert second.json()['status'] == 'ingested'
        assert ingest.await_count == 1
        changed = client.post('/api/upload', headers=headers, files={'file': ('sample.txt', b'Different content', 'text/plain')})
        assert changed.status_code == 409
        assert len(auth.list_documents(user['id'])) == 1


def test_migration_reentry_preserves_data(user):
    auth.save_chat_message(user['id'], 'user', 'Keep this history')
    auth.init_auth_store()
    auth.init_auth_store()
    assert auth.list_chat_messages(user['id'])[0]['content'] == 'Keep this history'


def test_readiness_separate_from_liveness(user):
    with TestClient(app) as client:
        assert client.get('/health').json()['status'] == 'ok'
        with patch('main._connect', side_effect=RuntimeError('unavailable')):
            assert client.get('/ready').status_code == 503
            assert client.get('/health').status_code == 200
