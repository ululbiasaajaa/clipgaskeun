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
