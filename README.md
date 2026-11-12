<div align="center">

# 🎬 FullcutStudio

**Give it a folder of raw clips. Get back a finished cut and an edit list you can change.**

An open-source AI auto-editing skill for Claude and other coding agents. Free, local, no API keys.

[English](README.md) · [中文](README.zh.md)

</div>

---

## 😩 The problem

You come back from a shoot with 89 clips. Before you can make anything, you have to:

- 🕒 **Watch every clip** to find the few seconds that are actually usable
- 🫨 **Throw out the bad parts** - blurry, shaky, too dark, the camera starting and stopping
- 🧩 **Decide the order** and trim each shot to the right length
- 🔁 **Start over** when someone asks for "the same, but 30 seconds shorter"

That is hours of work before any creative decision is made. Existing AI tools either need paid transcription APIs, only understand talking, or upload your footage to the cloud.

## ✅ How FullcutStudio solves it

| Pain point | What FullcutStudio does |
|---|---|
| Watching every clip | A free machine pass scores every second for sharpness, shake, exposure and camera movement. The AI then reviews compact contact sheets (4 clips per image) instead of thousands of frames |
| Picking usable parts | Every clip gets green "usable" windows. Shaky starts, whip pans, blur and dark sections are cut away automatically |
| Ordering the story | Built-in editing presets (real estate, talking head, event/vlog, travel, product) with a professional structure, pacing and shot lengths |
| Endless back-and-forth | Asks at most **one** short round of questions (only what the footage makes necessary), remembers your answers, and self-checks the result up to 3 times before showing you |
| Changing the result | Every cut comes with an **edit list (CSV)**. Change a time, reorder, delete a row - re-render in seconds without re-watching anything |
| Finishing in pro software | Exports a timeline for **Premiere Pro, DaVinci Resolve and Final Cut Pro** (CMX3600 EDL + FCPXML) |
| Privacy and cost | Everything runs on your own computer with ffmpeg and Python. No uploads, no API keys, no subscription |

## ✨ Features

- 📂 **Folder in, video out** - name a folder or give a path; it finds the clips itself
- ✂️ **Rough cut** from one sentence: *"Cut this into a 60-second house tour"*
- 📝 **Fine cut** from your script or storyboard: *"1: exterior, 2: living room, 3: kitchen..."*
- 🎯 **Frame-accurate** rendering - sound never drifts out of sync, even with 100+ cuts
- 🎨 **Untouched look** - keeps your colour, resolution, frame rate and orientation; iPhone HDR stays HDR
- 🗣️ **Speech-aware** - optional local transcription (faster-whisper) so talking clips are cut between sentences, never mid-word
- 🔍 **Self-check** - black frames, jump cuts, audio pops, length and sync are verified before you see anything
- 🧾 **Edit list + unused list** - see exactly what was used, and why everything else was left out
- 🧹 **Clean your own exports** - removes a static corner logo and trims the outro of videos you generated (for example NotebookLM Video Overviews)
- 🌏 **Bilingual** - answers in your language; edit lists in English or Chinese

## 🚀 How to use

Just talk to your agent:

> **"Cut the clips in ~/Movies/Maple House into a 90-second tour."**
>
> **"Follow this script: 1 exterior, 2 living room, 3 kitchen, 4 backyard. 45 seconds, vertical."**
>
> **"I edited edit_list.csv - render it again."**
>
> **"Export the timeline for DaVinci Resolve."**
>
> **"Remove the logo and outro from these NotebookLM videos."**

What you get in `<your folder>/_autocut/`:

| File | What it is |
|---|---|
| `<project>_v1.mp4` | The finished cut (v2, v3... for each revision) |
| `edit_list.csv` | Every shot: clip, in/out time, position in the cut, content, reason |
| `unused_clips.csv` | Every clip not used, with the reason |
| `timeline.fcpxml` / `timeline.edl` | Open the cut in Final Cut, Resolve or Premiere |
| `labels.json` | What the AI saw in each clip - reused next time, so footage is never reviewed twice |

## 🛠️ Install

**Requirements:** ffmpeg, Python 3, `numpy`, `opencv-python-headless` (optional: `faster-whisper`).

| System | Command |
|---|---|
| macOS | `brew install ffmpeg && python3 -m pip install --user numpy opencv-python-headless` |
| Windows | `winget install Gyan.FFmpeg` then `py -m pip install numpy opencv-python-headless` |
| Linux | `sudo apt install ffmpeg && pip install numpy opencv-python-headless` |

**Claude Code:** clone this repository into your skills folder as `~/.claude/skills/fullcut-studio`.

**Claude app (web / desktop):** download `fullcut-studio.zip` from this repository's Releases page, then go to **Customize → Skills → + → Create skill → Upload a skill**. Make sure code execution is enabled in Settings → Capabilities. In the desktop app, use **Add folder** so Claude can reach your footage.

**Other agents (Codex, Cursor, ...):** copy the folder into the agent's skills directory - it uses the standard `SKILL.md` format.

**Check that everything works:** `python3 tests/run_tests.py --quick` builds test footage and runs 18 checks (about 2 minutes).

## 📖 How it works

1. **Scan** - reads every clip: length, resolution, rotation, frame rate, HDR, audio
2. **Analyze** - a free machine pass scores sharpness, shake, exposure, camera movement, scene changes and speech, and makes small proxy files
3. **Watch** - the AI reviews contact sheets and labels each clip (room / scene, shot type, best range, quality)
4. **Ask once** - only what the footage makes necessary (length, mixed orientation, mixed speech)
5. **Plan** - writes an edit decision list using the matching preset's rules
6. **Render** - frame-accurate cuts, cached per shot, colour and orientation untouched
7. **Self-check** - up to 3 automatic fix passes, optional critic review
8. **Deliver** - video, edit list, unused list, timeline for editing software

**Presets:** 🏠 real estate · 🎤 talking head / interview · 🎉 event / vlog · ✈️ travel · 📦 product. Each preset is one short Markdown file in `presets/` - easy to read, change, or contribute.

## 📏 What it does not do (by design)

FullcutStudio **only cuts**. It never colour-grades, changes exposure, crops or reframes, rotates, adds text, subtitles, music or effects, and it never modifies your original files. Pair it with a grading or captioning tool if you need those steps.

## 🙏 Acknowledgements

FullcutStudio is an original implementation inspired by ideas from these open-source projects:

- **[video-use](https://github.com/browser-use/video-use)** (browser-use) - confirm-the-plan-first workflow, edit decision list, self-check loop, 30 ms audio fades
- **[RoughCut Agent](https://github.com/mocchalera/video-os-v2)** - progressive review (contact sheet → filmstrip → precise frame), NLE round-trip
- **[ECC video-editing](https://github.com/affaan-m/ecc)** - proxy files, CSV cut lists, layered workflow
- **[cutagent](https://github.com/DaKev/cutagent)** - agent-friendly, data-driven edit lists
- **[FFmpeg](https://ffmpeg.org)**, **[OpenCV](https://opencv.org)** and **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** - the tools that do the heavy lifting

No code was copied from these projects.

## ⚠️ Disclaimer

- AI editing decisions can be wrong. Always watch the result before publishing; the edit list exists so you can fix anything quickly.
- The **clean** command is meant only for videos you created or have the right to edit. Do not use it to remove someone else's branding or attribution. It does not touch invisible watermarks (such as SynthID).
- Respect the rights and privacy of people who appear in your footage.
- Provided "as is", without warranty of any kind.

## 👋 About the author

Built by **Ryan Yan, a data analyst**, who wanted his footage edited while he did something else.

## 📄 Copyright & license

© 2026 Ryan Yan. Released under the [MIT License](LICENSE) - free to use, modify and share, including commercially, as long as the copyright notice is kept.
