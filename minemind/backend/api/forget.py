from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from services.auth_service import current_user, get_document_for_user, document_state, _connect
from services.document_lifecycle import process_document
from services.query_cache import answers

router=APIRouter()


@router.delete('/api/forget/{dataset_name}')
async def forget_dataset(dataset_name: str,user: dict[str,str]=Depends(current_user)):
    doc=get_document_for_user(user['id'],dataset_name)
    if not doc:
        raise HTTPException(404,'Document not found')
    if doc['status']=='deleted':
        return {'status':'deleted','history_policy':'Prior chat text is retained; source access is disabled.'}
    with _connect() as conn:
        conn.execute("UPDATE documents SET status='delete_pending', failure_reason=NULL, version=version+1 WHERE user_id=%s AND id=%s AND status <> 'deleted'", (user['id'], doc['id']))
    answers.invalidate_user(user['id'])
    await process_document(user['id'],doc['id'])
    state=document_state(user['id'],doc['id'])
    status=state['status']
    return JSONResponse(status_code=200 if status=='deleted' else 503 if status=='delete_failed' else 202,
        content={'status':status,'detail':state.get('failure_reason') or 'Deletion is pending',
                 'history_policy':'Prior chat text is retained; source access is disabled.'})
