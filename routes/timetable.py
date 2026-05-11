from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Timetable, Subject
from pydantic import BaseModel
from typing import List
import datetime

router = APIRouter()

DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

class TimetableInput(BaseModel):
    subject_id: int
    day:        str
    start_time: str   # "09:00"
    end_time:   str   # "10:00"

class TimetableUpdate(BaseModel):
    id:         int
    subject_id: int
    day:        str
    start_time: str
    end_time:   str

# ─── Add Timetable Entry ──────────────────────────────────

@router.post("/add")
def add_timetable(data: TimetableInput, db: Session = Depends(get_db)):
    if data.day not in DAYS:
        raise HTTPException(status_code=400, detail=f"Invalid day. Use: {', '.join(DAYS)}")

    # Check if slot already exists for this subject+day
    existing = db.query(Timetable).filter(
        Timetable.subject_id == data.subject_id,
        Timetable.day        == data.day
    ).first()
    if existing:
        raise HTTPException(status_code=400,
            detail="Timetable slot already exists for this subject on this day ❌")

    entry = Timetable(
        subject_id = data.subject_id,
        day        = data.day,
        start_time = data.start_time,
        end_time   = data.end_time
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"message": "Timetable added successfully ✅", "id": entry.id}

# ─── Get Full Timetable ───────────────────────────────────

@router.get("/list")
def get_all_timetable(db: Session = Depends(get_db)):
    entries  = db.query(Timetable).all()
    subjects = db.query(Subject).all()
    subMap   = {s.id: s.name for s in subjects}
    return [
        {
            "id":           e.id,
            "subject_id":   e.subject_id,
            "subject_name": subMap.get(e.subject_id, "Unknown"),
            "day":          e.day,
            "start_time":   e.start_time,
            "end_time":     e.end_time
        }
        for e in entries
    ]

@router.get("/timetable")
def get_timetable(db: Session = Depends(get_db)):
    entries = db.query(Timetable).all()
    subjects = db.query(Subject).all()
    subMap = {s.id: s.name for s in subjects}
    return [
        {
            "id": e.id,
            "subject_id": e.subject_id,
            "subject_name": subMap.get(e.subject_id, "Unknown"),
            "day": e.day,
            "start_time": e.start_time,
            "end_time": e.end_time
        }
        for e in entries
    ]

# ─── Get Timetable for a Subject ─────────────────────────

@router.get("/subject/{subject_id}")
def get_subject_timetable(subject_id: int, db: Session = Depends(get_db)):
    entries = db.query(Timetable).filter(
        Timetable.subject_id == subject_id
    ).all()
    return [
        {
            "id":         e.id,
            "day":        e.day,
            "start_time": e.start_time,
            "end_time":   e.end_time
        }
        for e in entries
    ]

# ─── Get Today's Timetable ────────────────────────────────

@router.get("/today")
def get_today_timetable(db: Session = Depends(get_db)):
    today   = datetime.datetime.now().strftime("%A")  # e.g. "Monday"
    entries = db.query(Timetable).filter(Timetable.day == today).all()
    subjects= db.query(Subject).all()
    subMap  = {s.id: s.name for s in subjects}
    return {
        "today": today,
        "slots": [
            {
                "id":           e.id,
                "subject_id":   e.subject_id,
                "subject_name": subMap.get(e.subject_id, "Unknown"),
                "start_time":   e.start_time,
                "end_time":     e.end_time
            }
            for e in entries
        ]
    }

# ─── Delete Timetable Entry ───────────────────────────────

@router.delete("/delete/{id}")
def delete_timetable(id: int, db: Session = Depends(get_db)):
    entry = db.query(Timetable).filter(Timetable.id == id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found ❌")
    db.delete(entry)
    db.commit()
    return {"message": "Timetable entry deleted ✅"}