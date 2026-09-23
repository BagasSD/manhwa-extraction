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

- [ ] Cek resolusi gambar input asli vs resolusi yang benar-benar dikirim ke model (banyak wrapper Ollama/vision otomatis resize ke ukuran kecil seperti 336px atau 448px).
- [ ] Ambil satu halaman yang gagal, crop manual bagian yang ada teksnya, lalu kirim **hanya crop itu** ke model dengan prompt sederhana ("baca teks di gambar ini"). Jika berhasil → masalah ada di ukuran/resolusi gambar full-page, bukan di model.
- [ ] Cek log/response mentah dari Ollama (bukan hasil setelah di-parse ke JSON) — pastikan model benar-benar tidak pernah menyebut teks apa pun di output mentahnya, atau justru menyebutnya tapi hilang saat parsing ke schema.
- [ ] Cek model yang dipakai: pastikan itu model **vision-capable** (mis. `llama3.2-vision`, `llava`, `qwen2-vl`) dan bukan model teks biasa yang menerima gambar tapi mengabaikannya.
- [ ] Cek apakah prompt/schema mencontohkan (few-shot) bagaimana field `texts` seharusnya diisi. Field yang hanya dijelaskan lewat nama field saja ("texts") tanpa contoh isi sering diabaikan model.

---

## 3. Fase 2 — Perbaikan Prompt

- [ ] Pisahkan instruksi secara eksplisit: *"Untuk setiap teks yang terlihat di gambar (dialog, narasi, SFX), transkripsikan PERSIS kata demi kata ke dalam array `texts`. Jangan parafrase. Jangan rangkum di sini — ringkasan taruh di `visual_summary`."*
- [ ] Tambahkan definisi struktur tiap elemen `texts`, misalnya:
  ```json
  {
    "id": "text_1",
    "type": "narration | dialogue | sfx",
    "speaker": "char_1 | null",
    "content": "isi teks persis",
    "bbox": null
  }
  ```
- [ ] Tambahkan **1 contoh few-shot lengkap** (input gambar contoh → output JSON contoh dengan `texts` terisi) di dalam prompt. Model lokal kecil jauh lebih patuh terhadap contoh konkret dibanding instruksi abstrak.
- [ ] Set `temperature` rendah (0–0.2) khusus untuk task ekstraksi terstruktur, supaya model tidak "berimprovisasi" mengisi `visual_summary` dari tebakan gaya gambar.
- [ ] Tambahkan instruksi eksplisit: jika tidak ada teks yang terbaca, model harus tetap eksplisit menyatakan itu, misalnya field debug `"ocr_confidence": "low"` — supaya kasus "kosong karena gagal baca" bisa dibedakan dari "kosong karena memang tidak ada teks".

---

## 4. Fase 3 — Perbaikan Pra-pemrosesan Gambar

- [ ] Jangan kirim satu halaman manhwa utuh dalam resolusi tinggi ke model vision generalis — pecah dulu jadi per-panel (crop) menggunakan panel/bubble detector sederhana (mis. deteksi kontur/edge, atau tool seperti `manga-panel-extractor`).
- [ ] Untuk tiap panel/crop yang mengandung teks, **upscale** dulu (2x–3x) sebelum dikirim ke model, khususnya untuk font kecil khas caption/narasi.
- [ ] Pastikan proses resize di kode (PIL/OpenCV) tidak memaksa semua gambar ke ukuran persegi kecil sebelum encoding ke base64.
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

- [ ] Siapkan 5–10 halaman contoh dengan variasi kepadatan teks (narasi panjang, dialog pendek, SFX saja, tanpa teks sama sekali) sebagai test set tetap.
- [ ] Jalankan pipeline sebelum dan sesudah perbaikan pada test set yang sama, bandingkan jumlah teks yang berhasil ditangkap.
- [ ] Tambahkan assertion sederhana di kode: jika `visual_summary` menyebut indikasi teks (mis. mengandung kata seperti "narrative", "caption", "said") tapi `texts` kosong → tandai sebagai potential failure untuk di-review manual, alih-alih diam-diam lolos.

---

## 7. Checklist Ringkas (urutan eksekusi)

1. [ ] Diagnosis manual satu halaman (Fase 1)
2. [ ] Revisi prompt + tambah few-shot example (Fase 2)
3. [ ] Uji ulang tanpa ubah pra-pemrosesan gambar — lihat apakah prompt saja cukup
4. [ ] Jika masih gagal: perbaiki pra-pemrosesan gambar/crop+upscale (Fase 3)
5. [ ] Jika masih gagal juga: pisahkan OCR dari reasoning (Fase 4)
6. [ ] Validasi dengan test set tetap (Fase 5)

---

*Catatan: rencana ini disusun berdasarkan pola pada satu contoh output yang dibagikan, karena kode/prompt asli repo belum bisa diakses langsung. Kalau kamu share isi prompt template dan script pemanggilan Ollama-nya, saya bisa mempertajam rencana ini jadi patch konkret per baris kode.*
