from pathlib import Path
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'nilai_transkrip.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        conn.execute(text("DROP TRIGGER IF EXISTS trg_grades_after_update;"))
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

        conn.execute(text("DROP VIEW IF EXISTS v_student_grade_history;"))
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
