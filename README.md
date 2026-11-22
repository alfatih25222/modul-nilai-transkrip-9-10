# Modul Nilai & Transkrip Akademik

Sistem manajemen nilai mahasiswa, perhitungan IPS dan IPK, pencatatan riwayat perubahan nilai (*audit trail*), serta pembuatan transkrip akademik (HTML dan PDF) berbasis **FastAPI**, **SQLAlchemy**, **Jinja2**, dan **ReportLab**.

## Fitur Utama
- **Manajemen Nilai & Validasi Presensi:** Input dan pembaruan nilai huruf (`A`–`E`) dengan validasi kehadiran minimal `75%`.
- **Perhitungan IPS & IPK:** Menghitung IPS per semester dan IPK kumulatif dengan aturan pengambilan nilai tertinggi untuk mata kuliah yang diulang serta nilai `0.0` jika belum ada nilai lulus.
- **Audit Trail Nilai:** Mencatat perubahan nilai ke tabel `grade_history` melalui *trigger* SQLite dan menampilkannya lewat *view* `v_student_grade_history`.
- **Transkrip HTML & PDF:** Menampilkan dan mengunduh transkrip akademik lengkap dengan logo kampus, biodata mahasiswa, rincian per semester, ringkasan IPK dan predikat kelulusan, serta tanda tangan dekan.

## Menjalankan Aplikasi
```bash
uvicorn app.main:app --reload