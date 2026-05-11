from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Settings
from pydantic import BaseModel
from typing import Optional
import datetime

router = APIRouter()

class SettingsInput(BaseModel):
    semester_start_date: Optional[str] = None   # DD/MM/YYYY
    semester_end_date:   Optional[str] = None   # DD/MM/YYYY
    academic_year:       Optional[str] = None
    current_semester:    Optional[int] = None

def get_or_create_settings(db: Session):
    s = db.query(Settings).filter(Settings.id == 1).first()
    if not s:
        s = Settings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s

@router.get("/")
def get_settings(db: Session = Depends(get_db)):
    s = get_or_create_settings(db)
    return {
        "semester_start_date": s.semester_start_date,
        "semester_end_date":   s.semester_end_date,
        "academic_year":       s.academic_year,
        "current_semester":    s.current_semester,
        "classes_started":     is_classes_started(s),
        "classes_ended":       is_classes_ended(s),
    }

@router.post("/update")
def update_settings(data: SettingsInput, db: Session = Depends(get_db)):
    s = get_or_create_settings(db)
    if data.semester_start_date: s.semester_start_date = data.semester_start_date
    if data.semester_end_date:   s.semester_end_date   = data.semester_end_date
    if data.academic_year:       s.academic_year       = data.academic_year
    if data.current_semester:    s.current_semester    = data.current_semester
    db.commit()
    return {"message": "Settings updated ✅", "classes_started": is_classes_started(s)}

def is_classes_started(s: Settings) -> bool:
    if not s or not s.semester_start_date:
        return False
    try:
        start = datetime.datetime.strptime(s.semester_start_date, "%d/%m/%Y").date()
        return datetime.date.today() >= start
    except:
        return False

def is_classes_ended(s: Settings) -> bool:
    if not s or not s.semester_end_date:
        return False
    try:
        end = datetime.datetime.strptime(s.semester_end_date, "%d/%m/%Y").date()
        return datetime.date.today() > end
    except:
        return False