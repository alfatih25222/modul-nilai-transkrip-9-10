from collections import defaultdict
from typing import Any
from sqlalchemy.orm import Session
from app.grade_service import NotFoundError, PASSING_GRADE_POINT, letter_to_numeric
from app.models import Course, Grade, Student


def determine_predikat(ipk: float, total_sks_lulus: int) -> str:
    if total_sks_lulus <= 0 or ipk <= 0.0:
        return "Belum Ada Kelulusan"
    if ipk >= 3.50:
        return "Cum Laude"
    if ipk >= 3.00:
        return "Sangat Memuaskan"
    if ipk >= 2.75:
        return "Memuaskan"
    if ipk >= 2.00:
        return "Cukup"
    return "Perlu Perbaikan"


def _effective_grades_by_course(
    grades: list[Grade],
    courses_map: dict[str, Course],
) -> dict[str, dict[str, Any]]:
    best_per_course: dict[str, dict[str, Any]] = {}

    for g in grades:
        course = courses_map.get(g.course_kode) or g.course
        if not course:
            continue
        score = (
            float(g.numeric_grade)
            if g.numeric_grade is not None
            else letter_to_numeric(g.letter_grade)
        )
        if score < PASSING_GRADE_POINT:
            continue

        mutu = round(course.sks * score, 4)
        candidate = {
            "kode_mk": course.kode_mk,
            "nama_mk": course.nama_mk,
            "sks": int(course.sks),
            "semester": int(g.semester),
            "letter_grade": g.letter_grade,
            "numeric_grade": score,
            "mutu": mutu,
        }

        current = best_per_course.get(course.kode_mk)
        if current is None or candidate["numeric_grade"] > current["numeric_grade"]:
            best_per_course[course.kode_mk] = candidate

    return best_per_course


def calculate_ips(db: Session, nim: str, semester: int) -> float:
    student = db.query(Student).filter(Student.nim == nim).first()
    if not student:
        raise NotFoundError(f"Mahasiswa dengan NIM '{nim}' tidak ditemukan.")

    grades = (
        db.query(Grade)
        .filter(Grade.student_nim == nim, Grade.semester == semester)
        .all()
    )
    if not grades:
        return 0.0

    total_sks = 0
    total_bobot = 0.0

    for g in grades:
        course = g.course or db.query(Course).filter(Course.kode_mk == g.course_kode).first()
        if not course:
            continue
        score = (
            float(g.numeric_grade)
            if g.numeric_grade is not None
            else letter_to_numeric(g.letter_grade)
        )
        total_sks += int(course.sks)
        total_bobot += int(course.sks) * score

    if total_sks == 0:
        return 0.0

    return round(total_bobot / total_sks, 2)


def calculate_ipk(db: Session, nim: str) -> float:
    student = db.query(Student).filter(Student.nim == nim).first()
    if not student:
        raise NotFoundError(f"Mahasiswa dengan NIM '{nim}' tidak ditemukan.")

    grades = db.query(Grade).filter(Grade.student_nim == nim).all()
    if not grades:
        return 0.0

    courses = db.query(Course).all()
    courses_map = {c.kode_mk: c for c in courses}

    effective = _effective_grades_by_course(grades, courses_map)
    if not effective:
        return 0.0

    total_sks = sum(item["sks"] for item in effective.values())
    total_mutu = sum(item["sks"] * item["numeric_grade"] for item in effective.values())

    if total_sks == 0:
        return 0.0

    return round(total_mutu / total_sks, 2)


def get_transcript(db: Session, nim: str) -> dict[str, Any]:
    student = db.query(Student).filter(Student.nim == nim).first()
    if not student:
        raise NotFoundError(f"Mahasiswa dengan NIM '{nim}' tidak ditemukan.")

    grades = (
        db.query(Grade)
        .filter(Grade.student_nim == nim)
        .order_by(Grade.semester.asc(), Grade.course_kode.asc(), Grade.id.asc())
        .all()
    )
    courses = db.query(Course).all()
    courses_map = {c.kode_mk: c for c in courses}

    grouped_by_sem: dict[int, list[dict[str, Any]]] = defaultdict(list)
    semesters_seen: set[int] = set()

    for g in grades:
        course = courses_map.get(g.course_kode) or g.course
        if not course:
            continue
        semesters_seen.add(int(g.semester))
        score = (
            float(g.numeric_grade)
            if g.numeric_grade is not None
            else letter_to_numeric(g.letter_grade)
        )
        mutu = round(course.sks * score, 2)
        grouped_by_sem[int(g.semester)].append(
            {
                "kode_mk": course.kode_mk,
                "nama_mk": course.nama_mk,
                "sks": int(course.sks),
                "nilai": g.letter_grade,
                "bobot": score,
                "mutu": mutu,
                "lulus": score >= PASSING_GRADE_POINT,
            }
        )

    semesters_payload: list[dict[str, Any]] = []
    for sem in sorted(semesters_seen):
        rows = grouped_by_sem[sem]
        sem_sks = sum(r["sks"] for r in rows)
        sem_mutu = round(sum(r["mutu"] for r in rows), 2)
        ips = calculate_ips(db, nim, sem)
        semesters_payload.append(
            {
                "semester": sem,
                "ips": ips,
                "total_sks": sem_sks,
                "total_mutu": sem_mutu,
                "courses": rows,
            }
        )

    effective_passed = _effective_grades_by_course(grades, courses_map)
    total_sks_lulus = sum(item["sks"] for item in effective_passed.values())
    total_mutu_lulus = round(
        sum(item["sks"] * item["numeric_grade"] for item in effective_passed.values()),
        2,
    )
    ipk = calculate_ipk(db, nim)
    predikat = determine_predikat(ipk, total_sks_lulus)

    return {
        "biodata": {
            "nim": student.nim,
            "nama": student.nama,
            "program_studi": student.program_studi,
            "angkatan": student.angkatan,
        },
        "semesters": semesters_payload,
        "summary": {
            "total_sks": total_sks_lulus,
            "total_mutu": total_mutu_lulus,
            "ipk": ipk,
            "predikat": predikat,
        },
    }
