#!/usr/bin/env python3
"""wordcaptions: word-by-word highlighted captions ("karaoke style") for short videos, fully offline.

  python wordcaptions.py clip.mp4                 # -> clip_captioned.mp4 + clip.ass
  python wordcaptions.py clip.mp4 --render-only   # re-burn after editing clip.ass

How it works: faster-whisper returns a start/end time for every word. We group words into short
captions and write an Advanced SubStation Alpha (.ass) file with one event per spoken word, in which
that word is coloured and slightly enlarged. ffmpeg (libass) burns the .ass into the video.

MIT License. https://github.com/philippprimisser-max/whisper-word-captions
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__version__ = "0.1.0"


@dataclass
class Word:
    text: str
    start: float
    end: float


# ---------------------------------------------------------------- grouping

def group_words(words: list[Word], max_words: int = 3, max_pause: float = 0.6) -> list[list[Word]]:
    """Split into captions of <= max_words; also break after sentence punctuation or a longer pause."""
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (len(cur) >= max_words or w.start - cur[-1].end > max_pause
                    or re.search(r"[.!?…:;]$", cur[-1].text)):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


# ---------------------------------------------------------------- ASS

def ass_time(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_color(hex_rgb: str) -> str:
    """'#FFD400' -> ASS '&H0000D4FF' (ASS uses BGR with alpha first)."""
    h = hex_rgb.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"colour must look like #RRGGBB, got {hex_rgb!r}")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


ALIGN = {"bottom": 2, "middle": 5, "top": 8}


def build_ass(groups: list[list[Word]], width: int, height: int, *, font: str = "DejaVu Sans",
              size_pct: float = 6.5, highlight: str = "#FFD400", position: str = "bottom",
              uppercase: bool = True, scale: int = 115) -> str:
    font_size = round(min(width, height) * size_pct / 100 * (1.0 if height >= width else 0.8))
    margin_v = round(height * 0.18) if position == "bottom" else round(height * 0.08)
    hl = ass_color(highlight)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,{font},{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{max(2, font_size // 14)},{max(1, font_size // 30)},{ALIGN[position]},{round(width * 0.08)},{round(width * 0.08)},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for g in groups:
        texts = [escape_ass(w.text.strip().upper() if uppercase else w.text.strip()) for w in g]
        for i, w in enumerate(g):
            start = w.start
            # keep the caption on screen until the next word starts (no flicker in short pauses)
            end = g[i + 1].start if i + 1 < len(g) else max(w.end, w.start + 0.05)
            parts = []
            for j, t in enumerate(texts):
                if j == i:
                    parts.append(f"{{\\c{hl}\\fscx{scale}\\fscy{scale}}}{t}{{\\r}}")
                else:
                    parts.append(t)
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Word,,0,0,0,,{' '.join(parts)}")
    return header + "\n".join(lines) + "\n"


def to_srt(groups: list[list[Word]]) -> str:
    def t(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{i}\n{t(g[0].start)} --> {t(g[-1].end)}\n{' '.join(w.text.strip() for w in g)}\n"
                     for i, g in enumerate(groups, 1))


# ---------------------------------------------------------------- media

def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        sys.exit(f"Error: {tool} not found. Install ffmpeg (it includes ffprobe) and make sure it is on PATH.")
    return path


def video_size(path: Path) -> tuple[int, int]:
    out = subprocess.run([need("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:stream_side_data=rotation", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    st = json.loads(out)["streams"][0]
    w, h = int(st["width"]), int(st["height"])
    rot = next((abs(int(sd.get("rotation", 0))) for sd in st.get("side_data_list", []) if "rotation" in sd), 0)
    return (h, w) if rot in (90, 270) else (w, h)


def transcribe_words(path: Path, model: str, language: str | None, threads: int) -> list[Word]:
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads)
    segments, info = m.transcribe(str(path), language=language, word_timestamps=True, vad_filter=True,
                                  condition_on_previous_text=False)
    words = [Word(w.word.strip(), w.start, w.end) for s in segments for w in (s.words or []) if w.word.strip()]
    print(f"Language {info.language}, {len(words)} words.", file=sys.stderr)
    return words


def ffmpeg_filter_path(p: Path) -> str:
    # the subtitles filter needs ':' and '\' escaped (Windows drive letters)
    return str(p).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def burn(video: Path, ass: Path, out: Path, fonts_dir: Path | None = None, crf: int = 20) -> None:
    vf = f"subtitles='{ffmpeg_filter_path(ass)}'"
    if fonts_dir:
        vf += f":fontsdir='{ffmpeg_filter_path(fonts_dir)}'"
    cmd = [need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vf", vf,
           "-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy",
           str(out)]
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wordcaptions.py", description="Word-by-word highlighted captions, offline.")
    p.add_argument("video", type=Path)
    p.add_argument("--model", default="small", help="tiny, base, small (default), medium, ...")
    p.add_argument("--language", default=None, help="en, de, ... (default: auto-detect)")
    p.add_argument("--words", type=int, default=3, help="max words per caption (default 3)")
    p.add_argument("--highlight", default="#FFD400", help="colour of the spoken word, #RRGGBB")
    p.add_argument("--font", default="DejaVu Sans", help="installed font family (default DejaVu Sans)")
    p.add_argument("--fonts-dir", type=Path, help="folder with .ttf/.otf files to use for --font")
    p.add_argument("--size", type=float, default=6.5, help="font size in %% of the shorter video side (6.5)")
    p.add_argument("--position", choices=list(ALIGN), default="bottom")
    p.add_argument("--no-uppercase", action="store_true")
    p.add_argument("--srt", action="store_true", help="also write a plain .srt")
    p.add_argument("--threads", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    p.add_argument("--render-only", action="store_true", help="burn the existing .ass without transcribing")
    p.add_argument("--no-burn", action="store_true", help="only write the .ass (and .srt)")
    p.add_argument("--version", action="version", version=__version__)
    a = p.parse_args(argv)

    if not a.video.is_file():
        sys.exit(f"Error: file not found: {a.video}")
    ass_path = a.video.with_suffix(".ass")
    out_path = a.video.with_name(f"{a.video.stem}_captioned.mp4")
    if not a.render_only:
        width, height = video_size(a.video)
        words = transcribe_words(a.video, a.model, a.language, a.threads)
        if not words:
            sys.exit("Error: no speech found.")
        groups = group_words(words, a.words)
        ass_path.write_text(build_ass(groups, width, height, font=a.font, size_pct=a.size, highlight=a.highlight,
                                      position=a.position, uppercase=not a.no_uppercase), encoding="utf-8")
        print(f"Wrote {ass_path} ({len(groups)} captions). Fix typos there and re-run with --render-only.",
              file=sys.stderr)
        if a.srt:
            a.video.with_suffix(".srt").write_text(to_srt(groups), encoding="utf-8")
    elif not ass_path.is_file():
        sys.exit(f"Error: {ass_path} not found; run once without --render-only.")
    if not a.no_burn:
        burn(a.video, ass_path, out_path, a.fonts_dir)
        print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
