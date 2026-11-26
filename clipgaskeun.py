#!/usr/bin/env python3
"""ClipGaskeun - potong video panjang jadi Shorts 9:16 + subtitle otomatis. Lokal, gratis.

Contoh:
  clipgaskeun stream.mp4 --cut 4:09:41-4:10:17
  clipgaskeun stream.mp4 --cut 1:00-1:20 --cut 5:10-5:30 --preset tiktok --logo logo.png -o hasil.mp4
  clipgaskeun "https://www.youtube.com/watch?v=ID" --cut 4:09:41-4:10:17   (waktu = waktu di video YouTube)
  clipgaskeun --cek   (periksa apakah semua yang dibutuhkan sudah terpasang)
Tanpa pipx: ganti `clipgaskeun` dengan `python clipgaskeun.py`.
Bahasa ucapan dideteksi otomatis (kunci dengan --lang id bila perlu).
Butuh: ffmpeg + faster-whisper (subtitle) + yt-dlp (hanya untuk link YouTube). rich opsional (tampilan terminal).
"""
import argparse, json, math, os, re, shutil, subprocess, sys, tempfile
from contextlib import contextmanager
from importlib.util import find_spec

__version__ = "0.4.0"

# ───────────── tampilan terminal: pakai rich kalau ada, kalau tidak teks biasa ─────────────
try:
    from rich.console import Console
    from rich.table import Table
    _out = Console(highlight=False)
    _err = Console(stderr=True, highlight=False)
except ImportError:
    _out = _err = None


JSON_MODE = False  # --json: stdout hanya berisi JSON, semua pesan lain pindah ke stderr


def set_json_mode():
    global JSON_MODE, _out
    JSON_MODE = True
    _out = _err


def say(msg, style=None):
    if _out:
        _out.print(msg, style=style, markup=False)
    else:
        print(msg, file=sys.stderr if JSON_MODE else sys.stdout)


def step(n, msg):
    say(f"[{n}/3] {msg}", "bold cyan")


def note(msg):
    say(f"      {msg}", "dim")


def warn(msg):
    say(f"Catatan: {msg}", "yellow")


def die(msg):
    if JSON_MODE:
        print(json.dumps({"error": msg}, ensure_ascii=False))
    if _err:
        _err.print(msg, style="bold red", markup=False)
    else:
        print(msg, file=sys.stderr)
    sys.exit(1)


@contextmanager
def busy(msg):
    """Putaran 'sedang bekerja' selama langkah lama (tanpa rich: cukup satu baris)."""
    if _out and _out.is_terminal:
        with _out.status(f"      {msg}", spinner="dots"):
            yield
    else:
        yield


# ───────────── waktu ─────────────
def ts(s):
    """'1:02:03' | '2:03' | '123.5' -> detik. Format salah -> None.
    Menit/detik setelah titik dua harus 00-59 (jadi '1:99' ditolak); menit di format m:ss boleh > 59 ('75:00')."""
    m = re.fullmatch(r"(?:(\d+):)?(?:(\d+):)?(\d+(?:\.\d+)?)", s.strip())
    if not m:
        return None
    a, b, c = m.groups()
    nums = [int(x) for x in (a, b) if x is not None] + [float(c)]
    if len(nums) >= 2 and nums[-1] >= 60:
        return None
    if len(nums) == 3 and nums[1] >= 60:
        return None
    sec = 0.0
    for p in nums:
        sec = sec * 60 + p
    return sec


def hms(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec // 60 % 60:02}:{sec % 60:02}"


def parse_cut(c):
    """'1:05-1:40' -> (65.0, 100.0) atau pesan error (str)."""
    m = re.fullmatch(r"\s*([\d:.]+)\s*-\s*([\d:.]+)\s*", c)
    cs, ce = (ts(m[1]), ts(m[2])) if m else (None, None)
    if cs is None or ce is None:
        return f"Format waktu salah: {c!r}. Contoh: 1:05-1:40 atau 1:02:03-1:02:40 (menit & detik 00-59)"
    if ce <= cs:
        return f"Waktu selesai harus sesudah waktu mulai: {c!r}"
    if ce - cs < MIN_CUT:
        return f"Bagian terlalu pendek: {c!r} (minimal {MIN_CUT} detik)"
    return cs, ce


PAD = 3            # detik cadangan di awal & akhir bagian yang diunduh dari link
MIN_CUT = 0.5      # detik; bagian lebih pendek dari ini ditolak
LONG_WARN = 20 * 60  # detik; di atas ini beri peringatan transkripsi berat


# ───────────── file & alat luar ─────────────
def unique_path(path):
    """Kalau file sudah ada, pakai nama_2, nama_3, ... supaya hasil sebelumnya tidak tertimpa."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


def is_url(s):
    return re.match(r"^https?://", s, re.I) is not None


FROZEN = getattr(sys, "frozen", False)  # True kalau dijalankan sebagai clipgaskeun.exe (PyInstaller)


def find_ytdlp():
    """yt-dlp yang terpasang di sistem didahulukan (paling mudah diperbarui), lalu yang ikut di dalam paket."""
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    if find_spec("yt_dlp"):
        # di versi .exe, sys.executable = clipgaskeun.exe; `-m yt_dlp` ditangani oleh run_bundled_ytdlp()
        return [sys.executable, "-m", "yt_dlp"]
    return None


def run_bundled_ytdlp(argv):
    """Versi .exe: `clipgaskeun.exe -m yt_dlp ...` menjalankan yt-dlp yang ikut di dalam paket."""
    import yt_dlp
    return yt_dlp.main(argv)


def probe(path):
    """(durasi detik atau None, punya audio?) lewat ffprobe. Tanpa ffprobe: (None, True)."""
    if not shutil.which("ffprobe"):
        return None, True
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        info = json.loads(r.stdout or "{}")
    except ValueError:
        return None, True
    dur = info.get("format", {}).get("duration")
    has_audio = any(st.get("codec_type") == "audio" for st in info.get("streams", []))
    return (float(dur) if dur else None), has_audio


def ytdlp_run(cmd, quiet=False):
    """Jalankan yt-dlp. Di mode --json keluarannya dialihkan ke stderr supaya stdout tetap JSON bersih."""
    kw = {"stdout": sys.stderr} if JSON_MODE else {}
    if quiet:
        cmd = cmd + ["-q", "--no-warnings"]
    if subprocess.run(cmd, **kw).returncode:
        die("yt-dlp gagal mengunduh (pesan di atas). Coba perbarui: pip install -U yt-dlp  (atau: winget upgrade yt-dlp)")


def download_section(ytdlp, url, start, end, prefix, audio_only=False, pad=PAD):
    """Unduh hanya detik [start, end] (plus cadangan pad) dari link.
    Mengembalikan (path file, detik video tempat file itu dimulai)."""
    ds = max(0, int(start) - pad)
    de = int(math.ceil(end)) + pad
    if audio_only:  # cukup suaranya (untuk analisis --auto): jauh lebih kecil dari video
        cmd = ytdlp + ["--no-playlist", "--download-sections", f"*{hms(ds)}-{hms(de)}",
                       "-f", "ba/b", "-o", prefix + ".%(ext)s", url]
    else:
        cmd = ytdlp + ["--no-playlist", "--download-sections", f"*{hms(ds)}-{hms(de)}",
                       "--force-keyframes-at-cuts", "-f", "bv*[height<=1080]+ba/b",
                       "--downloader-args", "ffmpeg:-hide_banner -loglevel error",
                       "--merge-output-format", "mp4", "-o", prefix + ".%(ext)s", url]
    ytdlp_run(cmd, quiet=audio_only)
    if not audio_only and os.path.isfile(prefix + ".mp4"):
        return prefix + ".mp4", ds
    folder, base = os.path.split(prefix)
    found = [os.path.join(folder, x) for x in os.listdir(folder or ".")
             if x.startswith(base + ".") and not x.endswith((".part", ".ytdl"))]
    if not found:
        die("File hasil unduhan tidak ditemukan.")
    return found[0], ds


def video_info(ytdlp, url):
    """Info video dari YouTube (judul, durasi, heatmap) tanpa mengunduh videonya."""
    r = subprocess.run(ytdlp + ["-J", "--no-playlist", "--no-warnings", url], capture_output=True, text=True)
    if r.returncode:
        die("yt-dlp gagal membaca info video:\n" + r.stderr[-800:])
    try:
        return json.loads(r.stdout)
    except ValueError:
        die("Info video dari yt-dlp tidak bisa dibaca.")


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode:
        die("ffmpeg gagal:\n" + r.stderr[-1500:])


# ───────────── cek kelengkapan (--cek) ─────────────
INSTALL_HINT = {
    "ffmpeg": "Windows: winget install ffmpeg | macOS: brew install ffmpeg | Linux: sudo apt install ffmpeg",
    "ffprobe": "ikut terpasang bersama ffmpeg",
    "faster-whisper": "pip install faster-whisper",
    "yt-dlp": "pip install yt-dlp  (atau winget install yt-dlp)",
    "rich": "pip install rich",
    "deno": "dibutuhkan yt-dlp untuk YouTube. Windows: winget install DenoLand.Deno | macOS: brew install deno | lainnya: deno.land",
}


def check_deps():
    """Daftar (nama, wajib?, ada?, keterangan)."""
    if FROZEN:
        rows = [("ClipGaskeun .exe", True, True, f"versi {__version__} (Python sudah termasuk)")]
    else:
        rows = [("Python 3.9+", True, sys.version_info >= (3, 9), sys.version.split()[0])]
    for tool in ("ffmpeg", "ffprobe"):
        p = shutil.which(tool)
        rows.append((tool, tool == "ffmpeg", bool(p), p or INSTALL_HINT[tool]))
    fw = find_spec("faster_whisper") is not None
    rows.append(("faster-whisper", False, fw, "untuk subtitle otomatis" if fw else INSTALL_HINT["faster-whisper"]))
    yt = find_ytdlp()
    yt_info = ("bawaan paket .exe" if yt and yt[0] == sys.executable else "untuk link YouTube") if yt else INSTALL_HINT["yt-dlp"]
    rows.append(("yt-dlp", False, bool(yt), yt_info))
    js = shutil.which("deno") or shutil.which("node")
    rows.append(("deno / node", False, bool(js), "dipakai yt-dlp untuk YouTube" if js else INSTALL_HINT["deno"]))
    rows.append(("rich", False, _out is not None, "tampilan terminal" if _out else INSTALL_HINT["rich"]))
    return rows


def print_check():
    rows = check_deps()
    if _out:
        t = Table(title=f"ClipGaskeun {__version__} - cek kelengkapan", show_lines=False)
        t.add_column("Komponen"); t.add_column("Status"); t.add_column("Keterangan / cara pasang")
        for name, req, ok, info in rows:
            status = "[green]OK[/]" if ok else ("[red]BELUM ADA (wajib)[/]" if req else "[yellow]belum ada[/]")
            t.add_row(name, status, info)
        _out.print(t)
    else:
        for name, req, ok, info in rows:
            print(f"{'OK ' if ok else '-- '} {name:15} {info}")
    missing = [n for n, req, ok, _ in rows if req and not ok]
    say("Semua yang wajib sudah siap." if not missing else "Yang wajib belum lengkap: " + ", ".join(missing),
        "bold green" if not missing else "bold red")
    return 0 if not missing else 1


# ───────────── transkripsi ─────────────
_MODELS = {}


def transcribe(media, lang, model):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        die("faster-whisper belum terpasang. Jalankan: pip install faster-whisper (atau pakai --no-subs / --srt file.srt)")
    import numpy as np
    # baca audio lewat ffmpeg (16 kHz mono) supaya tidak bergantung pada versi PyAV
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", media, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True)
    if pcm.returncode or not pcm.stdout:
        die("Gagal membaca audio:\n" + pcm.stderr.decode(errors="ignore")[-800:])
    audio = np.frombuffer(pcm.stdout, dtype=np.float32)
    if model not in _MODELS:  # model dimuat sekali saja per jalan (--auto mentranskripsi beberapa bagian)
        _MODELS[model] = WhisperModel(model, device="cpu", compute_type="int8")
    m = _MODELS[model]
    segs, info = m.transcribe(audio, language=lang, word_timestamps=True, vad_filter=True,
                              vad_parameters=dict(min_silence_duration_ms=300, speech_pad_ms=120),
                              condition_on_previous_text=False, beam_size=5)
    words = []
    for s in segs:  # generator: transkripsi berjalan di sini
        for w in s.words:
            t = w.word.strip()
            if t and not re.match(r"^[\(\[♪]", t):
                words.append({"text": t, "start": w.start, "end": w.end})
    return words, (None if lang else (info.language, info.language_probability))


# ───────────── subtitle (ASS) ─────────────
COLORS = {"putih": "FFFFFF", "kuning": "FFD400", "hijau": "35E08A", "merah": "FF4D4D",
          "biru": "4DA6FF", "oranye": "FF8A00", "pink": "FF5FA2", "hitam": "000000"}


def parse_color(v):
    """'kuning' | 'FFD400' | '#ffd400' -> 'FFD400', salah -> None."""
    v = v.strip().lower()
    if v in COLORS:
        return COLORS[v]
    m = re.fullmatch(r"#?([0-9a-f]{6})", v)
    return m[1].upper() if m else None


def ass_color(rgb, alpha=0):
    """'RRGGBB' -> '&HAABBGGRR' (urutan warna ASS terbalik; alpha 00 = penuh, FF = tembus)."""
    return f"&H{alpha:02X}{rgb[4:6]}{rgb[2:4]}{rgb[0:2]}"


def ass_time(sec):
    cs = max(0, round(sec * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def ass_text(t):
    """Kurung kurawal & garis miring terbalik punya arti khusus di ASS -> diganti."""
    return t.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def group_lines(words, max_words=6, gap=0.7):
    """words [{text,start,end}] -> baris [{start,end,text,words}] (putus di tanda baca / jeda / max_words)."""
    lines, cur = [], []

    def flush():
        if cur:
            lines.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                          "text": " ".join(w["text"] for w in cur), "words": list(cur)})
            cur.clear()
    for w in words:
        if cur and w["start"] - cur[-1]["end"] > gap:
            flush()
        cur.append(w)
        if len(cur) >= max_words or re.search(r"[.?!]$", w["text"]):
            flush()
    flush()
    for a, b in zip(lines, lines[1:]):  # jangan tumpang tindih
        a["end"] = min(a["end"], b["start"])
    return lines


def parse_srt(path):
    """File SRT -> baris [{start,end,text,words=None}]."""
    raw = open(path, encoding="utf-8-sig", errors="replace").read().replace("\r\n", "\n")
    out = []
    tre = r"(\d+):(\d\d):(\d\d)[,.](\d{1,3})"
    for block in re.split(r"\n\s*\n", raw.strip()):
        rows = block.split("\n")
        for i, row in enumerate(rows):
            m = re.match(tre + r"\s*-->\s*" + tre, row.strip())
            if m:
                g = [int(x) for x in m.groups()]
                s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 10 ** len(m[4])
                e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 10 ** len(m[8])
                text = "\n".join(r for r in rows[i + 1:] if r.strip())
                if text:
                    out.append({"start": s, "end": e, "text": text, "words": None})
                break
    return out


SCALE = 1920 / 288  # --font-size memakai satuan lama (skala 288) supaya angka lama tetap sama hasilnya
POS = {  # (Alignment ASS, MarginV) dalam piksel 1080x1920
    "bawah": (2, 567),   # di bawah video (posisi v0.1)
    "tengah": (5, 0),    # tengah layar
    "atas": (8, 300),    # di atas video, di bawah logo
}


def build_ass(lines, cfg):
    """Baris subtitle -> isi file .ass. cfg: font, font_size, sub_pos, sub_color, highlight, sub_bg, style."""
    size = round(cfg["font_size"] * SCALE)
    align, margin_v = POS[cfg["sub_pos"]]
    primary = ass_color(cfg["sub_color"])
    if cfg["sub_bg"] == "kotak":  # kotak gelap semi transparan di belakang teks
        border, outline, outline_col, shadow = 3, round(size * 0.22), ass_color("000000", 0x60), 0
    else:  # garis tepi hitam tebal (tampilan v0.1)
        border, outline, outline_col, shadow = 1, round(3 * SCALE), ass_color("000000"), 0
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{cfg['font']},{size},{primary},{primary},{outline_col},{ass_color('000000', 0x80)},-1,0,0,0,100,100,0,0,{border},{outline},{shadow},{align},70,70,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    hl = ass_color(cfg["highlight"])
    ev = []
    for ln in lines:
        words = ln.get("words")
        if cfg["style"] == "karaoke" and words:
            # satu event per kata: kata yang sedang diucapkan diberi warna sorot
            for i, w in enumerate(words):
                s = ln["start"] if i == 0 else w["start"]
                e = words[i + 1]["start"] if i + 1 < len(words) else ln["end"]
                if e <= s:
                    continue
                parts = [("{\\c" + hl + "&}" + ass_text(x["text"]) + "{\\r}") if j == i else ass_text(x["text"])
                         for j, x in enumerate(words)]
                ev.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Default,,0,0,0,,{' '.join(parts)}")
        else:
            ev.append(f"Dialogue: 0,{ass_time(ln['start'])},{ass_time(ln['end'])},Default,,0,0,0,,{ass_text(ln['text'])}")
    return head + "\n".join(ev) + "\n"


# ───────────── cari momen seru otomatis (--auto) ─────────────
# Sinyal yang dipakai semuanya gratis & lokal:
#  1) heatmap "Most Replayed" YouTube (kalau ada) = bagian yang paling sering diputar ulang penonton
#  2) kerasnya suara per detik (teriak, tawa, heboh) dibanding biasanya di video itu
#  3) kepadatan kata dari transkrip singkat (obrolan yang padat & seru)
REGION_MARGIN = 15  # detik tambahan di kiri-kanan kandidat sebelum dicari potongan terbaiknya


def _np():
    try:
        import numpy as np
        return np
    except ImportError:
        die("numpy belum terpasang (ikut terpasang bersama faster-whisper). Jalankan: pip install faster-whisper")


def loudness_curve(path, start=None, dur=None, rate=8000):
    """Kerasnya suara (dB) per detik. Audio dibaca bertahap, jadi video berjam-jam pun tidak memenuhi RAM."""
    np = _np()
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", path, "-vn", "-f", "f32le", "-ac", "1", "-ar", str(rate), "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    sec_bytes = rate * 4
    out, buf = [], b""
    while True:
        chunk = p.stdout.read(sec_bytes * 60)
        if not chunk:
            break
        buf += chunk
        n = len(buf) // sec_bytes * sec_bytes
        if n:
            a = np.frombuffer(buf[:n], dtype=np.float32).reshape(-1, rate)
            out.extend((10 * np.log10(np.mean(a * a, axis=1) + 1e-10)).tolist())
            buf = buf[n:]
    p.wait()
    return out


def _excite(db):
    """dB per detik -> skor 'heboh' per detik: seberapa keras dibanding biasanya + lonjakan tiba-tiba."""
    np = _np()
    x = np.asarray(db, dtype=float)
    if len(x) == 0:
        return x
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826 + 1e-6
    z = np.clip((x - med) / mad, -3, 6)
    prev = np.concatenate([[x[0]] * 5, x])
    base = np.array([prev[i:i + 5].mean() for i in range(len(x))])  # rata-rata 5 detik sebelumnya
    spike = np.clip(x - base, 0, 20) / 10
    return z + spike


def loud_windows(db, length, k, min_gap=None):
    """Pilih k potongan sepanjang `length` detik yang paling 'heboh', berjauhan satu sama lain
    (min_gap detik antar-awal; default: 3x panjang atau 2 menit, mana yang lebih besar, dibatasi agar video pendek
    tetap dapat kandidat). -> [(mulai, selesai, skor)] urut dari skor tertinggi."""
    np = _np()
    s = _excite(db)
    if len(s) <= length:
        return [(0, len(s), float(s.mean()) if len(s) else 0.0)]
    c = np.concatenate([[0.0], np.cumsum(s)])
    win = (c[length:] - c[:-length]) / length  # win[i] = rata-rata skor detik i .. i+length
    if min_gap is None:
        min_gap = max(length, min(max(3 * length, 120), len(s) // (2 * k)))
    picks = []
    for i in np.argsort(-win):
        if all(abs(int(i) - p) >= min_gap for p, _ in picks):
            picks.append((int(i), float(win[i])))
            if len(picks) == k:
                break
    return [(i, i + length, v) for i, v in picks]


def heatmap_regions(heatmap, duration, length, k):
    """Data 'Most Replayed' -> k wilayah kandidat [{start,end,score}] (score 0-1).
    Bagian paling awal dilewati: di sana grafiknya selalu tinggi karena semua orang mulai menonton dari situ."""
    skip = max(5.0, 0.02 * duration)
    bins = [h for h in heatmap if h.get("start_time", 0) >= skip and h.get("value") is not None]
    picks = []
    for h in sorted(bins, key=lambda h: -h["value"]):
        c = (h["start_time"] + h["end_time"]) / 2
        width = h["end_time"] - h["start_time"]
        if any(abs(c - p["center"]) < max(length, width) for p in picks):
            continue
        half = max(width, length) / 2 + REGION_MARGIN
        rs, re_ = max(0.0, c - half), min(duration, c + half)
        picks.append({"start": rs, "end": re_, "center": c, "score": float(h["value"])})
        if len(picks) == k:
            break
    return picks


def snap_window(words, t0, t1, lo, hi):
    """Geser awal/akhir potongan ke jeda kalimat terdekat supaya tidak terpotong di tengah kalimat.
    words: [{text,start,end}] (waktu sama dengan t0/t1). lo/hi = batas wilayah yang boleh dipakai."""
    if not words:
        return t0, t1
    def boundary_before(i):  # kata i mengawali kalimat?
        return i == 0 or words[i]["start"] - words[i - 1]["end"] > 0.5 or re.search(r"[.?!,]$", words[i - 1]["text"])
    def boundary_after(i):   # kata i mengakhiri kalimat?
        return i == len(words) - 1 or words[i + 1]["start"] - words[i]["end"] > 0.5 or re.search(r"[.?!]$", words[i]["text"])
    first = next((i for i, w in enumerate(words) if w["start"] >= t0), None)
    if first is not None:
        j = first
        while j > 0 and not boundary_before(j) and t0 - words[j - 1]["start"] <= 5:
            j -= 1
        if boundary_before(j):
            t0 = max(lo, words[j]["start"] - 0.15)
    last = max((i for i, w in enumerate(words) if w["end"] <= t1), default=None)
    if last is not None:
        j = last
        while j < len(words) - 1 and not boundary_after(j) and words[j + 1]["end"] - t1 <= 6:
            j += 1
        if boundary_after(j):
            t1 = min(hi, words[j]["end"] + 0.35)
    return t0, t1


def best_window(words, db, length):
    """Di dalam satu wilayah (waktu relatif awal wilayah): cari awal potongan sepanjang `length`
    dengan gabungan kepadatan kata (60%) dan kehebohan suara (40%). -> (mulai, skor kepadatan kata/detik)."""
    np = _np()
    total = len(db)
    if total <= length:
        return 0.0, (len(words) / max(total, 1))
    ex = _excite(db)
    starts = range(0, total - length + 1)
    dens = np.array([sum(1 for w in words if t <= w["start"] < t + length) / length for t in starts])
    loud = np.array([ex[t:t + length].mean() for t in starts])
    norm = lambda v: (v - v.min()) / (v.max() - v.min() + 1e-9)
    score = 0.6 * norm(dens) + 0.4 * norm(loud)
    i = int(np.argmax(score))
    return float(i), float(dens[i])


def find_moments(a, url_mode, ytdlp, tmp):
    """Cari kandidat momen. -> (daftar kandidat, keterangan sumber). Kandidat: start,end,score,reason,snippet."""
    L, k = a.auto_len, a.auto_n
    method = None
    if url_mode:
        say("[auto] membaca info video (tanpa mengunduh) ...", "bold cyan")
        info = video_info(ytdlp, a.input)
        duration = float(info.get("duration") or 0)
        heat = info.get("heatmap") or []
        if heat and duration:
            regions = heatmap_regions(heat, duration, L, k)
            method = "heatmap"
            note(f"pakai data Most Replayed YouTube ({len(heat)} titik, per ±{hms(duration / max(len(heat), 1))})")
            for r in regions:
                r["reason"] = "sering diputar ulang penonton"
        else:
            note("video ini tidak punya data Most Replayed -> mengunduh SUARANYA saja (sekali) untuk dianalisis")
            ytdlp_run(ytdlp + ["--no-playlist", "-f", "ba/b", "-o", os.path.join(tmp, "full.%(ext)s"), a.input], quiet=True)
            found = [os.path.join(tmp, x) for x in os.listdir(tmp) if x.startswith("full.") and not x.endswith(".part")]
            if not found:
                die("Audio video tidak berhasil diunduh.")
            source, offset = found[0], 0.0
    else:
        source, offset = a.input, 0.0
    if method is None:  # dari kerasnya suara seluruh video
        say("[auto] mendengarkan kerasnya suara di seluruh video ...", "bold cyan")
        with busy("menganalisis suara"):
            db = loudness_curve(source)
        if not db:
            die("Tidak ada suara yang bisa dianalisis di video ini, jadi --auto tidak bisa mencari momen. Pakai --cut.")
        duration = float(len(db))
        wins = loud_windows(db, L, k)
        top = max(v for _, _, v in wins) or 1.0
        regions = [{"start": max(0.0, s - REGION_MARGIN), "end": min(duration, e + REGION_MARGIN),
                    "score": max(0.0, v / top) if top > 0 else 0.0, "reason": "suara memuncak"} for s, e, v in wins]
        method = "suara"

    cands = []
    for i, r in enumerate(regions, 1):
        cand = {"start": r["start"] + (r["end"] - r["start"] - L) / 2, "score_a": r["score"], "reason": r["reason"],
                "snippet": "", "density": None}
        cand["end"] = cand["start"] + L
        if not a.auto_cepat:
            say(f"[auto] menilai kandidat {i}/{len(regions)} ({hms(r['start'])}-{hms(r['end'])}) ...", "bold cyan")
            if url_mode and method == "heatmap":
                f, ds = download_section(ytdlp, a.input, r["start"], r["end"], os.path.join(tmp, f"reg{i}"), audio_only=True, pad=0)
                rs_in_file, base = r["start"] - ds, r["start"]
            else:
                f, rs_in_file, base = source, r["start"] - offset, r["start"]
            clip = os.path.join(tmp, f"cand{i}.wav")
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0, rs_in_file):.3f}", "-t", f"{r['end'] - r['start']:.3f}",
                 "-i", f, "-vn", "-ac", "1", "-ar", "16000", clip])
            with busy("mentranskripsi singkat"):
                words, _ = transcribe(clip, a.lang, a.auto_model)
                db = loudness_curve(clip)
            t, dens = best_window(words, db, L)
            t0, t1 = snap_window(words, t, t + L, 0.0, len(db))
            if t1 - t0 < L * 0.7:  # jangan sampai jadi terlalu pendek setelah digeser
                t0, t1 = t, t + L
            cand.update(start=base + t0, end=base + t1, density=dens,
                        snippet=" ".join(w["text"] for w in words if w["start"] >= t0)[:90])
        cands.append(cand)

    dmax = max((c["density"] or 0) for c in cands) or 1.0
    for c in cands:
        if c["density"] is None:
            c["score"] = c["score_a"]
        else:
            c["score"] = 0.6 * c["score_a"] + 0.4 * (c["density"] / dmax)
            if c["density"] / dmax > 0.8:
                c["reason"] += " + obrolan padat"
    cands.sort(key=lambda c: -c["score"])
    cands = dedupe(cands)
    for i, c in enumerate(cands, 1):
        c["rank"] = i
        c["score"] = round(100 * c["score"])
    return cands, method


def dedupe(cands, max_overlap=0.5):
    """Buang kandidat yang sebagian besar sama dengan kandidat berskor lebih tinggi (cands sudah urut skor)."""
    kept = []
    for c in cands:
        if all(min(c["end"], k["end"]) - max(c["start"], k["start"])
               <= max_overlap * min(c["end"] - c["start"], k["end"] - k["start"]) for k in kept):
            kept.append(c)
    return kept


def show_candidates(cands):
    if _out:
        t = Table(title="Kandidat momen", show_lines=True)
        for col in ("#", "Rentang", "Durasi", "Skor", "Alasan", "Cuplikan"):
            t.add_column(col, overflow="fold")
        for c in cands:
            t.add_row(str(c["rank"]), f"{hms(c['start'])} - {hms(c['end'])}", f"{c['end'] - c['start']:.0f} dtk",
                      str(c["score"]), c["reason"], c["snippet"] or "-")
        _out.print(t)
    else:
        for c in cands:
            say(f"{c['rank']}. {hms(c['start'])}-{hms(c['end'])}  skor {c['score']}  {c['reason']}  {c['snippet']}")


def parse_pick(text, n):
    """'1,3' -> [1, 3]; salah -> None."""
    try:
        picks = [int(x) for x in re.split(r"[,\s]+", text.strip()) if x]
    except ValueError:
        return None
    if not picks or any(not 1 <= p <= n for p in picks):
        return None
    return list(dict.fromkeys(picks))


# ───────────── preset ─────────────
BASE = dict(style="biasa", sub_pos="bawah", font="Poppins", font_size=10, sub_color="putih",
            highlight="kuning", sub_bg="tidak", logo_scale=0.62)
PRESETS = {
    "tiktok": dict(style="karaoke", sub_pos="bawah", font_size=12, highlight="kuning"),
    "podcast": dict(style="biasa", sub_pos="bawah", font_size=10, sub_bg="kotak"),
    "gaming": dict(style="karaoke", sub_pos="atas", font_size=12, highlight="hijau"),
}


def resolve(a):
    """Urutan: opsi yang kamu tulis > preset > bawaan."""
    pre = PRESETS.get(a.preset or "", {})
    cfg = {k: (getattr(a, k) if getattr(a, k) is not None else pre.get(k, v)) for k, v in BASE.items()}
    for k in ("sub_color", "highlight"):
        c = parse_color(str(cfg[k]))
        if not c:
            die(f"Warna tidak dikenal untuk --{k.replace('_', '-')}: {cfg[k]!r}. Pakai nama ({', '.join(COLORS)}) atau kode hex, mis. FFD400")
        cfg[k] = c
    return cfg


def ranged(kind, lo, hi):
    """Tipe argparse: angka dalam batas [lo, hi]."""
    def f(v):
        try:
            x = kind(v)
        except ValueError:
            raise argparse.ArgumentTypeError(f"bukan angka: {v!r}")
        if not lo <= x <= hi:
            raise argparse.ArgumentTypeError(f"harus antara {lo} dan {hi} (kamu isi {v})")
        return x
    return f


def build_parser():
    ap = argparse.ArgumentParser(prog="clipgaskeun", description="Potong video jadi Shorts 9:16 + subtitle.")
    ap.add_argument("input", nargs="?", help="file video lokal ATAU link YouTube (http...)")
    ap.add_argument("--cut", action="append", metavar="MULAI-SELESAI",
                    help="rentang waktu, boleh diulang untuk digabung (mis. 1:05-1:40). Untuk link = waktu di video YouTube")
    g0 = ap.add_argument_group("cari momen otomatis (pengganti --cut)")
    g0.add_argument("--auto", action="store_true", help="cari momen seru sendiri: Most Replayed YouTube, kerasnya suara, kepadatan obrolan")
    g0.add_argument("--auto-len", type=ranged(int, 15, 90), default=45, help="panjang tiap momen dalam detik, 15-90 (default 45)")
    g0.add_argument("--auto-n", type=ranged(int, 1, 10), default=5, help="jumlah kandidat yang ditampilkan, 1-10 (default 5)")
    g0.add_argument("--auto-cepat", action="store_true", help="lewati penilaian transkrip (lebih cepat, tanpa cuplikan kalimat)")
    g0.add_argument("--auto-model", default="base", help="model whisper untuk menilai kandidat (default base, cepat)")
    g0.add_argument("--pick", help="nomor kandidat yang langsung dirender, mis. 1 atau 1,3 (tanpa ditanya)")
    ap.add_argument("--json", action="store_true", help="keluaran JSON (untuk skrip / coding agent). Dengan --auto tanpa --pick: hanya daftar kandidat")
    ap.add_argument("-o", "--out", help="file hasil. Default: <nama>_short.mp4 di sebelah video asli (untuk link: clipgaskeun_short.mp4 di folder tempatmu menjalankan). Kalau sudah ada, otomatis diberi nomor _2, _3, ...")
    ap.add_argument("--preset", choices=sorted(PRESETS), help="gaya siap pakai: tiktok (karaoke kuning), podcast (kotak latar), gaming (karaoke hijau di atas)")
    ap.add_argument("--lang", default=None, help="bahasa ucapan, mis. id / en (default: dideteksi otomatis)")
    ap.add_argument("--model", default="small", help="model whisper (default small, semua bahasa; medium = lebih akurat tapi lambat; small.en = khusus Inggris)")
    ap.add_argument("--no-subs", action="store_true", help="tanpa subtitle")
    ap.add_argument("--srt", help="pakai SRT sendiri (waktu relatif awal hasil) alih-alih transkripsi")
    g = ap.add_argument_group("tampilan subtitle (kalau tidak diisi: ikut preset, lalu bawaan)")
    g.add_argument("--style", choices=["biasa", "karaoke"], default=None, help="karaoke = kata yang sedang diucapkan menyala")
    g.add_argument("--sub-pos", choices=list(POS), default=None, help="posisi subtitle (default bawah)")
    g.add_argument("--sub-color", default=None, help="warna teks: nama (putih, kuning, hijau, ...) atau hex FFFFFF")
    g.add_argument("--highlight", default=None, help="warna kata yang menyala di gaya karaoke (default kuning)")
    g.add_argument("--sub-bg", choices=["tidak", "kotak"], default=None, help="kotak gelap di belakang subtitle")
    g.add_argument("--font", default=None, help="nama font subtitle (default Poppins)")
    g.add_argument("--font-size", type=ranged(int, 4, 40), default=None, help="ukuran subtitle 4-40 (default 10)")
    ap.add_argument("--logo", help="PNG watermark (pojok kiri atas)")
    ap.add_argument("--logo-scale", type=ranged(float, 0.05, 3.0), default=None, help="ukuran logo 0.05-3 (default 0.62)")
    ap.add_argument("--keep-tmp", action="store_true", help="jangan hapus folder kerja sementara")
    ap.add_argument("--cek", action="store_true", help="periksa ffmpeg, faster-whisper, yt-dlp, dll. lalu keluar")
    ap.add_argument("--version", action="version", version=f"ClipGaskeun {__version__}")
    return ap


def default_out(a, url_mode, suffix="short"):
    return f"clipgaskeun_{suffix}.mp4" if url_mode else os.path.splitext(a.input)[0] + f"_{suffix}.mp4"


def render_clip(a, cfg, url_mode, ytdlp, cuts, labels, out):
    """Potong + subtitle + komposisi 9:16 untuk satu hasil. cuts = [(mulai, selesai)] dalam detik."""
    total = sum(ce - cs for cs, ce in cuts)
    if total > LONG_WARN and not a.no_subs and not a.srt:
        warn(f"total potongan {hms(total)}. Transkripsi akan lama dan makan RAM; pertimbangkan potongan lebih pendek.")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cfg = dict(cfg)
    tmp = tempfile.mkdtemp(prefix="clipgaskeun_")
    try:
        # 0) siapkan sumber tiap bagian: file lokal, atau unduh hanya bagian itu dari link
        n = len(cuts)
        segs = []  # (file, mulai, selesai) -- waktu relatif terhadap file itu
        if url_mode:
            for i, (cs, ce) in enumerate(cuts):
                say(f"[0/3] mengunduh bagian {i+1}/{n} dari link (hanya bagian itu) ...", "bold cyan")
                f, ds = download_section(ytdlp, a.input, cs, ce, os.path.join(tmp, f"dl{i}"))
                segs.append((f, cs - ds, ce - ds))
        else:
            segs = [(a.input, cs, ce) for cs, ce in cuts]

        # cek tiap sumber: rentang masih di dalam video? ada audionya?
        audio_of = {}
        for i, (f, cs, ce) in enumerate(segs):
            fdur, has_a = probe(f)
            audio_of.setdefault(f, has_a)
            if url_mode and fdur is not None and ce > fdur + 0.5:
                die(f"Rentang {labels[i]!r} melewati akhir video YouTube-nya. Cek lagi waktunya.")
        silent = not any(audio_of.values())
        if silent:
            note("video tidak punya suara -> diproses tanpa audio dan tanpa subtitle otomatis")

        # 1) potong (dan gabung) -> klip mentah 16:9. Presisi frame karena re-encode.
        raw = os.path.join(tmp, "raw.mp4")
        files = []
        for f, _, _ in segs:
            if f not in files:
                files.append(f)
        inputs = []
        for f in files:
            inputs += ["-i", f]
        fc = ""
        for i, (f, cs, ce) in enumerate(segs):
            k = files.index(f)
            # setpts di depan: timestamp file hasil unduhan tidak selalu mulai dari 0
            fc += f"[{k}:v]setpts=PTS-STARTPTS,trim={cs}:{ce},setpts=PTS-STARTPTS,fps=30[v{i}];"
            d = ce - cs
            fd = min(0.06, d / 4)  # fade tidak boleh lebih panjang dari klipnya
            fmt = "aformat=sample_rates=48000:channel_layouts=stereo"
            if audio_of[f]:
                fc += (f"[{k}:a]asetpts=PTS-STARTPTS,atrim={cs}:{ce},asetpts=PTS-STARTPTS,{fmt},"
                       f"afade=t=in:d={fd:.3f},afade=t=out:st={d-fd:.3f}:d={fd:.3f}[a{i}];")
            else:  # sumber tanpa suara -> isi dengan hening supaya gabungan tetap jalan
                fc += f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.3f},{fmt}[a{i}];"
        fc += "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
        step(1, f"memotong {n} bagian ...")
        with busy("memotong"):
            run(["ffmpeg", "-y", "-v", "error"] + inputs + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", raw])

        # 2) subtitle: ditranskripsi dari potongan itu sendiri -> waktu selalu pas
        lines = []
        if a.srt:
            step(2, "subtitle dari file SRT")
            lines = parse_srt(a.srt)
            if cfg["style"] == "karaoke":
                note("SRT tidak punya waktu per kata -> gaya karaoke diganti biasa")
                cfg["style"] = "biasa"
        elif a.no_subs:
            step(2, "tanpa subtitle")
        elif silent:
            step(2, "tanpa subtitle (video tidak bersuara)")
        else:
            step(2, "transkripsi (pertama kali akan mengunduh model) ...")
            with busy(f"mendengarkan dengan model {a.model}"):
                words, detected = transcribe(raw, a.lang, a.model)
            if detected:
                note(f"bahasa terdeteksi: {detected[0]} ({detected[1]:.0%}). Salah? ulangi dengan --lang id / --lang en")
            note(f"{len(words)} kata")
            if words:
                lines = group_lines(words, max_words=4 if cfg["style"] == "karaoke" else 6)
            else:
                note("tidak ada ucapan terdeteksi -> dirender tanpa subtitle")

        # 3) komposisi 9:16: latar blur + video di tengah + subtitle + logo
        step(3, "render 9:16 ...")
        chain = ("[0:v]split=2[a][b];[a]scale=540:960:force_original_aspect_ratio=increase,crop=540:960,"
                 "boxblur=15:2,scale=1080:1920,eq=brightness=-0.08[bg];[b]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2-120[c]")
        last = "c"
        if lines:
            open(os.path.join(tmp, "subs.ass"), "w", encoding="utf-8").write(build_ass(lines, cfg))
            chain += f";[{last}]subtitles=subs.ass[s]"; last = "s"  # ffmpeg dijalankan dari folder tmp
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", os.path.abspath(raw)]
        if a.logo:
            cmd += ["-i", os.path.abspath(a.logo)]
            chain += f";[1:v]format=rgba,scale=iw*{cfg['logo_scale']}:-1[w];[{last}][w]overlay=40:118[o]"; last = "o"
        cmd += ["-filter_complex", chain, "-map", f"[{last}]", "-map", "0:a", "-r", "30",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", os.path.abspath(out)]
        with busy("merender"):
            run(cmd, cwd=tmp)
        say(f"Selesai: {out}", "bold green")
        return out
    finally:
        if a.keep_tmp:
            say(f"tmp: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.json:
        set_json_mode()
    if a.cek:
        sys.exit(print_check())
    if not a.input or not (a.cut or a.auto):
        ap.error("butuh video/link dan --cut (atau --auto). Contoh: clipgaskeun video.mp4 --cut 1:05-1:40  (cek kelengkapan: clipgaskeun --cek)")
    if a.cut and a.auto:
        ap.error("pilih salah satu: --cut (kamu tentukan sendiri) atau --auto (dicarikan)")
    if a.pick and not a.auto:
        ap.error("--pick hanya dipakai bersama --auto")
    cfg = resolve(a)

    if not shutil.which("ffmpeg"):
        die("ffmpeg tidak ditemukan di PATH. Jalankan `clipgaskeun --cek` untuk cara memasangnya.")
    url_mode = is_url(a.input)
    if not url_mode and not os.path.isfile(a.input):
        die(f"File tidak ada: {a.input}")
    ytdlp = None
    if url_mode:
        ytdlp = find_ytdlp()
        if not ytdlp:
            die("yt-dlp belum terpasang (dibutuhkan untuk link). Pasang: winget install yt-dlp  atau  pip install yt-dlp")
    if a.logo and not os.path.isfile(a.logo):
        die(f"File logo tidak ada: {a.logo}")
    if a.srt and not os.path.isfile(a.srt):
        die(f"File SRT tidak ada: {a.srt}")
    if a.srt and a.auto:
        die("--srt tidak bisa dipakai bersama --auto (waktunya tidak akan cocok dengan momen yang dipilih)")
    if re.search(r"[',:;\\\[\]=]", cfg["font"]):
        die(f"Nama font tidak boleh berisi karakter ' , : ; \\ [ ] = (kamu isi {cfg['font']!r})")

    say(f"ClipGaskeun {__version__}" + (f" · preset {a.preset}" if a.preset else ""), "bold")
    result = {"version": __version__, "input": a.input}

    if not a.auto:
        cuts = []
        for c in a.cut:
            r = parse_cut(c)
            if isinstance(r, str):
                die(r)
            cuts.append(r)
        if not url_mode:
            dur, _ = probe(a.input)
            if dur is not None:
                for (cs, ce), c in zip(cuts, a.cut):
                    if cs >= dur:
                        die(f"Rentang {c!r} dimulai setelah video habis (panjang video {hms(dur)}).")
                    if ce > dur + 0.5:
                        die(f"Rentang {c!r} melewati akhir video (panjang video {hms(dur)}). Ganti waktu selesainya.")
        out = a.out or unique_path(default_out(a, url_mode))  # nama otomatis tidak menimpa hasil lama
        result["outputs"] = [render_clip(a, cfg, url_mode, ytdlp, cuts, a.cut, out)]
    else:
        tmp = tempfile.mkdtemp(prefix="clipgaskeun_auto_")
        try:
            cands, method = find_moments(a, url_mode, ytdlp, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        result.update(method=method, candidates=[
            {k: (round(c[k], 2) if isinstance(c[k], float) else c[k]) for k in ("rank", "start", "end", "score", "reason", "snippet")}
            for c in cands])
        show_candidates(cands)
        if a.pick:
            picks = parse_pick(a.pick, len(cands))
            if not picks:
                die(f"--pick tidak valid: {a.pick!r}. Isi nomor 1-{len(cands)}, mis. 1 atau 1,3")
        elif a.json or not sys.stdin.isatty():
            picks = []  # mode skrip: cukup daftar kandidat
        else:
            while True:
                ans = input(f"Pilih nomor yang dirender (mis. 1 atau 1,3; Enter = 1; q = batal): ").strip().lower()
                if ans == "q":
                    picks = []
                    break
                picks = parse_pick(ans or "1", len(cands))
                if picks:
                    break
                say(f"Isi nomor 1-{len(cands)}, pisahkan dengan koma.", "yellow")
        outputs = []
        for p in picks:
            c = cands[p - 1]
            say(f"Momen #{p}: {hms(c['start'])} - {hms(c['end'])}", "bold")
            if a.out:
                base, ext = os.path.splitext(a.out)
                out = a.out if len(picks) == 1 else f"{base}_{p}{ext or '.mp4'}"
            else:
                out = unique_path(default_out(a, url_mode, f"auto{p}"))
            outputs.append(render_clip(a, cfg, url_mode, ytdlp, [(c["start"], c["end"])], [f"auto #{p}"], out))
        result["outputs"] = outputs
        if not picks and not a.json:
            say("Tidak ada yang dirender. Untuk merender nanti: tambahkan --pick NOMOR, atau pakai --cut dengan rentang di tabel.", "yellow")
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def double_clicked():
    """Versi .exe dibuka dengan klik dua kali (tanpa argumen): jelaskan cara pakai, cek kelengkapan, lalu tunggu
    Enter supaya jendelanya tidak langsung tertutup."""
    say(f"ClipGaskeun {__version__}", "bold")
    say("Ini program terminal: jalankan lewat Command Prompt / PowerShell di folder ini, misalnya:\n"
        "  clipgaskeun.exe video.mp4 --cut 1:05-1:40 --preset tiktok\n"
        "  clipgaskeun.exe \"https://www.youtube.com/watch?v=ID\" --auto\n"
        "Semua opsi: clipgaskeun.exe --help\n")
    print_check()
    try:
        input("\nTekan Enter untuk menutup...")
    except EOFError:
        pass


if __name__ == "__main__":
    if FROZEN and sys.argv[1:3] == ["-m", "yt_dlp"]:
        sys.exit(run_bundled_ytdlp(sys.argv[3:]))
    if FROZEN and len(sys.argv) == 1:
        double_clicked()
        sys.exit(0)
    main()
