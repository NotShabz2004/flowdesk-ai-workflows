"""Generate the credential-backed SeaTable connector with schema and idempotency gates."""
import json,uuid
from pathlib import Path
w=json.loads(Path('portfolio-ai.json').read_text())
w.update(id='portfolio-crm',versionId=str(uuid.uuid4()),name='Portfolio - SeaTable CRM',active=False)
trigger=w['nodes'][0];trigger.update(webhookId='portfolio-crm');trigger['parameters']['path']='portfolio-crm'
cred={'seaTableApi':{'id':'fGbdHWd3D93qVwVD','name':'SeaTable account'}}
def sea(name,params,pos):return {'id':name,'name':name,'type':'n8n-nodes-base.seaTable','typeVersion':2,'position':pos,'parameters':params,'credentials':cred}
def code(name,js,pos):return {'id':name,'name':name,'type':'n8n-nodes-base.code','typeVersion':2,'position':pos,'parameters':{'jsCode':js}}
metadata=sea('Check CRM schema',{'resource':'base','operation':'metadata'},[200,0])
validate=code('Validate schema and reference',"""const required=['Name','Lead ID','Contact','Inquiry','Category','Summary','Status'];
const table=$input.first().json.tables?.find(t=>t.name==='Table1');
const missing=required.filter(n=>!table?.columns?.some(c=>c.name===n && c.type==='text'));
if(missing.length) throw new Error('SeaTable setup required: add Text columns '+missing.join(', '));
const body=$('Receive').first().json.body;
if(!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(body['Lead ID']||''))throw new Error('Invalid lead reference');
for(const name of required){if(typeof body[name]!=='string'||!body[name].trim())throw new Error('Missing '+name);}
return [{json:body}];""",[400,0])
search=sea('Find lead reference',{'resource':'row','operation':'search','tableName':'Table1','searchColumn':'Lead ID','searchTerm':"={{ $json['Lead ID'] }}",'options':{'wildcard':False,'simple':False,'convert':True}},[600,0]);search['alwaysOutputData']=True
branch={'id':'Already in CRM','name':'Already in CRM','type':'n8n-nodes-base.if','typeVersion':2.2,'position':[800,0],'parameters':{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':'exists','leftValue':'={{ Boolean($json._id) }}','rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}}}
columns=['Name','Lead ID','Contact','Inquiry','Category','Summary','Status']
create=sea('Create CRM lead',{'resource':'row','operation':'create','tableName':'Table1','fieldsToSend':'defineBelow','columnsUi':{'columnValues':[{'columnName':c,'columnValue':"={{ $('Validate schema and reference').first().json["+json.dumps(c)+"] }}"} for c in columns]},'bigdata':False,'apply_default':False},[1000,120])
result=code('CRM reference',"const item=$input.first().json; const row=item._id || item.first_row?._id || item.row_ids?.[0]; if(!row)throw new Error('CRM returned no row reference'); return [{json:{row_id:row}}];",[1200,0])
response=w['nodes'][-1];response['position']=[1400,0];response['parameters']={'respondWith':'json','responseBody':'={{ JSON.stringify($json) }}','options':{'responseCode':200}}
w['nodes']=[trigger,metadata,validate,search,branch,create,result,response]
def edge(name):return {'node':name,'type':'main','index':0}
w['connections']={a:{'main':[[edge(b)]]} for a,b in [('Receive','Check CRM schema'),('Check CRM schema','Validate schema and reference'),('Validate schema and reference','Find lead reference'),('Find lead reference','Already in CRM'),('Create CRM lead','CRM reference'),('CRM reference','Return')]}
w['connections']['Already in CRM']={'main':[[edge('CRM reference')],[edge('Create CRM lead')]]}
Path('portfolio-crm.json').write_text(json.dumps(w,indent=2))
print('Protected SeaTable workflow generated; checks schema before any write')
