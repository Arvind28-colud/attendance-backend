from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base

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
    id               = Column(Integer, primary_key=True, index=True)
    name             = Column(String(100))
    course_id        = Column(Integer, ForeignKey("courses.id"))
    course_name      = Column(String(100))           # beside course_id
    teacher_id       = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    teacher_name     = Column(String(100))           # beside teacher_id
    semester         = Column(Integer, default=1)
    classes_per_week = Column(Integer, default=4)
    total_classes    = Column(Integer, default=68)
    course           = relationship("Course",     back_populates="subjects")
    teacher          = relationship("Teacher",    back_populates="subjects")
    timetables       = relationship("Timetable",  back_populates="subject")
    attendances      = relationship("Attendance", back_populates="subject")

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
    course_name   = Column(String(100))              # beside course_id
    year          = Column(String(20),  nullable=True)
    academic_year = Column(String(20),  nullable=True)
    semester      = Column(Integer, default=1)
    face_data     = Column(Text(length=4294967295), nullable=True)  # LONGTEXT
    course        = relationship("Course",     back_populates="students")
    attendances   = relationship("Attendance", back_populates="student")

class Attendance(Base):
    __tablename__ = "attendance"
    id           = Column(Integer, primary_key=True, index=True)
    student_id   = Column(Integer, ForeignKey("students.id"))
    student_name = Column(String(100))               # beside student_id
    subject_id   = Column(Integer, ForeignKey("subjects.id"))
    subject_name = Column(String(100))               # beside subject_id
    date         = Column(String(12))                # DD/MM/YYYY
    is_present   = Column(String(10), default="Absent")  # Present or Absent
    gps_lat      = Column(Float, nullable=True)
    gps_lng      = Column(Float, nullable=True)
    student      = relationship("Student", back_populates="attendances")
    subject      = relationship("Subject", back_populates="attendances")

class Holiday(Base):
    __tablename__ = "holidays"
    id         = Column(Integer, primary_key=True, index=True)
    date       = Column(String(12), unique=True)     # DD/MM/YYYY
    reason     = Column(String(200))
    created_by = Column(Integer, ForeignKey("admins.id"), nullable=True)

class Settings(Base):
    __tablename__ = "settings"
    id                  = Column(Integer, primary_key=True, default=1)
    semester_start_date = Column(String(12), nullable=True)   # DD/MM/YYYY
    semester_end_date   = Column(String(12), nullable=True)   # DD/MM/YYYY
    academic_year       = Column(String(20), default='2025-2026')
    current_semester    = Column(Integer, default=4)