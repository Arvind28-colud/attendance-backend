from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Student, Teacher
from passlib.hash import bcrypt
from pydantic import BaseModel
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

router = APIRouter()

# ✅ Replace these with your Gmail credentials
GMAIL_ADDRESS  = "palemaravind50@gmail.com"
GMAIL_PASSWORD = "nvqa tthc qgbz dvjb"  # Gmail App Password (not your normal password)

# Temporary OTP storage (in memory)
otp_store = {}

def generate_otp():
    return "".join(random.choices(string.digits, k=6))

def send_email(to_email: str, otp: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🔐 Attendance System - Password Reset OTP"
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = to_email

        html = f"""
        <html><body style="font-family:Segoe UI,sans-serif;background:#f0f2ff;padding:30px;">
          <div style="background:white;border-radius:15px;padding:30px;max-width:400px;margin:auto;">
            <h2 style="color:#667eea;">🎓 College Attendance System</h2>
            <p style="color:#555;margin-top:10px;">Your password reset OTP is:</p>
            <div style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;
                        font-size:32px;font-weight:700;text-align:center;padding:20px;
                        border-radius:12px;letter-spacing:8px;margin:20px 0;">
              {otp}
            </div>
            <p style="color:#999;font-size:13px;">This OTP expires in 10 minutes.</p>
            <p style="color:#999;font-size:13px;">If you did not request this, ignore this email.</p>
          </div>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

# ─── Input Models ─────────────────────────────────────────

class SendOTPInput(BaseModel):
    email: str
    role:  str  # "student" or "teacher"

class VerifyOTPInput(BaseModel):
    email: str
    otp:   str

class ResetPasswordInput(BaseModel):
    email:        str
    otp:          str
    new_password: str

# ─── Send OTP ─────────────────────────────────────────────

@router.post("/send-otp")
def send_otp(data: SendOTPInput, db: Session = Depends(get_db)):
    # Check if email exists
    if data.role == "student":
        user = db.query(Student).filter(Student.email == data.email).first()
    else:
        user = db.query(Teacher).filter(Teacher.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email ❌")

    otp = generate_otp()
    otp_store[data.email] = otp
    print(f"OTP for {data.email}: {otp}")  # for testing in terminal

    sent = send_email(data.email, otp)
    if not sent:
        raise HTTPException(status_code=500, detail="Failed to send email. Check Gmail settings ❌")

    return {"message": f"OTP sent to {data.email} ✅"}

# ─── Verify OTP ───────────────────────────────────────────

@router.post("/verify-otp")
def verify_otp(data: VerifyOTPInput):
    stored = otp_store.get(data.email)
    if not stored:
        raise HTTPException(status_code=400, detail="No OTP found. Request a new one ❌")
    if stored != data.otp:
        raise HTTPException(status_code=400, detail="Incorrect OTP ❌")
    return {"message": "OTP verified ✅"}

# ─── Reset Password ───────────────────────────────────────

@router.post("/reset-password")
def reset_password(data: ResetPasswordInput, db: Session = Depends(get_db)):
    stored = otp_store.get(data.email)
    if not stored or stored != data.otp:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP ❌")

    # Update password for student or teacher
    user = db.query(Student).filter(Student.email == data.email).first()
    if not user:
        user = db.query(Teacher).filter(Teacher.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found ❌")

    user.password = bcrypt.hash(data.new_password)
    db.commit()

    # Remove OTP after successful reset
    del otp_store[data.email]

    return {"message": "Password reset successfully ✅"}