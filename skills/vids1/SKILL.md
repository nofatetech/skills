---
name: vids1
description: Write, render, and check animated videos with Vids1, a Godot tool that turns a Markdown script into a cartoon (flat characters, offline TTS voices, captions, music). Use when asked to make a Vids1 video/episode, write an episode script, render one wide/vertical/square, or check a render.
---

# Vids1: Markdown script → video

Vids1 lives in `Vids1/vids-1` of https://github.com/nofatetech/LeoLucasGame1. All paths below are relative to that folder. Its code is the source of truth for what a script can say; `docs/timeline-spec.md` describes the format but also lists planned verbs that are not built yet.

## Setup (once per machine)
Done when `./render.sh cow` ends with `render.sh: done` and the log says `tts=on`.
1. Clone the repo; install Godot 4.x and ffmpeg (both on `PATH`).
2. Piper TTS: extract the [piper release](https://github.com/rhasspy/piper/releases) so the binary is `~/Apps/piper/piper` (or set `VIDS_PIPER_BIN`), and put each voice's `.onnx` + `.onnx.json` from [piper-voices](https://huggingface.co/rhasspy/piper-voices) in `~/Apps/piper/voices/`. Needed voices: `grep -rhoE "[a-z]{2}_[A-Z]{2}-[a-z_]+-(x_low|low|medium|high)" universes | sort -u`. Without Piper, lines play as beeps (`tts=off (tone)`).
3. First run on a fresh clone: `godot --headless --path . --import`.

## Make a video

1. **Write** `episodes/<name>.md`. Copy the shape of an existing episode (`episodes/cow.md` is short; `episodes/promo_vids1.md` uses moods and `style:`). Pick from what exists:
   - cast: character ids in `universes/*/characters/` (`cast: { alias: id }` in frontmatter)
   - directives: the `match verb` in `_normalize()` of `domains/script/script_parser.gd`
   - `[sfx: …]` and `[music: …]` names: `SFX` / `MUSIC` in `domains/audio/audio_library.gd` (procedural placeholders)
   - `{mood: …}` on a `## Scene:` line: `domains/mood/mood_library.gd`
   - `style:`: `BUILTIN` in `domains/style/style_library.gd`, or `universes/<u>/styles/<id>.tres`
   Lines are `alias: (emote) text`; dialogue is the clock, so time everything relative to lines and `[wait: s]`, never absolute seconds. Set `language:` (`en`/`es`) to match the cast's voices.
2. **Render** — `./render.sh <name> [style] [--lang <code>]` → `output/<name>[_<style>].mp4`. It needs a display (`xvfb-run` is used when there is none); a Godot window flashes during the render. Done when it prints `render.sh: done` with no `WARNING: Directive not yet supported` lines (each one is a directive that silently did nothing: rewrite it with a supported verb).
3. **Check** — `<this skill's folder>/scripts/inspect.sh output/<name>.mp4`, then Read the `_sheet.png` it writes. Done when every one of these holds:
   - size matches the style (wide 1280×720, vertical 1080×1920, square 1080×1080)
   - audio present, `max_volume` near 0 dB, `mean_volume` above about −30 dB
   - every character fully in frame, captions readable, scene moods visible as background/grade changes
4. Report the MP4 path and duration. To publish it, hand the MP4 to the `shopify-publish` skill's `upload`.

## Gotchas
- `--headless` renders give 0-byte video (the dummy renderer can't draw). Audio-only work can run headless.
- A freshly added `class_name` is unknown to a headless run until the editor rescans: `preload()` the script by path instead, or the run fails to parse and hangs.
- Movie Maker bakes the resolution at launch, which is why `render.sh` writes `override.cfg` before starting. A leftover `override.cfg` makes `render.sh` stop; delete it if no render is running.
