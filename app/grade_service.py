from datetime import datetime
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models import Attendance, Course, Grade, Student

GRADE_SCALE: dict[str, float] = {
    "A": 4.0,
    "B": 3.0,
    "C": 2.0,
    "D": 1.0,
    "E": 0.0,
}

MIN_ATTENDANCE_PERCENTAGE = 75.0
PASSING_GRADE_POINT = 1.0


class GradeValidationError(ValueError):
    """Raised when grade input or update violates business rules."""


class NotFoundError(LookupError):
    """Raised when student, course, or grade record is not found."""


def normalize_letter_grade(letter_grade: str) -> str:
    cleaned = letter_grade.strip().upper()
    if cleaned not in GRADE_SCALE:
        allowed = ", ".join(GRADE_SCALE.keys())
        raise GradeValidationError(
            f"Nilai huruf '{letter_grade}' tidak valid. Gunakan salah satu: {allowed}."
        )
    return cleaned


def letter_to_numeric(letter_grade: str) -> float:
    normalized = normalize_letter_grade(letter_grade)
    return GRADE_SCALE[normalized]


def is_passed_grade(letter_grade: str) -> bool:
    return letter_to_numeric(letter_grade) >= PASSING_GRADE_POINT


def validate_attendance_for_grading(db: Session, nim: str, course_kode: str) -> float:
    attendance = (
        db.query(Attendance)
        .filter(Attendance.student_nim == nim, Attendance.course_kode == course_kode)
        .first()
    )
    percentage = float(attendance.attendance_percentage) if attendance else 0.0
    if percentage < MIN_ATTENDANCE_PERCENTAGE:
        raise GradeValidationError(
            f"Nilai tidak bisa diinput karena presensi mahasiswa {nim} pada MK {course_kode} "
            f"sebesar {percentage:.1f}% (< {MIN_ATTENDANCE_PERCENTAGE:.0f}%)."
        )
    return percentage


def input_grade(
    db: Session,
    nim: str,
    course_kode: str,
    semester: int,
    letter_grade: str,
    changed_by: str,
    reason: str = "Input nilai awal",
) -> Grade:
    student = db.query(Student).filter(Student.nim == nim).first()
    if not student:
        raise NotFoundError(f"Mahasiswa dengan NIM '{nim}' tidak ditemukan.")

    course = db.query(Course).filter(Course.kode_mk == course_kode).first()
    if not course:
        raise NotFoundError(f"Mata kuliah dengan kode '{course_kode}' tidak ditemukan.")

    if semester < 1:
        raise GradeValidationError("Semester harus lebih besar atau sama dengan 1.")

    validate_attendance_for_grading(db, nim, course_kode)

    normalized_letter = normalize_letter_grade(letter_grade)
    numeric_value = letter_to_numeric(normalized_letter)
    now = datetime.now()
    actor = changed_by.strip() or "dosen"
    clean_reason = reason.strip() or "Input nilai awal"

    existing = (
        db.query(Grade)
        .filter(
            Grade.student_nim == nim,
            Grade.course_kode == course_kode,
            Grade.semester == semester,
        )
        .first()
    )

    if existing:
        existing.letter_grade = normalized_letter
        existing.numeric_grade = numeric_value
        existing.last_updated_by = actor
        existing.last_updated_at = now
        existing.last_update_reason = clean_reason
        db.commit()
        db.refresh(existing)
        return existing

    grade = Grade(
        student_nim=nim,
        course_kode=course_kode,
        semester=semester,
        letter_grade=normalized_letter,
        numeric_grade=numeric_value,
        last_updated_by=actor,
        last_updated_at=now,
        last_update_reason=clean_reason,
    )
    db.add(grade)
    db.commit()
    db.refresh(grade)
    return grade


def update_grade(
    db: Session,
    grade_id: int,
    new_letter_grade: str,
    changed_by: str,
    reason: str,
) -> Grade:
    grade = db.query(Grade).filter(Grade.id == grade_id).first()
    if not grade:
        raise NotFoundError(f"Data nilai dengan ID {grade_id} tidak ditemukan.")

    if not changed_by or not changed_by.strip():
        raise GradeValidationError("Informasi pengubah (changed_by) wajib diisi untuk audit trail.")

    if not reason or not reason.strip():
        raise GradeValidationError("Alasan perubahan nilai (reason) wajib diisi untuk audit trail.")

    validate_attendance_for_grading(db, grade.student_nim, grade.course_kode)

    normalized_letter = normalize_letter_grade(new_letter_grade)
    numeric_value = letter_to_numeric(normalized_letter)

    grade.letter_grade = normalized_letter
    grade.numeric_grade = numeric_value
    grade.last_updated_by = changed_by.strip()
    grade.last_updated_at = datetime.now()
    grade.last_update_reason = reason.strip()

    db.commit()
    db.refresh(grade)
    return grade


def get_student_grade_history(db: Session, nim: str) -> list[dict[str, Any]]:
    student = db.query(Student).filter(Student.nim == nim).first()
    if not student:
        raise NotFoundError(f"Mahasiswa dengan NIM '{nim}' tidak ditemukan.")

    rows = db.execute(
        text("SELECT * FROM v_student_grade_history WHERE nim = :nim ORDER BY history_id DESC"),
        {"nim": nim},
    ).mappings().all()
    return [dict(row) for row in rows]
