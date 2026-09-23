# Rencana Perbaikan: Ekstraksi Teks Kosong pada `manhwa-extraction`

## 1. Ringkasan Masalah

Pipeline berhasil mengidentifikasi karakter dan menghasilkan `visual_summary` yang cukup detail (termasuk menyebut adanya "narrative text" di halaman), tetapi field `texts` selalu kosong (`[]`). Ini menunjukkan model **mengetahui ada teks di gambar tapi tidak mentranskripsikannya** — bukan kasus "model tidak melihat apa-apa".

Kemungkinan akar masalah (urutan dari paling mungkin):

1. Gambar di-*downscale* terlalu agresif sebelum dikirim ke model vision → teks kecil jadi tidak terbaca.
2. Prompt tidak cukup tegas memisahkan "transkripsi persis" (untuk `texts`) dari "ringkasan bebas" (untuk `visual_summary`).
3. Model vision lokal (via Ollama) punya kemampuan OCR lemah untuk teks stylized/bahasa non-Latin di dalam gambar komik.
4. Tidak ada tahap OCR khusus terpisah — semuanya dibebankan ke satu model vision-LLM sekaligus untuk membaca + menyusun struktur.

Karena saya belum bisa membuka isi repo langsung, rencana ini disusun sebagai **prosedur diagnosis + perbaikan bertahap**, bukan patch kode langsung. Setelah kamu share kode/prompt aktual, langkah-langkah ini bisa dipersempit.

---

## 2. Fase 1 — Diagnosis (lakukan dulu sebelum ubah apa pun)

- [x] Cek resolusi gambar input asli vs resolusi yang benar-benar dikirim ke model (banyak wrapper Ollama/vision otomatis resize ke ukuran kecil seperti 336px atau 448px).
- [ ] Ambil satu halaman yang gagal, crop manual bagian yang ada teksnya, lalu kirim **hanya crop itu** ke model dengan prompt sederhana ("baca teks di gambar ini"). Jika berhasil → masalah ada di ukuran/resolusi gambar full-page, bukan di model.
- [x] Cek log/response mentah dari Ollama (bukan hasil setelah di-parse ke JSON) — pastikan model benar-benar tidak pernah menyebut teks apa pun di output mentahnya, atau justru menyebutnya tapi hilang saat parsing ke schema.
- [x] Cek model yang dipakai: pastikan itu model **vision-capable** (mis. `llama3.2-vision`, `llava`, `qwen2-vl`) dan bukan model teks biasa yang menerima gambar tapi mengabaikannya.
- [x] Cek apakah prompt/schema mencontohkan (few-shot) bagaimana field `texts` seharusnya diisi. Field yang hanya dijelaskan lewat nama field saja ("texts") tanpa contoh isi sering diabaikan model.

---

## 3. Fase 2 — Perbaikan Prompt

- [x] Pisahkan instruksi secara eksplisit: *"Untuk setiap teks yang terlihat di gambar (dialog, narasi, SFX), transkripsikan PERSIS kata demi kata ke dalam array `texts`. Jangan parafrase. Jangan rangkum di sini — ringkasan taruh di `visual_summary`."*
- [x] Tambahkan definisi struktur tiap elemen `texts`, misalnya:
  ```json
  {
    "id": "text_1",
    "type": "narration | dialogue | sfx",
    "speaker": "char_1 | null",
    "content": "isi teks persis",
    "bbox": null
  }
  ```
- [x] Tambahkan **1 contoh few-shot lengkap** (input gambar contoh → output JSON contoh dengan `texts` terisi) di dalam prompt. Model lokal kecil jauh lebih patuh terhadap contoh konkret dibanding instruksi abstrak.
- [x] Set `temperature` rendah (0–0.2) khusus untuk task ekstraksi terstruktur, supaya model tidak "berimprovisasi" mengisi `visual_summary` dari tebakan gaya gambar.
- [x] Tambahkan instruksi eksplisit: jika tidak ada teks yang terbaca, model harus tetap eksplisit menyatakan itu, misalnya field debug `"ocr_confidence": "low"` — supaya kasus "kosong karena gagal baca" bisa dibedakan dari "kosong karena memang tidak ada teks".

---

## 4. Fase 3 — Perbaikan Pra-pemrosesan Gambar

- [x] Jangan kirim satu halaman manhwa utuh dalam resolusi tinggi ke model vision generalis — pecah dulu jadi per-panel (crop) menggunakan panel/bubble detector sederhana (mis. deteksi kontur/edge, atau tool seperti `manga-panel-extractor`).
- [x] Untuk tiap panel/crop yang mengandung teks, **upscale** dulu (2x–3x) sebelum dikirim ke model, khususnya untuk font kecil khas caption/narasi.
- [x] Pastikan proses resize di kode (PIL/OpenCV) tidak memaksa semua gambar ke ukuran persegi kecil sebelum encoding ke base64.
- [ ] Uji ulang halaman yang gagal dengan pipeline crop+upscale ini, bandingkan hasil `texts` sebelum/sesudah.

---

## 5. Fase 4 — Pisahkan OCR dari Reasoning (rekomendasi arsitektur jangka menengah)

Alih-alih membebankan satu model untuk "baca teks + susun JSON terstruktur" sekaligus, pecah jadi dua tahap:

1. **Tahap OCR** — pakai tool OCR khusus komik/manga:
   - `manga-ocr` (khusus teks Jepang di manga, cukup akurat untuk font komik)
   - `PaddleOCR` atau `EasyOCR` (lebih general, bisa untuk teks Latin/Indo)
   - Hasilnya: daftar teks mentah + koordinat bounding box per halaman.
2. **Tahap Reasoning (LLM/Ollama)** — model vision-LLM hanya bertugas: menghubungkan teks hasil OCR ke karakter yang bicara, menentukan jenis teks (dialog/narasi/SFX), dan menyusun `visual_summary`. Model tidak lagi harus "membaca" sendiri — cukup mencocokkan teks yang sudah diekstrak dengan konteks visual.

Ini biasanya jauh lebih andal daripada mengandalkan OCR bawaan vision-LLM lokal, yang memang lemah untuk teks kecil/stylized.

---

## 6. Fase 5 — Validasi & Regression Test

- [x] Siapkan 5–10 halaman contoh dengan variasi kepadatan teks (narasi panjang, dialog pendek, SFX saja, tanpa teks sama sekali) sebagai test set tetap.
- [ ] Jalankan pipeline sebelum dan sesudah perbaikan pada test set yang sama, bandingkan jumlah teks yang berhasil ditangkap.
- [x] Tambahkan assertion sederhana di kode: jika `visual_summary` menyebut indikasi teks (mis. mengandung kata seperti "narrative", "caption", "said") tapi `texts` kosong → tandai sebagai potential failure untuk di-review manual, alih-alih diam-diam lolos.

---

## 7. Checklist Ringkas (urutan eksekusi)

1. [ ] Diagnosis manual satu halaman (Fase 1)
2. [x] Revisi prompt + tambah few-shot example (Fase 2)
3. [ ] Uji ulang tanpa ubah pra-pemrosesan gambar — lihat apakah prompt saja cukup
4. [x] Jika masih gagal: perbaiki pra-pemrosesan gambar/crop+upscale (Fase 3)
5. [ ] Jika masih gagal juga: pisahkan OCR dari reasoning (Fase 4)
6. [ ] Validasi dengan test set tetap (Fase 5)

---

*Catatan: rencana ini disusun berdasarkan pola pada satu contoh output yang dibagikan, karena kode/prompt asli repo belum bisa diakses langsung. Kalau kamu share isi prompt template dan script pemanggilan Ollama-nya, saya bisa mempertajam rencana ini jadi patch konkret per baris kode.*

---

## 8. Status Eksekusi (2026-09-23)

Checkbox di atas yang dicentang sudah diimplementasikan di kode. Yang belum dicentang butuh model asli (`gemma4:31b-cloud`) dan halaman yang gagal. Semua tes unit memakai Ollama palsu (mock).

### Temuan diagnosis dari kode (Fase 1)

1. **Kemungkinan besar akar masalahnya: prompt tidak pernah menyebut nama key JSON.** `page_extraction.txt` cuma berisi daftar "visible text, text type, …", dan Ollama dipanggil dengan `format="json"` (JSON bebas). Model bebas menjawab dengan key seperti `visible_text` atau `dialogue`, padahal `ValidationService.normalize_dict` hanya membaca `texts`/`t`. Akibatnya teks dibuang diam-diam. Gejalanya cocok dengan laporan: `characters` dan `visual_summary` terisi (nama key-nya kebetulan cocok), `texts` selalu `[]`.
2. **Tidak ada resize di kode.** Mode `original` mengirim halaman dalam resolusi penuh, tetapi sebagai satu gambar. Encoder vision model sendiri yang mengecilkan gambar ke budget tetapnya, jadi teks kecil di strip yang tinggi hilang (Fase 3).
3. **Kasus "teks kosong" tidak pernah dideteksi.** `detect_suspicious` tidak punya cek teks kosong, dan percobaan terakhir diterima tanpa pemeriksaan.
4. Temperature default sudah `0`. `OLLAMA_VISUAL_TOKENS` ada di config tetapi tidak pernah dikirim ke Ollama (nilainya tidak berpengaruh).

### Yang diimplementasikan

| Fase | Perubahan | Lokasi |
|---|---|---|
| 1 | Script diagnosis: ukuran gambar yang dikirim, cek kapabilitas `vision`, jawaban mentah vs teks hasil parsing, uji crop dengan prompt sederhana, mode tiled, dan mode JSON lama (`--legacy-json`) yang menunjukkan key apa yang dipakai model. Hasilnya berupa kesimpulan dan laporan JSON. | `backend/scripts/diagnose_text_extraction.py`, `OllamaService.show_model/supports_vision` |
| 1 | Log per percobaan: mode dan ukuran tiap gambar yang dikirim | `ExtractionService.extract_page` |
| 2 | Prompt dengan struktur JSON eksplisit, pemisahan TRANSCRIBE vs DESCRIBE, satu contoh few-shot (berupa teks, bukan gambar, supaya hemat token), format bbox, `has_text`, dan `ocr_confidence` | `prompts/page_extraction.txt`, `page_retry.txt`/`page_reply.txt` |
| 2 | JSON schema dikirim sebagai `format` Ollama (structured output), dengan `has_text` di urutan pertama. Kalau host menolak schema (HTTP 400), otomatis jatuh ke mode `json` biasa. | `build_page_output_schema`, `EXTRACTION_STRUCTURED_OUTPUT` |
| 2 | Temperature ekstraksi dibatasi maksimal `0.2` | `EXTRACTION_MAX_TEMPERATURE` |
| 2 | Alias key sebagai pengaman: `visible_text`, `dialogue`, `content`, `text_type`, string polos, dll. Speaker/target `"unknown"`/`"null"` dijadikan `null`. | `validation_service.py` |
| 3 | Mode `tiled`: halaman tinggi dipotong di gutter (baris paling "tenang", dekat posisi ideal, tanpa overlap), maksimal `EXTRACTION_TILE_MAX_SEGMENTS` segmen, lalu di-upscale sampai lebar `EXTRACTION_TILE_MIN_WIDTH` (maksimal 3x). Semua segmen dikirim dalam **satu** request; bbox per segmen dipetakan kembali ke koordinat halaman (0–1000). | `ImageService.split_into_segments`, `ImageSegment` |
| 3 | Eskalasi retry: pada percobaan ke-3, kalau masalahnya teks yang terlewat, otomatis pindah ke `tiled`. Percobaan ke-2 memberi tahu model apa yang salah. | `select_preprocess_mode`, `build_retry_hint` |
| 5 | Deteksi teks hilang: `has_text=true` atau ringkasan menyebut "narrative/caption/said/bubble/…" padahal `texts` kosong, teks tanpa isi, `ocr_confidence=low`, atau ada key yang tidak dikenali. Kondisi ini memicu retry. Kalau masih terjadi di percobaan terakhir, hasil tetap disimpan tetapi diberi `review_flags` dan status halaman menjadi `manual_review`. Menyimpan koreksi manusia menghapus flag tersebut. | `detect_missing_text`, `chapter_service.py`, UI |
| 5 | Test set tetap: 8 halaman sintetis (narasi panjang, dialog pendek, SFX saja, tanpa teks, teks kecil, jendela sistem, strip tinggi 720x4200, campuran) beserta ground truth. Benchmark sekarang menghitung `avg_text_recall`, `missed_text_pages`, `hallucinated_text_pages`, dan `flagged_pages`, lalu merekomendasikan mode berdasarkan recall. | `tests/fixtures/regression/`, `tests/fixtures/expected.json`, `benchmark_service.py` |

Default `EXTRACTION_PREPROCESS_MODE` tetap `original` sampai benchmark dengan model asli membuktikan `tiled` lebih baik (PRD §15). Mode `tiled` tetap dipakai otomatis sebagai eskalasi saat teks terlewat.

### Fase 4: sengaja belum dikerjakan

Memisahkan OCR ke `manga-ocr`/`PaddleOCR`/`EasyOCR` bertentangan dengan arsitektur yang berlaku ("Ollama `gemma4:31b-cloud` adalah satu-satunya engine vision/OCR", lihat README, `docs/ARCHITECTURE.md`, dan tabel guardrail di `docs/TASKS.md`). Rencana ini juga hanya menjalankan Fase 4 kalau Fase 2–3 masih gagal, dan itu baru bisa diketahui setelah dijalankan dengan model asli. Ada dua opsi kalau nanti diperlukan: (a) dua tahap dengan Gemma saja (pass OCR per segmen, lalu pass reasoning), atau (b) menambah engine OCR terpisah, yang berarti mengubah keputusan arsitektur.

### Langkah berikutnya (butuh model asli)

```bash
cd backend
# 1. Diagnosis satu halaman yang gagal
python scripts/diagnose_text_extraction.py path/ke/halaman-gagal.png --legacy-json
# 2. Bandingkan mode pada test set tetap (butuh backend berjalan)
curl -X POST localhost:8000/benchmark/run -H "Content-Type: application/json" -d '{"modes": ["original", "tiled"]}'
```

Tambahkan 5–10 halaman manhwa **asli** beserta teksnya ke folder baru, misalnya `tests/fixtures/real/`, dengan `expected.json`-nya sendiri (format: `{"page-001.png": {"texts": ["..."]}}`). Benchmark membaca manifest per subfolder. Jangan taruh di `regression/`, karena `generate_fixtures.py` menulis ulang `expected.json` di sana. Halaman sintetis hanya batas bawah. Kalau `tiled` terbukti lebih baik, set `EXTRACTION_PREPROCESS_MODE=tiled` di `backend/.env`.
