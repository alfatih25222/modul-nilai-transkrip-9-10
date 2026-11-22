from io import BytesIO
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session
from app.gpa_service import get_transcript

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def find_campus_logo(custom_path: Optional[Path] = None) -> Optional[Path]:
    if custom_path is not None:
        p = Path(custom_path)
        return p if p.exists() and p.is_file() else None

    preferred_names = [
        "logo_kampus.png",
        "logo_kampus.jpg",
        "logo_kampus.jpeg",
        "logo.png",
        "logo.jpg",
    ]
    for name in preferred_names:
        candidate = ASSETS_DIR / name
        if candidate.exists() and candidate.is_file():
            return candidate

    if ASSETS_DIR.exists():
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            matches = sorted(ASSETS_DIR.glob(ext))
            if matches:
                return matches[0]

    return None


def render_transcript_html(transcript: dict, logo_path: Optional[Path] = None) -> str:
    resolved_logo = find_campus_logo(logo_path)
    logo_url = f"/assets/{resolved_logo.name}" if resolved_logo else None
    logo_uri = resolved_logo.resolve().as_uri() if resolved_logo else None
    template = _jinja_env.get_template("transcript.html")
    return template.render(transcript=transcript, logo_url=logo_url, logo_uri=logo_uri)


def generate_transcript_pdf(
    db: Session,
    nim: str,
    dean_name: str = "Dekan Fakultas",
    logo_path: Optional[Path] = None,
) -> bytes:
    transcript = get_transcript(db, nim)
    resolved_logo = find_campus_logo(logo_path)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Transkrip Akademik - {transcript['biodata']['nim']}",
    )

    styles = getSampleStyleSheet()
    navy = colors.HexColor("#1E3A5F")
    gold = colors.HexColor("#C5A059")
    soft_bg = colors.HexColor("#F8FAFC")
    cream_bg = colors.HexColor("#FAF8F2")
    border_gray = colors.HexColor("#CBD5E0")

    title_style = ParagraphStyle(
        "TranscriptTitle",
        parent=styles["Heading1"],
        fontName="Times-Bold",
        fontSize=16,
        leading=20,
        textColor=navy,
        alignment=1,
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "TranscriptSubtitle",
        parent=styles["Normal"],
        fontName="Times-Italic",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#4A5568"),
        alignment=1,
    )
    sem_heading_style = ParagraphStyle(
        "SemesterHeading",
        parent=styles["Heading2"],
        fontName="Times-Bold",
        fontSize=11,
        leading=14,
        textColor=navy,
        spaceBefore=8,
        spaceAfter=4,
    )
    normal_style = ParagraphStyle(
        "TranscriptNormal",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1A202C"),
    )

    story = []

    title_block = [
        Paragraph("TRANSKRIP AKADEMIK", title_style),
        Paragraph("Dokumen Catatan Prestasi Studi Mahasiswa", subtitle_style),
    ]
    if resolved_logo:
        img = Image(str(resolved_logo), width=18 * mm, height=18 * mm, kind="proportional")
        header_table = Table([[img, title_block]], colWidths=[24 * mm, doc.width - 24 * mm])
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "CENTER"),
                    ("LINEBELOW", (0, 0), (-1, 0), 2, navy),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ]
            )
        )
    else:
        header_table = Table([[title_block]], colWidths=[doc.width])
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBELOW", (0, 0), (-1, 0), 2, navy),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ]
            )
        )

    story.append(header_table)
    story.append(Spacer(1, 5 * mm))

    bio = transcript["biodata"]
    bio_data = [
        [
            Paragraph("<b>NIM</b>", normal_style),
            Paragraph(f": {bio['nim']}", normal_style),
            Paragraph("<b>Program Studi</b>", normal_style),
            Paragraph(f": {bio['program_studi']}", normal_style),
        ],
        [
            Paragraph("<b>Nama</b>", normal_style),
            Paragraph(f": {bio['nama']}", normal_style),
            Paragraph("<b>Angkatan</b>", normal_style),
            Paragraph(f": {bio['angkatan']}", normal_style),
        ],
    ]
    bio_table = Table(
        bio_data,
        colWidths=[24 * mm, doc.width * 0.28, 30 * mm, doc.width - (24 * mm + doc.width * 0.28 + 30 * mm)],
    )
    bio_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), cream_bg),
                ("BOX", (0, 0), (-1, -1), 0.8, gold),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2D9C5")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(bio_table)
    story.append(Spacer(1, 4 * mm))

    semesters = transcript.get("semesters", [])
    if not semesters:
        story.append(Paragraph("Belum ada data nilai mata kuliah yang tercatat.", normal_style))
    else:
        col_widths = [
            doc.width * 0.15,
            doc.width * 0.45,
            doc.width * 0.10,
            doc.width * 0.12,
            doc.width * 0.18,
        ]
        for sem in semesters:
            story.append(Paragraph(f"Semester {sem['semester']}", sem_heading_style))
            rows = [["Kode MK", "Nama MK", "SKS", "Nilai", "Mutu"]]
            for mk in sem["courses"]:
                rows.append(
                    [
                        mk["kode_mk"],
                        mk["nama_mk"],
                        str(mk["sks"]),
                        str(mk["nilai"]),
                        f"{mk['mutu']:.2f}",
                    ]
                )

            sem_table = Table(rows, colWidths=col_widths, repeatRows=1)
            sem_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), navy),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                        ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                        ("ALIGN", (2, 0), (3, -1), "CENTER"),
                        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft_bg]),
                        ("GRID", (0, 0), (-1, -1), 0.5, border_gray),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(sem_table)
            story.append(Spacer(1, 2 * mm))
            story.append(
                Paragraph(
                    f"<b>Total SKS Semester:</b> {sem['total_sks']} &nbsp;|&nbsp; <b>IPS:</b> {sem['ips']:.2f}",
                    ParagraphStyle(
                        "SemMeta",
                        parent=normal_style,
                        alignment=2,
                        fontSize=9.5,
                    ),
                )
            )
            story.append(Spacer(1, 3 * mm))

    story.append(Spacer(1, 4 * mm))

    summary = transcript["summary"]
    summary_data = [
        [Paragraph("<b>Total SKS</b>", normal_style), Paragraph(f"<b>{summary['total_sks']}</b>", normal_style)],
        [Paragraph("<b>IPK</b>", normal_style), Paragraph(f"<b>{summary['ipk']:.2f}</b>", normal_style)],
        [Paragraph("<b>Predikat</b>", normal_style), Paragraph(f"<b>{summary['predikat']}</b>", normal_style)],
    ]
    summary_table = Table(summary_data, colWidths=[doc.width * 0.30, doc.width * 0.20])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), soft_bg),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, border_gray),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    ttd_block = [
        Paragraph("<b>TTD Dekan</b>", ParagraphStyle("TTDTitle", parent=normal_style, alignment=1)),
        Spacer(1, 14 * mm),
        Paragraph(f"<u><b>{dean_name}</b></u>", ParagraphStyle("TTDName", parent=normal_style, alignment=1)),
    ]

    footer_table = Table(
        [[summary_table, ttd_block]],
        colWidths=[doc.width * 0.52, doc.width * 0.48],
    )
    footer_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEABOVE", (0, 0), (-1, 0), 1.5, navy),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
            ]
        )
    )
    story.append(footer_table)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
