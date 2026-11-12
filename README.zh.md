<div align="center">

# 🎬 FullcutStudio

**交给它一个素材文件夹，拿回一条成片和一份可以修改的剪辑清单。**

开源的 AI 自动剪辑 skill，适用于 Claude 和其他 AI 编程助手。免费、在本地运行、不需要 API key。

[English](README.md) · [中文](README.zh.md)

</div>

---

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

**Claude Code：** 把这个仓库克隆到 `~/.claude/skills/fullcut-studio`。

**Claude app（网页版 / 桌面版）：** 在本仓库的 Releases 页面下载 `fullcut-studio.zip`，然后进入 **Customize → Skills → + → Create skill → Upload a skill** 上传。确认 Settings → Capabilities 里已经打开代码执行。桌面版要点 **Add folder** 把素材文件夹加进来，Claude 才能看到你的素材。

**其他 AI 工具（Codex、Cursor 等）：** 把整个文件夹复制到它的 skills 目录，用的是通用的 `SKILL.md` 格式。

**检查安装是否正常：** 运行 `python3 tests/run_tests.py --quick`，它会自动生成测试素材，跑 18 项检查，大约 2 分钟。

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
