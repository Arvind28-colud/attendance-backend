from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Attendance, Student, Subject, Timetable, Holiday, Settings
from pydantic import BaseModel
from typing import Optional
import datetime

router = APIRouter()

class MarkInput(BaseModel):
    student_id:  int
    subject_id:  int
    gps_lat:     float
    gps_lng:     float
    face_ok:     bool
    face_image:  Optional[str] = None
    verify_only: Optional[bool] = False

# ── Helpers ────────────────────────────────────────────────

def today_ddmmyyyy():
    return datetime.datetime.now().strftime("%d/%m/%Y")

def check_timetable(subject_id: int, db: Session):
    now     = datetime.datetime.now()
    today   = now.strftime("%A")
    current = now.strftime("%H:%M")

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

# ── Mark Attendance ────────────────────────────────────────

@router.post("/mark")
def mark_attendance(data: MarkInput, db: Session = Depends(get_db)):
    if not data.face_ok:
        raise HTTPException(400, "Face verification failed ❌")

    # Face verify only — real DeepFace recognition
    if data.verify_only:
        student = db.query(Student).filter(Student.id == data.student_id).first()
        if not student:
            raise HTTPException(404, "Student not found ❌")
        if not student.face_data:
            raise HTTPException(400, "No face registered ❌")
        from routes.auth import get_face_embedding, str_to_embedding, cosine_similarity
        try:
            incoming   = get_face_embedding(data.face_image, f"att_verify_{student.id}.jpg")
            stored     = str_to_embedding(student.face_data)
            similarity = cosine_similarity(stored, incoming)
            match      = similarity >= 0.7
            return {
                "face_match": match,
                "verified":   match,
                "confidence": round(similarity * 100, 1),
                "message":    "Face matched ✅" if match else "Face not matched ❌"
            }
        except Exception as e:
            return {"face_match": False, "verified": False, "message": "No face detected ❌"}

    today = today_ddmmyyyy()

    # Block if classes haven't started yet
    settings = db.query(Settings).filter(Settings.id == 1).first()
    if not settings or not settings.semester_start_date:
        raise HTTPException(400, "Classes have not started yet. Admin hasn't set the semester start date ❌")
    try:
        import datetime as dt
        start = dt.datetime.strptime(settings.semester_start_date, "%d/%m/%Y").date()
        if dt.date.today() < start:
            raise HTTPException(400, f"Classes start on {settings.semester_start_date}. Attendance not allowed yet ❌")
        if settings.semester_end_date:
            end = dt.datetime.strptime(settings.semester_end_date, "%d/%m/%Y").date()
            if dt.date.today() > end:
                raise HTTPException(400, f"Semester ended on {settings.semester_end_date} ❌")
    except HTTPException:
        raise
    except:
        pass

    # Block if today is a holiday
    holiday = db.query(Holiday).filter(Holiday.date == today).first()
    if holiday:
        raise HTTPException(400, f"Today is a holiday — {holiday.reason} 🎉 No attendance today!")

    time_check = check_timetable(data.subject_id, db)
    if not time_check["allowed"]:
        raise HTTPException(400, time_check["message"])

    existing = db.query(Attendance).filter(
        Attendance.student_id == data.student_id,
        Attendance.subject_id == data.subject_id,
        Attendance.date       == today
    ).first()
    if existing:
        raise HTTPException(400, "Attendance already marked today ❌")

    # Fetch names to store beside IDs
    student = db.query(Student).filter(Student.id == data.student_id).first()
    subject = db.query(Subject).filter(Subject.id == data.subject_id).first()

    if not student: raise HTTPException(404, "Student not found ❌")
    if not subject: raise HTTPException(404, "Subject not found ❌")

    record = Attendance(
        student_id   = data.student_id,
        student_name = student.name,
        subject_id   = data.subject_id,
        subject_name = subject.name,
        date         = today,
        is_present   = "Present",
        gps_lat      = data.gps_lat,
        gps_lng      = data.gps_lng
    )
    db.add(record)
    db.commit()
    return {"message": "Attendance marked successfully ✅"}

# ── Auto Mark Absent ───────────────────────────────────────

@router.post("/auto-absent")
def auto_mark_absent(db: Session = Depends(get_db)):
    now     = datetime.datetime.now()
    today   = now.strftime("%A")
    current = now.strftime("%H:%M")
    date    = today_ddmmyyyy()
    marked  = []

    slots = db.query(Timetable).filter(Timetable.day == today).all()

    for slot in slots:
        fmt        = "%H:%M"
        end        = datetime.datetime.strptime(slot.end_time, fmt)
        window_end = (end + datetime.timedelta(minutes=5)).strftime(fmt)

        if current <= window_end:
            continue

        subject = db.query(Subject).filter(Subject.id == slot.subject_id).first()
        if not subject: continue

        students = db.query(Student).filter(
            Student.course_id == subject.course_id
        ).all()

        for student in students:
            existing = db.query(Attendance).filter(
                Attendance.student_id == student.id,
                Attendance.subject_id == slot.subject_id,
                Attendance.date       == date
            ).first()

            if not existing:
                db.add(Attendance(
                    student_id   = student.id,
                    student_name = student.name,
                    subject_id   = slot.subject_id,
                    subject_name = subject.name,
                    date         = date,
                    is_present   = "Absent",
                    gps_lat      = None,
                    gps_lng      = None
                ))
                marked.append({"student": student.name, "subject": subject.name})

    db.commit()
    return {
        "message": f"Auto-absent marked for {len(marked)} records ✅",
        "marked":  marked
    }

# ── Get Student Attendance for a Subject ──────────────────

@router.get("/student/{student_id}/subject/{subject_id}")
def get_subject_attendance(student_id: int, subject_id: int,
                           db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(404, "Subject not found ❌")

    records = db.query(Attendance).filter(
        Attendance.student_id == student_id,
        Attendance.subject_id == subject_id
    ).order_by(Attendance.date.desc()).all()

    total_classes = subject.total_classes or 68
    present       = sum(1 for r in records if r.is_present == "Present")
    absent        = sum(1 for r in records if r.is_present == "Absent")
    percent       = round((present / total_classes) * 100, 1) if total_classes > 0 else 0

    # Classes needed to reach 75%
    needed_75 = max(0, int((0.75 * total_classes - present) / 0.25)) if percent < 75 else 0

    return {
        "subject_id":    subject_id,
        "subject_name":  subject.name,
        "total_classes": total_classes,
        "present":       present,
        "absent":        absent,
        "percent":       percent,
        "needed_75":     needed_75,
        "records": [
            {
                "date":       r.date,           # already DD/MM/YYYY
                "is_present": r.is_present      # "Present" or "Absent"
            } for r in records
        ]
    }

# ── Get All Attendance for a Student ──────────────────────

@router.get("/student/{student_id}")
def get_student_attendance(student_id: int, db: Session = Depends(get_db)):
    records = db.query(Attendance).filter(
        Attendance.student_id == student_id
    ).all()
    return {
        "records": [
            {
                "date":         r.date,
                "is_present":   r.is_present,
                "subject_id":   r.subject_id,
                "subject_name": r.subject_name
            } for r in records
        ]
    }

# ── Teacher View: Subject Attendance ──────────────────────

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
                "student_id":   r.student_id,
                "student_name": r.student_name,
                "date":         r.date,
                "is_present":   r.is_present
            } for r in records
        ]
    }

# ── Timetable for Subject ─────────────────────────────────

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