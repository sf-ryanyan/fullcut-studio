---
name: fullcut-studio
description: FullcutStudio - AI auto-editing. Give a folder of raw clips (path or name) and get a finished cut plus an editable edit list. Rough cut from one sentence, fine cut from a script or storyboard, re-render after editing the list, export a timeline to Premiere / DaVinci Resolve / Final Cut, and clean corner logos and outros from your own exported videos. Use for auto edit, rough cut, cut my footage, edit these clips, make a video from this folder, 自动剪辑, 粗剪, 精剪. Cuts only - no colour grading, no reframing.
---

# FullcutStudio

Turns a folder of raw clips into one finished video plus an edit list the user can check and change.
Runs locally with free tools (ffmpeg, Python). No API keys. Footage never leaves the computer.

**Language:** reply in the language the user writes in. Write CSVs with `--lang zh` for Chinese users, default English.

## Golden rules
1. **Cut only.** Never grade colour, change exposure, crop, reframe, rotate, add text, subtitles, music or effects.
2. **Never modify originals.** Everything is written to `<footage folder>/_autocut/`.
3. **One question round at most**, asked after looking at the footage, with recommended answers pre-selected. "Just cut it" / "直接剪" means ask nothing.
4. **Self-check before showing anything** (up to 3 fix passes).
5. **Every cut ships with its edit list** (CSV) and a short report.
6. **Save tokens:** read contact sheets (4 clips per image), not single frames; open dense strips only for hard decisions; reuse `labels.json` so footage is never watched twice.

## 0. Setup
The engine is `scripts/fullcut.py` in this skill folder. Run it **where the footage is** (video files are too big to upload):
- **Claude Code / terminal on the user's computer:** run it in place: `FC = python3 <skill folder>/scripts/fullcut.py`.
- **Claude desktop app linked to the computer:** commands run through `device_bash` (a Linux VM; connected folders are under `$HOME/mnt/<folder>`). Copy `scripts/fullcut.py` from the skill folder to `/mnt/user-data/outputs/fullcut.py`, then `device_commit_files` it into a connected folder (e.g. `<footage>/_autocut/fullcut.py`). If the footage folder is not connected, ask for it with `device_request_folder_access` (one request).
- **Clips uploaded into the chat:** run in the workspace.

Requirements: `ffmpeg`, `ffprobe`, `python3`, `numpy`, `opencv-python-headless` (optional: `faster-whisper` for speech).
- macOS: `brew install ffmpeg` · `python3 -m pip install --user numpy opencv-python-headless`
- Windows: `winget install Gyan.FFmpeg` · `py -m pip install numpy opencv-python-headless`
- Linux / VM: `apt-get install -y ffmpeg` (or `pip install static-ffmpeg && static_ffmpeg_paths`) · `pip install numpy opencv-python-headless`
Install only what is missing; tell the user in one line.

**Preferences:** `~/.fullcut/preferences.json` (or `_autocut/../.fullcut-preferences.json` next to the footage in the VM). Read it first; never ask what it already answers.

## 1. Find and scan
Resolve the folder the user named (search Movies/Videos, Desktop, Downloads, Documents if only a name is given; ask if several match).
```
FC scan "<folder>" [--recursive]        # prints WORK=<folder>/_autocut
```
Tell the user: clip count, total length, orientation mix, HDR.

## 2. Analyze (machine pass, free)
```
FC analyze "<WORK>" --jobs 2 --budget 150     # repeat until it prints DONE
FC summary "<WORK>" --table
```
Per clip: usable windows (sharp, steady, exposed), camera move, scene changes, blur/shake/exposure ratios, speech score. Long recordings are sampled lighter automatically. `--hwaccel` may speed up 4K on Macs.

**Pick the preset** from the footage and the request, then read ONLY that file:
`presets/real-estate.md` · `presets/talking-head.md` · `presets/event-vlog.md` · `presets/travel.md` · `presets/product.md`.
If speech matters (talking-head, interviews, speeches): `FC transcribe "<WORK>"` (needs `pip install faster-whisper`; first run downloads a model) -> `transcript.md` with timestamps.

## 3. Watch (progressive detail)
1. `FC sheets "<WORK>"` -> `sheets/*.jpg`. Bar under each clip: green = usable, red = bad, white = scene change. Read every sheet.
2. Write `<WORK>/labels.json`, one short entry per clip:
   `{"C001": {"space": "<preset label>", "shot": "static|pan_left|pan_right|tilt_up|tilt_down|walk|push|drone|handheld", "best": [in, out], "score": 1-5, "notes": "..."}}`
3. Only for hard choices: `FC strip "<WORK>" C012 --start 3 --end 9`.

## 4. One question round
| Situation | Action |
|---|---|
| Length / platform not given and not saved | **Ask.** Recommend the preset default (landscape vs portrait) |
| One orientation, or one side >= 70% | Don't ask - use the majority, list the rest as unused |
| Mixed ~50/50, or a key scene exists only in the minority orientation | **Ask** which orientation |
| No speech anywhere | Don't ask - silent output |
| Speech in all used clips | Don't ask - keep sound |
| Speech in some clips | **Ask**: keep sound only on speech clips (recommended) / keep all / silent |
| User said "just cut it" | Ask nothing |

Use the multiple-choice question tool if available (max 4 questions, recommended option first), else a short numbered list. With the questions, give the plan in 4-8 sentences. Save stable answers to preferences.

## 5. Plan
- **Rough cut:** follow the preset (opening, structure, shot lengths, sound). Use green windows and labels; prefer score 4-5; record every dropped clip with a reason in `unused`.
- **Fine cut (script / storyboard):** map each line to the best clip and range, keep the user's order and timing. If nothing fits a line, say so and offer the closest option - never invent.
- Hit the target length within about ±10%.

`<WORK>/edl.json`:
```json
{"version": 1, "project": "Maple Street House", "mode": "rough",
 "settings": {"audio": "auto", "fade_edges": 0.5, "duration_target": 90},
 "segments": [
   {"clip": "C012", "in": 1.2, "out": 4.6, "label": "Exterior, front, static", "reason": "best opening shot"},
   {"clip": "C003", "in": 0.8, "out": 4.1, "label": "Living room, pan right", "reason": "complete move, best light", "mute": false}],
 "unused": [{"clip": "C044", "reason": "shaky all the way"}]}
```
- `audio`: `auto` (keep sound only if a used clip has speech) | `keep` | `mute`; per segment `"mute": true`.
- `fade_edges`: fade in/out at the very start/end; inner cuts are hard cuts with 30 ms audio fades.
- Optional: `settings.orientation`, `settings.max_height` (e.g. 1080 for a lighter file), `settings.crf`.
- Write `label` / `reason` in the user's language.
Run `FC validate "<WORK>"` and fix every ERROR.

## 6. Render
```
FC render "<WORK>" --jobs 2 --budget 150      # repeat until OUTPUT=... ; output <project>_v1.mp4, v2, ...
```
Frame-accurate (sound never drifts), cached per segment (re-renders are fast), source colour/resolution/fps kept, HDR stays HDR.

## 7. Self-check (max 3 passes, before telling the user)
```
FC check "<WORK>"
```
Read `check_cuts.jpg` (before | after each cut). Fix and re-render for: black frames, near-identical shots at a cut, audio spikes, wrong length, A/V mismatch, blur/shake at a cut, a shot that does not match its label, wrong order.
For important videos, if you can start a sub-agent, ask a fresh one to review `check_cuts.jpg`, `edl.json` and the brief as a critic and list problems; fix what is real.
You cannot hear: say so and report the measured loudness instead of claiming the sound is fine.

## 8. Deliver
```
FC csv "<WORK>" [--lang zh]          # edit_list.csv + unused_clips.csv  (zh: 剪辑清单.csv + 未使用素材.csv)
FC export "<WORK>"                   # timeline.fcpxml (Final Cut, Resolve) + timeline.edl (Premiere, Resolve)
```
In the desktop-app VM add `--path-map "$HOME/mnt/<folder>=<real path on the computer>"` to `export` so editing software finds the files.
Report briefly: output path, length, number of shots, resolution/orientation, sound; 3-5 lines of structure; unused clips count + main reasons; self-check result; how to revise.

## 9. Revise
User edits the CSV (or says "swap the kitchen shot for C031 2-6 s"):
```
FC csv "<WORK>" --from-csv "<WORK>/edit_list.csv"   # Chinese headers are accepted too
FC validate "<WORK>" && FC render "<WORK>" && FC check "<WORK>" && FC csv "<WORK>"
```
Editable columns: No (order), Clip ID or File, In, Out, Content, Reason, Mute. Deleting a row removes the shot. Do not re-watch footage.

## 10. Clean exported videos (logo + outro)
For videos the user generated themselves (e.g. NotebookLM Video Overviews, other AI or screen-recording tools):
```
FC clean "<file or folder>" --preset notebooklm --config ~/.fullcut/clean.json   # bottom-right mark + 2.5 s fallback outro
FC clean "<file or folder>"                                                     # generic: any corner, trims only a detected outro
```
Finds a static corner mark and removes it with ffmpeg `delogo`; finds where the outro starts (mark disappears / scene change) and cuts there. Output `_clean/<name>_clean.mp4` + `_preview.jpg` - read the preview. Manual overrides: `--box x,y,w,h` (0-1), `--corner br|bl|tr|tl`, `--tail <s>`, `--no-logo`, `--no-trim`.
Only for content the user owns or may edit; invisible watermarks (e.g. SynthID) are not touched.

## Troubleshooting
- `NOT DONE`: run the same command again (time budget per call).
- Big 4K batches: `--jobs 3` on strong machines; `settings.max_height: 1080` for faster, lighter output.
- Unreadable clips are listed in `assets.json -> unreadable`.
- Mixed HDR/SDR: validate warns; prefer one kind.
- Self-test of the engine: `python3 tests/run_tests.py --quick`.
