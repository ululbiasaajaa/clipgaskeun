"""Tes cepat untuk bagian yang tidak butuh ffmpeg/whisper. Jalankan: python -m pytest"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import clipgaskeun as cg


def test_ts_valid():
    assert cg.ts("90") == 90
    assert cg.ts("1:30") == 90
    assert cg.ts("1:30.5") == 90.5
    assert cg.ts("4:09:41") == 4 * 3600 + 9 * 60 + 41
    assert cg.ts("75:00") == 4500  # menit boleh > 59 di format m:ss


def test_ts_invalid():
    for bad in ["1:99", "1::2", "1:60:00", "abc", "", "1:2:3:4", "-5"]:
        assert cg.ts(bad) is None, bad


def test_parse_cut():
    assert cg.parse_cut("1:05-1:40") == (65, 100)
    assert "Format waktu salah" in cg.parse_cut("1::05-1:40")
    assert "sesudah" in cg.parse_cut("5-3")
    assert "terlalu pendek" in cg.parse_cut("2-2.2")


def test_colors():
    assert cg.parse_color("kuning") == "FFD400"
    assert cg.parse_color("#ff0000") == "FF0000"
    assert cg.parse_color("nope") is None
    assert cg.ass_color("FF8000") == "&H000080FF"  # ASS = AABBGGRR
    assert cg.ass_color("000000", 0x60) == "&H60000000"


def test_ass_time_and_text():
    assert cg.ass_time(3723.456) == "1:02:03.46"
    assert cg.ass_text("a{b}\\c") == "a(b)/c"


def W(t, s, e):
    return {"text": t, "start": s, "end": e}


def test_group_lines_breaks_and_no_overlap():
    words = [W("Halo", 0, 0.3), W("semua.", 0.3, 0.8), W("Ini", 0.9, 1.0), W("tes", 2.5, 2.8)]
    lines = cg.group_lines(words)
    assert [l["text"] for l in lines] == ["Halo semua.", "Ini", "tes"]  # putus di titik & jeda > 0.7 s
    for a, b in zip(lines, lines[1:]):
        assert a["end"] <= b["start"]


def test_build_ass_karaoke_one_event_per_word():
    cfg = dict(cg.BASE, style="karaoke", sub_color="FFFFFF", highlight="FFD400")
    lines = cg.group_lines([W("satu", 0, 0.4), W("dua", 0.5, 0.9), W("tiga", 1.0, 1.4)])
    ass = cg.build_ass(lines, cfg)
    events = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(events) == 3
    assert "{\\c&H0000D4FF&}dua{\\r}" in events[1]
    assert "PlayResY: 1920" in ass


def test_build_ass_box_background():
    cfg = dict(cg.BASE, sub_bg="kotak", sub_color="FFFFFF", highlight="FFD400")
    ass = cg.build_ass([{"start": 0, "end": 1, "text": "x", "words": None}], cfg)
    style = next(l for l in ass.splitlines() if l.startswith("Style:"))
    assert style.split(",")[15] == "3"  # BorderStyle 3 = kotak


def test_parse_srt(tmp_path):
    p = tmp_path / "a.srt"
    srt = "\ufeff1\r\n00:00:01,500 --> 00:00:02,000\r\nHalo\r\ndunia\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,250\r\nlagi\r\n"
    for raw in (srt, srt.replace("\r\n", "\r\r\n"), srt.replace("\r\n", "\n")):  # Windows, rusak, Unix
        p.write_bytes(raw.encode("utf-8"))  # bytes: tanpa terjemahan baris baru otomatis dari OS
        lines = cg.parse_srt(str(p))
        assert len(lines) == 2
        assert lines[0]["start"] == 1.5 and lines[0]["text"] == "Halo\ndunia"
        assert lines[1]["end"] == 4.25


def test_preset_and_override():
    ap = cg.build_parser()
    cfg = cg.resolve(ap.parse_args(["v.mp4", "--cut", "1-3", "--preset", "tiktok"]))
    assert cfg["style"] == "karaoke" and cfg["font_size"] == 12
    cfg = cg.resolve(ap.parse_args(["v.mp4", "--cut", "1-3", "--preset", "tiktok", "--style", "biasa", "--font-size", "9"]))
    assert cfg["style"] == "biasa" and cfg["font_size"] == 9  # opsi yang ditulis menang atas preset
    cfg = cg.resolve(ap.parse_args(["v.mp4", "--cut", "1-3"]))
    assert cfg["style"] == "biasa" and cfg["sub_color"] == "FFFFFF"


# ───────────── --auto ─────────────
def test_heatmap_regions_skips_start_and_overlap():
    heat = [{"start_time": i * 10, "end_time": (i + 1) * 10, "value": v}
            for i, v in enumerate([1.0, 0.2, 0.9, 0.85, 0.1, 0.1, 0.7, 0.1, 0.1, 0.1])]
    r = cg.heatmap_regions(heat, 100, 20, 3)
    centers = [x["center"] for x in r]
    assert 5 not in centers                  # bin pertama (0-10 s) dilewati
    assert centers[0] == 25                  # puncak berikutnya
    assert 35 not in centers                 # terlalu dekat dengan 25
    assert all(0 <= x["start"] < x["end"] <= 100 for x in r)


def test_loud_windows_finds_loud_part():
    db = [-40.0] * 60 + [-15.0] * 10 + [-40.0] * 60
    (s, e, _), = cg.loud_windows(db, 10, 1)
    assert 55 <= s <= 65 and e - s == 10


def test_snap_window_moves_to_sentence_edges():
    words = [W("Halo.", 0.0, 0.5), W("Ini", 1.5, 1.7), W("kalimat", 1.8, 2.2), W("panjang", 2.3, 2.7),
             W("sekali.", 2.8, 3.2), W("Lalu", 4.5, 4.8)]
    t0, t1 = cg.snap_window(words, 2.0, 2.9, 0, 10)
    assert abs(t0 - 1.35) < 1e-6           # mundur ke awal kalimat "Ini ..."
    assert abs(t1 - 3.55) < 1e-6           # maju ke akhir "sekali."


def test_parse_pick_and_dedupe():
    assert cg.parse_pick("1,3", 5) == [1, 3]
    assert cg.parse_pick("3 1 3", 5) == [3, 1]
    assert cg.parse_pick("0", 5) is None and cg.parse_pick("x", 5) is None and cg.parse_pick("6", 5) is None
    cands = [{"start": 0, "end": 10}, {"start": 2, "end": 12}, {"start": 20, "end": 30}]
    assert [c["start"] for c in cg.dedupe(cands)] == [0, 20]


def test_cli_rules():
    import pytest
    ap = cg.build_parser()
    a = ap.parse_args(["v.mp4", "--auto", "--auto-len", "30"])
    assert a.auto and a.auto_len == 30 and a.auto_model == "base"
    with pytest.raises(SystemExit):
        ap.parse_args(["v.mp4", "--auto", "--auto-len", "5"])


def test_loud_windows_are_spread_out():
    db = [-40.0] * 3600
    for start in (1000, 1060, 1120, 2500):  # tiga puncak berdekatan + satu jauh
        db[start:start + 20] = [-10.0] * 20
    picks = cg.loud_windows(db, 45, 2)
    starts = sorted(s for s, _, _ in picks)
    assert starts[1] - starts[0] >= 135      # kandidat kedua tidak boleh tetangga kandidat pertama


def _fake_tool(folder, name):
    """Buat file 'program' palsu yang bisa dijalankan (di Windows perlu akhiran .exe)."""
    p = folder / (name + (".exe" if os.name == "nt" else ""))
    p.write_text("x")
    p.chmod(0o755)
    return p


def test_which_safe_returns_full_path_and_skips_cwd(tmp_path, monkeypatch):
    bin_dir, work = tmp_path / "bin", tmp_path / "work"
    bin_dir.mkdir(); work.mkdir()
    real = _fake_tool(bin_dir, "faketool")
    _fake_tool(work, "decoytool")                      # 'program palsu' di folder tempat terminal dibuka
    monkeypatch.chdir(work)
    monkeypatch.setenv("PATHEXT", ".EXE")
    monkeypatch.setenv("PATH", os.pathsep.join([".", "relbin", str(bin_dir)]))
    assert cg.which_safe("faketool") == str(real)      # path lengkap, bukan sekadar nama
    assert os.path.isabs(cg.which_safe("faketool"))
    assert cg.which_safe("decoytool") is None          # folder kerja / PATH relatif tidak dipercaya


def test_tool_dies_when_missing(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(SystemExit):
        cg.tool("tidak-ada-program-ini")


def test_no_bare_tool_names_in_commands():
    """Penjaga: ffmpeg/ffprobe tidak boleh dipanggil hanya dengan namanya (lihat which_safe)."""
    src = open(cg.__file__, encoding="utf-8").read()
    assert '["ffmpeg"' not in src and '["ffprobe"' not in src
    assert '"ffmpeg", "-' not in src


# ───────────── webcam streamer: --cam / --layout ─────────────
def test_parse_cam():
    assert cg.parse_cam("1480,40,400,300") == (1480, 40, 400, 300)
    assert cg.parse_cam(" 10 , 20 , 320 , 240 ") == (10, 20, 320, 240)
    for bad in ["", "1,2,3", "a,b,c,d", "1,2,3,4,5", "0,0,4,4", "-1,0,100,100"]:
        assert isinstance(cg.parse_cam(bad), str), bad


def test_parse_layout_single_and_timeline():
    assert cg.parse_layout("split", 10) == [(0.0, 10.0, "split")]
    segs = cg.parse_layout("0-5:split,5-12:pip-kanan-atas,12-:wajah-penuh", 20)
    assert [(round(a), round(b), n) for a, b, n in segs] == [(0, 5, "split"), (5, 12, "pip-kanan-atas"), (12, 20, "wajah-penuh")]
    # waktu dalam menit:detik, dan rentang melewati akhir klip dipotong
    segs = cg.parse_layout("0-0:30:game-penuh", 20)
    assert isinstance(segs, (list, str))  # '0:30' di dalam rentang membingungkan -> tidak boleh crash


def test_parse_layout_gaps_free_pip_and_errors():
    segs = cg.parse_layout("2-4:game-penuh", 6)       # bagian yang tidak disebut = split
    assert [n for _, _, n in segs] == ["split", "game-penuh", "split"]
    segs = cg.parse_layout("0-3:pip@79,12,3-:pip-kiri-bawah", 6)
    assert [n for _, _, n in segs] == ["pip@79,12", "pip-kiri-bawah"]
    for bad in ["", "nope", "0-5:nope", "5-3:split", "0-5:split,3-8:game-penuh", "pip@120,5", "0-x:split"]:
        assert isinstance(cg.parse_layout(bad, 10), str), bad


def test_auto_focus_avoids_cam():
    # video 1280x720, webcam di pojok kanan atas, panel 1080x960 (rasio 1.125) -> lebar jendela 810
    f = cg.auto_focus((1280, 720), (940, 20, 320, 240), 1080 / 960)
    ww = 720 * 1080 / 960
    x0 = f / 100 * (1280 - ww)
    assert x0 + ww <= 940 + 1e-6            # jendela game berhenti sebelum webcam
    # webcam di tengah-bawah tidak bisa dihindari -> kembali ke tengah
    assert cg.auto_focus((1280, 720), (400, 500, 480, 200), 1080 / 960) == 50.0
    # sumber sudah sempit (vertikal) -> tidak ada yang dipotong
    assert cg.auto_focus((720, 1280), (0, 0, 200, 200), 1080 / 1920) == 50.0


def test_layout_chain_structure():
    segs = [(0.0, 3.0, "split"), (3.0, 6.0, "pip-kanan-atas"), (6.0, 8.0, "wajah-penuh"), (8.0, 10.0, "game-penuh")]
    fc = cg.build_layout_chain(segs, (940, 20, 320, 240), None, size=(1280, 720))
    assert "concat=n=4:v=1:a=0[c]" in fc and fc.count("setsar=1") == 4
    assert "crop=320:240:940:20" in fc
    one = cg.build_layout_chain([(0.0, 5.0, "split")], (940, 20, 320, 240), 50, size=(1280, 720))
    assert one.endswith("[c]") and "concat" not in one


def test_layout_requires_cam():
    import pytest
    with pytest.raises(SystemExit):
        cg.main(["v.mp4", "--cut", "1-5", "--layout", "split"])
    with pytest.raises(SystemExit):
        cg.main(["v.mp4", "--cut", "1-5", "--cam", "1,2,3"])
    with pytest.raises(SystemExit):
        cg.main(["v.mp4", "--cut", "1-5", "--cam", "10,10,100,100", "--layout", "0-5:nope"])


def _make_stream(tmp_path):
    """Video sumber 1280x720: latar warna-warni + 'webcam' (batang warna) di pojok kanan atas, ada suara."""
    import subprocess
    ff = cg.which_safe("ffmpeg")
    out = tmp_path / "stream.mp4"
    subprocess.run([ff, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=8",
                    "-f", "lavfi", "-i", "smptebars=size=320x240:rate=30:duration=8", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=8", "-filter_complex", "[0:v][1:v]overlay=940:20[v]", "-map", "[v]",
                    "-map", "2:a", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(out)], check=True)
    return out


def test_render_with_layout_changes(tmp_path):
    import pytest
    if not cg.which_safe("ffmpeg") or not cg.which_safe("ffprobe"):
        pytest.skip("butuh ffmpeg + ffprobe")
    src = _make_stream(tmp_path)
    out = tmp_path / "hasil.mp4"
    cg.main([str(src), "--cut", "1-7", "--cam", "940,20,320,240", "--no-subs", "-o", str(out),
             "--layout", "0-2:split,2-4:pip-kanan-atas,4-:wajah-penuh"])
    assert out.is_file()
    assert cg.video_size(str(out)) == (1080, 1920)
    dur, has_audio = cg.probe(str(out))
    assert abs(dur - 6) < 0.3 and has_audio     # panjang & suara tetap utuh walau tata letak berganti


def test_cam_preview_makes_images(tmp_path):
    import pytest
    if not cg.which_safe("ffmpeg") or not cg.which_safe("ffprobe"):
        pytest.skip("butuh ffmpeg + ffprobe")
    src = _make_stream(tmp_path)
    cg.main([str(src), "--cam", "940,20,320,240", "--cam-preview", "--cam-waktu", "2"])
    assert (tmp_path / "stream_cam.png").is_file() and (tmp_path / "stream_layout.png").is_file()
    import pytest as _p
    with _p.raises(SystemExit):   # kotak di luar video ditolak
        cg.main([str(src), "--cam", "1200,600,320,240", "--cam-preview"])
