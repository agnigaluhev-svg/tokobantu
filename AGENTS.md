# AGENTS.md — TokoBantu

## Tentang project
TokoBantu adalah agent AI customer service untuk toko online Shopify
(development store). Pelanggan bertanya lewat chat, agent memakai tool
untuk mengambil data produk dan pesanan, lalu menjawab. Kasus yang tidak
bisa ditangani dieskalasi ke staf manusia lewat tiket.

## Tech stack
- Python 3.13, FastAPI, uvicorn
- httpx untuk memanggil Shopify Admin GraphQL API
- anthropic SDK (Claude API) dengan tool calling
- python-dotenv untuk membaca rahasia dari .env
- SQLite saat development (percakapan dan tiket)
- Virtual environment ada di .venv

## Aturan keamanan (wajib)
- JANGAN membaca, mencetak, atau mengubah file .env.
- JANGAN menaruh API key, token, atau secret di dalam kode.
  Semua rahasia dibaca dari environment variable.
- Jangan menjalankan git commit atau git push. Itu dikerjakan pemilik project.
- Semua tool yang terhubung ke Shopify bersifat READ-ONLY.
  Jangan membuat tool yang mengubah, membatalkan, atau menghapus pesanan.
- get_order_status wajib memverifikasi email pelanggan sebelum
  mengembalikan data pesanan.

## Aturan kode
- Nama variabel, fungsi, dan komentar kode memakai bahasa Inggris.
- Jawaban chatbot ke pelanggan memakai bahasa Indonesia yang ramah dan sopan.
- Beri type hints dan docstring singkat pada setiap fungsi.
- Pisahkan tanggung jawab: tool di app/tools/, klien Shopify di
  app/shopify_client.py, loop agent di app/agent.py.
- Tambahkan dependency baru hanya jika perlu, dan catat di requirements.txt.

## Cara bekerja dengan pemilik project
- Pemilik project sedang belajar. Kerjakan SATU langkah kecil per tugas.
- Setelah menulis kode, jelaskan dalam bahasa Indonesia sederhana
  apa fungsi tiap bagian dan mengapa dibuat begitu.
- Jika ada pilihan desain, sebutkan opsinya singkat sebelum memilih.
- Jangan membuat file atau fitur di luar yang diminta.