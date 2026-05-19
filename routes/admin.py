from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import (Admin, Department, Course, Subject,
                    Teacher, Student, Timetable, Attendance, Holiday, SemesterSettings)
from passlib.hash import bcrypt
from pydantic import BaseModel
from typing import Optional
import datetime

router = APIRouter()

# ── Temporary schema fix — remove after running once ────────
from sqlalchemy import text

@router.get("/fix-holidays-schema")
def fix_holidays_schema(db: Session = Depends(get_db)):
    results = []
    migrations = [
        "ALTER TABLE holidays CHANGE COLUMN `name` `reason` VARCHAR(200) NULL",
        "ALTER TABLE holidays ADD COLUMN `reason` VARCHAR(200) NULL",
        "ALTER TABLE holidays ADD COLUMN `created_by` INT NULL",
        "ALTER TABLE holidays ADD COLUMN `created_at` DATETIME NULL",
    ]
    for sql in migrations:
        try:
            db.execute(text(sql))
            db.commit()
            results.append(f"✅ {sql[:60]}")
        except Exception as e:
            results.append(f"⏭ skipped: {str(e)[:80]}")
    return {"results": results, "message": "Done — remove this endpoint now"}


# ── Input Models ───────────────────────────────────────────

class AdminLoginInput(BaseModel):
    email:    str
    password: str

class DepartmentInput(BaseModel):
    name: str

class CourseInput(BaseModel):
    name:          str
    department_id: int

class SubjectInput(BaseModel):
    name:       str
    course_id:  int
    teacher_id: Optional[int] = None
    semester:   Optional[int] = 1

class UpdateClassesInput(BaseModel):
    subject_id:    int
    total_classes: int

class TimetableInput(BaseModel):
    subject_id: int
    day:        str
    start_time: str
    end_time:   str

class AssignTeacherInput(BaseModel):
    subject_id: int
    teacher_id: int

class HolidayInput(BaseModel):
    date:       str          #DD-MM-YYYY
    reason:     str
    admin_id:   Optional[int] = None

DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

# ── Admin Login ────────────────────────────────────────────

@router.post("/login")
def admin_login(data: AdminLoginInput, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.email == data.email).first()
    if not admin:
        raise HTTPException(401, "Invalid admin credentials ❌")
    try:
        pwd = data.password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
        if not bcrypt.verify(pwd, admin.password):
            raise HTTPException(401, "Invalid admin credentials ❌")
    except Exception as e:
        raise HTTPException(500, f"Auth error: {str(e)}")
    return {"message": "Admin login successful ✅",
            "admin_id": admin.id, "name": admin.name, "email": admin.email}

# ── Department Management ──────────────────────────────────

@router.post("/department/add")
def add_department(data: DepartmentInput, db: Session = Depends(get_db)):
    if db.query(Department).filter(Department.name == data.name).first():
        raise HTTPException(400, "Department already exists ❌")
    dept = Department(name=data.name)
    db.add(dept); db.commit(); db.refresh(dept)
    return {"message": f"Department '{data.name}' added ✅", "id": dept.id}

@router.get("/departments")
def get_departments(db: Session = Depends(get_db)):
    depts = db.query(Department).all()
    return [{"id": d.id, "name": d.name} for d in depts]

@router.delete("/department/{id}")
def delete_department(id: int, db: Session = Depends(get_db)):
    dept = db.query(Department).filter(Department.id == id).first()
    if not dept: raise HTTPException(404, "Not found ❌")
    db.delete(dept); db.commit()
    return {"message": "Department deleted ✅"}

# ── Course Management ──────────────────────────────────────

@router.post("/course/add")
def add_course(data: CourseInput, db: Session = Depends(get_db)):
    course = Course(name=data.name, department_id=data.department_id)
    db.add(course); db.commit(); db.refresh(course)
    return {"message": f"Course '{data.name}' added ✅", "id": course.id}

@router.get("/courses")
def get_courses(db: Session = Depends(get_db)):
    courses = db.query(Course).all()
    depts   = db.query(Department).all()
    dMap    = {d.id: d.name for d in depts}
    return [{"id": c.id, "name": c.name,
             "department_id": c.department_id,
             "department_name": dMap.get(c.department_id, "")} for c in courses]

@router.delete("/course/{id}")
def delete_course(id: int, db: Session = Depends(get_db)):
    c = db.query(Course).filter(Course.id == id).first()
    if not c: raise HTTPException(404, "Not found ❌")
    db.delete(c); db.commit()
    return {"message": "Course deleted ✅"}

# ── Subject Management ─────────────────────────────────────

@router.post("/subject/add")
def add_subject(data: SubjectInput, db: Session = Depends(get_db)):
    course  = db.query(Course).filter(Course.id == data.course_id).first()
    teacher = db.query(Teacher).filter(Teacher.id == data.teacher_id).first() if data.teacher_id else None

    # Calculate total_classes = 68 minus holidays already marked
    holidays_count = db.query(Holiday).count()
    total_classes  = max(0, 68 - holidays_count)

    subject = Subject(
        name             = data.name,
        course_id        = data.course_id,
        course_name      = course.name if course else "",
        teacher_id       = data.teacher_id,
        teacher_name     = teacher.name if teacher else "Not assigned",
        semester         = data.semester or 1,
        classes_per_week = 4,
        total_classes    = total_classes
    )
    db.add(subject); db.commit(); db.refresh(subject)
    return {"message": f"Subject '{data.name}' added ✅", "id": subject.id,
            "total_classes": total_classes}

@router.get("/subjects")
def get_all_subjects(db: Session = Depends(get_db)):
    subjects = db.query(Subject).all()
    teachers = db.query(Teacher).all()
    courses  = db.query(Course).all()
    tMap     = {t.id: f"{t.name} ({t.qualification or 'N/A'})" for t in teachers}
    cMap     = {c.id: c.name for c in courses}
    return [{
        "id":            s.id,
        "name":          s.name,
        "course_id":     s.course_id,
        "course_name":   cMap.get(s.course_id, ""),
        "teacher_id":    s.teacher_id,
        "teacher_name":  tMap.get(s.teacher_id, "Not assigned"),
        "total_classes": s.total_classes,
        "semester":      s.semester or 1
    } for s in subjects]

@router.get("/subjects/course/{course_id}")
def get_subjects_by_course(course_id: int, db: Session = Depends(get_db)):
    subjects = db.query(Subject).filter(Subject.course_id == course_id).all()
    teachers = db.query(Teacher).all()
    tMap     = {t.id: t.name for t in teachers}
    return [{
        "id":            s.id,
        "name":          s.name,
        "teacher_name":  tMap.get(s.teacher_id, "Not assigned"),
        "semester":      s.semester or 1,
        "total_classes": s.total_classes
    } for s in subjects]

@router.post("/subject/assign-teacher")
def assign_teacher(data: AssignTeacherInput, db: Session = Depends(get_db)):
    subject = db.query(Subject).filter(Subject.id == data.subject_id).first()
    if not subject: raise HTTPException(404, "Subject not found ❌")
    teacher = db.query(Teacher).filter(Teacher.id == data.teacher_id).first()
    subject.teacher_id   = data.teacher_id
    subject.teacher_name = teacher.name if teacher else "Not assigned"
    db.commit()
    return {"message": "Teacher assigned ✅"}

@router.get("/subjects/teacher/{teacher_id}")
def get_subjects_by_teacher(teacher_id: int, db: Session = Depends(get_db)):
    subjects = db.query(Subject).filter(Subject.teacher_id == teacher_id).all()
    return [{
        "id":            s.id,
        "name":          s.name,
        "course_id":     s.course_id,
        "course_name":   s.course_name or "",
        "teacher_id":    s.teacher_id,
        "teacher_name":  s.teacher_name or "",
        "semester":      s.semester or 1,
        "total_classes": s.total_classes or 68,
    } for s in subjects]

@router.delete("/subject/{id}")
def delete_subject(id: int, db: Session = Depends(get_db)):
    s = db.query(Subject).filter(Subject.id == id).first()
    if not s: raise HTTPException(404, "Not found ❌")
    db.delete(s); db.commit()
    return {"message": "Subject deleted ✅"}

# ── Holiday Management ─────────────────────────────────────

@router.post("/holiday/mark")
def mark_holiday(data: HolidayInput, db: Session = Depends(get_db)):
    # Check already marked
    existing = db.query(Holiday).filter(Holiday.date == data.date).first()
    if existing:
        raise HTTPException(400, f"{data.date} is already marked as holiday ❌")

    # Validate date is today or future only
    try:
        holiday_date = datetime.datetime.strptime(data.date, "%d-%m-%Y").date()
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use DD-MM-YYYY ❌")

    if holiday_date < datetime.date.today():
        raise HTTPException(400, "Cannot mark past dates as holiday ❌")

    # Save holiday
    holiday = Holiday(date=data.date, reason=data.reason)
    db.add(holiday)

    # Reduce total_classes by 1 for ALL subjects
    all_subjects = db.query(Subject).all()
    for subject in all_subjects:
        subject.total_classes = max(0, (subject.total_classes or 68) - 1)

    # Insert "Holiday" attendance for ALL students for ALL subjects
    all_students = db.query(Student).all()
    inserted = 0
    for student in all_students:
        # Get subjects for this student's course
        student_subjects = db.query(Subject).filter(
            Subject.course_id == student.course_id
        ).all()
        for subject in student_subjects:
            # Check not already exists
            exists = db.query(Attendance).filter(
                Attendance.student_id == student.id,
                Attendance.subject_id == subject.id,
                Attendance.date       == data.date
            ).first()
            if not exists:
                db.add(Attendance(
                    student_id   = student.id,
                    student_name = student.name,
                    subject_id   = subject.id,
                    subject_name = subject.name,
                    date         = data.date,
                    is_present   = "Holiday",
                    gps_lat      = None,
                    gps_lng      = None
                ))
                inserted += 1

    db.commit()
    return {
        "message":        f"Holiday marked for {data.date} ✅",
        "reason":         data.reason,
        "records_added":  inserted,
        "subjects_updated": len(all_subjects)
    }

@router.get("/holidays")
def get_holidays(db: Session = Depends(get_db)):
    holidays = db.query(Holiday).order_by(Holiday.date).all()
    return [{
        "id":     h.id,
        "date":   h.date,
        "reason": h.reason
    } for h in holidays]

@router.delete("/holiday/{id}")
def delete_holiday(id: int, db: Session = Depends(get_db)):
    h = db.query(Holiday).filter(Holiday.id == id).first()
    if not h: raise HTTPException(404, "Holiday not found ❌")

    # Restore total_classes by 1 for ALL subjects
    all_subjects = db.query(Subject).all()
    for subject in all_subjects:
        subject.total_classes = min(68, (subject.total_classes or 0) + 1)

    # Remove Holiday attendance records for that date
    db.query(Attendance).filter(
        Attendance.date       == h.date,
        Attendance.is_present == "Holiday"
    ).delete()

    db.delete(h)
    db.commit()
    return {"message": "Holiday removed ✅ — classes restored"}

# ── Timetable ──────────────────────────────────────────────

@router.post("/timetable/add")
def add_timetable(data: TimetableInput, db: Session = Depends(get_db)):
    if data.day not in DAYS:
        raise HTTPException(400, "Invalid day ❌")
    existing = db.query(Timetable).filter(
        Timetable.subject_id == data.subject_id,
        Timetable.day        == data.day).first()
    if existing:
        raise HTTPException(400, "Slot already exists ❌")
    entry = Timetable(subject_id=data.subject_id, day=data.day,
                      start_time=data.start_time, end_time=data.end_time)
    db.add(entry); db.commit(); db.refresh(entry)
    return {"message": "Timetable slot added ✅", "id": entry.id}

@router.get("/timetable")
def get_all_timetable(db: Session = Depends(get_db)):
    entries  = db.query(Timetable).all()
    subjects = db.query(Subject).all()
    courses  = db.query(Course).all()
    sMap     = {s.id: s for s in subjects}
    cMap     = {c.id: c.name for c in courses}
    return [{
        "id":           e.id,
        "subject_id":   e.subject_id,
        "subject_name": sMap[e.subject_id].name if e.subject_id in sMap else "Unknown",
        "day":          e.day,
        "start_time":   e.start_time,
        "end_time":     e.end_time,
        "course_id":    sMap[e.subject_id].course_id if e.subject_id in sMap else None,
        "semester":     sMap[e.subject_id].semester  if e.subject_id in sMap else None,
    } for e in entries]

@router.get("/timetable/today")
def get_today_timetable(db: Session = Depends(get_db)):
    today   = datetime.datetime.now().strftime("%A")
    entries = db.query(Timetable).filter(Timetable.day == today).all()
    subjects = db.query(Subject).all()
    teachers = db.query(Teacher).all()
    sMap     = {s.id: s for s in subjects}
    tMap     = {t.id: f"{t.name} ({t.qualification or 'N/A'})" for t in teachers}
    courses  = db.query(Course).all()
    cMap     = {c.id: c.name for c in courses}

    grouped = {}
    for e in entries:
        sub    = sMap.get(e.subject_id)
        if not sub: continue
        course = cMap.get(sub.course_id, "Unknown")
        if course not in grouped:
            grouped[course] = []
        grouped[course].append({
            "subject_name": sub.name,
            "start_time":   e.start_time,
            "end_time":     e.end_time,
            "faculty":      tMap.get(sub.teacher_id, "Not assigned")
        })

    return {
        "today":   today,
        "grouped": [{"course": k, "slots": v} for k, v in grouped.items()]
    }

@router.delete("/timetable/{id}")
def delete_timetable(id: int, db: Session = Depends(get_db)):
    e = db.query(Timetable).filter(Timetable.id == id).first()
    if not e: raise HTTPException(404, "Not found ❌")
    db.delete(e); db.commit()
    return {"message": "Deleted ✅"}

# ── Teacher Management ─────────────────────────────────────

@router.get("/teachers")
def get_teachers(db: Session = Depends(get_db)):
    teachers = db.query(Teacher).all()
    depts    = db.query(Department).all()
    dMap     = {d.id: d.name for d in depts}
    return [{
        "id":              t.id,
        "name":            t.name,
        "email":           t.email,
        "qualification":   t.qualification or "N/A",
        "department_id":   t.department_id,
        "department_name": dMap.get(t.department_id, "Not assigned")
    } for t in teachers]

@router.delete("/teacher/{id}")
def remove_teacher(id: int, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.id == id).first()
    if not teacher: raise HTTPException(404, "Not found ❌")
    db.delete(teacher); db.commit()
    return {"message": "Deleted ✅"}

# ── Faculty Overview ───────────────────────────────────────

@router.get("/faculty/overview")
def faculty_overview(db: Session = Depends(get_db)):
    depts    = db.query(Department).all()
    teachers = db.query(Teacher).all()
    courses  = db.query(Course).all()
    result   = []
    for d in depts:
        dept_teachers = [t for t in teachers if t.department_id == d.id]
        dept_courses  = [c for c in courses  if c.department_id == d.id]
        result.append({
            "department_id":   d.id,
            "department_name": d.name,
            "total_faculty":   len(dept_teachers),
            "courses":         [{"id": c.id, "name": c.name} for c in dept_courses],
            "faculty": [{
                "id":            t.id,
                "name":          t.name,
                "qualification": t.qualification or "N/A",
                "email":         t.email
            } for t in dept_teachers]
        })
    return result

# ── Student Overview ───────────────────────────────────────

@router.get("/students/overview")
def students_overview(db: Session = Depends(get_db)):
    depts    = db.query(Department).all()
    courses  = db.query(Course).all()
    students = db.query(Student).all()
    result   = []
    for d in depts:
        dept_courses = [c for c in courses if c.department_id == d.id]
        groups       = []
        for c in dept_courses:
            group_students = [s for s in students if s.course_id == c.id]
            groups.append({
                "course_id":      c.id,
                "course_name":    c.name,
                "total_students": len(group_students)
            })
        result.append({
            "department_name": d.name,
            "groups":          groups,
            "total_students":  sum(g["total_students"] for g in groups)
        })
    return result

@router.get("/students")
def get_students(db: Session = Depends(get_db)):
    students = db.query(Student).all()
    courses  = db.query(Course).all()
    cMap     = {c.id: c.name for c in courses}
    return [{
        "id":          s.id,
        "name":        s.name,
        "roll_no":     s.roll_no,
        "email":       s.email,
        "course_id":   s.course_id,
        "course_name": cMap.get(s.course_id, "Unassigned"),
        "semester":    s.semester or 1,
        "group":       cMap.get(s.course_id, "Unassigned"),
    } for s in students]

@router.delete("/student/{id}")
def remove_student(id: int, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == id).first()
    if not student: raise HTTPException(404, "Not found ❌")
    db.delete(student); db.commit()
    return {"message": "Deleted ✅"}


# ── Semester Settings ────────────────────────────────────────
class SemesterSettingsSchema(BaseModel):
    start_date: str
    end_date:   str

@router.get("/semester-settings")
def get_semester_settings(db: Session = Depends(get_db)):
    try:
        s = db.query(SemesterSettings).first()
        if not s:
            return {"start_date": None, "end_date": None}
        return {
            "id":         s.id,
            "start_date": s.semester_start_date,
            "end_date":   s.semester_end_date,
        }
    except Exception as e:
        return {"start_date": None, "end_date": None, "error": str(e)}

@router.post("/semester-settings")
def save_semester_settings(data: SemesterSettingsSchema, db: Session = Depends(get_db)):
    try:
        s = db.query(SemesterSettings).first()
        if s:
            s.semester_start_date = data.start_date
            s.semester_end_date   = data.end_date
        else:
            s = SemesterSettings(
                semester_start_date = data.start_date,
                semester_end_date   = data.end_date,
            )
            db.add(s)
        db.commit(); db.refresh(s)
        return {"message": "Semester settings saved ✅", "id": s.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Attendance Report ──────────────────────────────────────

@router.get("/attendance/course/{course_id}")
def get_course_attendance(course_id: int, db: Session = Depends(get_db)):
    from models import Attendance as AttModel
    students = db.query(Student).filter(Student.course_id == course_id).all()
    subjects = db.query(Subject).filter(Subject.course_id == course_id).all()
    course   = db.query(Course).filter(Course.id == course_id).first()

    # Pre-load all attendance records for these students + subjects in one query
    student_ids = [s.id for s in students]
    subject_ids = [sub.id for sub in subjects]
    all_att = db.query(AttModel).filter(
        AttModel.student_id.in_(student_ids),
        AttModel.subject_id.in_(subject_ids)
    ).all()

    # Index: {(student_id, subject_id): [records]}
    att_map = {}
    for a in all_att:
        key = (a.student_id, a.subject_id)
        if key not in att_map:
            att_map[key] = []
        att_map[key].append(a)

    result = []
    for s in students:
        subject_rows    = []
        overall_present = 0
        overall_total   = 0
        for sub in subjects:
            records = att_map.get((s.id, sub.id), [])
            present = sum(1 for a in records if a.is_present == "Present")
            total   = sub.total_classes or 0
            pct     = round((present / total) * 100, 1) if total > 0 else 0
            overall_present += present
            overall_total   += total
            subject_rows.append({
                "subject_id":    sub.id,
                "subject_name":  sub.name,
                "present":       present,
                "total_classes": total,
                "percent":       pct,
            })
        overall_pct = round((overall_present / overall_total) * 100, 1) if overall_total > 0 else 0
        result.append({
            "student_id":      s.id,
            "name":            s.name,
            "roll_no":         s.roll_no,
            "semester":        s.semester,
            "overall_present": overall_present,
            "overall_total":   overall_total,
            "overall_percent": overall_pct,
            "subjects":        subject_rows,
        })
    result.sort(key=lambda x: x["roll_no"] or "")
    return {
        "course_name": course.name if course else "",
        "students":    result,
        "subjects":    [{ "id": sub.id, "name": sub.name, "total": sub.total_classes } for sub in subjects],
    }

# ── Overview Stats ─────────────────────────────────────────

@router.get("/overview/stats")
def overview_stats(db: Session = Depends(get_db)):
    return {
        "departments": db.query(Department).count(),
        "courses":     db.query(Course).count(),
        "teachers":    db.query(Teacher).count(),
        "students":    db.query(Student).count(),
        "subjects":    db.query(Subject).count(),
        "holidays":    db.query(Holiday).count()
    }
