import pytest
from fastapi import HTTPException
from test_workflows import client, LEAD, BOOKING
import integrations

@pytest.fixture
def provider(monkeypatch):
    state={'events':{},'crm':{},'calls':[],'busy':False,'broken_ai':False,'lost_create_response':False,'get_fails':False}
    async def fake(service,body):
        state['calls'].append(service)
        if service=='ai':
            if state['broken_ai']:return {'candidates':[{'content':{'parts':[{'text':'not JSON'}]}}]}
            return {'candidates':[{'content':{'parts':[{'text':'{"category":"booking","summary":"Appointment inquiry","missing_information":["date"]}'}]}}]}
        if service=='crm':
            row=state['crm'].setdefault(body['Lead ID'],'row-'+body['Lead ID'])
            return {'row_id':row}
        if service=='calendar-busy':return {'calendars':{integrations.CALENDAR:{'busy':[{'start':'busy'}] if state['busy'] else []}}}
        if service=='calendar-create':
            state['events'][body['id']]={**body,'status':'confirmed'}
            if state['lost_create_response']:raise HTTPException(503,'lost response')
            return state['events'][body['id']]
        if service=='calendar-get':
            if state['get_fails']:raise HTTPException(503,'network unavailable')
            return state['events'].get(body['event_id'],{'_missing':True})
        if service=='calendar-delete':state['events'].pop(body['event_id'],None);return {}
        raise AssertionError(service)
    monkeypatch.setattr(integrations,'external',fake)
    return state

def test_live_lead_validated_and_idempotent(client,provider):
    assert client.post('/api/leads',json={**LEAD,'consent':False}).status_code==422
    assert provider['calls']==[]
    first=client.post('/api/leads',json=LEAD);assert first.status_code==200
    second=client.post('/api/leads',json=LEAD).json()
    assert first.json()['crm_row_id']==second['crm_row_id']
    assert len(provider['crm'])==1
    assert provider['calls'].count('ai')==1
    assert client.get('/api/leads').json()[0]['analysis']['category']=='booking'

def test_invalid_ai_never_reaches_crm(client,provider):
    provider['broken_ai']=True
    assert client.post('/api/leads',json=LEAD).status_code==502
    assert 'crm' not in provider['calls']
    assert len(client.get('/api/leads').json())==1

def test_live_booking_verified_duplicate_conflict_and_cancel(client,provider):
    first=client.post('/api/bookings',json=BOOKING);assert first.status_code==200
    identifier=first.json()['id'];assert identifier in provider['events']
    assert client.post('/api/bookings',json=BOOKING).json()['duplicate'] is True
    assert client.post('/api/bookings',json={**BOOKING,'contact':'other@example.com'}).status_code==409
    assert provider['calls'].count('calendar-create')==1
    assert client.delete('/api/bookings/'+identifier).status_code==200
    assert provider['events']=={}

def test_busy_and_invalid_slot_no_calendar_create(client,provider):
    provider['busy']=True
    assert client.post('/api/bookings',json=BOOKING).status_code==409
    assert client.get('/api/bookings').json()==[]
    assert client.get('/api/availability',params={'day':BOOKING['day'],'slot':'banana'}).status_code==422
    assert client.get('/api/availability',params={'day':'2000-01-01','slot':'10:00'}).status_code==422
    assert 'calendar-create' not in provider['calls']

def test_lost_creation_response_recovers_by_readback(client,provider):
    provider['lost_create_response']=True
    result=client.post('/api/bookings',json=BOOKING)
    assert result.status_code==200
    assert result.json()['status']=='confirmed'

def test_uncertain_booking_stays_pending_then_recovers(client,provider):
    provider['get_fails']=True
    result=client.post('/api/bookings',json=BOOKING)
    assert result.status_code==503
    identifier=result.json()['detail']['booking_id']
    assert client.get('/api/bookings').json()[0]['state']=='pending'
    provider['get_fails']=False
    recovered=client.post('/api/bookings',json=BOOKING)
    assert recovered.status_code==200
    assert recovered.json()['id']==identifier
    assert provider['calls'].count('calendar-create')==1

@pytest.mark.parametrize('service,status,payload,expected',[
    ('calendar-delete',200,None,503),
    ('calendar-delete',204,None,None),
    ('calendar-delete',404,{'code':404,'message':'Webhook not registered'},503),
    ('calendar-delete',404,{'error':{'code':404,'message':'Not Found'}},None),
    ('ai',200,None,503),
])
def test_connector_does_not_mistake_missing_workflow_for_success(monkeypatch,service,status,payload,expected):
    import asyncio,httpx
    monkeypatch.setenv('N8N_CONNECTOR_SECRET','synthetic-test-secret')
    response=httpx.Response(status,json=payload) if payload is not None else httpx.Response(status,content=b'')
    class FakeClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):return response
    monkeypatch.setattr(integrations.httpx,'AsyncClient',lambda **kwargs:FakeClient())
    if expected:
        with pytest.raises(HTTPException) as exc:asyncio.run(integrations.external(service,{}))
        assert exc.value.status_code==expected
    else:
        assert isinstance(asyncio.run(integrations.external(service,{})),dict)
