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
from base64 import b64decode
import io
from PIL import Image

router = APIRouter()

HF_URL = os.getenv("HF_URL", "https://YOUR-USERNAME-YOUR-SPACE-NAME.hf.space")

# ── Input Data Validations ───────────────────────────────────
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
    face_data: str 

class FaceVerifyInput(BaseModel):
    roll_no:   str
    face_data: str  

class GridCheckInput(BaseModel):
    face_data: str

# ── HuggingFace Connections ─────────────────────────────────
def hf_get_embedding(image_base64: str) -> dict:
    try:
        res = httpx.post(
            f"{HF_URL}/get-embedding",
            json    = {"image": image_base64},
            timeout = 60,
        )
        return res.json()
    except Exception as e:
        print(f"[HF Error] get-embedding: {e}")
        return {"success": False, "error": str(e)}

def hf_match_faces(live_image: str, stored_image: str) -> dict:
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

# ── Exact face-api.js Oval Grid Calibration ─────────────────
def check_oval_alignment(bbox: list, img_w: int, img_h: int) -> dict:
    """
    Computes mathematical boundaries against a formal 72% Width / 62% Height
    elliptical target envelope mapped onto the physical dimensions of the frame matrix.
    """
    if not bbox or len(bbox) < 4:
        return {"ok": False, "reason": "No face detected 🔍"}

    # Translate absolute pixel maps to normalized vector properties [0.0 -> 1.0]
    norm_x_min = bbox[0] / img_w
    norm_y_min = bbox[1] / img_h
    norm_x_max = bbox[2] / img_w
    norm_y_max = bbox[3] / img_h

    face_w = norm_x_max - norm_x_min
    face_h = norm_y_max - norm_y_min
    face_center_x = norm_x_min + (face_w / 2)
    face_center_y = norm_y_min + (face_h / 2)

    # UI Oval Overlay constants (72% screen width, 62% screen height)
    target_oval_w = 0.72
    target_oval_h = 0.62
    target_center_x = 0.50
    target_center_y = 0.50

    # Test 1: Center Drift (Threshold = Max 8% variance allowed from origin center)
    max_drift = 0.08
    drift_x = abs(face_center_x - target_center_x)
    drift_y = abs(face_center_y - target_center_y)

    if drift_x > max_drift:
        return {"ok": False, "reason": "Center your face → Move Right" if face_center_x < target_center_x else "Center your face → Move Left"}
    if drift_y > max_drift:
        return {"ok": False, "reason": "Center your face → Move Down" if face_center_y < target_center_y else "Center your face → Move Up"}

    # Test 2: Scale Factor / Target Proximity (Face must cleanly occupy 65% to 95% of target window)
    min_scale = 0.65
    max_scale = 0.95
    current_scale = face_w / target_oval_w

    if current_scale < min_scale:
        return {"ok": False, "reason": "Come closer to the camera"}
    if current_scale > max_scale:
        return {"ok": False, "reason": "Step back slightly"}

    return {"ok": True, "reason": "Face Aligned Successfully ✅"}

# ── Live Polling Grid Alignment Endpoint ────────────────────
@router.post("/student/check-grid-alignment")
def check_grid_alignment(data: GridCheckInput):
    try:
        image_bytes = b64decode(data.face_data)
        image = Image.open(io.BytesIO(image_bytes))
        img_w, img_h = image.size
    except Exception:
        raise HTTPException(400, "Corrupted frame data array")

    result = hf_get_embedding(data.face_data)
    if not result.get("success"):
        return {"ok": False, "reason": "No face found 🔍"}

    bbox = result.get("bbox")
    if not bbox:
        raise HTTPException(400, "Hugging Face endpoint missing 'bbox' coordinate payload mappings")

    return check_oval_alignment(bbox, img_w, img_h)

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

# ── Update Face ─────────────────────────────────────────────
@router.post("/student/update-face")
def update_face(data: UpdateFaceInput, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.roll_no == data.roll_no.strip().upper()).first()
    if not student:
        raise HTTPException(404, "Student profile execution target not found")

    result = hf_get_embedding(data.face_data)
    if not result.get("success"):
        raise HTTPException(400, f"Face registration failed: {result.get('error', 'Unknown Error')} ❌")

    student.face_data = json.dumps({
        "embedding": result["embedding"],         
        "image":     data.face_data,    
    })
    db.commit()
    return {"message": "Face registered successfully ✅"}

# ── Verify Face ─────────────────────────────────────────────
@router.post("/student/verify-face")
def verify_face(data: FaceVerifyInput, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.roll_no == data.roll_no.strip().upper()).first()
    if not student: raise HTTPException(404, "Student not found ❌")
    if not student.face_data: raise HTTPException(400, "No face registered ❌")

    try:
        stored = json.loads(student.face_data)
        stored_emb = stored.get("embedding")
        stored_img = stored.get("image")
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid face data structural schema ❌")

    if stored_emb:
        try:
            import numpy as np
            live_result = hf_get_embedding(data.face_data)
            if not live_result.get("success"):
                raise HTTPException(400, "Face extraction failed ❌")

            e1 = np.array(stored_emb)
            e2 = np.array(live_result["embedding"])
            cos = float(np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2)))

            verified = cos > 0.5
            confidence = round(cos * 100, 1)

            return {
                "match":      verified,
                "confidence": confidence,
                "message":    f"Face matched ✅ ({confidence}%)" if verified else f"Face not matched ❌ ({confidence}%)",
            }
        except Exception:
            pass # Fall through to backup logic below if array shapes clash

    if stored_img:
        result = hf_match_faces(data.face_data, stored_img)
        if not result.get("success"): raise HTTPException(400, "Verification pipeline failure")
        return {"match": result["verified"], "confidence": result["confidence"], "message": "Face verified via fallback match engine"}

    raise HTTPException(400, "No matching parameter targets found")

# ── Secondary Boilerplate Context Routes ───────────────────
@router.get("/student/face/{roll_no}")
def get_face_status(roll_no: str, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.roll_no == roll_no.strip().upper()).first()
    if not student: raise HTTPException(404, "Target missing")
    return {"has_face": student.face_data is not None, "roll_no": student.roll_no}

@router.post("/student/login")
def student_login(data: LoginInput, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.roll_no == data.roll_no.strip().upper()).first() if data.roll_no else db.query(Student).filter(Student.email == data.email).first()
    if not student or not bcrypt.verify(data.password.encode('utf-8')[:72].decode('utf-8', errors='ignore'), student.password):
        raise HTTPException(401, "Invalid credentials")
    if not student.face_data: raise HTTPException(403, "Face setup mandatory")
    return {"message": "Login successful ✅", "roll_no": student.roll_no, "name": student.name}

@router.post("/teacher/register")
def teacher_register(data: TeacherRegisterInput, db: Session = Depends(get_db)):
    if db.query(Teacher).filter(Teacher.email == data.email).first(): raise HTTPException(400, "Email taken")
    teacher = Teacher(name=data.name, email=data.email, password=bcrypt.hash(data.password))
    db.add(teacher)
    db.commit()
    return {"message": "Success"}

@router.post("/teacher/login")
def teacher_login(data: LoginInput, db: Session = Depends(get_db)):
    teacher = db.query(Teacher).filter(Teacher.email == data.email).first()
    if not teacher or not bcrypt.verify(data.password, teacher.password): raise HTTPException(401, "Failed")
    return {"message": "Success"}
