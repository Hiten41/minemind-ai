import asyncio
import uuid
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from services import auth_service as auth, document_lifecycle as lifecycle
from services.settings import STORAGE_ROOT
from main import app


def add_doc(user,status='ingested'):
    doc_id=uuid.uuid4().hex
    original=STORAGE_ROOT/'user_files'/user['id']/doc_id/'sample.txt'
    text=STORAGE_ROOT/'user_text'/user['id']/(doc_id+'.txt')
    for path in [original,text]:
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text('Pump pressure 42 kPa.')
    doc={'id':doc_id,'name':'sample.txt','type':'manual','status':status,'node_count':1,'uploaded_at':'2026-10-07T00:00:00+00:00',
         'dataset_name':'user_'+user['id']+'_'+doc_id,'text_path':str(text),'file_path':str(original),'extracted_text':'Pump pressure 42 kPa.','file_content':b'Pump pressure 42 kPa.'}
    auth.save_document(user['id'],doc)
    return doc


def test_delete_failure_retry_cleanup_and_idempotency(user):
    doc=add_doc(user)
    headers={'Authorization':'Bearer '+auth.create_token(user['id'])}
    with TestClient(app) as client:
        with patch.object(lifecycle,'delete_dataset',AsyncMock(return_value=False)):
            response=client.delete('/api/forget/'+doc['dataset_name'],headers=headers)
        assert response.status_code in {202,503}
        assert auth.document_state(user['id'],doc['id'])['status']=='delete_failed'
        assert auth.document_state(user['id'],doc['id'])['dataset_name']==doc['dataset_name']
        with patch.object(lifecycle,'delete_dataset',AsyncMock(return_value=True)):
            response=client.delete('/api/forget/'+doc['dataset_name'],headers=headers)
        assert response.status_code==200
        assert response.json()['status']=='deleted'
        from pathlib import Path
        assert not Path(doc['text_path']).exists() and not Path(doc['file_path']).exists()
        assert auth.document_state(user['id'],doc['id'])['extracted_text'] is None
        assert client.delete('/api/forget/'+doc['dataset_name'],headers=headers).status_code==200
        assert client.get('/api/documents/'+doc['id']+'/file',headers=headers).status_code==404


def test_delete_during_indexing_finishes_after_ingest(user):
    doc=add_doc(user,'queued')
    async def run():
        started=asyncio.Event(); release=asyncio.Event()
        async def ingest(*args):
            started.set(); await release.wait(); return 1
        with patch.object(lifecycle,'ingest_document',ingest), patch.object(lifecycle,'delete_dataset',AsyncMock(return_value=True)) as delete:
            task=asyncio.create_task(lifecycle.process_document(user['id'],doc['id']))
            await started.wait()
            auth.set_document_state(user['id'],doc['id'],'delete_pending')
            release.set(); await task
            assert delete.await_count==1
    asyncio.run(run())
    assert auth.document_state(user['id'],doc['id'])['status']=='deleted'


def test_index_failure_is_durable_and_retry_recovers(user):
    doc=add_doc(user,'queued')
    with patch.object(lifecycle,'ingest_document',AsyncMock(side_effect=RuntimeError('outage'))):
        asyncio.run(lifecycle.process_document(user['id'],doc['id']))
    assert auth.document_state(user['id'],doc['id'])['status']=='failed'
    auth.set_document_state(user['id'],doc['id'],'queued')
    with patch.object(lifecycle,'delete_dataset',AsyncMock(return_value=True)),patch.object(lifecycle,'ingest_document',AsyncMock(return_value=1)):
        asyncio.run(lifecycle.process_document(user['id'],doc['id']))
    assert auth.document_state(user['id'],doc['id'])['status']=='ingested'


def test_corrupt_upload_is_client_error(user):
    with TestClient(app) as client:
        response=client.post('/api/upload',headers={'Authorization':'Bearer '+auth.create_token(user['id'])},files={'file':('broken.pdf',b'broken','application/pdf')})
    assert 400 <= response.status_code < 500
