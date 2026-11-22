import pytest
from fastapi.testclient import TestClient
import main

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'test.sqlite3')
    with TestClient(main.app) as client:
        yield client

LEAD = dict(name='Sam', contact='sam@example.com', inquiry='Book an appointment', consent=True)
BOOKING = dict(name='Sam', contact='sam@example.com', day='2099-01-01', slot='10:00')

def test_lead_duplicate_and_consent(client):
    assert client.post('/leads', json={**LEAD,'consent':False}).status_code == 422
    first=client.post('/leads',json=LEAD).json()
    second=client.post('/leads',json=LEAD).json()
    assert first['lead']['id']==second['lead']['id']
    assert second['duplicate'] is True
    assert len(client.get('/leads').json())==1

def test_sync_failure_retry_idempotency(client):
    identifier=client.post('/leads',json=LEAD).json()['lead']['id']
    assert client.post(f'/leads/{identifier}/sync?simulate_failure=true').status_code==503
    assert client.get('/leads').json()[0]['crm_status']=='failed'
    assert client.post(f'/leads/{identifier}/sync').status_code==200
    assert client.post(f'/leads/{identifier}/sync').json()['already_delivered'] is True
    assert len(client.get('/mock-crm').json())==1

def test_booking_and_cancel(client):
    assert client.get('/availability',params={'day':BOOKING['day'],'slot':'10:00'}).json()['status']=='available'
    booking=client.post('/bookings',json=BOOKING)
    assert booking.status_code==201
    assert client.post('/bookings',json=BOOKING).status_code==409
    assert client.get('/availability',params={'day':BOOKING['day'],'slot':'10:00'}).json()['status']=='unavailable'
    assert client.delete('/bookings/'+booking.json()['id']).status_code==200
    assert client.get('/availability',params={'day':BOOKING['day'],'slot':'10:00'}).json()['status']=='available'

@pytest.mark.parametrize('slot',['banana','25:90','9:00','10:00:00'])
def test_invalid_times(client,slot):
    assert client.post('/bookings',json={**BOOKING,'slot':slot}).status_code==422
    assert client.get('/availability',params={'day':BOOKING['day'],'slot':slot}).status_code==422

def test_outside_hours_and_past_date(client):
    assert client.post('/bookings',json={**BOOKING,'slot':'19:00'}).status_code==409
    assert client.post('/bookings',json={**BOOKING,'day':'2000-01-01'}).status_code==422

def test_validation_and_missing_records(client):
    assert client.post('/leads',json={**LEAD,'contact':'bad'}).status_code==422
    assert client.post('/leads',json={**LEAD,'name':'   '}).status_code==422
    assert client.post('/leads/missing/sync').status_code==404
    assert client.delete('/bookings/missing').status_code==404
    assert client.get('/').status_code==200

def test_concurrent_booking_only_one_wins(client):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes=list(pool.map(lambda _: client.post('/bookings',json=BOOKING).status_code,range(4)))
    assert codes.count(201)==1
    assert codes.count(409)==3

def test_concurrent_duplicate_leads(client):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _: client.post('/leads',json=LEAD).json(),range(4)))
    assert len({result['lead']['id'] for result in results})==1
