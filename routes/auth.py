from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Student, Teacher, Course, Department
from passlib.hash import bcrypt
from pydantic import BaseModel
from typing import Optional
import base64
import json
import io
import os
import requests

router = APIRouter()

# ── Face++ Config ───────────────────────────────────────────
FACEPP_API_KEY     = os.getenv("FACEPP_API_KEY")
FACEPP_API_SECRET  = os.getenv("FACEPP_API_SECRET")
FACEPP_DETECT_URL  = "https://api-us.faceplusplus.com/facepp/v3/detect"
FACEPP_COMPARE_URL = "https://api-us.faceplusplus.com/facepp/v3/compare"

# ── Face++ Helper Functions ─────────────────────────────────
def detect_face(image_base64: str) -> str:
    """Send image to Face++ and get face_token"""
    try:
        response = requests.post(FACEPP_DETECT_URL, data={
            "api_key":        FACEPP_API_KEY,
            "api_secret":     FACEPP_API_SECRET,
            "image_base64":   image_base64,
            "return_landmark": 0,
            "return_attributes": "none"
        })
        result = response.json()
        print(f"[Face++ Detect] {result}")
        if "faces" not in result or len(result["faces"]) == 0:
            return None
        return result["faces"][0]["face_token"]
    except Exception as e:
        print(f"[Face++ Detect Error] {e}")
        return None

def compare_faces(face_token1: str, face_token2: str) -> float:
    """Compare two face tokens and return confidence score"""
    try:
        response = requests.post(FACEPP_COMPARE_URL, data={
            "api_key":      FACEPP_API_KEY,
            "api_secret":   FACEPP_API_SECRET,
            "face_token1":  face_token1,
            "face_token2":  face_token2,
        })
        result = response.json()
        print(f"[Face++ Compare] {result}")
        if "confidence" not in result:
            return 0.0
        return result["confidence"]
    except Exception as e:
        print(f"[Face++ Compare Error] {e}")
        return 0.0

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

# ── Student Register ────────────────────────────────────────
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

    # Send to Face++ and get face token
    face_token = detect_face(data.face_data)
    if not face_token:
        raise HTTPException(400, "No face detected! Please retake in good lighting ❌")

    # Store face token + original image in database
    student.face_data = json.dumps({
        "face_token": face_token,
        "image":      data.face_data
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

    # Get stored face token
    try:
        stored       = json.loads(student.face_data)
        stored_token = stored.get("face_token")
        if not stored_token:
            raise HTTPException(400, "Invalid face data. Please re-register face ❌")
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid face data. Please re-register face ❌")

    # Detect face in new image
    new_token = detect_face(data.face_data)
    if not new_token:
        raise HTTPException(400, "No face detected! Try better lighting ❌")

    # Compare faces using Face++
    confidence = compare_faces(stored_token, new_token)
    match      = confidence >= 80  # 80% threshold for strict verification

    print(f"[Face++] {student.roll_no} → confidence: {confidence:.1f}% → {'✅' if match else '❌'}")

    return {
        "match":      match,
        "confidence": round(confidence, 1),
        "message":    f"Face matched ✅ ({confidence:.1f}% confidence)" if match else f"Face not matched ❌ ({confidence:.1f}%) — possible proxy attendance!"
    }

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
        "roll_no":  student.roll_no
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
    dept = db.query(Department).filter(Department.id == data.department_id).first() if data.department_id else None
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
