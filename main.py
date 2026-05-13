from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
import models
from routes import auth, attendance, gps, reset, admin, timetable, assignments
import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# ✅ Tables already exist — this line is safe:
#    create_all uses checkfirst=True by default so it won't
#    touch or drop existing tables, only create missing ones.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="College Attendance System API", version="2.0.0")

ALLOWED_ORIGINS = [
    "http://localhost:5173",                        # Vite dev server
    "http://localhost:8000",                        # Local FastAPI
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
    "https://attendance-web-kohl.vercel.app",       # ✅ Vercel frontend
    # Add any ngrok URL here when testing, e.g.:
    # "https://abc123.ngrok-free.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ─────────────────────────────────────────────
app.include_router(auth.router,         prefix="/auth",        tags=["Auth"])
app.include_router(attendance.router,   prefix="/attendance",  tags=["Attendance"])
app.include_router(gps.router,          prefix="/gps",         tags=["GPS"])
app.include_router(reset.router,        prefix="/reset",       tags=["Reset Password"])
app.include_router(admin.router,        prefix="/admin",       tags=["Admin"])
app.include_router(timetable.router,    prefix="/timetable",   tags=["Timetable"])
app.include_router(assignments.router,  prefix="/work",        tags=["Assignments & Lab Records"])


# ── Auto-Absent Scheduler ─────────────────────────────────
def run_auto_absent():
    try:
        from models import Timetable, Subject, Student, Attendance
        from database import SessionLocal
        db      = SessionLocal()
        now     = datetime.datetime.now()
        today   = now.strftime("%A")
        current = now.strftime("%H:%M")
        date    = now.date()
        count   = 0

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
            students = db.query(Student).filter(Student.course_id == subject.course_id).all()
            for student in students:
                existing = db.query(Attendance).filter(
                    Attendance.student_id == student.id,
                    Attendance.subject_id == slot.subject_id,
                    Attendance.date >= datetime.datetime.combine(date, datetime.time.min)
                ).first()
                if not existing:
                    db.add(Attendance(
                        student_id=student.id,
                        subject_id=slot.subject_id,
                        is_present=False
                    ))
                    count += 1

        db.commit()
        db.close()
        if count > 0:
            print(f"[Auto-Absent] Marked {count} absent records at {current}")
    except Exception as e:
        print(f"[Auto-Absent Error] {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(run_auto_absent, "interval", minutes=5)
scheduler.start()
print("✅ Auto-absent scheduler started")

# ── Serve React Frontend ───────────────────────────────────
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

dist_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))

if os.path.exists(dist_path):
    # Serve /assets/* (JS, CSS, images) — must be before catch-all
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_path, "assets")), name="assets")
    app.mount("/icons", StaticFiles(directory=os.path.join(dist_path, "icons")), name="icons")
    print("Looking for dist at:", dist_path)  # ← add this
    print("Exists:", os.path.exists(dist_path))  # ← and this

    # Serve favicon
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        f = os.path.join(dist_path, "favicon.ico")
        return FileResponse(f) if os.path.exists(f) else FileResponse(os.path.join(dist_path, "index.html"))
    
    @app.get("/", include_in_schema=False)
    async def serve_root():
        return FileResponse(os.path.join(dist_path, "index.html"))

    @app.get("/manifest.json")
    async def serve_manifest():     
        return FileResponse(
            os.path.join(dist_path, "manifest.json"),
            headers={"Content-Type": "application/manifest+json"}
        )

    # Catch-all: return index.html for React Router paths
    # This must be LAST so it doesn't override API routes
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        return FileResponse(os.path.join(dist_path, "index.html"))
