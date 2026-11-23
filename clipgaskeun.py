#!/usr/bin/env python3
"""ClipGaskeun - potong video panjang jadi Shorts 9:16 + subtitle otomatis. Lokal, gratis.

Contoh:
  python clipgaskeun.py stream.mp4 --cut 4:09:41-4:10:17
  python clipgaskeun.py stream.mp4 --cut 1:00-1:20 --cut 5:10-5:30 --logo logo.png -o hasil.mp4
Butuh: ffmpeg + `pip install faster-whisper` (untuk subtitle).
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile


def ts(s):
    """'1:02:03' | '2:03' | '123.5' -> detik."""
    parts = [float(p) for p in s.split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode:
        sys.exit("ffmpeg gagal:\n" + r.stderr[-1500:])


def srt_time(sec):
    ms = max(0, round(sec * 1000))
    return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"


def build_srt(words, max_words=6, gap=0.7):
    """words: [{text,start,end}] -> baris subtitle (frasa <= max_words, putus di tanda baca / jeda)."""
    lines, cur = [], []
    def flush():
        if cur:
            lines.append((cur[0]["start"], cur[-1]["end"], " ".join(w["text"] for w in cur)))
            cur.clear()
    for w in words:
        if cur and w["start"] - cur[-1]["end"] > gap:
            flush()
        cur.append(w)
        if len(cur) >= max_words or re.search(r"[.?!]$", w["text"]):
            flush()
    flush()
    for i in range(len(lines) - 1):  # jangan tumpang tindih
        s, e, t = lines[i]
        lines[i] = (s, min(e, lines[i + 1][0]), t)
    return "\n".join(f"{i+1}\n{srt_time(s)} --> {srt_time(e)}\n{t}\n" for i, (s, e, t) in enumerate(lines))


def transcribe(media, lang, model):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper belum terpasang. Jalankan: pip install faster-whisper (atau pakai --no-subs / --srt file.srt)")
    import numpy as np
    # baca audio lewat ffmpeg (16 kHz mono) supaya tidak bergantung pada versi PyAV
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", media, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True)
    if pcm.returncode or not pcm.stdout:
        sys.exit("Gagal membaca audio:\n" + pcm.stderr.decode(errors="ignore")[-800:])
    audio = np.frombuffer(pcm.stdout, dtype=np.float32)
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, language=lang, word_timestamps=True, vad_filter=True,
                           vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=120),
                           condition_on_previous_text=False, beam_size=5)
    words = []
    for s in segs:
        for w in s.words:
            t = w.word.strip()
            if t and not re.match(r"^[\(\[♪]", t):
                words.append({"text": t, "start": w.start, "end": w.end})
    return words


def main():
    ap = argparse.ArgumentParser(description="Potong video jadi Shorts 9:16 + subtitle.")
    ap.add_argument("input")
    ap.add_argument("--cut", action="append", required=True, metavar="MULAI-SELESAI",
                    help="rentang waktu, boleh diulang untuk digabung (mis. 1:05-1:40)")
    ap.add_argument("-o", "--out", help="file hasil (default: <nama>_short.mp4)")
    ap.add_argument("--lang", default="en", help="bahasa ucapan (default en)")
    ap.add_argument("--model", default="small.en", help="model whisper (default small.en; pakai small/medium untuk non-Inggris)")
    ap.add_argument("--no-subs", action="store_true", help="tanpa subtitle")
    ap.add_argument("--srt", help="pakai SRT sendiri (waktu relatif awal hasil) alih-alih transkripsi")
    ap.add_argument("--font", default="Poppins", help="nama font subtitle")
    ap.add_argument("--font-size", type=int, default=10)
    ap.add_argument("--logo", help="PNG watermark (pojok kiri atas)")
    ap.add_argument("--logo-scale", type=float, default=0.62)
    ap.add_argument("--keep-tmp", action="store_true")
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg tidak ditemukan di PATH.")
    if not os.path.isfile(a.input):
        sys.exit(f"File tidak ada: {a.input}")
    cuts = []
    for c in a.cut:
        m = re.fullmatch(r"\s*([\d:.]+)\s*-\s*([\d:.]+)\s*", c)
        if not m or ts(m[2]) <= ts(m[1]):
            sys.exit(f"Rentang tidak valid: {c!r} (contoh: 1:05-1:40)")
        cuts.append((ts(m[1]), ts(m[2])))
    out = a.out or os.path.splitext(a.input)[0] + "_short.mp4"
    tmp = tempfile.mkdtemp(prefix="clipgaskeun_")
    try:
        # 1) potong (dan gabung) -> klip mentah 16:9. Presisi frame karena re-encode.
        raw = os.path.join(tmp, "raw.mp4")
        fc, n = "", len(cuts)
        for i, (s, e) in enumerate(cuts):
            fc += f"[0:v]trim={s}:{e},setpts=PTS-STARTPTS,fps=30[v{i}];"
            fc += f"[0:a]atrim={s}:{e},asetpts=PTS-STARTPTS,afade=t=in:d=0.06,afade=t=out:st={e-s-0.06:.3f}:d=0.06[a{i}];"
        fc += "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
        print(f"[1/3] memotong {n} bagian ...")
        run(["ffmpeg", "-y", "-v", "error", "-i", a.input, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", raw])

        # 2) subtitle: ditranskripsi dari potongan itu sendiri -> waktu selalu pas
        srt = None
        if a.srt:
            srt = os.path.join(tmp, "subs.srt"); shutil.copy(a.srt, srt)
        elif not a.no_subs:
            print("[2/3] transkripsi (pertama kali akan mengunduh model) ...")
            words = transcribe(raw, a.lang, a.model)
            print(f"      {len(words)} kata")
            if words:
                srt = os.path.join(tmp, "subs.srt")
                open(srt, "w", encoding="utf-8").write(build_srt(words))
            else:
                print("      tidak ada ucapan terdeteksi -> dirender tanpa subtitle")
        else:
            print("[2/3] tanpa subtitle")

        # 3) komposisi 9:16: latar blur + video di tengah + subtitle + logo
        print("[3/3] render 9:16 ...")
        chain = ("[0:v]split=2[a][b];[a]scale=540:960:force_original_aspect_ratio=increase,crop=540:960,"
                 "boxblur=15:2,scale=1080:1920,eq=brightness=-0.08[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2-120[c]")
        last = "c"
        if srt:
            sp = "subs.srt"  # ffmpeg dijalankan dari folder tmp, jadi cukup nama file
            style = (f"FontName={a.font},Bold=1,FontSize={a.font_size},PrimaryColour=&H00FFFFFF,"
                     "OutlineColour=&H00000000,Outline=3,Shadow=0,Alignment=2,MarginV=85")
            chain += f";[{last}]subtitles='{sp}':force_style='{style}'[s]"; last = "s"
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", os.path.abspath(raw)]
        if a.logo:
            cmd += ["-i", os.path.abspath(a.logo)]
            chain += f";[1:v]format=rgba,scale=iw*{a.logo_scale}:-1[w];[{last}][w]overlay=40:118[o]"; last = "o"
        cmd += ["-filter_complex", chain, "-map", f"[{last}]", "-map", "0:a", "-r", "30",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", os.path.abspath(out)]
        run(cmd, cwd=tmp)
        print(f"Selesai: {out}")
    finally:
        if a.keep_tmp:
            print("tmp:", tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
