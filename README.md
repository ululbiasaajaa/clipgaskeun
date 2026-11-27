# ClipGaskeun

**Bahasa Indonesia** · [English](README.en.md)

Potong video panjang (stream, podcast, dll) jadi Shorts 9:16 dengan latar blur, subtitle otomatis, dan watermark opsional. Bisa dari file di komputermu **atau langsung dari link YouTube**. Jalan lokal, gratis, tanpa API berbayar.

![Sebelum 16:9, sesudah 9:16 dengan latar blur, subtitle otomatis, dan watermark](docs/demo.gif)

*Contoh di atas: rekaman layar berbahasa Indonesia, diproses dengan satu perintah. Bahasa dideteksi otomatis.*

## Yang dibutuhkan
- **ffmpeg** (semua cara pasang)
- **Deno** (hanya untuk link YouTube): dipakai yt-dlp menembus sistem YouTube. Windows: `winget install DenoLand.Deno`, macOS: `brew install deno`.
- **Python 3.10+** ([python.org](https://www.python.org/downloads/), centang "Add Python to PATH" saat instal di Windows). *Tidak perlu* kalau memakai versi `.exe` Windows.
- faster-whisper (subtitle), yt-dlp (link YouTube), dan rich (tampilan terminal) ikut terpasang otomatis di versi `.exe` maupun cara pasang cepat.

## Paling gampang (Windows): versi .exe, tanpa Python
1. Pasang ffmpeg: buka PowerShell, jalankan `winget install ffmpeg` (untuk link YouTube, tambah `winget install DenoLand.Deno`). Tutup lalu buka lagi terminalnya.
2. Unduh **`clipgaskeun-windows.zip`** dari halaman [Releases](https://github.com/ululbiasaajaa/clipgaskeun/releases/latest), lalu ekstrak.
   (Mau memastikan filenya asli? Catatan rilis memuat **SHA256**-nya. Cocokkan dengan `Get-FileHash clipgaskeun-windows.zip -Algorithm SHA256` di PowerShell. Dengan GitHub CLI: `gh attestation verify clipgaskeun-windows.zip --repo ululbiasaajaa/clipgaskeun`.)
3. Buka folder `clipgaskeun` hasil ekstrak. Klik **kolom alamat** File Explorer (yang berisi path folder, bukan kotak Search), tekan **Ctrl + A** supaya path-nya ter-blok, ketik `cmd`, lalu Enter. Terminal terbuka di folder itu.
   Cara lain: buka Command Prompt dari menu Start, lalu `cd /d C:\lokasi\folder\clipgaskeun`.
4. Pakai seperti contoh di bawah, dengan `clipgaskeun.exe` di depan:
   ```
   clipgaskeun.exe D:\Video\stream.mp4 --cut 1:05-1:40 --preset tiktok
   clipgaskeun.exe "https://www.youtube.com/watch?v=ID_VIDEO" --auto
   ```
Kalau `clipgaskeun.exe` diklik dua kali, muncul petunjuk singkat dan hasil cek kelengkapan. Programnya sendiri dijalankan lewat terminal.

Kalau YouTube tiba-tiba gagal diunduh, biasanya yt-dlp di dalam paket sudah kedaluwarsa. Pasang yt-dlp terpisah (`winget install yt-dlp`, perbarui dengan `winget upgrade yt-dlp`). ClipGaskeun otomatis memakai yt-dlp yang terpasang di sistem, jadi kamu tidak perlu menunggu versi `.exe` baru.

## Pasang (semua sistem, lewat Python)

### 1. Pasang ffmpeg
- **Windows:** buka PowerShell, jalankan `winget install ffmpeg`. Tutup lalu buka lagi terminalnya.
- **macOS:** `brew install ffmpeg`
- **Linux (Debian/Ubuntu):** `sudo apt install ffmpeg`

Cek berhasil: `ffmpeg -version` harus menampilkan nomor versi.

### 2a. Pasang cepat (disarankan): satu perintah lewat pipx
```
pip install pipx
pipx ensurepath
```
Tutup lalu buka lagi terminal, kemudian:
```
pipx install git+https://github.com/ululbiasaajaa/clipgaskeun.git
```
Belum punya git? Pakai ini sebagai gantinya:
```
pipx install https://github.com/ululbiasaajaa/clipgaskeun/archive/refs/heads/main.zip
```
Setelah itu perintah `clipgaskeun` bisa dipakai dari folder mana saja. Memperbarui ke versi terbaru: `pipx upgrade clipgaskeun`.

### 2b. Atau cara manual (unduh foldernya)
```
git clone https://github.com/ululbiasaajaa/clipgaskeun.git
cd clipgaskeun
pip install -r requirements.txt
```
Dengan cara ini, ganti `clipgaskeun` di semua contoh dengan `python clipgaskeun.py`.

### 3. Cek kelengkapan
```
clipgaskeun --cek
```
Muncul tabel berisi apa yang sudah terpasang dan cara memasang yang belum.

## Pakai

**Format waktu di `--cut`:** detik (`90`), menit:detik (`1:30`), atau jam:menit:detik (`4:09:41`). Pecahan detik boleh (`1:30.5`). Pisahkan awal dan akhir dengan tanda minus: `1:05-1:40`. Menit dan detik setelah titik dua harus 00–59, dan tiap bagian minimal 0,5 detik.

> **Bahasa video dideteksi otomatis** (Indonesia, Inggris, dan lainnya). Kalau terdeteksi salah, ClipGaskeun memberi tahu di terminal; ulangi dengan `--lang id` (Indonesia) atau `--lang en` (Inggris).

### Dari file di komputer
Potong satu bagian:
```
clipgaskeun video.mp4 --cut 4:09:41-4:10:17
```
Gabung beberapa bagian, pakai preset TikTok dan logo, tentukan nama hasil:
```
clipgaskeun video.mp4 --cut 1:05-1:40 --cut 5:10-5:30 --preset tiktok --logo clipgaskeun-watermark.png -o hasil.mp4
```
Hasilnya disimpan **di folder yang sama dengan video asli**, bernama `<nama>_short.mp4`.

### Dari link YouTube
```
clipgaskeun "https://www.youtube.com/watch?v=ID_VIDEO" --cut 4:09:41-4:10:17
```
- **Waktu di `--cut` adalah waktu di video YouTube-nya**, jadi tidak perlu menghitung apa-apa.
- Yang diunduh hanya bagian yang kamu minta (ditambah 3 detik cadangan di awal dan akhir), bukan seluruh video.
- **Selalu beri tanda kutip pada link** (`"..."`), terutama di PowerShell, karena karakter `&` dan `?` di link bisa memecah perintah.
- Hasilnya disimpan **di folder tempatmu menjalankan perintah**, bernama `clipgaskeun_short.mp4`.
- Boleh menggabung beberapa bagian dari satu link dengan `--cut` berulang.

### Cari momen seru otomatis (`--auto`)
Tidak tahu menit berapa yang seru? Biarkan ClipGaskeun mencarikan:
```
clipgaskeun "https://www.youtube.com/watch?v=ID_VIDEO" --auto
clipgaskeun stream.mp4 --auto --preset tiktok
```
Muncul tabel 5 kandidat berisi rentang waktu, skor, alasan, dan cuplikan kalimat pertamanya. Ketik nomornya (`1`, atau `1,3` untuk beberapa sekaligus). Tiap nomor jadi satu Short terpisah (`<nama>_auto1.mp4`, `_auto3.mp4`, ...).

Cara mencarinya, semuanya lokal dan gratis:
- **Link YouTube:** memakai data **Most Replayed** (bagian yang paling sering diputar ulang penonton), dibaca tanpa mengunduh videonya. Lalu untuk tiap kandidat, hanya *suaranya* yang diunduh untuk mencari potongan paling pas.
- **File di komputer, atau video tanpa data Most Replayed:** mencari bagian yang suaranya paling memuncak (tawa, teriak, heboh) dibanding biasanya di video itu.
- Tiap kandidat lalu dinilai ulang dengan **kepadatan obrolan** dari transkrip singkat, dan awal-akhirnya digeser ke **jeda kalimat** supaya tidak terpotong di tengah omongan.

Ini perkiraan, bukan jaminan: skor tinggi berarti "layak dicek dulu". Tonton cuplikannya sebelum diunggah.

| Opsi | Fungsi |
|---|---|
| `--auto-len 45` | Panjang tiap momen, 15–90 detik (default 45). |
| `--auto-n 5` | Jumlah kandidat, 1–10 (default 5). |
| `--pick 1,3` | Langsung render nomor itu tanpa ditanya. |
| `--auto-cepat` | Lewati penilaian transkrip: jauh lebih cepat, tapi tanpa cuplikan kalimat. |
| `--auto-model` | Model Whisper untuk menilai kandidat (default `base`, cepat). Subtitle hasil akhir tetap memakai `--model`. |
| `--json` | Keluaran JSON (daftar kandidat dan file hasil), untuk skrip atau coding agent seperti Claude Code. |

### Video stream dengan webcam: tata letak wajah (`--cam`, `--layout`)
Kalau videonya stream yang ada kotak webcam-nya di satu pojok, ClipGaskeun bisa memisahkan wajah dan game, lalu menatanya ke layar vertikal. Ada dua langkah.

**1. Cari letak kotak webcam** (cukup sekali per streamer). Tulis perkiraan `x,y,lebar,tinggi` dalam piksel, lalu minta gambar pratinjau:
```
clipgaskeun stream.mp4 --cam 1480,40,400,300 --cam-preview --cam-waktu 1:30
```
Hasilnya dua gambar di sebelah videomu: `stream_cam.png` (kotak merah di bingkai video, geser angkanya kalau meleset) dan `stream_layout.png` (semua tata letak berdampingan, supaya kamu bisa memilih).

**2. Render dengan tata letak:**
```
clipgaskeun stream.mp4 --cut 1:05-1:40 --cam 1480,40,400,300 --layout split --sub-pos tengah
clipgaskeun stream.mp4 --cut 1:05-1:40 --cam 1480,40,400,300 --layout "0-5:split,5-12:pip-kanan-atas,12-:wajah-penuh"
```

| Tata letak | Tampilan |
|---|---|
| `split` (default) | Wajah di atas, game di bawah (masing-masing setengah layar). |
| `pip-kanan-atas`, `pip-kiri-atas`, `pip-kanan-bawah`, `pip-kiri-bawah` | Game memenuhi layar, wajah jadi kotak kecil berbingkai putih di pojok itu. |
| `pip@X,Y` | Seperti di atas, tetapi posisinya bebas dalam persen, mis. `pip@79,12` (kanan atas). |
| `wajah-penuh` | Wajah di tengah layar dengan latar blur. |
| `game-penuh` | Game saja memenuhi layar, tanpa wajah. |

- Tata letak bisa **berganti sesuai waktu**: `0-5:split,5-12:pip-kanan-atas,12-:wajah-penuh`. Waktunya relatif ke **awal hasil** (sama seperti `--srt`), bukan ke video asli. Bagian yang tidak disebut memakai `split`. Rentang tidak boleh tumpang tindih.
- Saat game dipotong jadi vertikal, bagian yang dipertahankan dipilih otomatis: dekat tengah, tetapi menjauhi kotak webcam supaya wajah tidak ikut muncul di panel game. Mau menentukan sendiri: `--game-fokus 0` (kiri) sampai `100` (kanan).
- Tidak ada deteksi wajah otomatis dan tidak ada geser pakai mouse. Letak webcam kamu tentukan lewat `--cam`, dan `--cam-preview` membantu memastikan angkanya pas.
- Kualitas `wajah-penuh` dibatasi resolusi webcam di streamnya. Kalau kotaknya kecil (mis. 300 px), wajahnya akan terlihat lebih buram saat diperbesar.
- Subtitle tetap bisa diatur seperti biasa. `--sub-pos tengah` menaruhnya di sambungan wajah dan game pada tata letak `split`.

### Di mana hasilnya, dan apakah tertimpa?
- Mau lokasi atau nama lain: pakai `-o`, misalnya `-o D:\Shorts\klip1.mp4`. Folder yang belum ada dibuat otomatis.
- Kalau nama otomatis sudah dipakai, hasil baru diberi nomor (`_short_2.mp4`, `_short_3.mp4`, ...), jadi **klip sebelumnya tidak tertimpa**. Kalau kamu memakai `-o` dengan nama yang sudah ada, file itu akan ditimpa.
- Video tanpa suara tetap bisa diproses (hasilnya hening, tanpa subtitle otomatis).

**Catatan pertama kali:** model Whisper diunduh otomatis (sekitar 500 MB), jadi langkah subtitle pertama akan lebih lama. Sesudahnya tidak perlu unduh lagi.

## Preset
Gaya siap pakai, supaya tidak perlu mengatur satu per satu:

| Preset | Subtitle |
|---|---|
| `--preset tiktok` | Karaoke: kata yang sedang diucapkan menyala **kuning**, 4 kata per baris, sedikit lebih besar. |
| `--preset podcast` | Kalimat biasa dengan **kotak gelap** di belakangnya, mudah dibaca di latar apa pun. |
| `--preset gaming` | Karaoke **hijau**, diletakkan **di atas video** supaya tidak menutupi layar game. |

Tanpa `--preset`: subtitle putih bergaris tepi hitam di bawah video. Opsi yang kamu tulis sendiri selalu menang atas preset, misalnya `--preset tiktok --highlight hijau`.

## Opsi
| Opsi | Fungsi |
|---|---|
| `--cut MULAI-SELESAI` | Rentang waktu (`1:05-1:40`). Boleh diulang, bagian-bagiannya digabung berurutan. |
| `--auto` | Cari momen seru otomatis (pengganti `--cut`, lihat di atas). |
| `-o, --out` | Nama dan lokasi file hasil. |
| `--preset` | `tiktok`, `podcast`, atau `gaming` (lihat di atas). |
| `--lang` | Bahasa ucapan, mis. `id` atau `en`. Default: dideteksi otomatis. |
| `--model` | Model Whisper. Default `small` (semua bahasa). `medium` lebih akurat tapi lebih lambat; `small.en` sedikit lebih cepat untuk video berbahasa Inggris. |
| `--no-subs` | Tanpa subtitle. |
| `--srt file.srt` | Pakai subtitle buatan sendiri (waktunya relatif ke awal hasil). |
| `--style` | `biasa` atau `karaoke` (kata yang sedang diucapkan menyala). |
| `--sub-pos` | Posisi subtitle: `bawah` (default), `tengah`, `atas`. |
| `--sub-color` | Warna teks: `putih` (default), `kuning`, `hijau`, `merah`, `biru`, `oranye`, `pink`, `hitam`, atau kode hex seperti `FFD400`. |
| `--highlight` | Warna kata yang menyala di gaya karaoke (default `kuning`). |
| `--sub-bg` | `kotak` untuk kotak gelap di belakang subtitle, `tidak` (default) untuk garis tepi. |
| `--font`, `--font-size` | Font dan ukuran subtitle (default Poppins, 10; ukuran `4`–`40`). Kalau font tidak terpasang, ffmpeg memakai font bawaan. |
| `--cam x,y,w,h` | Letak kotak webcam di video stream (piksel). Mengaktifkan tata letak wajah (lihat di atas). |
| `--layout` | `split`, `pip-kanan-atas`, `wajah-penuh`, `game-penuh`, ... atau berganti per waktu. Butuh `--cam`. |
| `--game-fokus` | Bagian game yang dipertahankan: `0` kiri sampai `100` kanan. Default otomatis. |
| `--cam-preview`, `--cam-waktu` | Simpan gambar pratinjau kotak webcam dan semua tata letak, lalu keluar. |
| `--logo file.png` | Watermark PNG di pojok kiri atas. |
| `--logo-scale` | Ukuran logo, `0.05`–`3` (default `0.62`). |
| `--cek` | Periksa ffmpeg, faster-whisper, yt-dlp, dll. |
| `--version` | Tampilkan versi. |

Contoh video berbahasa Indonesia, bahasanya dikunci supaya tidak salah deteksi:
```
clipgaskeun "https://www.youtube.com/watch?v=ID_VIDEO" --cut 12:00-12:45 --lang id --preset tiktok
```

## Kalau ada masalah
Jalankan `clipgaskeun --cek` dulu: biasanya langsung kelihatan apa yang kurang.
- **`ffmpeg tidak ditemukan`**: ffmpeg belum terpasang atau belum ada di PATH. Ulangi langkah 1 dan buka terminal baru.
- **`faster-whisper belum terpasang`** / **`yt-dlp belum terpasang`**: pakai cara pasang cepat (langkah 2a), atau `pip install -r requirements.txt`.
- **`clipgaskeun.exe` diblokir Windows ("Windows protected your PC")**: file ini belum punya tanda tangan digital berbayar. Klik **More info → Run anyway**, atau klik kanan file zip → Properties → centang **Unblock** sebelum diekstrak.
- **`clipgaskeun` tidak dikenali** setelah pipx: jalankan `pipx ensurepath`, lalu tutup dan buka lagi terminal.
- **`yt-dlp gagal mengunduh`**: YouTube sering mengubah sistemnya, jadi perbarui yt-dlp dengan `pip install -U "yt-dlp[default]"` (kalau lewat pipx: `pipx upgrade clipgaskeun`), lalu coba lagi.
- **Peringatan `n challenge solving failed` / `Error solving ... using "deno"`**: skrip pemecah yt-dlp belum mengenal pemutar YouTube yang baru. Perbarui yt-dlp seperti di atas. Supaya selalu memakai skrip terbaru, buat file konfigurasi yt-dlp berisi `--remote-components ejs:github`:
  - Windows (cmd): `mkdir "%APPDATA%\yt-dlp"` lalu `echo --remote-components ejs:github> "%APPDATA%\yt-dlp\config.txt"`
  - macOS/Linux: `mkdir -p ~/.config/yt-dlp && echo "--remote-components ejs:github" > ~/.config/yt-dlp/config`
- **Ada dua yt-dlp terpasang** (cek dengan `where yt-dlp` di Windows, `which -a yt-dlp` di macOS/Linux): ClipGaskeun memakai yang paling atas, jadi perbarui yang itu.
- **`0 kata`**: tidak ada ucapan di bagian itu, jadi video dirender tanpa subtitle.
- **`Format waktu salah`**: cek penulisan `--cut`, misalnya `1:05-1:40` (bukan `1::05` atau `1:75`).
- **`melewati akhir video`**: waktu selesai lebih panjang dari videonya. Cek panjang video lalu ganti angkanya.
- **Bahasa terdeteksi salah / subtitle jadi terjemahan**: tambahkan `--lang id` (atau bahasa yang benar).
- **`--auto` lama di video panjang**: untuk file lokal, seluruh suara video dianalisis dulu (stream 4 jam butuh beberapa menit). Pakai `--auto-cepat` atau link YouTube yang punya data Most Replayed.
- **Subtitle salah-salah kata**: coba model lebih besar, misalnya `--model medium`.

## Untuk yang mau ikut mengembangkan
Tes cepat (tidak butuh ffmpeg atau model Whisper):
```
pip install pytest
python -m pytest
```
Tes yang sama dijalankan otomatis oleh GitHub Actions setiap kali ada push.

Versi `.exe` Windows dibuat otomatis oleh GitHub Actions (`.github/workflows/release.yml`) setiap kali tag versi baru di-push, misalnya `git tag v0.4.1` lalu `git push origin v0.4.1`. Hasilnya muncul di halaman Releases, lengkap dengan SHA256 dan bukti asal-usul (attestation).
Supaya rilisnya tidak bisa disusupi lewat pihak ketiga, setiap action dikunci ke commit-nya (SHA) dan pustaka build dipasang dari `requirements-build.txt` (versi persis + hash). Perbarui daftar itu dengan sadar sebelum rilis, bukan otomatis.

## Penting
Mengunduh dan memakai ulang konten orang lain bisa melanggar Ketentuan Layanan YouTube dan hak cipta kreatornya. Gunakan hanya untuk konten yang kamu punya haknya atau yang izin pemakaiannya jelas. Tanggung jawab pemakaian ada pada kamu.

## Lisensi
MIT, lihat file `LICENSE`.
