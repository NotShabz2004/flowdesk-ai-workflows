"""Opt-in real-service smoke test. Creates one synthetic CRM lead and cancels its test appointment."""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import httpx

BASE='http://127.0.0.1:18766'
def run():
    checks=[]
    with httpx.Client(base_url=BASE,timeout=95) as c:
        assert c.get('/').status_code==200;checks.append('Frontend served')
        lead={'name':'Portfolio Demo','contact':'portfolio-demo@example.com','inquiry':'Synthetic test '+uuid4().hex[:8]+': I want to book an appointment but have not picked a day or time.','consent':True}
        assert c.post('/api/leads',json={**lead,'consent':False}).status_code==422;checks.append('Consent enforced')
        first=c.post('/api/leads',json=lead)
        if first.status_code!=200:
            raise RuntimeError('Live lead flow: '+str(first.status_code)+' '+first.text[:300])
        first=first.json();assert first['crm_row_id'];checks.append('Gemini structured extraction + SeaTable row created')
        second=c.post('/api/leads',json=lead);assert second.status_code==200
        assert second.json()['crm_row_id']==first['crm_row_id'];checks.append('Duplicate inquiry reuses CRM row')
        day=(datetime.now(timezone(timedelta(hours=4)))+timedelta(days=8)).date().isoformat()
        booking={'day':day,'slot':'14:00','name':'Portfolio Demo','contact':'portfolio-demo@example.com'}
        available=c.get('/api/availability',params={'day':day,'slot':'14:00'})
        assert available.status_code==200 and available.json()['status']=='available';checks.append('Live Calendar availability')
        identifier=None
        try:
            r=c.post('/api/bookings',json=booking)
            if r.status_code!=200:raise RuntimeError('Booking flow: '+str(r.status_code)+' '+r.text[:300])
            identifier=r.json()['id'];assert r.json()['status']=='confirmed';checks.append('Calendar creation verified by readback')
            assert c.post('/api/bookings',json=booking).json()['id']==identifier;checks.append('Booking retry idempotent')
            assert c.post('/api/bookings',json={**booking,'contact':'other@example.com'}).status_code==409;checks.append('Conflicting booking rejected')
            assert c.post('/api/bookings/'+identifier+'/verify').status_code==200;checks.append('Explicit booking verification')
        finally:
            if identifier:
                cancellation=c.delete('/api/bookings/'+identifier)
                assert cancellation.status_code==200;checks.append('Calendar cancellation')
        available=c.get('/api/availability',params={'day':day,'slot':'14:00'})
        assert available.json()['status']=='available';checks.append('Cancelled slot available again')
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'synthetic_crm_row_retained':True}
    Path('verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':run()
