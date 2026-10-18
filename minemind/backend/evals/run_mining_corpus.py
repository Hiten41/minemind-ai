"""Isolated public-PDF evaluation. Never touches the user's database or Cognee datasets."""
import argparse, asyncio, hashlib, json, os, sys, time, tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
sys.stdout.reconfigure(encoding='utf-8')

p=argparse.ArgumentParser()
p.add_argument('--backend',default=str(Path(__file__).resolve().parents[1]))
p.add_argument('--corpus',required=True)
p.add_argument('--output',required=True)
p.add_argument('--live',action='store_true')
p.add_argument('--interval',type=float,default=60)
p.add_argument('--only',default='')
args=p.parse_args()
root=Path(__file__).resolve().parent
corpus=Path(args.corpus).resolve()
manifest=json.loads((root/'mining_corpus.json').read_text(encoding='utf-8'))
sys.path.insert(0,str(Path(args.backend).resolve()))
from dotenv import load_dotenv
if args.live:
    load_dotenv(Path(args.backend).resolve()/'.env')
storage=Path(tempfile.mkdtemp(prefix='minemind-public-eval-'))
os.environ.update(APP_ENV='development',DATABASE_URL='',AUTH_SECRET='public-corpus-test-only',MINEMIND_DISABLE_WORKER='true',MINEMIND_STORAGE_DIR=str(storage),MINEMIND_SQLITE_PATH=str(storage/'eval.db'),COGNEE_BASE_URL='',COGNEE_API_KEY='')
if not args.live: os.environ['GROQ_API_KEY']=''
import dotenv
dotenv.load_dotenv=lambda *a,**k:False
from services.parser import parse_pdf
from services.retrieval import retrieval_question, retrieve
from models.schemas import QueryRequest
from services import auth_service as auth
from api import query
from main import app
from fastapi.testclient import TestClient
provider_records=[]
original_client=query.create_llm_client
def recording_client():
    client=original_client()
    create=client.chat.completions.create
    async def recorded(**kwargs):
        try:
            result=await create(**kwargs)
            provider_records.append({'purpose':'resolve' if kwargs['messages'][0]['content']==query.RESOLVE_RULES else 'answer',
                'content':result.choices[0].message.content,'finish_reason':result.choices[0].finish_reason})
            return result
        except Exception as exc:
            provider_records.append({'exception':type(exc).__name__})
            raise
    client.chat.completions.create=recorded
    return client
if args.live: query.create_llm_client=recording_client

documents=[]
for item in manifest['documents']:
    path=corpus/item['file']
    text=parse_pdf(str(path))
    documents.append(dict(id=item['file'],name=item['file'],dataset_name='public-eval-'+item['file'],
        type='manual',status='ingested',node_count=0,uploaded_at='2026-10-15T00:00:00',extracted_text=text,
        content_hash=hashlib.sha256(path.read_bytes()).hexdigest()))
results=[]
report={'mode':'live HTTP / real answer provider / local retrieval; semantic provider disabled' if args.live else 'offline local retrieval',
        'model':query.ANSWER_LLM_MODEL,'semantic_correctness':'Requires independent source review; exact citation offsets alone are not correctness.',
        'backend':str(Path(args.backend).resolve()),'documents':[{'name':d['name'],'sha256':d['content_hash']} for d in documents], 'results':results}
output=Path(args.output).resolve()
output.parent.mkdir(parents=True,exist_ok=True)
def save(): output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
auth.init_auth_store()
user=auth.create_user('Corpus Evaluation',f'eval-{time.time_ns()}@example.com','+919999999999','corpus-test-password')
for d in documents: auth.save_document(user['id'],d)
app.dependency_overrides[auth.current_user]=lambda:user
chains=[]
for d in manifest['documents']:
    for ci,chain in enumerate(d['chains']): chains.append((d['file']+f':{ci}',[d['file']],chain))
for i,test in enumerate(manifest['cross_document_checks']):chains.append((f'cross:{i}',test['scope'],[test]))
only=set(args.only.split(',')) if args.only else None
last=0
with TestClient(app) as client, patch('services.retrieval.query_memory',AsyncMock(return_value=[])):
    for chain_id,scope,turns in chains:
        if only and chain_id not in only: continue
        history=[]
        for i,turn in enumerate(turns):
            request=QueryRequest(question=turn['q'],scope_mode='selected',document_ids=scope,chat_history=history[-20:])
            selected=[d for d in documents if d['id'] in scope]
            resolved=retrieval_question(request,selected)
            chunks,diagnostics=asyncio.run(retrieve(resolved,selected))
            row={'id':chain_id+f':{i}','question':turn['q'],'resolved':resolved,'expected':turn,
                 'retrieved':[{'page':c.page,'document':c.title,'text':c.text} for c in chunks]}
            if args.live:
                time.sleep(max(0,args.interval-(time.monotonic()-last)))
                last=time.monotonic()
                response=client.post('/api/query',json=request.model_dump())
                row['provider_records']=list(provider_records);provider_records.clear()
                row['seconds']=round(time.monotonic()-last,2)
                row['http_status']=response.status_code
                row['response']=response.json()
                sources=row['response'].get('sources',[])
                byid={d['id']:d for d in selected}
                row['exact_scoped_citations']=all(s['document_id'] in byid and byid[s['document_id']]['extracted_text'][s['start_offset']:s['end_offset']]==s['excerpt'] for s in sources)
                history.extend([{'role':'user','content':turn['q']},{'role':'assistant','content':row['response'].get('answer','')}])
                print(row['id'],row['response'].get('evidence_status'),row['seconds'],row['response'].get('answer','')[:200],flush=True)
            else:
                history.append({'role':'user','content':turn['q']})
                print(row['id'],'pages',sorted({c.page for c in chunks if c.page}),flush=True)
            results.append(row);save()
print('Saved',len(results),'turns',str(output),flush=True)
