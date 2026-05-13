from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Attendance, Student, Subject, Timetable, Course
from pydantic import BaseModel
import datetime
import pytz

router = APIRouter()

# ── IST timezone ──────────────────────────────────────────
IST = pytz.timezone('Asia/Kolkata')

class MarkInput(BaseModel):
    student_id: int
    subject_id: int
    gps_lat:    float
    gps_lng:    float
    face_ok:    bool

# ── Helper: current IST date string ───────────────────────
def now_ist_str() -> str:
    """Returns current IST time as DD/MM/YYYY HH:MM — fits String(20)"""
    return datetime.datetime.now(IST).strftime("%d/%m/%Y %H:%M")

def today_ist_str() -> str:
    """Returns today's IST date as DD/MM/YYYY — fits String(12)"""
    return datetime.datetime.now(IST).strftime("%d/%m/%Y")

# ─── Check Timetable Window (IST) ────────────────────────

def check_timetable(subject_id: int, db: Session):
    now_ist = datetime.datetime.now(IST)
    today   = now_ist.strftime("%A")
    current = now_ist.strftime("%H:%M")

    slot = db.query(Timetable).filter(
        Timetable.subject_id == subject_id,
        Timetable.day        == today
    ).first()

    if not slot:
        return {"allowed": False,
                "message": f"No class scheduled today ({today}) ❌"}

    fmt     = "%H:%M"
    start   = datetime.datetime.strptime(slot.start_time, fmt)
    end     = datetime.datetime.strptime(slot.end_time,   fmt)
    w_start = (start - datetime.timedelta(minutes=5)).strftime(fmt)
    w_end   = (end   + datetime.timedelta(minutes=5)).strftime(fmt)

    if w_start <= current <= w_end:
        return {"allowed": True,
                "message": f"✅ Within class time ({slot.start_time}–{slot.end_time})"}
    return {"allowed": False,
            "message": f"❌ Attendance window: {w_start}–{w_end}. Now: {current}"}

# ─── Mark Attendance ──────────────────────────────────────

@router.post("/mark")
def mark_attendance(data: MarkInput, db: Session = Depends(get_db)):
    if not data.face_ok:
        raise HTTPException(400, "Face verification failed ❌")

    time_check = check_timetable(data.subject_id, db)
    if not time_check["allowed"]:
        raise HTTPException(400, time_check["message"])

    # Check duplicate using date string prefix
    today_str = today_ist_str()
    existing = db.query(Attendance).filter(
        Attendance.student_id == data.student_id,
        Attendance.subject_id == data.subject_id,
        Attendance.date.like(f"{today_str}%")
    ).first()
    if existing:
        raise HTTPException(400, "Attendance already marked today ❌")

    # Fetch names to populate denormalized columns
    student = db.query(Student).filter(Student.id == data.student_id).first()
    subject = db.query(Subject).filter(Subject.id == data.subject_id).first()

    record = Attendance(
        student_id   = data.student_id,
        student_name = student.name if student else None,
        subject_id   = data.subject_id,
        subject_name = subject.name if subject else None,
        date         = now_ist_str(),  # ✅ "DD/MM/YYYY HH:MM" — update col to String(20) if needed
        is_present   = "Present",      # ✅ matches Column(String(10))
        gps_lat      = data.gps_lat,
        gps_lng      = data.gps_lng
    )
    db.add(record)
    db.commit()
    return {"message": "Attendance marked successfully ✅"}

# ─── Auto Mark Absent (IST) ───────────────────────────────

@router.post("/auto-absent")
def auto_mark_absent(db: Session = Depends(get_db)):
    now_ist   = datetime.datetime.now(IST)
    today     = now_ist.strftime("%A")
    current   = now_ist.strftime("%H:%M")
    today_str = today_ist_str()
    marked    = []

    slots = db.query(Timetable).filter(Timetable.day == today).all()

    for slot in slots:
        fmt        = "%H:%M"
        end        = datetime.datetime.strptime(slot.end_time, fmt)
        window_end = (end + datetime.timedelta(minutes=5)).strftime(fmt)

        if current <= window_end:
            continue

        subject = db.query(Subject).filter(Subject.id == slot.subject_id).first()
        if not subject:
            continue

        students = db.query(Student).filter(
            Student.course_id == subject.course_id
        ).all()

        for student in students:
            existing = db.query(Attendance).filter(
                Attendance.student_id == student.id,
                Attendance.subject_id == slot.subject_id,
                Attendance.date.like(f"{today_str}%")
            ).first()

            if not existing:
                absent_record = Attendance(
                    student_id   = student.id,
                    student_name = student.name,
                    subject_id   = slot.subject_id,
                    subject_name = subject.name,
                    date         = now_ist_str(),  # ✅ string format
                    is_present   = "Absent",        # ✅ matches Column(String(10))
                    gps_lat      = None,
                    gps_lng      = None
                )
                db.add(absent_record)
                marked.append({
                    "student": student.name,
                    "subject": subject.name
                })

    db.commit()
    return {
        "message": f"Auto-absent marked for {len(marked)} records ✅",
        "marked":  marked
    }

# ─── Get Student Attendance for Subject ───────────────────

@router.get("/student/{student_id}/subject/{subject_id}")
def get_subject_attendance(student_id: int, subject_id: int,
                           db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(404, "Subject not found ❌")

    records = db.query(Attendance).filter(
        Attendance.student_id == student_id,
        Attendance.subject_id == subject_id
    ).all()

    total_classes = subject.total_classes or 0
    classes_held  = len(records)
    present       = sum(1 for r in records if r.is_present == "Present")
    absent        = classes_held - present
    denom         = total_classes if total_classes > 0 else classes_held
    percent       = round((present / denom) * 100, 1) if denom > 0 else 0

    warning = None
    if percent < 75 and denom > 0:
        warning = f"⚠️ Only {percent}% attendance. Minimum required is 75%"

    return {
        "subject_id":    subject_id,
        "subject_name":  subject.name,
        "total_classes": total_classes,
        "classes_held":  classes_held,
        "present":       present,
        "absent":        absent,
        "percent":       percent,
        "warning":       warning,
        "records": [
            {
                "date":   r.date if r.date else None,
                "status": r.is_present  # already "Present" or "Absent"
            } for r in records
        ]
    }

# ─── Get All Student Attendance ───────────────────────────

@router.get("/student/{student_id}")
def get_student_attendance(student_id: int, db: Session = Depends(get_db)):
    records = db.query(Attendance).filter(
        Attendance.student_id == student_id
    ).all()
    return {
        "records": [
            {
                "date":       r.date if r.date else None,
                "is_present": r.is_present,
                "subject_id": r.subject_id
            } for r in records
        ]
    }

# ─── Get Subject Attendance (teacher view) ────────────────

@router.get("/subject/{subject_id}")
def get_subject_attendance_teacher(subject_id: int,
                                   db: Session = Depends(get_db)):
    records = db.query(Attendance).filter(
        Attendance.subject_id == subject_id
    ).all()
    return {
        "total_records": len(records),
        "records": [
            {
                "student_id": r.student_id,
                "date":       r.date if r.date else None,
                "is_present": r.is_present
            } for r in records
        ]
    }

# ─── Get Timetable for Subject ────────────────────────────

@router.get("/timetable/{subject_id}")
def get_subject_timetable(subject_id: int, db: Session = Depends(get_db)):
    slots = db.query(Timetable).filter(
        Timetable.subject_id == subject_id
    ).all()
    return [
        {
            "id":         s.id,
            "day":        s.day,
            "start_time": s.start_time,
            "end_time":   s.end_time
        } for s in slots
    ]
