from contextlib import asynccontextmanager
from pathlib import Path
from typing import Generator, Optional
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import SessionLocal, init_db
from app.gpa_service import calculate_ipk, calculate_ips, get_transcript
from app.grade_service import (
    GradeValidationError,
    NotFoundError,
    get_student_grade_history,
    input_grade,
    update_grade,
)
from app.models import Attendance, Course, Grade, Student
from app.pdf_service import generate_transcript_pdf, render_transcript_html

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_sample_data(db: Session) -> None:
    if db.query(Student).count() > 0:
        return

    students = [
        Student(nim="251635006", nama="Dira Rassya Alfatih", program_studi="Sistem Informasi", angkatan=2025),
        Student(nim="251635010", nama="Mahasiswa Baru Semester 1", program_studi="Sistem Informasi", angkatan=2026),
        Student(nim="251635020", nama="Mahasiswa Presensi Kurang", program_studi="Sistem Informasi", angkatan=2025),
    ]
    courses = [
        Course(kode_mk="SI101", nama_mk="Algoritma dan Pemrograman", sks=3),
        Course(kode_mk="SI102", nama_mk="Basis Data", sks=3),
        Course(kode_mk="SI201", nama_mk="Rekayasa Perangkat Lunak", sks=4),
        Course(kode_mk="SI202", nama_mk="Analisis Perancangan Sistem Informasi", sks=3),
    ]
    db.add_all(students + courses)
    db.flush()

    attendances = [
        Attendance(student_nim="251635006", course_kode="SI101", attendance_percentage=92.0),
        Attendance(student_nim="251635006", course_kode="SI102", attendance_percentage=88.0),
        Attendance(student_nim="251635006", course_kode="SI201", attendance_percentage=85.0),
        Attendance(student_nim="251635006", course_kode="SI202", attendance_percentage=90.0),
        Attendance(student_nim="251635010", course_kode="SI101", attendance_percentage=100.0),
        Attendance(student_nim="251635020", course_kode="SI101", attendance_percentage=65.0),
    ]
    db.add_all(attendances)
    db.flush()

    initial_grades = [
        Grade(
            student_nim="251635006",
            course_kode="SI101",
            semester=1,
            letter_grade="A",
            numeric_grade=4.0,
            last_updated_by="Dosen SI101",
            last_update_reason="Nilai akhir semester 1",
        ),
        Grade(
            student_nim="251635006",
            course_kode="SI102",
            semester=1,
            letter_grade="A",
            numeric_grade=4.0,
            last_updated_by="Dosen SI102",
            last_update_reason="Nilai akhir semester 1",
        ),
    ]
    db.add_all(initial_grades)
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_sample_data(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Modul Nilai & Transkrip Akademik", lifespan=lifespan)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    nim: Optional[str] = None,
    message: Optional[str] = None,
    message_type: str = "success",
    db: Session = Depends(get_db),
):
    students = db.query(Student).order_by(Student.nim.asc()).all()
    courses = db.query(Course).order_by(Course.kode_mk.asc()).all()
    selected_nim = nim or (students[0].nim if students else "")

    transcript = None
    history = []
    if selected_nim:
        try:
            transcript = get_transcript(db, selected_nim)
            history = get_student_grade_history(db, selected_nim)
        except NotFoundError:
            selected_nim = students[0].nim if students else ""

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "students": students,
            "courses": courses,
            "selected_nim": selected_nim,
            "transcript": transcript,
            "history": history,
            "message": message,
            "message_type": message_type,
        },
    )


@app.post("/grades/submit", response_class=HTMLResponse)
def submit_grade_form(
    request: Request,
    nim: str = Form(...),
    course_kode: str = Form(...),
    semester: int = Form(...),
    letter_grade: str = Form(...),
    changed_by: str = Form(...),
    reason: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        grade = input_grade(
            db=db,
            nim=nim,
            course_kode=course_kode,
            semester=semester,
            letter_grade=letter_grade,
            changed_by=changed_by,
            reason=reason,
        )
        msg = f"Nilai {grade.letter_grade} untuk {nim} ({course_kode}, Sem {semester}) berhasil disimpan."
        msg_type = "success"
    except (GradeValidationError, NotFoundError) as exc:
        msg = str(exc)
        msg_type = "error"

    students = db.query(Student).order_by(Student.nim.asc()).all()
    courses = db.query(Course).order_by(Course.kode_mk.asc()).all()
    transcript = get_transcript(db, nim) if db.query(Student).filter(Student.nim == nim).first() else None
    history = get_student_grade_history(db, nim) if transcript else []

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "students": students,
            "courses": courses,
            "selected_nim": nim,
            "transcript": transcript,
            "history": history,
            "message": msg,
            "message_type": msg_type,
        },
    )


@app.post("/api/grades")
def api_input_grade(
    nim: str,
    course_kode: str,
    semester: int,
    letter_grade: str,
    changed_by: str = "dosen",
    reason: str = "Input nilai via API",
    db: Session = Depends(get_db),
):
    try:
        grade = input_grade(db, nim, course_kode, semester, letter_grade, changed_by, reason)
        return {
            "id": grade.id,
            "nim": grade.student_nim,
            "course_kode": grade.course_kode,
            "semester": grade.semester,
            "letter_grade": grade.letter_grade,
            "numeric_grade": grade.numeric_grade,
        }
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GradeValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/grades/{grade_id}")
def api_update_grade(
    grade_id: int,
    new_letter_grade: str,
    changed_by: str,
    reason: str,
    db: Session = Depends(get_db),
):
    try:
        grade = update_grade(db, grade_id, new_letter_grade, changed_by, reason)
        return {
            "id": grade.id,
            "nim": grade.student_nim,
            "course_kode": grade.course_kode,
            "semester": grade.semester,
            "letter_grade": grade.letter_grade,
            "numeric_grade": grade.numeric_grade,
        }
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GradeValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/students/{nim}/gpa")
def api_student_gpa(nim: str, semester: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        ipk = calculate_ipk(db, nim)
        ips = calculate_ips(db, nim, semester) if semester is not None else None
        return {"nim": nim, "semester": semester, "ips": ips, "ipk": ipk}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/students/{nim}/history")
def api_student_history(nim: str, db: Session = Depends(get_db)):
    try:
        return {"nim": nim, "history": get_student_grade_history(db, nim)}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/transcript/{nim}/html", response_class=HTMLResponse)
def transcript_html(nim: str, db: Session = Depends(get_db)):
    try:
        transcript = get_transcript(db, nim)
        return HTMLResponse(content=render_transcript_html(transcript))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/transcript/{nim}/pdf")
def transcript_pdf(nim: str, db: Session = Depends(get_db)):
    try:
        pdf_bytes = generate_transcript_pdf(db, nim)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="transkrip_{nim}.pdf"'},
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
