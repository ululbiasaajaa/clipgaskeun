# ClipGaskeun

Potong video panjang (stream, podcast, dll) jadi Shorts 9:16 dengan latar blur, subtitle otomatis, dan watermark opsional. Bisa dari file di komputermu **atau langsung dari link YouTube**. Jalan lokal, gratis, tanpa API berbayar.

## Yang dibutuhkan
- **Python 3.9+** ([python.org](https://www.python.org/downloads/), centang "Add Python to PATH" saat instal di Windows)
- **ffmpeg**
- **faster-whisper** (untuk subtitle otomatis)
- **yt-dlp** (hanya kalau mau memakai link YouTube)

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

### 4. Pasang yt-dlp (opsional, untuk link YouTube)
- **Windows:** `winget install yt-dlp`
- **macOS:** `brew install yt-dlp`
- **Semua sistem:** `pip install yt-dlp`

Cek berhasil: `yt-dlp --version`.

Siap dipakai.

## Pakai

### Dari file di komputer
Potong satu bagian:
```
python clipgaskeun.py video.mp4 --cut 4:09:41-4:10:17
```
Gabung beberapa bagian, pakai logo, tentukan nama hasil:
```
python clipgaskeun.py video.mp4 --cut 1:05-1:40 --cut 5:10-5:30 --logo clipgaskeun-watermark.png -o hasil.mp4
```
Hasilnya disimpan di sebelah video asli dengan nama `<nama>_short.mp4`, kecuali kamu tentukan lewat `-o`.

### Dari link YouTube
```
python clipgaskeun.py "https://www.youtube.com/watch?v=ID_VIDEO" --cut 4:09:41-4:10:17
```
- **Waktu di `--cut` adalah waktu di video YouTube-nya**, jadi tidak perlu menghitung apa-apa.
- Yang diunduh hanya bagian yang kamu minta (ditambah 3 detik cadangan di awal dan akhir), bukan seluruh video.
- **Selalu beri tanda kutip pada link** (`"..."`), terutama di PowerShell, karena karakter `&` dan `?` di link bisa memecah perintah.
- Hasilnya disimpan di folder tempatmu menjalankan perintah dengan nama `clipgaskeun_short.mp4`, kecuali kamu tentukan lewat `-o`.
- Boleh menggabung beberapa bagian dari satu link dengan `--cut` berulang.

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
python clipgaskeun.py "https://www.youtube.com/watch?v=ID_VIDEO" --cut 12:00-12:45 --lang id --model small
```

## Kalau ada masalah
- **`ffmpeg tidak ditemukan`**: ffmpeg belum terpasang atau belum ada di PATH. Ulangi langkah 1 dan buka terminal baru.
- **`faster-whisper belum terpasang`**: jalankan langkah 3.
- **`yt-dlp belum terpasang`**: jalankan langkah 4.
- **`yt-dlp gagal mengunduh`**: YouTube sering mengubah sistemnya, jadi perbarui yt-dlp dengan `pip install -U yt-dlp` atau `winget upgrade yt-dlp`, lalu coba lagi.
- **`0 kata`**: tidak ada ucapan di bagian itu, jadi video dirender tanpa subtitle.
- **Subtitle salah-salah kata**: coba model lebih besar, misalnya `--model medium`.

## Penting
Mengunduh dan memakai ulang konten orang lain bisa melanggar Ketentuan Layanan YouTube dan hak cipta kreatornya. Gunakan hanya untuk konten yang kamu punya haknya atau yang izin pemakaiannya jelas. Tanggung jawab pemakaian ada pada kamu.

## Lisensi
MIT, lihat file `LICENSE`.
