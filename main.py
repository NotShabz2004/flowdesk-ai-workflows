from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4
import os
import re
import sqlite3

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

DB = Path(os.environ.get("WORKFLOWS_DB", "workflows.sqlite3"))
SLOTS = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00"]

@contextmanager
def connection():
    with sqlite3.connect(DB, timeout=10) as db:
        db.row_factory = sqlite3.Row
        yield db

@asynccontextmanager
async def lifespan(app):
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, contact TEXT NOT NULL,
          inquiry TEXT NOT NULL, consent INTEGER NOT NULL, category TEXT NOT NULL,
          crm_status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
          UNIQUE(contact, inquiry));
        CREATE TABLE IF NOT EXISTS mock_crm (lead_id TEXT PRIMARY KEY, contact TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bookings (
          id TEXT PRIMARY KEY, day TEXT NOT NULL, slot TEXT NOT NULL, name TEXT NOT NULL,
          contact TEXT NOT NULL, UNIQUE(day, slot));
        """)
    from integrations import setup
    setup(connection)
    yield

app = FastAPI(title="Business Workflows Portfolio", lifespan=lifespan,
              description="AI-assisted portfolio demo: Gemini lead qualification, SeaTable CRM and verified Google Calendar appointments. Legacy mock endpoints remain for isolated tests.")

class LeadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    contact: str = Field(min_length=3, max_length=200)
    inquiry: str = Field(min_length=5, max_length=2000)
    consent: bool = Field(strict=True)

    @field_validator("contact")
    @classmethod
    def valid_contact(cls, value):
        value = value.lower()
        if not (re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) or re.fullmatch(r"\+?[0-9]{7,15}", value)):
            raise ValueError("Use an email address or phone number containing 7-15 digits")
        return value

class BookingInput(BaseModel):
    day: date
    slot: str
    name: str = Field(min_length=1, max_length=100)
    contact: str = Field(min_length=3, max_length=200)
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @field_validator("slot")
    @classmethod
    def valid_time(cls, value):
        if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
            raise ValueError("Use HH:MM in 24-hour format")
        return value

    @field_validator("day")
    @classmethod
    def future_day(cls, value):
        if value < date.today():
            raise ValueError("Choose today or a future date")
        return value

    @field_validator("contact")
    @classmethod
    def valid_contact(cls, value):
        return LeadInput.valid_contact(value)

@app.get("/", include_in_schema=False)
def home():
    return FileResponse(Path(__file__).with_name("index.html"))

@app.post("/leads")
def create_lead(lead: LeadInput):
    if not lead.consent:
        raise HTTPException(422, "Consent is required for this demo; no record was stored")
    text = lead.inquiry.lower()
    category = "booking" if any(word in text for word in ("book", "appointment")) else "general"
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT * FROM leads WHERE contact=? AND inquiry=?", (lead.contact, lead.inquiry)).fetchone()
        if existing:
            return {"duplicate": True, "lead": dict(existing)}
        identifier = str(uuid4())
        db.execute("INSERT INTO leads(id,name,contact,inquiry,consent,category) VALUES(?,?,?,?,?,?)",
                   (identifier, lead.name, lead.contact, lead.inquiry, 1, category))
        result = dict(db.execute("SELECT * FROM leads WHERE id=?", (identifier,)).fetchone())
    return {"duplicate": False, "lead": result}

@app.get("/leads")
def list_leads():
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT * FROM leads ORDER BY rowid DESC LIMIT 100")]

@app.post("/leads/{lead_id}/sync")
def sync_lead(lead_id: str, simulate_failure: bool = False):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        lead = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not lead:
            raise HTTPException(404, "Lead not found")
        if lead["crm_status"] == "synced":
            return {"status": "synced", "already_delivered": True}
        db.execute("UPDATE leads SET attempts=attempts+1, crm_status=? WHERE id=?",
                   ("failed" if simulate_failure else "synced", lead_id))
        if not simulate_failure:
            db.execute("INSERT OR IGNORE INTO mock_crm VALUES(?,?)", (lead_id, lead["contact"]))
    if simulate_failure:
        raise HTTPException(503, "Simulated CRM outage. Lead saved; retry sync when available.")
    return {"status": "synced", "already_delivered": False}

@app.get("/mock-crm")
def mock_crm():
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT * FROM mock_crm")]

@app.get("/availability")
def availability(day: date, slot: str = Query(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")):
    if day < date.today():
        raise HTTPException(422, "Choose today or a future date")
    with connection() as db:
        booked = db.execute("SELECT id FROM bookings WHERE day=? AND slot=?", (day.isoformat(), slot)).fetchone()
    return {"status": "available" if slot in SLOTS and not booked else "unavailable", "day": day, "slot": slot}

@app.post("/bookings", status_code=201)
def create_booking(booking: BookingInput):
    if booking.slot not in SLOTS:
        raise HTTPException(409, "Slot outside appointment hours")
    identifier = str(uuid4())
    try:
        with connection() as db:
            db.execute("INSERT INTO bookings VALUES(?,?,?,?,?)", (identifier, booking.day.isoformat(), booking.slot, booking.name, booking.contact))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Slot already booked; choose another time")
    return {"id": identifier, "status": "confirmed", **booking.model_dump()}

@app.get("/bookings")
def list_bookings():
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT * FROM bookings ORDER BY day,slot LIMIT 100")]

@app.delete("/bookings/{booking_id}")
def cancel_booking(booking_id: str):
    with connection() as db:
        result = db.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
        if not result.rowcount:
            raise HTTPException(404, "Booking not found")
    return {"status": "cancelled"}


from integrations import attach
attach(app, connection, LeadInput, BookingInput, create_lead, SLOTS)
