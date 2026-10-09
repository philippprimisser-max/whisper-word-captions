# whisper-word-captions

Word-by-word highlighted captions (the Shorts/Reels/TikTok style) for your videos, made **offline** with faster-whisper and ffmpeg. No account, no upload, no watermark, no per-minute pricing. One Python file of about 200 lines that you can read and change.

![demo](docs/demo.gif)

```bash
python wordcaptions.py clip.mp4
# -> clip_captioned.mp4  and  clip.ass (editable)
```

## How it works

1. **faster-whisper** transcribes the audio with `word_timestamps=True`, so every word gets its own start and end time.
2. Words are grouped into short captions (max 3 words by default; a new caption also starts after `.?!` or a pause of more than 0.6 s).
3. For **each spoken word** one subtitle event is written to an `.ass` file (Advanced SubStation Alpha). The event shows the whole caption, with only the current word coloured and scaled up:
   ```
   Dialogue: 0,0:00:03.20,0:00:03.52,Word,,0,0,0,,{\c&H0000D4FF\fscx115\fscy115}THAT{\r} ALL MEN
   Dialogue: 0,0:00:03.52,0:00:03.68,Word,,0,0,0,,THAT {\c&H0000D4FF\fscx115\fscy115}ALL{\r} MEN
   ```
   Each event lasts until the next word starts, so nothing flickers during short pauses. (ASS colours are `&HAABBGGRR`, i.e. blue-green-red.)
4. **ffmpeg** burns the `.ass` into the picture with libass (`-vf subtitles=clip.ass`). Audio is copied unchanged.

Because the `.ass` file is plain text, you can fix misheard names and re-burn in seconds with `--render-only`.

## Install

You need Python 3.10–3.13 and ffmpeg (with libass, which the normal builds include).

```bash
# ffmpeg: Windows `winget install Gyan.FFmpeg` · macOS `brew install ffmpeg` · Debian/Ubuntu `sudo apt install ffmpeg`
git clone https://github.com/philippprimisser-max/whisper-word-captions
cd whisper-word-captions
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The first run downloads the speech model (small ≈ 490 MB). `requirements.txt` pins `av<19`, because PyAV 19 broke faster-whisper 1.2.1 on a fresh install in October 2026.

## Usage

```bash
python wordcaptions.py clip.mp4 --language en
python wordcaptions.py clip.mp4 --words 2 --highlight "#00E676" --position middle
python wordcaptions.py clip.mp4 --font "Montserrat ExtraBold" --fonts-dir ./fonts
python wordcaptions.py clip.mp4 --srt              # also a normal .srt for YouTube
python wordcaptions.py clip.mp4 --no-burn          # only write the .ass
python wordcaptions.py clip.mp4 --render-only      # after editing clip.ass
```

| Option | Default | |
|---|---|---|
| `--model` | small | `base` is faster and fine for clear English; non-English: `small` or bigger |
| `--language` | auto | set it, auto-detection can be wrong on short clips |
| `--words` | 3 | max words per caption |
| `--highlight` | `#FFD400` | colour of the spoken word |
| `--font` / `--fonts-dir` | DejaVu Sans | any installed font, or a folder with .ttf/.otf files |
| `--size` | 6.5 | font size in % of the shorter video side |
| `--position` | bottom | `bottom`, `middle`, `top` |
| `--no-uppercase` | | keep normal case |
| `--threads` | min(4, cores) | with int8, 8 threads dropped passages in 13/15 runs on one test machine, 4 threads in 1/15; fewer threads reduce the risk but don't remove it. Check with [faster-whisper-gap-check](https://github.com/philippprimisser-max/faster-whisper-gap-check) |

Measured on an 8-core x86-64 Linux server (`os.cpu_count()` = 8, default 4 threads, model already downloaded): a 15-second 1080×1920 clip took 6.1–6.7 s in total with `small` (model loading, transcription and rendering; two runs). The clip was made from the test audio, so you can repeat it:

```bash
ffmpeg -f lavfi -i color=c=0x1e1e2e:s=1080x1920:r=30:d=15 -i tests/fixtures/gettysburg.mp3 -t 15 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest clip.mp4
time python wordcaptions.py clip.mp4 --model small --language en
```

Your machine will differ.

## Limits

- Speech recognition makes mistakes; check the `.ass` before you publish.
- One style. If you want something fancier (bounce, emoji, per-word colours), the `.ass` override tags (`\t`, `\move`, `\blur`, …) are where to start.
- Fonts: if the font isn't found, libass silently falls back to another one. Use `--fonts-dir` to be sure.

## Tests

```bash
pip install pytest
python -m pytest -q        # includes one real run with the tiny model; SKIP_SLOW=1 to skip
```

Test and demo audio: [LibriVox](https://librivox.org) recording of the Gettysburg Address (public domain). The demo background is generated with ffmpeg.

## More small tools from the same workflow

- [podcast-to-text](https://github.com/philippprimisser-max/podcast-to-text): transcribe an episode from its RSS feed or Apple Podcasts link, locally.
- [faster-whisper-gap-check](https://github.com/philippprimisser-max/faster-whisper-gap-check): find speech that is missing from a Whisper transcript.

Write-ups: [DEV.to/@prime619](https://dev.to/prime619)

## Related

- [Word-by-Word Captions](https://pppioneer54.gumroad.com/l/word-by-word-captions) on Gumroad (pay what you want, 0 is fine): a packaged version of this idea with a bundled font (Montserrat, OFL) and step-by-step install guides in English and German. Disclosure: that's my product. This repository is free and fully usable on its own.
- [Short-Form Clip & Content Planner](https://pppioneer54.gumroad.com/l/clip-content-planner) on Gumroad (€12): a spreadsheet template (Excel and Google Sheets, English/German) for keeping clip ideas, a posting calendar and per-post stats in one place. Disclosure: also mine; you don't need it for anything in this repository.

## License

Code written with AI assistance and tested with the commands above.

MIT, see [LICENSE](LICENSE). Not affiliated with OpenAI, SYSTRAN, the ffmpeg or libass projects, TikTok, YouTube or Instagram.
