from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
import models
from routes import auth, attendance, gps, reset, admin, timetable, settings
import datetime

# ✅ Tables already exist — this line is safe:
#    create_all uses checkfirst=True by default so it won't
#    touch or drop existing tables, only create missing ones.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="College Attendance System API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ✅ Allows any origin — works with ngrok + localhost
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ─────────────────────────────────────────────
app.include_router(auth.router,       prefix="/auth",       tags=["Auth"])
app.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
app.include_router(gps.router,        prefix="/gps",        tags=["GPS"])
app.include_router(reset.router,      prefix="/reset",      tags=["Reset Password"])
app.include_router(admin.router,      prefix="/admin",      tags=["Admin"])
app.include_router(timetable.router,  prefix="/timetable",  tags=["Timetable"])
app.include_router(settings.router,   prefix="/settings",   tags=["Settings"])




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