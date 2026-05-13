from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
import datetime

class Admin(Base):
    __tablename__ = "admins"
    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String(100))
    email    = Column(String(100), unique=True)
    password = Column(String(255))

class Department(Base):
    __tablename__ = "departments"
    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String(100), unique=True)
    courses  = relationship("Course",  back_populates="department")
    teachers = relationship("Teacher", back_populates="department")

class Course(Base):
    __tablename__ = "courses"
    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(100))
    department_id = Column(Integer, ForeignKey("departments.id"))
    department    = relationship("Department", back_populates="courses")
    students      = relationship("Student",    back_populates="course")
    subjects      = relationship("Subject",    back_populates="course")

class Teacher(Base):
    __tablename__ = "teachers"
    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(100))
    email         = Column(String(100), unique=True)
    password      = Column(String(255))
    qualification = Column(String(100), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    department    = relationship("Department", back_populates="teachers")
    subjects      = relationship("Subject",    back_populates="teacher")

class Subject(Base):
    __tablename__ = "subjects"
    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(100))
    course_id     = Column(Integer, ForeignKey("courses.id"))
    teacher_id    = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    total_classes = Column(Integer, default=0)
    semester      = Column(Integer, default=1)   # ✅ 1 to 6
    course        = relationship("Course",     back_populates="subjects")
    teacher       = relationship("Teacher",    back_populates="subjects")
    timetables    = relationship("Timetable",  back_populates="subject")
    attendances   = relationship("Attendance", back_populates="subject")

class Timetable(Base):
    __tablename__ = "timetable"
    id         = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    day        = Column(String(20))
    start_time = Column(String(10))
    end_time   = Column(String(10))
    subject    = relationship("Subject", back_populates="timetables")

class Student(Base):
    __tablename__ = "students"
    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(100))
    email         = Column(String(100), unique=True)
    roll_no       = Column(String(50),  unique=True)
    password      = Column(String(255))
    course_id     = Column(Integer, ForeignKey("courses.id"))
    year          = Column(String(20),  nullable=True)
    academic_year = Column(String(20),  nullable=True)
    semester      = Column(Integer, default=1)   # ✅ 1 to 6
    face_data     = Column(Text, nullable=True)
    course        = relationship("Course",     back_populates="students")
    attendances   = relationship("Attendance", back_populates="student")

class Attendance(Base):
    __tablename__ = "attendance"
    id         = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    date       = Column(DateTime, default=datetime.datetime.now)
    is_present = Column(Boolean, default=False)
    gps_lat    = Column(Float, nullable=True)
    gps_lng    = Column(Float, nullable=True)
    student    = relationship("Student",  back_populates="attendances")
    subject    = relationship("Subject",  back_populates="attendances")

# ── Assignment: up to 4 per subject, teacher uploads title + due date ──
class Assignment(Base):
    __tablename__ = "assignments"
    id           = Column(Integer, primary_key=True, index=True)
    subject_id   = Column(Integer, ForeignKey("subjects.id"))
    teacher_id   = Column(Integer, ForeignKey("teachers.id"))
    title        = Column(String(200))
    description  = Column(Text, nullable=True)
    due_date     = Column(String(20))           # stored as "YYYY-MM-DD"
    created_at   = Column(DateTime, default=datetime.datetime.now)
    subject      = relationship("Subject")
    teacher      = relationship("Teacher")

# ── Lab Record: exactly 1 per subject per semester ─────────────────────
class LabRecord(Base):
    __tablename__ = "lab_records"
    id           = Column(Integer, primary_key=True, index=True)
    subject_id   = Column(Integer, ForeignKey("subjects.id"))
    teacher_id   = Column(Integer, ForeignKey("teachers.id"))
    semester     = Column(Integer)
    title        = Column(String(200))
    description  = Column(Text, nullable=True)
    due_date     = Column(String(20))           # stored as "YYYY-MM-DD"
    created_at   = Column(DateTime, default=datetime.datetime.now)
    subject      = relationship("Subject")
    teacher      = relationship("Teacher")
# ── Holiday: used by admin route ───────────────────────────
class Holiday(Base):
    __tablename__ = "holidays"
    id      = Column(Integer, primary_key=True, index=True)
    date    = Column(String(20))        # "YYYY-MM-DD"
    name    = Column(String(200))
    created_at = Column(DateTime, default=datetime.datetime.now)
