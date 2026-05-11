"""
Run this ONCE to drop all tables and recreate fresh.
Usage: python reset_db.py
"""

from sqlalchemy import create_engine, text

# ── Change this to your actual DB URL ──────────────────────────
DATABASE_URL = "mysql+pymysql://root:root@localhost/attendance_db"
# ── If PostgreSQL:
# DATABASE_URL = "postgresql://user:password@localhost/attendance_db"
# ───────────────────────────────────────────────────────────────

engine = create_engine(DATABASE_URL)

DROP_ALL = """
DROP TABLE IF EXISTS attendance;
DROP TABLE IF EXISTS timetable;
DROP TABLE IF EXISTS subjects;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS teachers;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS departments;
DROP TABLE IF EXISTS holidays;
DROP TABLE IF EXISTS admins;
"""

CREATE_ALL = """

-- 1. DEPARTMENTS
CREATE TABLE departments (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 2. COURSES
CREATE TABLE courses (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,   -- BCA, B.COM etc
    department_id   INT,
    duration_years  INT DEFAULT 3,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
);

-- 3. ADMINS
CREATE TABLE admins (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    email        VARCHAR(150) UNIQUE NOT NULL,
    password     VARCHAR(255) NOT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 4. TEACHERS
CREATE TABLE teachers (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    email          VARCHAR(150) UNIQUE NOT NULL,
    password       VARCHAR(255) NOT NULL,
    qualification  VARCHAR(100),
    department_id  INT,
    department_name VARCHAR(100),
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
);

-- 5. STUDENTS
CREATE TABLE students (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(150) UNIQUE NOT NULL,
    password        VARCHAR(255) NOT NULL,
    roll_no         VARCHAR(50) UNIQUE NOT NULL,
    course_id       INT,
    course_name     VARCHAR(100),
    semester        INT DEFAULT 1,
    year            VARCHAR(20),
    academic_year   VARCHAR(20) DEFAULT '2025-2026',
    face_image      LONGTEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
);

-- 6. SUBJECTS
CREATE TABLE subjects (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    name              VARCHAR(100) NOT NULL,   -- Python, Java, DBMS etc
    course_id         INT,
    course_name       VARCHAR(100),            -- BCA, B.COM (beside course_id)
    teacher_id        INT,
    teacher_name      VARCHAR(100),            -- Mr. Raj (beside teacher_id)
    semester          INT NOT NULL,            -- 1 to 6
    academic_year     VARCHAR(20) DEFAULT '2025-2026',
    classes_per_week  INT DEFAULT 4,           -- 4 for all subjects
    total_classes     INT DEFAULT 68,          -- 4 classes/week x 17 weeks
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id)  REFERENCES courses(id)   ON DELETE SET NULL,
    FOREIGN KEY (teacher_id) REFERENCES teachers(id)  ON DELETE SET NULL
);

-- 7. TIMETABLE
CREATE TABLE timetable (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    subject_id    INT NOT NULL,
    subject_name  VARCHAR(100),
    course_id     INT,
    course_name   VARCHAR(100),
    day_of_week   VARCHAR(10) NOT NULL,   -- Monday, Tuesday etc
    start_time    TIME NOT NULL,          -- 09:30:00
    end_time      TIME NOT NULL,          -- 10:15:00
    semester      INT,
    academic_year VARCHAR(20) DEFAULT '2025-2026',
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id)  REFERENCES courses(id)  ON DELETE SET NULL
);

-- 8. HOLIDAYS
CREATE TABLE holidays (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    date         DATE NOT NULL UNIQUE,
    reason       VARCHAR(200),             -- 'Republic Day', 'Pongal' etc
    created_by   INT,                      -- admin id
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES admins(id) ON DELETE SET NULL
);

-- 9. ATTENDANCE
CREATE TABLE attendance (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    student_id       INT NOT NULL,
    student_name     VARCHAR(100),
    subject_id       INT NOT NULL,
    subject_name     VARCHAR(100),
    date             VARCHAR(12) NOT NULL,
    is_present       VARCHAR(10) DEFAULT 'Absent',
    gps_lat          DECIMAL(10, 8),
    gps_lng          DECIMAL(11, 8),
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    UNIQUE KEY unique_attendance (student_id, subject_id, date)
);
"""

def reset():
    with engine.connect() as conn:
        print("⚠️  Dropping all tables...")
        # Drop in reverse order to avoid FK issues
        for stmt in DROP_ALL.strip().split("\n"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
        print("✅ All tables dropped!")

        print("\n📦 Creating fresh tables...")
        # Split by semicolon and run each
        statements = [s.strip() for s in CREATE_ALL.split(";") if s.strip() and not s.strip().startswith("--")]
        for stmt in statements:
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
        print("✅ All tables created fresh!")

        print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ DATABASE RESET COMPLETE!

Tables created:
  ✓ departments
  ✓ courses
  ✓ admins
  ✓ teachers
  ✓ students
  ✓ subjects  (with course_name, teacher_name, total_classes)
  ✓ timetable (with subject_name, course_name)
  ✓ holidays  (admin marks, affects all)
  ✓ attendance (student_name, subject_name, DD/MM/YYYY date)

Now update your DATABASE_URL in your FastAPI app
and restart the server!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """)

if __name__ == "__main__":
    reset()