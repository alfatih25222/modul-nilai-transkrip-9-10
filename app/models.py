from datetime import datetime
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base


class Student(Base):
    __tablename__ = "students"

    nim = Column(String(30), primary_key=True, index=True)
    nama = Column(String(120), nullable=False)
    program_studi = Column(String(100), nullable=False)
    angkatan = Column(Integer, nullable=False)

    attendances = relationship("Attendance", back_populates="student", cascade="all, delete-orphan")
    grades = relationship("Grade", back_populates="student", cascade="all, delete-orphan")


class Course(Base):
    __tablename__ = "courses"

    kode_mk = Column(String(20), primary_key=True, index=True)
    nama_mk = Column(String(120), nullable=False)
    sks = Column(Integer, nullable=False)

    attendances = relationship("Attendance", back_populates="course", cascade="all, delete-orphan")
    grades = relationship("Grade", back_populates="course", cascade="all, delete-orphan")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("student_nim", "course_kode", name="uq_attendance_student_course"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_nim = Column(String(30), ForeignKey("students.nim", ondelete="CASCADE"), nullable=False)
    course_kode = Column(String(20), ForeignKey("courses.kode_mk", ondelete="CASCADE"), nullable=False)
    attendance_percentage = Column(Float, nullable=False, default=100.0)

    student = relationship("Student", back_populates="attendances")
    course = relationship("Course", back_populates="attendances")


class Grade(Base):
    __tablename__ = "grades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_nim = Column(String(30), ForeignKey("students.nim", ondelete="CASCADE"), nullable=False, index=True)
    course_kode = Column(String(20), ForeignKey("courses.kode_mk", ondelete="CASCADE"), nullable=False, index=True)
    semester = Column(Integer, nullable=False)
    letter_grade = Column(String(2), nullable=False)
    numeric_grade = Column(Float, nullable=False)
    last_updated_by = Column(String(100), nullable=True)
    last_updated_at = Column(DateTime, default=datetime.now, nullable=True)
    last_update_reason = Column(String(255), nullable=True)

    student = relationship("Student", back_populates="grades")
    course = relationship("Course", back_populates="grades")
    history = relationship("GradeHistory", back_populates="grade", cascade="all, delete-orphan")


class GradeHistory(Base):
    __tablename__ = "grade_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    grade_id = Column(Integer, ForeignKey("grades.id", ondelete="CASCADE"), nullable=False, index=True)
    old_value = Column(String(2), nullable=False)
    new_value = Column(String(2), nullable=False)
    changed_by = Column(String(100), nullable=False)
    changed_at = Column(DateTime, default=datetime.now, nullable=False)
    reason = Column(String(255), nullable=False)

    grade = relationship("Grade", back_populates="history")
