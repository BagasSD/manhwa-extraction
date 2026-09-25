# Plan Implementasi: Panel Detection & Manual Crop Review

## 0. Prinsip Desain Utama

Dua pipeline dipisah total — **tidak saling bergantung secara eksekusi**, hanya berbagi sumber gambar yang sama:

| | **Extract Context** (fitur utama, sudah ada) | **Extract Image** (fitur baru) |
|---|---|---|
| Tujuan | Teks, karakter, ekspresi, scene | Panel/gambar siap pakai untuk CapCut |
| Engine | Gemma via Ollama Cloud | OpenCV/Pillow — 100% lokal |
| Trigger | CTA "Extract Context" | CTA "Extract Image" |
| Biaya | Token cloud per halaman | Zero token, murni komputasi lokal |
| Output | `page-{n}.json` (texts, characters, scene) | `page-{n}.panels.json` → `extractedImage/` |
| Bisa jalan tanpa yang lain? | Ya, independen | Ya, independen (hanya butuh gambar mentah, tidak butuh hasil context extraction) |

Kenapa dipisah: supaya user tidak bingung mana yang "mahal" (pakai cloud) dan mana yang "gratis" (lokal), dan supaya user bisa re-run salah satu tanpa mengulang yang lain (mis. re-crop panel tanpa re-extract teks, atau sebaliknya).

---

## 1. Perubahan Schema

### 1.1 Model baru: `Panel`
Ditambahkan ke `page_context.py`, terpisah dari `TextRegion` dan `Character`:

```python
class Panel(BaseModel):
    panel_index: int
    bbox: list[int]  # [ymin, xmin, ymax, xmax]
    status: Literal["auto_detected", "reviewed"] = "auto_detected"
    image_path: str | None = None  # diisi setelah crop final dijalankan
```

### 1.2 File penyimpanan terpisah
- `data/results/{chapter_id}/page-{n}.json` → tetap khusus hasil context extraction (tidak diubah).
- `data/results/{chapter_id}/page-{n}.panels.json` → **file baru**, khusus data panel. Dipisah fisik biar dua proses tidak saling menimpa atau saling menunggu.

### 1.3 Status level chapter
Tambah tracking status per chapter untuk masing-masing pipeline, misalnya di `chapter_service.py`:

```python
{
  "context_status": "not_started" | "extracting" | "done",
  "image_status": "not_started" | "detecting" | "reviewing" | "cropped"
}
```

Dua field independen — chapter bisa saja `context_status: done` tapi `image_status: not_started`, atau sebaliknya.

---

## 2. Backend

### 2.1 Endpoint baru (terpisah dari endpoint context extraction yang sudah ada)

| Endpoint | Fungsi |
|---|---|
| `POST /chapters/{id}/detect-panels` | Jalankan auto-detect panel (OpenCV) untuk semua halaman di chapter, simpan sebagai `panels.json` dengan status `auto_detected` |
| `GET /chapters/{id}/pages/{n}/panels` | Ambil data panel satu halaman untuk ditampilkan di review UI |
| `PUT /chapters/{id}/pages/{n}/panels` | Simpan hasil adjust manual (resize/geser/tambah/hapus box), update status jadi `reviewed` |
| `POST /chapters/{id}/crop-all` | Baca semua panel berstatus `reviewed` di seluruh chapter, jalankan crop, simpan ke `extractedImage/` |

Endpoint ini **tidak menyentuh** service yang dipakai context extraction (`ollama_service.py`, `chapter_context_service.py`) sama sekali — murni jalur baru.

### 2.2 Modul baru
- `panel_service.py` (baru) — isi:
  - `detect_panels(image) -> list[Panel]` — projection profile / whitespace-gap scanning via OpenCV.
  - `crop_region(image, bbox) -> Image` — Pillow/OpenCV slicing.
  - `crop_all_reviewed(chapter_id)` — iterasi semua halaman, crop tiap panel `reviewed`, simpan dengan nama `page{n}-chapter{chapter_id}-crop{i}.png` ke `data/extractedImage/{chapter_id}/`.

### 2.3 Guard sebelum crop-all
`crop-all` harus cek dulu: kalau masih ada panel berstatus `auto_detected` (belum direview) di halaman manapun dalam chapter itu → tolak jalankan, balikan response berisi daftar halaman yang belum selesai direview. Ini mencegah crop jalan dari box yang belum divalidasi manusia.

---

## 3. Frontend

### 3.1 Halaman Chapter: dua CTA terpisah dan jelas

```
┌─────────────────────────────────────────────┐
│  Chapter 12                                  │
│                                               │
│  [ Extract Context ]   ← fitur utama         │
│  Status: ✅ Done (48/48 halaman)             │
│                                               │
│  [ Extract Image ]     ← fitur baru           │
│  Status: ⏳ 12/48 halaman direview            │
└─────────────────────────────────────────────┘
```

Dua tombol, dua progress indicator, dua alur kerja — tidak digabung jadi satu tombol "Extract All" supaya user selalu sadar mana proses yang dijalankan.

### 3.2 Alur "Extract Image" (CTA kedua)

1. Klik **Extract Image** → trigger `detect-panels`, tampilkan progress bar (auto-detect jalan cepat, tapi tetap tampilkan progress per halaman biar user tahu sedang proses).
2. Setelah selesai → masuk ke **Panel Review View** (halaman baru/tab baru, terpisah dari review UI teks yang sudah ada di `Chapter.tsx`).
3. Di Panel Review View:
   - Navigasi per halaman (mirip pola review teks yang sudah ada).
   - Overlay box dari hasil auto-detect, sekarang **interaktif**: drag untuk pindah, drag handle sudut untuk resize, tombol "+" untuk tambah box manual, tombol hapus per box.
   - Tiap perubahan pada satu halaman → simpan via `PUT .../panels`, status halaman itu jadi `reviewed`.
4. Tombol **"Crop All"** hanya aktif/enabled kalau semua halaman di chapter sudah berstatus `reviewed`. Kalau belum, tombol disabled dengan tooltip "X halaman belum direview".
5. Klik **Crop All** → trigger `crop-all`, tampilkan hasil akhir: jumlah panel ter-crop + link ke folder `extractedImage/`.

### 3.3 Komponen baru
- `PanelReviewView.tsx` (baru, terpisah dari `Chapter.tsx` yang menangani teks) — reuse pola layout yang sama biar konsisten.
- `PanelOverlay.tsx` (extend dari `RegionOverlay.tsx`, atau buat baru kalau butuh interaktivitas berbeda) — pakai library siap pakai (`react-rnd` atau `react-moveable`) untuk drag/resize, jangan bangun logic drag dari nol.

---

## 4. Urutan Pengerjaan (Fase)

### Fase 1 — Backend core (tanpa UI dulu)
- [x] Buat `panel_service.py`: `detect_panels()` dan `crop_region()`.
- [x] Test manual via script/CLI di beberapa halaman contoh, cek visual hasil bbox (bisa gambar box di atas image pakai PIL, save sebagai file, buka manual) — validasi akurasi sebelum lanjut ke integrasi.
- [x] Tambah schema `Panel` ke `page_context.py`.
- [x] Buat 4 endpoint baru di atas.

### Fase 2 — Frontend review (baca-tulis, belum ada crop)
- [x] Buat `PanelReviewView.tsx` dengan navigasi per halaman.
- [x] Integrasi library drag/resize, render box dari hasil auto-detect.
- [x] Sambungkan ke endpoint `GET`/`PUT panels` — pastikan perubahan tersimpan & status berubah jadi `reviewed`.

### Fase 3 — CTA & status di halaman Chapter
- [x] Tambah dua CTA terpisah + progress indicator masing-masing di `Chapter.tsx` (atau parent page-nya).
- [x] Tambah field `context_status`/`image_status` di `chapter_service.py`.

### Fase 4 — Crop final
- [x] Implementasi `crop_all_reviewed()` + guard status.
- [x] Sambungkan tombol "Crop All" di frontend, termasuk disabled-state & tooltip saat belum semua direview.
- [x] Test end-to-end satu chapter penuh: detect → review semua halaman → crop all → cek isi `extractedImage/`.

### Fase 5 — Validasi
- [x] Uji di chapter dengan variasi kasus: panel jelas bergap, panel full-bleed nyambung, halaman nyaris tanpa panel (mis. splash art satu gambar penuh).
- [x] Cek penamaan file `page{n}-chapter{id}-crop{i}.png` konsisten dan tidak collision antar chapter.

---

## 5. Yang Sengaja Tidak Dikerjakan Dulu (di luar scope)

- Tidak ada auto-matching panel ke naskah/VO (itu opsi A yang sudah kamu tolak).
- Tidak ada `dummy.png` fallback (tidak relevan untuk alur manual-review ini).
- Tidak menyentuh/mengubah pipeline context extraction yang sudah jalan sama sekali.

---

## 6. Status Implementasi (2026-09-25)

Semua fase di atas sudah dikerjakan. Pengujian end-to-end dijalankan pada salinan `chapter-1` (17 halaman strip 800×~14000 px): deteksi → review → Crop All menghasilkan 79 PNG. Data asli di `data/` tidak disentuh.

### Penyesuaian terhadap plan

| Plan | Implementasi | Alasan |
|---|---|---|
| `data/results/{id}/page-{n}.panels.json` | `data/results/{id}/panels/page-{n}.panels.json` | `character_service` dan `chapter_context_service` membaca semua `page-*.json` di folder chapter. Di lokasi versi plan, data panel akan terbaca sebagai page context. Sub-folder menjaga kedua pipeline tetap terpisah tanpa mengubah service context. |
| 4 endpoint | 4 endpoint + `GET /detect-panels/status` + `GET /extracted-images[/{file}]` | Status dibutuhkan untuk progress bar per halaman. Listing/file dipakai sebagai "link ke folder" di browser, karena browser tidak bisa membuka path lokal. |
| `page{n}-chapter{id}-crop{i}.png` | `page001-chapter{id}-crop01.png` (zero-padded) | Supaya urutan file benar saat diimpor/diurutkan (tanpa padding, `page10` muncul sebelum `page2`). |
| Status per panel | Status per panel + status per halaman (`status`, `cropped_at`) | Halaman tanpa panel (mis. halaman teks saja) tetap bisa ditandai reviewed. Crop yang sudah basi (box diubah setelah crop) terdeteksi. |

### Detail yang perlu diketahui

- **Deteksi** (`panel_service.detect_panels`): XY-cut pada baris/kolom gutter yang seragam. Blok yang **hanya teks** (kotak narasi, bubble, caption di antara panel) dibuang otomatis berdasarkan entropi histogram + kontras. Ambang ini diukur dari halaman asli: teks ≤ 2.4 bit, art ≥ 2.9 bit. Art yang sangat gelap tetap terdeteksi. Waktunya ~0.6 detik per halaman strip.
- **Keterbatasan**: panel yang hanya dibatasi garis bingkai 1–2 px di atas latar datar bisa terpangkas ke art-nya. Panel yang bersambung tanpa gutter tergabung jadi satu box. Keduanya diperbaiki saat review (drag/resize/tambah box).
- **Re-detect** tidak pernah menimpa halaman yang sudah direview, kecuali lewat tombol "↺ Auto-detect page" (dengan konfirmasi).
- **Crop All** menolak (HTTP 409 + daftar halaman) selama masih ada halaman yang belum direview. Crop lama chapter itu dihapus dulu, supaya box yang sudah dihapus tidak meninggalkan file basi. PNG tetap lossless (`compress_level=1`, ~3× lebih cepat dari default).
- **Hapus halaman** ikut menggeser file panel. Halaman yang bergeser perlu di-crop ulang karena nomor halaman ada di nama file.
- **Preview manual**: `python scripts/preview_panels.py <folder halaman>` (dari `backend/`) menyimpan gambar dengan box bernomor untuk dicek secara visual.
