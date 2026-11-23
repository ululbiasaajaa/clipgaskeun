# ClipGaskeun

Potong video panjang (stream, podcast, dll) jadi Shorts 9:16 dengan latar blur, subtitle otomatis, dan watermark opsional. Jalan lokal di komputermu, gratis, tanpa API berbayar.

## Yang dibutuhkan
- **Python 3.9+** ([python.org](https://www.python.org/downloads/), centang "Add Python to PATH" saat instal di Windows)
- **ffmpeg**
- **faster-whisper** (untuk subtitle otomatis)

## Pasang, dari nol

### 1. Pasang ffmpeg
- **Windows:** buka PowerShell, jalankan `winget install ffmpeg`. Tutup lalu buka lagi terminalnya.
- **macOS:** `brew install ffmpeg`
- **Linux (Debian/Ubuntu):** `sudo apt install ffmpeg`

Cek berhasil: `ffmpeg -version` harus menampilkan nomor versi.

### 2. Unduh ClipGaskeun
```
git clone https://github.com/ululbiasaajaa/clipgaskeun.git
cd clipgaskeun
```
Tidak punya git? Klik tombol hijau **Code → Download ZIP** di halaman GitHub, ekstrak, lalu buka terminal di foldernya.

### 3. Pasang faster-whisper
```
pip install faster-whisper
```
(Di macOS/Linux, kalau `pip` tidak dikenali, pakai `pip3`.)

Siap dipakai.

## Pakai
Potong satu bagian:
```
python clipgaskeun.py video.mp4 --cut 4:09:41-4:10:17
```
Gabung beberapa bagian, pakai logo, tentukan nama hasil:
```
python clipgaskeun.py video.mp4 --cut 1:05-1:40 --cut 5:10-5:30 --logo clipgaskeun-watermark.png -o hasil.mp4
```
Hasilnya disimpan di sebelah video asli dengan nama `<nama>_short.mp4`, kecuali kamu tentukan lewat `-o`.

**Catatan pertama kali:** model Whisper diunduh otomatis (sekitar 500 MB), jadi langkah subtitle pertama akan lebih lama. Sesudahnya tidak perlu unduh lagi.

## Opsi
| Opsi | Fungsi |
|---|---|
| `--cut MULAI-SELESAI` | Rentang waktu (`1:05-1:40`). Boleh diulang, bagian-bagiannya digabung berurutan. |
| `-o, --out` | Nama file hasil. |
| `--lang` | Bahasa ucapan. Default `en`; untuk Indonesia pakai `id`. |
| `--model` | Model Whisper. Default `small.en` (khusus Inggris). Untuk bahasa lain pakai `small` atau `medium`. |
| `--no-subs` | Tanpa subtitle. |
| `--srt file.srt` | Pakai subtitle buatan sendiri (waktunya relatif ke awal hasil). |
| `--logo file.png` | Watermark PNG di pojok kiri atas. |
| `--logo-scale` | Ukuran logo (default `0.62`). |
| `--font`, `--font-size` | Font dan ukuran subtitle (default Poppins, 10). Kalau font tidak terpasang, ffmpeg memakai font bawaan. |

Contoh video berbahasa Indonesia:
```
python clipgaskeun.py podcast.mp4 --cut 12:00-12:45 --lang id --model small
```

## Kalau ada masalah
- **`ffmpeg tidak ditemukan`**: ffmpeg belum terpasang atau belum ada di PATH. Ulangi langkah 1 dan buka terminal baru.
- **`faster-whisper belum terpasang`**: jalankan langkah 3.
- **`0 kata`**: tidak ada ucapan di bagian itu, jadi video dirender tanpa subtitle.
- **Subtitle salah-salah kata**: coba model lebih besar, misalnya `--model medium`.

Hanya untuk file lokal. Pastikan kamu punya hak memakai konten yang diklip.

## Lisensi
MIT, lihat file `LICENSE`.
