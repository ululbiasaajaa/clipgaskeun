# ClipGaskeun

Potong video panjang (stream, podcast, dll) jadi Shorts 9:16 dengan latar blur, subtitle otomatis, dan watermark opsional. Jalan lokal, gratis, tanpa API berbayar.

## Pasang
1. Pasang [ffmpeg](https://ffmpeg.org) (harus ada di PATH).
2. `pip install faster-whisper`

## Pakai
```
python clipgaskeun.py video.mp4 --cut 4:09:41-4:10:17
python clipgaskeun.py video.mp4 --cut 1:05-1:40 --cut 5:10-5:30 --logo logo.png -o hasil.mp4
```
- `--cut MULAI-SELESAI` boleh diulang; bagian-bagiannya digabung berurutan.
- Subtitle ditranskripsi dari hasil potongan itu sendiri, jadi waktunya selalu pas.
- `--lang id --model small` untuk video bahasa Indonesia. `--no-subs` untuk tanpa subtitle. `--srt file.srt` untuk subtitle buatan sendiri.
- Pertama kali jalan, model whisper diunduh otomatis.

Hanya untuk file lokal. Pastikan kamu punya hak memakai konten yang diklip.
