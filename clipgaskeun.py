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

__version__ = "0.2.0"

# ───────────── tampilan terminal: pakai rich kalau ada, kalau tidak teks biasa ─────────────
try:
    from rich.console import Console
    from rich.table import Table
    _out = Console(highlight=False)
    _err = Console(stderr=True, highlight=False)
except ImportError:
    _out = _err = None


def say(msg, style=None):
    if _out:
        _out.print(msg, style=style, markup=False)
    else:
        print(msg)


def step(n, msg):
    say(f"[{n}/3] {msg}", "bold cyan")


def note(msg):
    say(f"      {msg}", "dim")


def warn(msg):
    say(f"Catatan: {msg}", "yellow")


def die(msg):
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


def find_ytdlp():
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    if find_spec("yt_dlp"):
        return [sys.executable, "-m", "yt_dlp"]
    return None


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


def download_section(ytdlp, url, start, end, prefix):
    """Unduh hanya detik [start, end] (plus cadangan PAD) dari link.
    Mengembalikan (path file, detik video tempat file itu dimulai)."""
    ds = max(0, int(start) - PAD)
    de = int(math.ceil(end)) + PAD
    cmd = ytdlp + ["--no-playlist", "--download-sections", f"*{hms(ds)}-{hms(de)}",
                   "--force-keyframes-at-cuts", "-f", "bv*[height<=1080]+ba/b",
                   "--merge-output-format", "mp4", "-o", prefix + ".%(ext)s", url]
    if subprocess.run(cmd).returncode:
        die("yt-dlp gagal mengunduh (pesan di atas). Coba perbarui: pip install -U yt-dlp  (atau: winget upgrade yt-dlp)")
    f = prefix + ".mp4"
    if not os.path.isfile(f):
        die("File hasil unduhan tidak ditemukan.")
    return f, ds


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
}


def check_deps():
    """Daftar (nama, wajib?, ada?, keterangan)."""
    rows = [("Python 3.9+", True, sys.version_info >= (3, 9), sys.version.split()[0])]
    for tool in ("ffmpeg", "ffprobe"):
        p = shutil.which(tool)
        rows.append((tool, tool == "ffmpeg", bool(p), p or INSTALL_HINT[tool]))
    fw = find_spec("faster_whisper") is not None
    rows.append(("faster-whisper", False, fw, "untuk subtitle otomatis" if fw else INSTALL_HINT["faster-whisper"]))
    yt = find_ytdlp()
    rows.append(("yt-dlp", False, bool(yt), "untuk link YouTube" if yt else INSTALL_HINT["yt-dlp"]))
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
    m = WhisperModel(model, device="cpu", compute_type="int8")
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


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.cek:
        sys.exit(print_check())
    if not a.input or not a.cut:
        ap.error("butuh video/link dan minimal satu --cut. Contoh: clipgaskeun video.mp4 --cut 1:05-1:40  (cek kelengkapan: clipgaskeun --cek)")
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
    if re.search(r"[',:;\\\[\]=]", cfg["font"]):
        die(f"Nama font tidak boleh berisi karakter ' , : ; \\ [ ] = (kamu isi {cfg['font']!r})")
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
    total = sum(ce - cs for cs, ce in cuts)
    if total > LONG_WARN and not a.no_subs and not a.srt:
        warn(f"total potongan {hms(total)}. Transkripsi akan lama dan makan RAM; pertimbangkan potongan lebih pendek.")
    out = a.out or ("clipgaskeun_short.mp4" if url_mode else os.path.splitext(a.input)[0] + "_short.mp4")
    if not a.out:  # nama otomatis -> jangan menimpa hasil sebelumnya (kalau -o diberikan, itu pilihanmu)
        out = unique_path(out)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    say(f"ClipGaskeun {__version__}" + (f" · preset {a.preset}" if a.preset else ""), "bold")
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
                die(f"Rentang {a.cut[i]!r} melewati akhir video YouTube-nya. Cek lagi waktunya.")
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
    finally:
        if a.keep_tmp:
            say(f"tmp: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
