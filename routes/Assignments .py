from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Assignment, LabRecord, Subject
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

MAX_ASSIGNMENTS_PER_SUBJECT = 4

# ── Input schemas ──────────────────────────────────────────

class AssignmentInput(BaseModel):
    subject_id:  int
    teacher_id:  int
    title:       str
    description: Optional[str] = None
    due_date:    str            # "YYYY-MM-DD"

class LabRecordInput(BaseModel):
    subject_id:  int
    teacher_id:  int
    semester:    int
    title:       str
    description: Optional[str] = None
    due_date:    str            # "YYYY-MM-DD"

class UpdateAssignmentInput(BaseModel):
    title:       Optional[str] = None
    description: Optional[str] = None
    due_date:    Optional[str] = None

class UpdateLabRecordInput(BaseModel):
    title:       Optional[str] = None
    description: Optional[str] = None
    due_date:    Optional[str] = None

# ── Assignments ────────────────────────────────────────────

@router.post("/assignment/add")
def add_assignment(data: AssignmentInput, db: Session = Depends(get_db)):
    count = db.query(Assignment).filter(Assignment.subject_id == data.subject_id).count()
    if count >= MAX_ASSIGNMENTS_PER_SUBJECT:
        raise HTTPException(400, f"Maximum {MAX_ASSIGNMENTS_PER_SUBJECT} assignments allowed per subject ❌")
    a = Assignment(
        subject_id  = data.subject_id,
        teacher_id  = data.teacher_id,
        title       = data.title,
        description = data.description,
        due_date    = data.due_date,
    )
    db.add(a); db.commit(); db.refresh(a)
    return {"message": "Assignment added ✅", "id": a.id}

@router.get("/assignments/subject/{subject_id}")
def get_assignments_by_subject(subject_id: int, db: Session = Depends(get_db)):
    rows = db.query(Assignment).filter(Assignment.subject_id == subject_id).order_by(Assignment.created_at).all()
    return [_fmt_assignment(r) for r in rows]

@router.get("/assignments/teacher/{teacher_id}")
def get_assignments_by_teacher(teacher_id: int, db: Session = Depends(get_db)):
    rows = db.query(Assignment).filter(Assignment.teacher_id == teacher_id).order_by(Assignment.created_at.desc()).all()
    return [_fmt_assignment(r) for r in rows]

@router.get("/assignments/course/{course_id}")
def get_assignments_by_course(course_id: int, db: Session = Depends(get_db)):
    """Used by student dashboard — returns all assignments for subjects in their course."""
    subjects = db.query(Subject).filter(Subject.course_id == course_id).all()
    sub_ids  = [s.id for s in subjects]
    rows     = db.query(Assignment).filter(Assignment.subject_id.in_(sub_ids)).order_by(Assignment.due_date).all()
    return [_fmt_assignment(r) for r in rows]

@router.put("/assignment/{id}")
def update_assignment(id: int, data: UpdateAssignmentInput, db: Session = Depends(get_db)):
    a = db.query(Assignment).filter(Assignment.id == id).first()
    if not a: raise HTTPException(404, "Assignment not found ❌")
    if data.title       is not None: a.title       = data.title
    if data.description is not None: a.description = data.description
    if data.due_date    is not None: a.due_date    = data.due_date
    db.commit()
    return {"message": "Assignment updated ✅"}

@router.delete("/assignment/{id}")
def delete_assignment(id: int, db: Session = Depends(get_db)):
    a = db.query(Assignment).filter(Assignment.id == id).first()
    if not a: raise HTTPException(404, "Assignment not found ❌")
    db.delete(a); db.commit()
    return {"message": "Assignment deleted ✅"}

# ── Lab Records ────────────────────────────────────────────

@router.post("/lab-record/add")
def add_lab_record(data: LabRecordInput, db: Session = Depends(get_db)):
    existing = db.query(LabRecord).filter(
        LabRecord.subject_id == data.subject_id,
        LabRecord.semester   == data.semester,
    ).first()
    if existing:
        raise HTTPException(400, "Lab record already exists for this subject & semester. Use PUT to update ❌")
    r = LabRecord(
        subject_id  = data.subject_id,
        teacher_id  = data.teacher_id,
        semester    = data.semester,
        title       = data.title,
        description = data.description,
        due_date    = data.due_date,
    )
    db.add(r); db.commit(); db.refresh(r)
    return {"message": "Lab record added ✅", "id": r.id}

@router.get("/lab-records/subject/{subject_id}")
def get_lab_record_by_subject(subject_id: int, db: Session = Depends(get_db)):
    rows = db.query(LabRecord).filter(LabRecord.subject_id == subject_id).all()
    return [_fmt_lab(r) for r in rows]

@router.get("/lab-records/teacher/{teacher_id}")
def get_lab_records_by_teacher(teacher_id: int, db: Session = Depends(get_db)):
    rows = db.query(LabRecord).filter(LabRecord.teacher_id == teacher_id).order_by(LabRecord.created_at.desc()).all()
    return [_fmt_lab(r) for r in rows]

@router.get("/lab-records/course/{course_id}")
def get_lab_records_by_course(course_id: int, db: Session = Depends(get_db)):
    """Used by student dashboard."""
    subjects = db.query(Subject).filter(Subject.course_id == course_id).all()
    sub_ids  = [s.id for s in subjects]
    rows     = db.query(LabRecord).filter(LabRecord.subject_id.in_(sub_ids)).order_by(LabRecord.due_date).all()
    return [_fmt_lab(r) for r in rows]

@router.put("/lab-record/{id}")
def update_lab_record(id: int, data: UpdateLabRecordInput, db: Session = Depends(get_db)):
    r = db.query(LabRecord).filter(LabRecord.id == id).first()
    if not r: raise HTTPException(404, "Lab record not found ❌")
    if data.title       is not None: r.title       = data.title
    if data.description is not None: r.description = data.description
    if data.due_date    is not None: r.due_date    = data.due_date
    db.commit()
    return {"message": "Lab record updated ✅"}

@router.delete("/lab-record/{id}")
def delete_lab_record(id: int, db: Session = Depends(get_db)):
    r = db.query(LabRecord).filter(LabRecord.id == id).first()
    if not r: raise HTTPException(404, "Lab record not found ❌")
    db.delete(r); db.commit()
    return {"message": "Lab record deleted ✅"}

# ── Helpers ────────────────────────────────────────────────

def _fmt_assignment(a: Assignment):
    return {
        "id":           a.id,
        "subject_id":   a.subject_id,
        "subject_name": a.subject.name if a.subject else "",
        "teacher_id":   a.teacher_id,
        "teacher_name": a.teacher.name if a.teacher else "",
        "title":        a.title,
        "description":  a.description or "",
        "due_date":     a.due_date,
        "created_at":   str(a.created_at),
    }

def _fmt_lab(r: LabRecord):
    return {
        "id":           r.id,
        "subject_id":   r.subject_id,
        "subject_name": r.subject.name if r.subject else "",
        "teacher_id":   r.teacher_id,
        "teacher_name": r.teacher.name if r.teacher else "",
        "semester":     r.semester,
        "title":        r.title,
        "description":  r.description or "",
        "due_date":     r.due_date,
        "created_at":   str(r.created_at),
    }
