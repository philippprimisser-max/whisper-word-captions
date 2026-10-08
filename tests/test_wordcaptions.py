import os
import shutil
import subprocess
from pathlib import Path

import pytest

import wordcaptions as wc

W = wc.Word


def test_group_words_limits_and_breaks():
    words = [W("Four", 0.0, 0.3), W("score", 0.3, 0.6), W("and", 0.6, 0.7), W("seven", 0.7, 1.0),
             W("years.", 1.0, 1.4), W("Now", 1.5, 1.7), W("we", 3.0, 3.1)]
    g = wc.group_words(words, max_words=3)
    assert [[w.text for w in x] for x in g] == [["Four", "score", "and"], ["seven", "years."], ["Now"], ["we"]]


def test_ass_color():
    assert wc.ass_color("#FFD400") == "&H0000D4FF"
    assert wc.ass_color("00ff00") == "&H0000FF00"
    with pytest.raises(ValueError):
        wc.ass_color("yellow")


def test_ass_time():
    assert wc.ass_time(0) == "0:00:00.00"
    assert wc.ass_time(3725.257) == "1:02:05.26"


def test_build_ass_one_event_per_word():
    g = [[W("hello", 0.0, 0.4), W("{world}", 0.5, 0.9)]]
    ass = wc.build_ass(g, 1080, 1920, highlight="#00FF00")
    events = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert len(events) == 2
    assert events[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.50,Word")  # held until next word starts
    assert "{\\c&H0000FF00\\fscx115\\fscy115}HELLO{\\r} (WORLD)" in events[0]
    assert "HELLO {\\c&H0000FF00" in events[1]
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass


def test_srt():
    g = [[W("a", 0, 0.5), W("b", 0.5, 1.25)]]
    assert wc.to_srt(g) == "1\n00:00:00,000 --> 00:00:01,250\na b\n"


def test_filter_path_escaping():
    assert wc.ffmpeg_filter_path(Path("C:\\clips\\my clip.ass")) in ("C\\:/clips/my clip.ass",)


@pytest.mark.skipif(os.environ.get("SKIP_SLOW") == "1" or not shutil.which("ffmpeg"), reason="slow / no ffmpeg")
def test_end_to_end(tmp_path):
    audio = Path(__file__).parent / "fixtures" / "gettysburg.mp3"
    video = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x223344:s=540x960:d=12",
                    "-ss", "18", "-t", "12", "-i", str(audio), "-shortest", "-c:v", "libx264", "-c:a", "aac",
                    str(video)], check=True)
    assert wc.main([str(video), "--model", "tiny", "--language", "en", "--srt"]) == 0
    ass = (tmp_path / "clip.ass").read_text()
    assert ass.count("Dialogue:") >= 10
    out = tmp_path / "clip_captioned.mp4"
    assert out.is_file() and out.stat().st_size > 10_000
    assert (tmp_path / "clip.srt").is_file()
    # render-only re-burns without transcribing
    out.unlink()
    assert wc.main([str(video), "--render-only"]) == 0 and out.is_file()
