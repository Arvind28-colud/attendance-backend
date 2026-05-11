from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Student, Teacher, Course, Department
from passlib.hash import bcrypt
from pydantic import BaseModel
from typing import Optional
try:
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except ImportError:
    DeepFace = None
    DEEPFACE_AVAILABLE = False
import numpy as np
import base64
import json
import io
from PIL import Image

router = APIRouter()

# ── Input Models ───────────────────────────────────────────

class StudentRegisterInput(BaseModel):
    name:          str
    email:         str
    roll_no:       str
    password:      str
    course_id:     int
    year:          Optional[str] = None
    semester:      Optional[int] = 1
    academic_year: Optional[str] = '2025-2026'

class TeacherRegisterInput(BaseModel):
    name:          str
    email:         str
    password:      str
    qualification: Optional[str] = None
    department_id: Optional[int] = None

class LoginInput(BaseModel):
    email:    Optional[str] = None
    roll_no:  Optional[str] = None
    password: str

class UpdateFaceInput(BaseModel):
    roll_no:   str
    face_data: str   # base64 image

class FaceVerifyInput(BaseModel):
    roll_no:   str
    face_data: str   # base64 image

# ── Helpers ────────────────────────────────────────────────

def base64_to_image_path(b64: str, filename: str = "temp_face.jpg") -> str:
    """Save base64 image to a temp file and return path"""
    import os, tempfile
    if ',' in b64:
        b64 = b64.split(',')[1]
    b64 += '=' * (-len(b64) % 4)
    img_bytes = base64.b64decode(b64)
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
    tmp_path = os.path.join(tempfile.gettempdir(), filename)
    img.save(tmp_path)
    return tmp_path

def get_face_embedding(b64: str, filename: str = "temp.jpg") -> list:
    """Get face embedding using DeepFace. Returns list or raises."""
    img_path = base64_to_image_path(b64, filename)
    result   = DeepFace.represent(
        img_path      = img_path,
        model_name    = "Facenet",
        enforce_detection = True,
        detector_backend  = "opencv"
    )
    return result[0]["embedding"]

def embedding_to_str(embedding: list) -> str:
    return json.dumps(embedding)

def str_to_embedding(s: str) -> list:
    return json.loads(s)

def cosine_similarity(a: list, b: list) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

# ── Student Register ───────────────────────────────────────

@router.post("/student/register")
def student_register(data: StudentRegisterInput, db: Session = Depends(get_db)):
    if db.query(Student).filter(Student.email == data.email).first():
        raise HTTPException(400, "Email already registered ❌")
    if db.query(Student).filter(Student.roll_no == data.roll_no).first():
        raise HTTPException(400, "Roll number already registered ❌")

    course = db.query(Course).filter(Course.id == data.course_id).first()
    student = Student(
        name          = data.name,
        email         = data.email,
        roll_no       = data.roll_no.strip().upper(),
        password      = bcrypt.hash(data.password),
        course_id     = data.course_id,
        course_name   = course.name if course else "",
        year          = data.year,
        semester      = data.semester,
        academic_year = data.academic_year,
        face_data     = None,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return {
        "message":    "Student registered ✅ Please capture your face to complete registration",
        "student_id": student.id,
        "roll_no":    student.roll_no,
    }

# ── Update Face (Registration) ─────────────────────────────

@router.post("/student/update-face")
def update_face(data: UpdateFaceInput, db: Session = Depends(get_db)):
    student = db.query(Student).filter(
        Student.roll_no == data.roll_no.strip().upper()
    ).first()
    if not student:
        raise HTTPException(404, "Student not found ❌")

    try:
        embedding = get_face_embedding(data.face_data, f"reg_{student.roll_no}.jpg")
    except Exception as e:
        print(f"[Face Register Error] {e}")
        raise HTTPException(400, "No face detected in photo. Please retake in good lighting ❌")

    student.face_data = embedding_to_str(embedding)
    db.commit()
    return {"message": "Face registered successfully ✅"}

# ── Verify Face (Attendance) ───────────────────────────────

@router.post("/student/verify-face")
def verify_face(data: FaceVerifyInput, db: Session = Depends(get_db)):
    student = db.query(Student).filter(
        Student.roll_no == data.roll_no.strip().upper()
    ).first()
    if not student:
        raise HTTPException(404, "Student not found ❌")
    if not student.face_data:
        raise HTTPException(400, "No face registered. Please register face first ❌")

    try:
        incoming_embedding = get_face_embedding(data.face_data, f"att_{student.roll_no}.jpg")
    except Exception as e:
        print(f"[Face Verify Error] {e}")
        raise HTTPException(400, "No face detected. Try better lighting ❌")

    stored_embedding = str_to_embedding(student.face_data)
    similarity       = cosine_similarity(stored_embedding, incoming_embedding)
    match            = similarity >= 0.7   # 70% similarity threshold
    confidence       = round(similarity * 100, 1)

    print(f"[Face Match] {student.roll_no} → similarity: {similarity:.3f} → {'✅' if match else '❌'}")

    return {
        "match":      match,
        "confidence": confidence,
        "message":    f"Face matched ✅ ({confidence}% confidence)" if match else f"Face not matched ❌ ({confidence}%)"
    }

# ── Get Face Status ────────────────────────────────────────

@router.get("/student/face/{roll_no}")
def get_face_status(roll_no: str, db: Session = Depends(get_db)):
    student = db.query(Student).filter(
        Student.roll_no == roll_no.strip().upper()
    ).first()
    if not student:
        raise HTTPException(404, "Student not found ❌")
    return {
        "has_face": student.face_data is not None,
        "roll_no":  student.roll_no
    }

# ── Student Login ──────────────────────────────────────────

@router.post("/student/login")
def student_login(data: LoginInput, db: Session = Depends(get_db)):
    if not data.roll_no and not data.email:
        raise HTTPException(400, "Roll number or email required ❌")

    student = None
    if data.roll_no:
        student = db.query(Student).filter(
            Student.roll_no == data.roll_no.strip().upper()
        ).first()
    else:
        student = db.query(Student).filter(Student.email == data.email).first()

    if not student or not bcrypt.verify(data.password, student.password):
        raise HTTPException(401, "Invalid credentials ❌")
    if not student.face_data:
        raise HTTPException(403, "Face not registered. Please complete registration ❌")
    course = db.query(Course).filter(Course.id == student.course_id).first()
    return {
        "message":     "Login successful ✅",
        "student_id":  student.id,
        "name":        student.name,
        "email":       student.email,
        "roll_no":     student.roll_no,
        "course_id":   student.course_id,
        "course_name": course.name if course else "",
        "semester":    student.semester,
        "year":        student.year,
    }

# ── Teacher Register ───────────────────────────────────────

@router.post("/teacher/register")
def teacher_register(data: TeacherRegisterInput, db: Session = Depends(get_db)):
    if db.query(Teacher).filter(Teacher.email == data.email).first():
        raise HTTPException(400, "Email already registered ❌")
    dept = db.query(Department).filter(Department.id == data.department_id).first() if data.department_id else None
    teacher = Teacher(
        name          = data.name,
        email         = data.email,
        password      = bcrypt.hash(data.password),
        qualification = data.qualification,
        department_id = data.department_id,
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return {"message": "Teacher registered ✅", "teacher_id": teacher.id}

# ── Teacher Login ──────────────────────────────────────────

@router.post("/teacher/login")
def teacher_login(data: LoginInput, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.email == data.email).first()
    if not teacher or not bcrypt.verify(data.password, teacher.password):
        raise HTTPException(401, "Invalid email or password ❌")
    dept = db.query(Department).filter(Department.id == teacher.department_id).first() if teacher.department_id else None
    return {
        "message":         "Login successful ✅",
        "teacher_id":      teacher.id,
        "name":            teacher.name,
        "email":           teacher.email,
        "qualification":   teacher.qualification,
        "department_name": dept.name if dept else "",
    }
