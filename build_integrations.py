"""Generate credential-backed n8n service workflows; never embed secrets."""
import json,uuid
from pathlib import Path
CALENDAR='6eb1955c34502def63f25be36f8a7ad339087b1d66e5e88ce4b1ec8e576074a4@group.calendar.google.com'
from urllib.parse import quote
EVENTS='https://www.googleapis.com/calendar/v3/calendars/'+quote(CALENDAR,safe='')+'/events'
CREDENTIALS={'googlePalmApi':{'id':'uHBHaSV4u59W9jid','name':'Google Gemini(PaLM) Api account'},'googleCalendarOAuth2Api':{'id':'sKqfNb3VIhv2YtrK','name':'Google Calendar account'}}
def http_node(name,url,kind,method='POST',body='={{ JSON.stringify($json.body) }}'):
    params={'url':url,'method':method,'authentication':'predefinedCredentialType','nodeCredentialType':kind,'options':{'timeout':65000,'response':{'response':{'fullResponse':True,'neverError':True}}}}
    if method=='POST':params.update(sendBody=True,specifyBody='json',jsonBody=body)
    return {'id':name,'name':name,'type':'n8n-nodes-base.httpRequest','typeVersion':4.2,'position':[250,0],'parameters':params,'credentials':{kind:CREDENTIALS[kind]},'onError':'continueRegularOutput'}
def workflow(identifier,service):
    trigger={'id':'Receive','name':'Receive','type':'n8n-nodes-base.webhook','typeVersion':2,'webhookId':identifier,'position':[0,0],'parameters':{'httpMethod':'POST','path':identifier,'responseMode':'responseNode','authentication':'headerAuth','options':{}},'credentials':{'httpHeaderAuth':{'id':'portfolio-connector-auth','name':'Portfolio backend access'}}}
    response={'id':'Return','name':'Return','type':'n8n-nodes-base.respondToWebhook','typeVersion':1.4,'position':[500,0],'parameters':{'respondWith':'json','responseBody':'={{ JSON.stringify($json.body || {}) }}','options':{'responseCode':'={{ $json.statusCode || 503 }}'}}}
    return {'id':identifier,'versionId':str(uuid.uuid4()),'name':'Portfolio - '+identifier.removeprefix('portfolio-').replace('-',' ').title(),'active':False,'settings':{'executionOrder':'v1'},'nodes':[trigger,service,response],'connections':{'Receive':{'main':[[{'node':service['name'],'type':'main','index':0}]]},service['name']:{'main':[[{'node':'Return','type':'main','index':0}]]}}}
services={
'portfolio-ai':http_node('Gemini extraction','https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent','googlePalmApi'),
'portfolio-calendar-busy':http_node('Calendar availability','https://www.googleapis.com/calendar/v3/freeBusy','googleCalendarOAuth2Api'),
'portfolio-calendar-create':http_node('Create calendar event',EVENTS,'googleCalendarOAuth2Api'),
'portfolio-calendar-get':http_node('Verify calendar event',"={{ '"+EVENTS+"/' + encodeURIComponent($json.body.event_id) }}",'googleCalendarOAuth2Api','GET'),
'portfolio-calendar-delete':http_node('Cancel calendar event',"={{ '"+EVENTS+"/' + encodeURIComponent($json.body.event_id) }}",'googleCalendarOAuth2Api','DELETE')}
workflows=[]
for identifier,service in services.items():
    if identifier.endswith('-delete'):
        # A 204 has no JSON body; return a stable empty object.
        w=workflow(identifier,service);w['nodes'][-1]['parameters']['responseBody']='={{ JSON.stringify($json.body || {}) }}'
    else:w=workflow(identifier,service)
    workflows.append(w)
    Path(identifier+'.json').write_text(json.dumps(w,indent=2))
Path('integration-workflows.json').write_text(json.dumps(workflows,indent=2))
print('Generated five external-service workflows')
