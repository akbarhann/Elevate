
# SPEC: Dashboard Web

Isi setiap bagian sebelum diserahkan ke coding agent. Bagian yang masih kosong wajib ditanyakan dulu ke user, jangan diasumsikan sendiri.

## 1. Konteks & Tujuan

- Nama project / dashboard:
- Tujuan utama dashboard ini (satu kalimat, apa keputusan yang diambil dari sini):
- Audiens pengguna (siapa yang buka, seberapa teknis mereka):
- Frekuensi penggunaan (dibuka tiap menit / harian / mingguan):
- Sifat data (real-time streaming / refresh berkala / statis-historis):

## 2. Sumber Data

- Sumber data (API, database, file CSV, scraping, dll):
- Format data mentah (contoh struktur JSON/tabel):
- Volume data (jumlah baris/record perkiraan):
- Update frequency data di backend:

## 3. Metrik & KPI Utama

Daftar metrik yang wajib tampil, urutkan dari paling penting:

| Prioritas | Nama Metrik | Definisi/Rumus | Format Tampilan | Target/Threshold (jika ada) |
| --------- | ----------- | -------------- | --------------- | --------------------------- |
| 1         |             |                |                 |                             |
| 2         |             |                |                 |                             |
| 3         |             |                |                 |                             |

Hero metric (satu angka/insight yang harus langsung terlihat dalam 3 detik pertama):

## 4. Struktur Halaman

- Jumlah halaman/tab (contoh: Overview, Detail, Settings):
- Navigasi utama (sidebar / top nav / tab horizontal):
- Filter global yang dibutuhkan (rentang tanggal, kategori, region, dll):

### Layout per halaman (isi per halaman yang dibutuhkan)

**Halaman: [nama]**

- Baris 1 (KPI cards): [daftar KPI]
- Baris 2 (chart utama): [jenis chart + data apa]
- Baris 3 (chart pendukung/tabel): [jenis + data apa]
- Interaksi yang dibutuhkan (klik chart untuk drill-down, hover tooltip, export data, dll):

## 5. Pemilihan Chart per Data

Isi berdasarkan tabel keputusan chart (rujuk ke rules pemilihan chart yang sudah ditetapkan):

| Data / Insight | Jenis Chart | Alasan |
| -------------- | ----------- | ------ |
|                |             |        |
|                |             |        |

## 6. Gaya Visual

- Rujukan gaya: Stripe Dashboard (clean enterprise) — lihat file `frontend-expert-no-ai-slop.md` untuk token lengkap
- Brand color (jika ada, override --accent-primary):
- Light mode / dark mode / keduanya:
- Logo/identitas visual yang harus disertakan:

## 7. Constraint Teknis

- Stack yang dipakai (React/Vue/plain HTML, library chart yang diizinkan):
- Harus jalan di device/browser apa saja:
- Batasan performa (jumlah data poin maksimal di-render, target load time):
- Autentikasi/akses (siapa saja yang boleh lihat, ada role berbeda atau tidak):
- Integrasi lain (export PDF/Excel, notifikasi, share link, dll):

## 8. Non-Goal / Di Luar Scope

Tulis eksplisit apa yang TIDAK perlu dibuat di versi ini, supaya coding agent tidak over-engineer:

## 9. Definisi Selesai (Definition of Done)

- [ ] Semua metrik di section 3 tampil dengan data benar
- [ ] Loading state, empty state, error state ada di setiap komponen data
- [ ] Responsif sampai breakpoint mobile
- [ ] Kontras warna lolos WCAG AA, chart tetap terbaca untuk colorblind
- [ ] Tidak ada item dari AI Slop Checklist yang muncul
- [ ] Sudah direview terhadap brief ini poin per poin sebelum diserahkan
