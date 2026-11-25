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
    p.write_text("﻿1\r\n00:00:01,500 --> 00:00:02,000\r\nHalo\r\ndunia\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,250\r\nlagi\r\n", encoding="utf-8")
    lines = cg.parse_srt(str(p))
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
