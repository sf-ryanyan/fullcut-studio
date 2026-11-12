<div align="center">

# 🎬 FullcutStudio

**Give it a folder of raw clips. Get back a finished cut and an edit list you can change.**<br>
**交给它一个素材文件夹，拿回一条成片和一份可以修改的剪辑清单。**

Open-source AI auto-editing skill for Claude and other coding agents. Free, local, no API keys.<br>
开源 AI 自动剪辑 skill，适用于 Claude 和其他 AI 编程助手。免费、本地运行、不需要 API key。

[English](#english) · [中文](#中文说明) · [⬇️ Download / 下载](https://github.com/sf-ryanyan/fullcut-studio/releases/latest)

</div>

---

<a id="english"></a>

# 🇺🇸 English

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

**Claude Code:**
```bash
git clone https://github.com/sf-ryanyan/fullcut-studio.git ~/.claude/skills/fullcut-studio
```

**Claude app (web / desktop):** download `fullcut-studio.zip` from the [latest release](https://github.com/sf-ryanyan/fullcut-studio/releases/latest), then go to **Customize → Skills → + → Create skill → Upload a skill**. Make sure code execution is enabled in Settings → Capabilities. In the desktop app, use **Add folder** so Claude can reach your footage.

**Other agents (Codex, Cursor, ...):**
```bash
npx skills add sf-ryanyan/fullcut-studio
```
Or copy the folder into the agent's skills directory - it uses the standard `SKILL.md` format.

**Check that everything works:** `python3 ~/.claude/skills/fullcut-studio/tests/run_tests.py --quick` builds test footage and runs 18 checks (about 2 minutes).

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

---

<a id="中文说明"></a>

# 🇨🇳 中文说明

## 😩 痛点

拍完回来，手上有 89 段素材。在真正开始创作之前，你得先：

- 🕒 **把每一段看一遍**，找出真正能用的那几秒
- 🫨 **去掉不能用的部分**：糊的、抖的、太暗的、开机关机时晃的
- 🧩 **决定顺序**，把每个镜头剪到合适的长度
- 🔁 别人一句"再短 30 秒"，**全部重来**

这些活要花好几个小时，而且还没开始做任何创意上的决定。现有的 AI 工具，有的要付费转写 API，有的只看得懂讲话类视频，有的要把素材上传到云端。

## ✅ FullcutStudio 怎么解决

| 痛点 | FullcutStudio 的做法 |
|---|---|
| 每段都要看 | 先用免费的机器分析给每一秒打分（清晰度、抖动、曝光、运镜），AI 再看缩略图拼图（一张图 4 段素材），不用看成千上万帧 |
| 挑出能用的部分 | 每段素材都标出绿色"可用区间"，开机晃动、甩镜头、模糊、过暗的部分自动去掉 |
| 排顺序 | 内置剪辑预设（房产、口播/采访、活动/vlog、旅行、产品），结构、节奏、镜头长度都按专业做法来 |
| 来回改 | 最多只问**一轮**问题（只问素材让它必须问的），记住你的选择，给你看之前自己检查最多 3 轮 |
| 想改结果 | 每次都附**剪辑清单（CSV）**。改时间、调顺序、删一行，几秒钟重新出片，不用重新看素材 |
| 要在专业软件里精修 | 导出 **Premiere Pro、DaVinci Resolve、Final Cut Pro** 都能打开的时间线（CMX3600 EDL + FCPXML） |
| 隐私和费用 | 全部在你自己的电脑上用 ffmpeg 和 Python 运行。不上传、不需要 API key、不用订阅 |

## ✨ 功能

- 📂 **给文件夹就出片**：说文件夹名字或路径，它自己去找素材
- ✂️ **粗剪**：一句话就行，比如"剪成一条 60 秒的看房视频"
- 📝 **精剪**：按你的脚本或分镜，比如"第 1 段外观，第 2 段客厅，第 3 段厨房……"
- 🎯 **精确到帧**：剪 100 多刀，声音也不会跑偏
- 🎨 **保持原样**：颜色、分辨率、帧率、横竖屏都不变，iPhone HDR 剪完还是 HDR
- 🗣️ **懂讲话**：可选本地转写（faster-whisper），讲话的素材在句子之间切，绝不切在半个字上
- 🔍 **自检**：黑帧、跳剪、爆音、时长、音画同步都检查过才给你看
- 🧾 **剪辑清单 + 未使用清单**：用了什么一目了然，没用的也写明原因
- 🧹 **清理自己导出的视频**：去掉固定的角标，切掉片尾（比如 NotebookLM 生成的视频）
- 🌏 **中英双语**：你用什么语言说，它就用什么语言回复；剪辑清单可以是中文或英文

## 🚀 怎么用

直接跟 AI 说：

> **「把 ~/Movies/Maple House 里的素材剪成一条 90 秒的看房视频。」**
>
> **「按这个脚本剪：1 外观、2 客厅、3 厨房、4 后院。45 秒，竖屏。」**
>
> **「我改好剪辑清单了，按清单重新出片。」**
>
> **「导出 DaVinci Resolve 能打开的时间线。」**
>
> **「把这几个 NotebookLM 视频的水印和片尾去掉。」**

结果都在 `你的素材文件夹/_autocut/` 里：

| 文件 | 内容 |
|---|---|
| `<项目名>_v1.mp4` | 成片（每改一次就有 v2、v3……） |
| `剪辑清单.csv` / `edit_list.csv` | 每个镜头：素材、起止时间、在成片中的位置、画面内容、选用理由 |
| `未使用素材.csv` / `unused_clips.csv` | 没用上的素材和原因 |
| `timeline.fcpxml` / `timeline.edl` | 在 Final Cut、Resolve、Premiere 里打开继续精修 |
| `labels.json` | AI 对每段素材的判断，下次直接复用，同一批素材不用看第二遍 |

## 🛠️ 安装

**需要：** ffmpeg、Python 3、`numpy`、`opencv-python-headless`（可选：`faster-whisper`）。

| 系统 | 命令 |
|---|---|
| macOS | `brew install ffmpeg && python3 -m pip install --user numpy opencv-python-headless` |
| Windows | `winget install Gyan.FFmpeg`，然后 `py -m pip install numpy opencv-python-headless` |
| Linux | `sudo apt install ffmpeg && pip install numpy opencv-python-headless` |

**Claude Code：**
```bash
git clone https://github.com/sf-ryanyan/fullcut-studio.git ~/.claude/skills/fullcut-studio
```

**Claude app（网页版 / 桌面版）：** 在[最新版本页面](https://github.com/sf-ryanyan/fullcut-studio/releases/latest)下载 `fullcut-studio.zip`，然后进入 **Customize → Skills → + → Create skill → Upload a skill** 上传。确认 Settings → Capabilities 里已经打开代码执行。桌面版要点 **Add folder** 把素材文件夹加进来，Claude 才能看到你的素材。

**其他 AI 工具（Codex、Cursor 等）：**
```bash
npx skills add sf-ryanyan/fullcut-studio
```
也可以把整个文件夹复制到它的 skills 目录，用的是通用的 `SKILL.md` 格式。

**检查安装是否正常：** 运行 `python3 ~/.claude/skills/fullcut-studio/tests/run_tests.py --quick`，它会自动生成测试素材，跑 18 项检查，大约 2 分钟。

## 📖 工作原理

1. **扫描**：读出每段素材的时长、分辨率、旋转、帧率、HDR、声音
2. **分析**：免费的机器分析，给清晰度、抖动、曝光、运镜、场景切换和人声打分，并生成小代理文件
3. **看片**：AI 看缩略图拼图，给每段素材打标签（哪个空间/场景、什么镜头、最佳区间、质量分）
4. **只问一次**：只问素材让它必须问的（时长、横竖混拍、部分有人声）
5. **规划**：按对应预设的规则写剪辑清单
6. **渲染**：精确到帧，每个镜头单独缓存，颜色和横竖屏不动
7. **自检**：最多自动修 3 轮，重要的片子还可以加一轮"挑刺"评审
8. **交付**：成片、剪辑清单、未使用清单、剪辑软件时间线

**预设：** 🏠 房产 · 🎤 口播/采访 · 🎉 活动/vlog · ✈️ 旅行 · 📦 产品。每个预设都是 `presets/` 里一个很短的 Markdown 文件，容易看懂、修改，也欢迎贡献新的。

## 📏 刻意不做的事

FullcutStudio **只负责剪辑**：不调色、不调曝光、不裁切、不改画幅、不旋转、不加文字、字幕、音乐和特效，也不会改动你的原素材。需要这些步骤，可以搭配调色或字幕工具。

## 🙏 致谢

FullcutStudio 是原创实现，思路借鉴了以下开源项目：

- **[video-use](https://github.com/browser-use/video-use)**（browser-use）：先确认方案再剪、剪辑清单、自检循环、30 毫秒声音淡入淡出
- **[RoughCut Agent](https://github.com/mocchalera/video-os-v2)**：渐进看片（缩略图拼图 → 胶片条 → 精确帧）、与剪辑软件互通
- **[ECC video-editing](https://github.com/affaan-m/ecc)**：代理文件、CSV 剪辑清单、分层流程
- **[cutagent](https://github.com/DaKev/cutagent)**：适合 AI 使用、用数据驱动的剪辑清单
- **[FFmpeg](https://ffmpeg.org)**、**[OpenCV](https://opencv.org)**、**[faster-whisper](https://github.com/SYSTRAN/faster-whisper)**：真正干重活的工具

没有复制上述项目的代码。

## ⚠️ 免责声明

- AI 的剪辑判断可能出错。发布前请自己看一遍成片；剪辑清单就是为了让你能快速修改。
- **clean（清理）** 功能只用于你自己制作或有权编辑的视频。不要用它去掉别人的品牌标识或署名。它不处理隐形水印（比如 SynthID）。
- 请尊重素材中出现的人的权利和隐私。
- 本项目按"原样"提供，不提供任何担保。

## 👋 关于作者

作者 **Ryan Yan，一名数据分析师**。他希望自己去做别的事的时候，素材已经被剪好了。

## 📄 版权与许可

© 2026 Ryan Yan。基于 [MIT 许可证](LICENSE) 发布：可以免费使用、修改、分享，包括商用，只要保留版权声明。
