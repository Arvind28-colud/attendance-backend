from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Student, Teacher, Course, Department
from passlib.hash import bcrypt
from pydantic import BaseModel
from typing import Optional
import json
import os
import httpx

router = APIRouter()

# ── HuggingFace ArcFace Space URL ──────────────────────────
# Replace with your actual HuggingFace Space URL after deploying
HF_URL = os.getenv("HF_URL", "https://YOUR-USERNAME-YOUR-SPACE-NAME.hf.space")

# ── Input Models ────────────────────────────────────────────
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

# ── HuggingFace Helper ──────────────────────────────────────
def hf_get_embedding(image_base64: str) -> dict:
    """Send image to HuggingFace ArcFace Space and get 512-dim embedding"""
    try:
        res = httpx.post(
            f"{HF_URL}/get-embedding",
            json    = {"image": image_base64},
            timeout = 60,   # HF cold start can take 30-60s
        )
        return res.json()
    except Exception as e:
        print(f"[HF Error] get-embedding: {e}")
        return {"success": False, "error": str(e)}

def hf_match_faces(live_image: str, stored_image: str) -> dict:
    """Compare live face vs stored face using ArcFace on HuggingFace"""
    try:
        res = httpx.post(
            f"{HF_URL}/match-faces",
            json    = {"live_image": live_image, "stored_image": stored_image},
            timeout = 60,
        )
        return res.json()
    except Exception as e:
        print(f"[HF Error] match-faces: {e}")
        return {"success": False, "verified": False, "error": str(e)}

# ── Student Register ────────────────────────────────────────
@router.post("/student/register")
def student_register(data: StudentRegisterInput, db: Session = Depends(get_db)):
    if db.query(Student).filter(Student.email == data.email).first():
        raise HTTPException(400, "Email already registered ❌")
    if db.query(Student).filter(Student.roll_no == data.roll_no).first():
        raise HTTPException(400, "Roll number already registered ❌")

    student = Student(
        name          = data.name,
        email         = data.email,
        roll_no       = data.roll_no.strip().upper(),
        password      = bcrypt.hash(data.password.encode('utf-8')[:72].decode('utf-8', errors='ignore')),
        course_id     = data.course_id,
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

# ── Update Face (Registration) ──────────────────────────────
@router.post("/student/update-face")
def update_face(data: UpdateFaceInput, db: Session = Depends(get_db)):
    student = db.query(Student).filter(
        Student.roll_no == data.roll_no.strip().upper()
    ).first()
    if not student:
        raise HTTPException(404, "Student not found ❌")

    # Send to HuggingFace ArcFace to get 512-dim embedding
    result = hf_get_embedding(data.face_data)

    if not result.get("success"):
        error = result.get("error", "Unknown error")
        raise HTTPException(400, f"Face registration failed: {error} ❌")

    embedding = result["embedding"]   # 512 numbers

    # Store both embedding + original image in DB
    # Embedding is used for fast matching
    # Original image is backup for re-matching if needed
    student.face_data = json.dumps({
        "embedding": embedding,         # 512-dim ArcFace vector
        "image":     data.face_data,    # base64 original image
    })
    db.commit()
    return {"message": "Face registered successfully ✅"}

# ── Verify Face (Attendance) ────────────────────────────────
@router.post("/student/verify-face")
def verify_face(data: FaceVerifyInput, db: Session = Depends(get_db)):
    student = db.query(Student).filter(
        Student.roll_no == data.roll_no.strip().upper()
    ).first()
    if not student:
        raise HTTPException(404, "Student not found ❌")
    if not student.face_data:
        raise HTTPException(400, "No face registered. Please register face first ❌")

    # Parse stored face data
    try:
        stored      = json.loads(student.face_data)
        stored_emb  = stored.get("embedding")
        stored_img  = stored.get("image")
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid face data. Please re-register face ❌")

    # ── Fast path: compare embeddings directly (no HF call needed) ──
    if stored_emb:
        try:
            import numpy as np
            # Get embedding for live image from HuggingFace
            live_result = hf_get_embedding(data.face_data)
            if not live_result.get("success"):
                raise HTTPException(400, f"Face detection failed: {live_result.get('error')} ❌")

            live_emb = live_result["embedding"]

            # Cosine similarity locally — no second HF call needed
            e1  = np.array(stored_emb)
            e2  = np.array(live_emb)
            cos = float(np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2)))

            verified   = cos > 0.5
            confidence = round(cos * 100, 1)

            print(f"[ArcFace] {student.roll_no} → score: {cos:.3f} ({confidence}%) → {'✅' if verified else '❌'}")

            return {
                "match":      verified,
                "confidence": confidence,
                "message":    f"Face matched ✅ ({confidence}% confidence)" if verified
                              else f"Face not matched ❌ ({confidence}%) — possible proxy attendance!",
            }
        except Exception as e:
            print(f"[Embedding compare error] {e}")
            # Fall through to image-based comparison

    # ── Fallback: send both images to HuggingFace for comparison ──
    if stored_img:
        result = hf_match_faces(data.face_data, stored_img)
        if not result.get("success"):
            raise HTTPException(400, f"Face verification failed: {result.get('error')} ❌")

        verified   = result["verified"]
        confidence = result["confidence"]

        print(f"[ArcFace HF] {student.roll_no} → {confidence}% → {'✅' if verified else '❌'}")

        return {
            "match":      verified,
            "confidence": confidence,
            "message":    f"Face matched ✅ ({confidence}% confidence)" if verified
                          else f"Face not matched ❌ ({confidence}%) — possible proxy attendance!",
        }

    raise HTTPException(400, "No face data available. Please re-register ❌")

# ── Get Face Status ─────────────────────────────────────────
@router.get("/student/face/{roll_no}")
def get_face_status(roll_no: str, db: Session = Depends(get_db)):
    student = db.query(Student).filter(
        Student.roll_no == roll_no.strip().upper()
    ).first()
    if not student:
        raise HTTPException(404, "Student not found ❌")
    return {
        "has_face": student.face_data is not None,
        "roll_no":  student.roll_no,
    }

# ── Student Login ───────────────────────────────────────────
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

    if not student:
        raise HTTPException(401, "Invalid credentials ❌")

    pwd = data.password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    if not bcrypt.verify(pwd, student.password):
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

# ── Teacher Register ────────────────────────────────────────
@router.post("/teacher/register")
def teacher_register(data: TeacherRegisterInput, db: Session = Depends(get_db)):
    if db.query(Teacher).filter(Teacher.email == data.email).first():
        raise HTTPException(400, "Email already registered ❌")
    teacher = Teacher(
        name          = data.name,
        email         = data.email,
        password      = bcrypt.hash(data.password.encode('utf-8')[:72].decode('utf-8', errors='ignore')),
        qualification = data.qualification,
        department_id = data.department_id,
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return {"message": "Teacher registered ✅", "teacher_id": teacher.id}

# ── Teacher Login ───────────────────────────────────────────
@router.post("/teacher/login")
def teacher_login(data: LoginInput, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.email == data.email).first()
    if not teacher:
        raise HTTPException(401, "Invalid email or password ❌")

    pwd = data.password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    if not bcrypt.verify(pwd, teacher.password):
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
