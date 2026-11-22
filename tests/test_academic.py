import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.gpa_service import calculate_ipk, get_transcript
from app.grade_service import (
    GradeValidationError,
    get_student_grade_history,
    input_grade,
    update_grade,
)
from app.models import Attendance, Course, Student
from app.pdf_service import generate_transcript_pdf


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()

    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            text("""
            CREATE TRIGGER trg_grades_after_update
            AFTER UPDATE ON grades
            WHEN OLD.letter_grade IS NOT NEW.letter_grade
            BEGIN
                INSERT INTO grade_history (
                    grade_id,
                    old_value,
                    new_value,
                    changed_by,
                    changed_at,
                    reason
                )
                VALUES (
                    NEW.id,
                    OLD.letter_grade,
                    NEW.letter_grade,
                    COALESCE(NEW.last_updated_by, 'system'),
                    COALESCE(NEW.last_updated_at, datetime('now', 'localtime')),
                    COALESCE(NEW.last_update_reason, 'Perubahan nilai')
                );
            END;
            """)
        )
        conn.execute(
            text("""
            CREATE VIEW v_student_grade_history AS
            SELECT
                s.nim AS nim,
                s.nama AS nama_mahasiswa,
                s.program_studi,
                s.angkatan,
                c.kode_mk,
                c.nama_mk,
                c.sks,
                g.semester,
                g.id AS grade_id,
                gh.id AS history_id,
                gh.old_value,
                gh.new_value,
                gh.changed_by,
                gh.changed_at,
                gh.reason
            FROM grade_history gh
            JOIN grades g ON g.id = gh.grade_id
            JOIN students s ON s.nim = g.student_nim
            JOIN courses c ON c.kode_mk = g.course_kode
            ORDER BY gh.changed_at DESC, gh.id DESC;
            """)
        )

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_basic(db):
    db.add_all(
        [
            Student(nim="251635001", nama="Budi Santoso", program_studi="Sistem Informasi", angkatan=2025),
            Student(nim="251635002", nama="Siti Aminah", program_studi="Sistem Informasi", angkatan=2025),
            Student(nim="251635003", nama="Andi Pratama", program_studi="Sistem Informasi", angkatan=2026),
            Course(kode_mk="MK01", nama_mk="Pemrograman Dasar", sks=3),
            Course(kode_mk="MK02", nama_mk="Struktur Data", sks=4),
            Attendance(student_nim="251635001", course_kode="MK01", attendance_percentage=90.0),
            Attendance(student_nim="251635001", course_kode="MK02", attendance_percentage=85.0),
            Attendance(student_nim="251635002", course_kode="MK01", attendance_percentage=95.0),
            Attendance(student_nim="251635002", course_kode="MK02", attendance_percentage=80.0),
            Attendance(student_nim="251635003", course_kode="MK01", attendance_percentage=70.0),
        ]
    )
    db.commit()


def test_perfect_student_ipk_4(db_session):
    _seed_basic(db_session)
    input_grade(db_session, "251635001", "MK01", 1, "A", "Dosen A", "Nilai awal")
    input_grade(db_session, "251635001", "MK02", 1, "A", "Dosen B", "Nilai awal")

    assert calculate_ipk(db_session, "251635001") == 4.0


def test_repeated_course_takes_highest_grade(db_session):
    _seed_basic(db_session)
    input_grade(db_session, "251635002", "MK01", 1, "C", "Dosen A", "Semester 1")
    input_grade(db_session, "251635002", "MK01", 3, "A", "Dosen A", "Mengulang MK01")
    input_grade(db_session, "251635002", "MK02", 1, "B", "Dosen B", "Semester 1")

    assert calculate_ipk(db_session, "251635002") == 3.43


def test_freshman_without_grades_returns_zero(db_session):
    _seed_basic(db_session)
    assert calculate_ipk(db_session, "251635003") == 0.0


def test_attendance_below_75_rejected(db_session):
    _seed_basic(db_session)
    with pytest.raises(GradeValidationError):
        input_grade(db_session, "251635003", "MK01", 1, "B", "Dosen A", "Presensi 70%")


def test_audit_trail_and_pdf_generation(db_session):
    _seed_basic(db_session)
    g = input_grade(db_session, "251635001", "MK01", 1, "B", "Dosen A", "Nilai awal")
    update_grade(db_session, g.id, "A", "Kaprodi", "Revisi hasil ujian susulan")

    history = get_student_grade_history(db_session, "251635001")
    assert len(history) == 1
    assert history[0]["old_value"] == "B"
    assert history[0]["new_value"] == "A"
    assert history[0]["changed_by"] == "Kaprodi"
    assert history[0]["reason"] == "Revisi hasil ujian susulan"

    transcript = get_transcript(db_session, "251635001")
    assert transcript["biodata"]["nim"] == "251635001"
    assert transcript["summary"]["ipk"] == 4.0

    pdf_bytes = generate_transcript_pdf(db_session, "251635001")
    assert pdf_bytes.startswith(b"%PDF")

from app.gpa_service import calculate_ips, determine_predikat


def test_calculate_ips_per_semester(db_session):
    _seed_basic(db_session)
    input_grade(db_session, "251635001", "MK01", 1, "A", "Dosen A", "Sem 1")
    input_grade(db_session, "251635001", "MK02", 1, "B", "Dosen B", "Sem 1")
    assert calculate_ips(db_session, "251635001", 1) == 3.43
    assert calculate_ips(db_session, "251635001", 2) == 0.0


def test_passing_grade_d_and_failing_e(db_session):
    _seed_basic(db_session)
    input_grade(db_session, "251635001", "MK01", 1, "D", "Dosen A", "Nilai D lulus")
    input_grade(db_session, "251635001", "MK02", 1, "E", "Dosen B", "Nilai E tidak lulus")
    assert calculate_ipk(db_session, "251635001") == 1.0


def test_multiple_retakes_highest_wins(db_session):
    _seed_basic(db_session)
    input_grade(db_session, "251635002", "MK01", 1, "D", "Dosen A", "Percobaan 1")
    input_grade(db_session, "251635002", "MK01", 2, "A", "Dosen A", "Percobaan 2")
    input_grade(db_session, "251635002", "MK01", 3, "B", "Dosen A", "Percobaan 3")
    assert calculate_ipk(db_session, "251635002") == 4.0


def test_predikat_kelulusan_tiers():
    assert determine_predikat(3.75, 144) == "Cum Laude"
    assert determine_predikat(3.20, 144) == "Sangat Memuaskan"
    assert determine_predikat(2.85, 144) == "Memuaskan"
    assert determine_predikat(2.25, 144) == "Cukup"
    assert determine_predikat(0.0, 0) == "Belum Ada Kelulusan"


def test_no_history_when_grade_unchanged(db_session):
    _seed_basic(db_session)
    g = input_grade(db_session, "251635001", "MK01", 1, "A", "Dosen A", "Awal")
    update_grade(db_session, g.id, "A", "Dosen A", "Tidak berubah")
    assert get_student_grade_history(db_session, "251635001") == []
