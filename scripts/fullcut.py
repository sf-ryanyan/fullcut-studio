#!/usr/bin/env python3
"""FullcutStudio VERSION 1.0.0 - AI auto-editing engine: footage folder -> final cut + edit list.
MIT License  |  (c) 2026 Ryan Yan

Subcommands (run `python3 fullcut.py <cmd> -h`):
  scan        find clips in a folder, probe them                    -> assets.json
  analyze     quality / motion / scene / speech analysis            -> analysis/*.json, proxies/
              (resumable: --budget keeps each call short; re-run until DONE)
  transcribe  optional local speech-to-text (faster-whisper)       -> analysis/*.words.json, transcript.md
  summary     one-screen overview used for the question round
  sheets      contact sheets (several clips per image)              -> sheets/*.jpg
  strip       dense filmstrip of one clip range                     -> strips/*.jpg
  validate    check an EDL against the footage
  render      EDL -> final mp4 (frame-accurate, cached per segment, resumable)
  check       self-check the rendered file                          -> check.json + check_cuts.jpg
  csv         EDL -> edit list CSV (+ unused list) / --from-csv CSV -> EDL
  export      EDL -> timeline for editing software (FCPXML + CMX3600 EDL)
  clean       remove a static corner logo and trim the outro of your own exported videos

Cuts only. Never grades colour, never changes orientation, never adds text or music.
Requires: ffmpeg + ffprobe on PATH, python3, numpy, opencv-python-headless.
"""
import argparse, csv, hashlib, json, math, os, re, shutil, subprocess, sys, time, urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import cv2

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts", ".m2ts", ".webm", ".3gp"}
AN_FPS = 4          # analysis sample rate (long clips use fewer, see an_fps())
AN_W = 320          # analysis width
STD_FPS = [23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60, 120]
STD_FPS_RAW = {23.976: "24000/1001", 29.97: "30000/1001", 59.94: "60000/1001"}
PROXY_W = 640


# ----------------------------------------------------------------- helpers
def run(cmd, **kw):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)


def jload(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def jsave(p, obj):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def fmt_t(s):
    s = max(0.0, float(s))
    m = int(s // 60)
    return f"{m}:{s - 60 * m:05.2f}"


def parse_fps(r):
    try:
        a, b = r.split("/")
        v = float(a) / float(b)
        return v if v > 0 else 30.0
    except Exception:
        return 30.0


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


# ----------------------------------------------------------------- probe
def probe(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    if r.returncode != 0:
        return None
    d = json.loads(r.stdout or b"{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"
              and not s.get("disposition", {}).get("attached_pic")), None)
    if not v:
        return None
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if not rot and v.get("tags", {}).get("rotate"):
        rot = int(v["tags"]["rotate"])
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    if abs(rot) % 180 == 90:
        w, h = h, w
    dur = float(v.get("duration") or d.get("format", {}).get("duration") or 0)
    trc = v.get("color_transfer", "") or ""
    hdr = trc in ("arib-std-b67", "smpte2084")
    tags = d.get("format", {}).get("tags", {}) or {}
    tc = tags.get("timecode") or next((st.get("tags", {}).get("timecode") for st in d.get("streams", [])
                                       if st.get("tags", {}).get("timecode")), "") or ""
    ctime = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate") or ""
    return {
        "duration": round(dur, 3), "w": w, "h": h, "rotation": rot,
        "orientation": "portrait" if h > w else ("square" if h == w else "landscape"),
        "fps": round(parse_fps(v.get("avg_frame_rate") or v.get("r_frame_rate", "30/1")), 3),
        "fps_raw": v.get("avg_frame_rate") or v.get("r_frame_rate", "30/1"),
        "vcodec": v.get("codec_name"), "pix_fmt": v.get("pix_fmt", ""),
        "color_transfer": trc, "color_primaries": v.get("color_primaries", ""),
        "color_space": v.get("color_space", ""), "hdr": hdr,
        "has_audio": a is not None, "creation_time": ctime, "timecode": tc,
        "size_mb": round(int(d.get("format", {}).get("size", 0)) / 1e6, 1),
    }


def cmd_scan(a):
    root = os.path.abspath(a.folder)
    if not os.path.isdir(root):
        sys.exit(f"ERROR: folder not found: {root}")
    work = os.path.abspath(a.work or os.path.join(root, "_autocut"))
    files = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith("_autocut") and not d.startswith(".")]
        if not a.recursive and os.path.abspath(dp) != root:
            continue
        for f in fn:
            if os.path.splitext(f)[1].lower() in VIDEO_EXT and not f.startswith("._"):
                files.append(os.path.join(dp, f))
    files.sort(key=lambda p: natural_key(os.path.relpath(p, root)))
    old = {c["file"]: c for c in (jload(os.path.join(work, "assets.json"), {}) or {}).get("clips", [])}
    clips, bad = [], []
    for i, p in enumerate(files, 1):
        info = probe(p)
        if not info or info["duration"] <= 0.3:
            bad.append(os.path.basename(p))
            continue
        clips.append({"id": old.get(p, {}).get("id"), "file": p, "name": os.path.relpath(p, root), **info})
    # keep old ids stable, give new clips the next free number
    used = {c["id"] for c in clips if c["id"]}
    nxt = 1
    for c in clips:
        if c["id"]:
            continue
        while f"C{nxt:03d}" in used:
            nxt += 1
        c["id"] = f"C{nxt:03d}"
        used.add(c["id"])
    jsave(os.path.join(work, "assets.json"), {"folder": root, "project": os.path.basename(root.rstrip("/\\")),
                                             "work": work, "clips": clips, "unreadable": bad})
    tot = sum(c["duration"] for c in clips)
    print(f"WORK={work}")
    print(f"clips={len(clips)} total={fmt_t(tot)} unreadable={len(bad)}")
    print("orientation:", dict(Counter(c["orientation"] for c in clips)))
    print("resolution:", dict(Counter(f'{c["w"]}x{c["h"]}' for c in clips)))
    print("fps:", dict(Counter(c["fps"] for c in clips)), " hdr:", sum(c["hdr"] for c in clips))


def load_assets(work):
    d = jload(os.path.join(work, "assets.json"))
    if not d:
        sys.exit(f"ERROR: no assets.json in {work} - run scan first")
    return d


# ----------------------------------------------------------------- analyze
def analyze_audio(path, dur):
    """Per-second loudness + voiced-speech activity and a 0-1 speech likelihood. Streams the audio in blocks.

    Speech = voiced frames (clear pitch 80-400 Hz) + a syllable rhythm (energy modulation 2-8 Hz).
    Wind, hum, traffic and steady tones fail one of the two tests."""
    sr, hop = 16000, 480                      # 30 ms frames
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    rms_l, per_l = [], []
    lag0, lag1 = sr // 400, sr // 80          # pitch range 80-400 Hz
    buf = b""
    while True:
        chunk = p.stdout.read(hop * 2 * 2000)      # ~60 s per block
        if not chunk:
            break
        buf += chunk
        n = len(buf) // (hop * 2)
        if n == 0:
            continue
        x = np.frombuffer(buf[: n * hop * 2], dtype=np.int16).astype(np.float32) / 32768.0
        buf = buf[n * hop * 2:]
        fr = x.reshape(n, hop)
        fr = fr - fr.mean(1, keepdims=True)
        rms_l.append(np.sqrt((fr ** 2).mean(1) + 1e-12))
        X = np.fft.rfft(fr, n=1024, axis=1)
        ac = np.fft.irfft(np.abs(X) ** 2, axis=1)[:, : lag1 + 1]
        # normalise by the overlap so long lags are not penalised
        ac = ac / (ac[:, :1] + 1e-9) * (hop / (hop - np.arange(lag1 + 1)))
        per_l.append(ac[:, lag0:lag1 + 1].max(1))
    p.wait()
    if not rms_l or sum(len(r) for r in rms_l) < 20:
        return {"speech_score": 0.0, "speech_seconds": 0.0, "loud_db": [], "speech_sec": []}
    rms, per = np.concatenate(rms_l), np.concatenate(per_l)
    n = rms.size
    floor = np.percentile(rms, 10) + 1e-6
    loud_enough = (rms > 0.003) & (rms > floor * 2.0)
    voiced = loud_enough & (per > 0.45)
    # syllable rhythm: modulation of the log-energy envelope (first ~10 min is enough)
    env = np.log(rms[:20000] + 1e-4)
    mod = 0.0
    if env.size > 64:
        e = env - env.mean()
        ps = np.abs(np.fft.rfft(e)) ** 2
        mf = np.fft.rfftfreq(e.size, hop / sr)
        mod = float(ps[(mf >= 2) & (mf <= 8)].sum() / (ps[(mf > 0.3) & (mf <= 15)].sum() + 1e-12))
    # voiced frames must come and go (speech), not stay on (a steady tone or motor hum)
    vf = float(voiced.mean())
    switches = float(np.abs(np.diff(voiced.astype(np.int8))).sum()) / max(1.0, n * hop / sr)   # per second
    rhythm = float(np.clip((mod - 0.1) * 4.0, 0, 1)) * float(np.clip(switches / 2.0, 0, 1))
    score = float(np.clip(vf * 2.5, 0, 1)) * rhythm
    per_s = int(round(sr / hop))
    secs = int(math.ceil(n / per_s))
    loud = [round(20 * math.log10(float(rms[i * per_s:(i + 1) * per_s].mean()) + 1e-9), 1) for i in range(secs)]
    sp = [round(float(voiced[i * per_s:(i + 1) * per_s].mean()), 2) for i in range(secs)]
    return {"speech_score": round(score, 2), "speech_seconds": round(float(voiced.sum()) * hop / sr, 1),
            "loud_db": loud, "speech_sec": sp}


def windows_from_mask(ok, step, min_len, gap):
    """ok: bool per sample -> list of [start,end] seconds."""
    wins, start = [], None
    for i, v in enumerate(list(ok) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            wins.append([start * step, i * step])
            start = None
    merged = []
    for w in wins:
        if merged and w[0] - merged[-1][1] <= gap:
            merged[-1][1] = w[1]
        else:
            merged.append(w)
    return [[round(s, 2), round(e, 2)] for s, e in merged if e - s >= min_len]


def an_fps(dur):
    """Analysis sample rate: dense for short clips, lighter for long recordings."""
    return AN_FPS if dur <= 300 else (2 if dur <= 1200 else 1)


def analyze_clip(clip, work, hwaccel=False):
    out_json = os.path.join(work, "analysis", clip["id"] + ".json")
    proxy = os.path.join(work, "proxies", clip["id"] + ".mp4")
    os.makedirs(os.path.dirname(proxy), exist_ok=True)
    dur = clip["duration"]
    fps_a = an_fps(dur)
    W = AN_W
    H = int(round(W * clip["h"] / clip["w"] / 2) * 2)
    cmd = ["ffmpeg", "-v", "error", "-y"] + (["-hwaccel", "auto"] if hwaccel else []) + ["-i", clip["file"],
           "-map", "0:v:0", "-vf", f"scale={PROXY_W}:-2", "-c:v", "libx264", "-preset", "ultrafast",
           "-crf", "30", "-g", "12", "-pix_fmt", "yuv420p", "-an", proxy + ".part.mp4",
           "-map", "0:v:0", "-vf", f"fps={fps_a},scale={W}:{H},format=gray", "-f", "rawvideo", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    win = cv2.createHanningWindow((W, H), cv2.CV_32F)
    sharp, bright, over, dark = [], [], [], []
    dx, dy, hist_d, diff = [0.0], [0.0], [0.0], [0.0]
    prev_f = prev_h = None
    fsz = W * H
    nf = 0
    while True:                                   # stream frame by frame: constant memory for any length
        b = p.stdout.read(fsz)
        if len(b) < fsz:
            break
        f = np.frombuffer(b, dtype=np.uint8).reshape(H, W)
        nf += 1
        sharp.append(float(cv2.Laplacian(f, cv2.CV_64F).var()))
        bright.append(float(f.mean()))
        over.append(float((f > 245).mean()))
        dark.append(float((f < 18).mean()))
        ff = f.astype(np.float32)
        h = cv2.calcHist([f], [0], None, [32], [0, 256])
        cv2.normalize(h, h)
        if prev_f is not None:
            (sx, sy), _ = cv2.phaseCorrelate(prev_f, ff, win)
            dx.append(float(sx)); dy.append(float(sy))
            hist_d.append(float(1 - cv2.compareHist(prev_h, h, cv2.HISTCMP_CORREL)))
            diff.append(float(np.abs(ff - prev_f).mean()))
        prev_f, prev_h = ff, h
    err = p.stderr.read().decode(errors="ignore")
    p.wait()
    if nf < 2:
        jsave(out_json, {"id": clip["id"], "error": "decode_failed", "stderr": err[-400:]})
        return
    if os.path.exists(proxy + ".part.mp4"):
        os.replace(proxy + ".part.mp4", proxy)
    sharp, dx, dy = np.array(sharp), np.array(dx), np.array(dy)
    bright, over, dark = np.array(bright), np.array(over), np.array(dark)
    step = 1.0 / fps_a
    k = max(3, int(round(5 * fps_a / AN_FPS)) | 1)
    sm_x = np.convolve(dx, np.ones(k) / k, mode="same")
    sm_y = np.convolve(dy, np.ones(k) / k, mode="same")
    scale = AN_FPS / fps_a                          # motion per sample grows when sampling is sparser
    jitter = np.sqrt((dx - sm_x) ** 2 + (dy - sm_y) ** 2) / scale
    speed = np.sqrt(sm_x ** 2 + sm_y ** 2) / scale
    ref = np.percentile(sharp, 80)
    blur_bad = sharp < max(12.0, 0.40 * ref)
    shake_bad = np.convolve(jitter > 2.2, np.ones(3), mode="same") >= 2
    expo_bad = (bright < 28) | (over > 0.45) | (dark > 0.6)
    fast_bad = speed > W * 0.12                     # whip pan
    ok = ~(blur_bad | shake_bad | expo_bad | fast_bad)
    ok[:1] = False                                  # never start on frame 0
    wins = windows_from_mask(ok, step, 1.2, 0.5)
    wins = [[s, min(e, dur - 0.15)] for s, e in wins if min(e, dur - 0.15) - s >= 1.2]
    cuts = [round(i * step, 2) for i, v in enumerate(hist_d) if v > 0.45]

    def move_label(s, e):
        i0 = int(s * fps_a)
        i1 = max(i0 + 1, int(e * fps_a))
        mx, my = float(np.mean(sm_x[i0:i1])) / scale, float(np.mean(sm_y[i0:i1])) / scale
        if math.hypot(mx, my) < 0.6:
            return "static"
        if abs(mx) >= abs(my):                      # content moves opposite to the camera
            return "pan_right" if mx < 0 else "pan_left"
        return "tilt_down" if my < 0 else "tilt_up"

    per_sec = []
    for sec in range(int(math.ceil(nf / fps_a))):
        sl = slice(sec * fps_a, (sec + 1) * fps_a)
        per_sec.append({"t": sec, "sharp": round(float(sharp[sl].mean()), 1), "bright": round(float(bright[sl].mean()), 1),
                        "shake": round(float(jitter[sl].mean()), 2), "speed": round(float(speed[sl].mean()), 2),
                        "bad": [n for n, m in (("blur", blur_bad), ("shake", shake_bad), ("exposure", expo_bad),
                                               ("whip", fast_bad)) if m[sl].mean() > 0.5]})
    usable = sum(e - s for s, e in wins)
    res = {"id": clip["id"], "duration": dur, "samples": nf, "an_fps": fps_a,
           "usable": [{"in": s, "out": e, "move": move_label(s, e)} for s, e in wins],
           "usable_seconds": round(usable, 2), "usable_ratio": round(usable / max(dur, 0.01), 2),
           "bad_ratio": {n: round(float(m.mean()), 2) for n, m in (("blur", blur_bad), ("shake", shake_bad),
                                                                 ("exposure", expo_bad), ("whip", fast_bad))},
           "scene_cuts": cuts,
           "frozen": bool(np.mean(np.array(diff[1:]) < 0.4) > 0.9 and float(np.mean(speed)) < 0.2),
           "sharp_ref": round(float(ref), 1), "per_sec": per_sec}
    res["audio"] = analyze_audio(clip["file"], dur) if clip.get("has_audio") else \
        {"speech_score": 0.0, "speech_seconds": 0.0, "loud_db": [], "speech_sec": []}
    jsave(out_json, res)


def cmd_analyze(a):
    work = os.path.abspath(a.work)
    assets = load_assets(work)
    todo = [c for c in assets["clips"] if a.force or not os.path.exists(os.path.join(work, "analysis", c["id"] + ".json"))]
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        it = iter(todo)
        # submit progressively so the budget is respected
        running = set()
        while True:
            while len(running) < a.jobs and time.time() - t0 < a.budget:
                c = next(it, None)
                if c is None:
                    break
                running.add(ex.submit(analyze_clip, c, work, a.hwaccel))
            if not running:
                break
            fin = [f for f in running if f.done()]
            for f in fin:
                running.discard(f)
                f.result()
                done += 1
            if not fin:
                time.sleep(0.2)
    left = len(todo) - done
    print(f"analyzed {done}, remaining {left}")
    print("DONE" if left == 0 else "NOT DONE - run analyze again")


def load_analysis(work, cid):
    return jload(os.path.join(work, "analysis", cid + ".json"), {}) or {}


def cmd_summary(a):
    work = os.path.abspath(a.work)
    assets = load_assets(work)
    clips = assets["clips"]
    rows, speech, ori = [], [], Counter()
    for c in clips:
        an = load_analysis(work, c["id"])
        ori[c["orientation"]] += 1
        sc = (an.get("audio") or {}).get("speech_score", 0)
        if sc >= 0.35:
            speech.append(c["id"])
        rows.append((c["id"], c["name"], c["duration"], c["orientation"][0].upper(),
                     an.get("usable_seconds", "?"), len(an.get("usable", [])), sc,
                     ",".join(k for k, v in (an.get("bad_ratio") or {}).items() if v > 0.3)))
    tot = sum(c["duration"] for c in clips)
    use = sum(r[4] for r in rows if isinstance(r[4], (int, float)))
    print(f"folder: {assets['folder']}")
    print(f"clips {len(clips)} | footage {fmt_t(tot)} | usable {fmt_t(use)}")
    print(f"orientation {dict(ori)} | HDR {sum(c['hdr'] for c in clips)} | with audio {sum(c['has_audio'] for c in clips)}")
    print(f"speech likely in {len(speech)} clips: {' '.join(speech[:30])}")
    if a.table:
        print("id   dur   O usable wins speech bad  name")
        for r in rows:
            print(f"{r[0]:5}{r[2]:6.1f} {r[3]} {r[4]!s:>6} {r[5]:3}  {r[6]:4.2f}  {r[7]:<10} {r[1]}")


# ----------------------------------------------------------------- sheets / strips
def grab(cap, t, fps):
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(t * fps)))
    ok, fr = cap.read()
    return fr if ok else None


def label(img, text, org, scale=0.5, color=(255, 255, 255)):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def clip_row(work, clip, n, tile_h, t0=None, t1=None):
    proxy = os.path.join(work, "proxies", clip["id"] + ".mp4")
    an = load_analysis(work, clip["id"])
    cap = cv2.VideoCapture(proxy if os.path.exists(proxy) else clip["file"])
    pfps = cap.get(cv2.CAP_PROP_FPS) or clip["fps"]
    dur = clip["duration"]
    t0 = 0.2 if t0 is None else max(0, t0)
    t1 = dur - 0.2 if t1 is None else min(dur - 0.15, t1)
    ts = [t0 + (t1 - t0) * i / max(1, n - 1) for i in range(n)] if n > 1 else [(t0 + t1) / 2]
    tw = int(round(tile_h * clip["w"] / clip["h"]))
    tiles = []
    for t in ts:
        fr = grab(cap, t, pfps)
        if fr is None:
            fr = np.zeros((tile_h, tw, 3), np.uint8)
        fr = cv2.resize(fr, (tw, tile_h), interpolation=cv2.INTER_AREA)
        label(fr, fmt_t(t), (4, tile_h - 6), 0.45)
        tiles.append(fr)
    cap.release()
    gap = np.full((tile_h, 3, 3), 30, np.uint8)
    strip = tiles[0]
    for tl in tiles[1:]:
        strip = np.hstack([strip, gap, tl])
    # quality bar: green usable / red not, white ticks scene cuts, markers at sample times
    bar = np.full((10, strip.shape[1], 3), (40, 40, 160), np.uint8)
    span = max(0.01, t1 - t0)
    for u in an.get("usable", []):
        x0 = int((max(u["in"], t0) - t0) / span * strip.shape[1])
        x1 = int((min(u["out"], t1) - t0) / span * strip.shape[1])
        if x1 > x0:
            bar[:, x0:x1] = (60, 170, 60)
    for c in an.get("scene_cuts", []):
        if t0 <= c <= t1:
            x = int((c - t0) / span * strip.shape[1])
            bar[:, max(0, x - 1):x + 1] = (255, 255, 255)
    head = np.full((tile_h + 10, 150, 3), 22, np.uint8)
    label(head, clip["id"], (8, 24), 0.75, (120, 220, 255))
    label(head, f"{dur:.1f}s {clip['orientation'][:4]}", (8, 48), 0.45)
    label(head, f"use {an.get('usable_seconds', '?')}s", (8, 70), 0.45)
    sc = (an.get("audio") or {}).get("speech_score", 0)
    if sc >= 0.35:
        label(head, f"speech {sc:.2f}", (8, 92), 0.45, (120, 255, 120))
    nm = os.path.basename(clip["name"])[:20]
    label(head, nm, (8, tile_h + 2), 0.38, (200, 200, 200))
    return np.hstack([head, np.vstack([strip, bar])])


def stack_rows(rows, width):
    out = []
    for r in rows:
        if r.shape[1] < width:
            r = np.hstack([r, np.full((r.shape[0], width - r.shape[1], 3), 15, np.uint8)])
        out.append(r)
        out.append(np.full((6, width, 3), 60, np.uint8))
    return np.vstack(out)


def cmd_sheets(a):
    work = os.path.abspath(a.work)
    clips = load_assets(work)["clips"]
    if a.ids:
        want = set(a.ids.split(","))
        clips = [c for c in clips if c["id"] in want]
    d = os.path.join(work, "sheets")
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        if a.ids is None and f.endswith(".jpg"):
            os.remove(os.path.join(d, f))
    paths = []
    for i in range(0, len(clips), a.per_sheet):
        group = clips[i:i + a.per_sheet]
        rows = []
        for c in group:
            th = a.tile_h if c["orientation"] != "portrait" else a.tile_h + 40
            n = a.frames if c["orientation"] != "portrait" else a.frames + 2
            rows.append(clip_row(work, c, n, th))
        width = min(max(r.shape[1] for r in rows), 2400)
        rows = [r if r.shape[1] <= width else cv2.resize(r, (width, int(r.shape[0] * width / r.shape[1]))) for r in rows]
        img = stack_rows(rows, width)
        p = os.path.join(d, f"sheet_{i // a.per_sheet + 1:03d}_{group[0]['id']}-{group[-1]['id']}.jpg")
        cv2.imwrite(p, img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        paths.append(p)
    print("\n".join(paths))


def cmd_strip(a):
    work = os.path.abspath(a.work)
    clip = next((c for c in load_assets(work)["clips"] if c["id"] == a.id), None)
    if not clip:
        sys.exit("unknown clip id")
    t0 = a.start if a.start is not None else 0.0
    t1 = a.end if a.end is not None else clip["duration"]
    half = a.n // 2
    th = 150 if clip["orientation"] != "portrait" else 210
    r1 = clip_row(work, clip, half, th, t0, t0 + (t1 - t0) * (half - 1) / max(1, a.n - 1))
    r2 = clip_row(work, clip, a.n - half, th, t0 + (t1 - t0) * half / max(1, a.n - 1), t1)
    w = max(r1.shape[1], r2.shape[1])
    img = stack_rows([r1, r2], w)
    d = os.path.join(work, "strips")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{clip['id']}_{t0:.1f}-{t1:.1f}.jpg")
    cv2.imwrite(p, img, [cv2.IMWRITE_JPEG_QUALITY, 82])
    print(p)


# ----------------------------------------------------------------- EDL
def load_edl(path):
    e = jload(path)
    if not e:
        sys.exit(f"ERROR: cannot read EDL {path}")
    return e


def snap_fps(f):
    """Snap variable / odd frame rates (e.g. iPhone 29.96) to the nearest standard rate string."""
    if isinstance(f, str):
        if "/" in f:
            f = parse_fps(f)
        else:
            f = float(f)
    best = min(STD_FPS, key=lambda x: abs(x - f))
    return STD_FPS_RAW.get(best, str(int(best))) if abs(best - f) < 0.6 else f"{f:.3f}"


def fps_float(r):
    return parse_fps(r) if "/" in str(r) else float(r)


def seg_frames(s, fps):
    """Number of frames for a segment - every cut lands on a frame boundary, so audio never drifts."""
    return max(1, int(round((s["out"] - s["in"]) * fps_float(fps))))


def resolve_target(edl, clipmap):
    st = edl.setdefault("settings", {})
    used = [clipmap[s["clip"]] for s in edl["segments"] if s["clip"] in clipmap]
    if not used:
        sys.exit("ERROR: EDL has no valid segments")
    ori = st.get("orientation") or Counter(c["orientation"] for c in used).most_common(1)[0][0]
    same = [c for c in used if c["orientation"] == ori] or used
    tgt = st.get("target") or {}
    if not tgt.get("w"):
        w, h = Counter((c["w"], c["h"]) for c in same).most_common(1)[0][0]
        if a_max := st.get("max_height"):
            if min(w, h) > a_max:
                f = a_max / min(w, h)
                w, h = int(round(w * f / 2) * 2), int(round(h * f / 2) * 2)
        tgt["w"], tgt["h"] = w, h
    if not tgt.get("fps"):
        tgt["fps"] = snap_fps(Counter(snap_fps(c["fps"]) for c in same).most_common(1)[0][0])
    hdr = any(c["hdr"] for c in same)
    tgt.setdefault("hdr", hdr)
    if hdr:
        ref = next(c for c in same if c["hdr"])
        tgt.setdefault("transfer", ref["color_transfer"])
        tgt.setdefault("primaries", ref["color_primaries"] or "bt2020")
        tgt.setdefault("colorspace", ref["color_space"] or "bt2020nc")
    st["orientation"], st["target"] = ori, tgt
    return st


def validate(edl, clipmap, quiet=False):
    st = edl.get("settings", {})
    errs, warns = [], []
    total = 0.0
    for i, s in enumerate(edl.get("segments", []), 1):
        c = clipmap.get(s.get("clip"))
        if not c:
            errs.append(f"#{i}: unknown clip {s.get('clip')}")
            continue
        if not (0 <= s["in"] < s["out"] <= c["duration"] + 0.05):
            errs.append(f"#{i} {c['id']}: in/out {s['in']}-{s['out']} outside 0-{c['duration']}")
        d = s["out"] - s["in"]
        total += d
        if d < 1.0:
            warns.append(f"#{i} {c['id']}: very short ({d:.2f}s)")
        if st.get("orientation") and c["orientation"] != st["orientation"]:
            errs.append(f"#{i} {c['id']}: orientation {c['orientation']} != {st['orientation']} (would need padding)")
    segs = edl.get("segments", [])
    hd = {clipmap[x["clip"]]["hdr"] for x in segs if x.get("clip") in clipmap}
    if len(hd) > 1:
        warns.append("mix of HDR and SDR clips - SDR clips will look slightly different; consider using only one kind")
    for i in range(1, len(segs)):
        a, b = segs[i - 1], segs[i]
        if a.get("clip") == b.get("clip") and abs(b["in"] - a["out"]) < 0.3:
            warns.append(f"#{i}-#{i + 1}: contiguous parts of {a['clip']} (jump cut risk)")
    tgt = st.get("duration_target")
    if tgt and abs(total - tgt) > max(3, 0.12 * tgt):
        warns.append(f"total {total:.1f}s vs target {tgt}s")
    if not quiet:
        print(f"segments {len(segs)} total {total:.1f}s")
        for e in errs: print("ERROR", e)
        for w in warns: print("WARN ", w)
        print("OK" if not errs else "FIX ERRORS")
    return errs, warns, total


def cmd_validate(a):
    work = os.path.abspath(a.work)
    clipmap = {c["id"]: c for c in load_assets(work)["clips"]}
    edl = load_edl(a.edl or os.path.join(work, "edl.json"))
    resolve_target(edl, clipmap)
    validate(edl, clipmap)


# ----------------------------------------------------------------- render
def seg_cmd(s, c, st, out, first, last, amode):
    tgt = st["target"]
    W, H, fps = tgt["w"], tgt["h"], tgt["fps"]
    nfr = seg_frames(s, fps)
    d = nfr / fps_float(fps)
    edge = float(st.get("fade_edges", 0.5) or 0)
    vf = [f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos",
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2", "setsar=1", f"fps={fps}"]
    if first and edge:
        vf.append(f"fade=t=in:st=0:d={edge}")
    if last and edge:
        vf.append(f"fade=t=out:st={max(0, d - edge):.3f}:d={edge}")
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{s['in']:.3f}", "-i", c["file"]]
    keep_audio = amode != "mute"
    if keep_audio and not c["has_audio"]:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-map", "0:v:0", "-frames:v", str(nfr)]
    if tgt.get("hdr"):
        vf.append("format=yuv420p10le")
        cmd += ["-vf", ",".join(vf), "-c:v", "libx265", "-preset", st.get("preset", "veryfast"),
                "-crf", str(st.get("crf", 18)), "-pix_fmt", "yuv420p10le", "-tag:v", "hvc1",
                "-color_primaries", tgt.get("primaries", "bt2020"), "-color_trc", tgt.get("transfer", "arib-std-b67"),
                "-colorspace", tgt.get("colorspace", "bt2020nc"),
                "-x265-params", "log-level=error:hdr-opt=1:repeat-headers=1"]
    else:
        vf.append("format=yuv420p")
        cmd += ["-vf", ",".join(vf), "-c:v", "libx264", "-preset", st.get("preset", "veryfast"),
                "-crf", str(st.get("crf", 18)), "-pix_fmt", "yuv420p"]
        if c.get("color_primaries") == "bt709" or c.get("color_space") == "bt709":
            cmd += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    cmd += ["-an", "-video_track_timescale", "90000", out]
    if keep_audio:
        mute_this = s.get("mute") or (amode == "auto" and s.get("speech") is False)
        af = ["aresample=48000", "aformat=sample_fmts=s16:channel_layouts=stereo"]
        fi = edge if (first and edge) else 0.03
        fo = edge if (last and edge) else 0.03
        af += [f"atrim=0:{d:.6f}", f"apad=whole_dur={d:.6f}",
               f"afade=t=in:st=0:d={fi}", f"afade=t=out:st={max(0, d - fo):.3f}:d={fo}"]
        if mute_this:
            af.append("volume=0")
        cmd += ["-map", "1:a:0" if not c["has_audio"] else "0:a:0", "-af", ",".join(af),
                "-t", f"{d:.6f}", "-c:a", "pcm_s16le", out[:-4] + ".wav"]
    return cmd


def seg_key(s, c, st, first, last, amode):
    blob = json.dumps([c["file"], os.path.getmtime(c["file"]), s["in"], s["out"], s.get("mute"),
                       s.get("speech"), st["target"], st.get("fade_edges", 0.5), st.get("crf", 18),
                       st.get("preset", "veryfast"), first, last, amode], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def cmd_render(a):
    work = os.path.abspath(a.work)
    assets = load_assets(work)
    clipmap = {c["id"]: c for c in assets["clips"]}
    edl_path = a.edl or os.path.join(work, "edl.json")
    edl = load_edl(edl_path)
    st = resolve_target(edl, clipmap)
    errs, warns, total = validate(edl, clipmap, quiet=True)
    if errs:
        print("\n".join("ERROR " + e for e in errs))
        sys.exit("EDL has errors - fix before rendering")
    amode = st.get("audio", "auto")
    if amode == "auto":
        used = [clipmap[s["clip"]] for s in edl["segments"]]
        has = any(c["has_audio"] for c in used)
        sp = [(load_analysis(work, c["id"]).get("audio") or {}).get("speech_score", 0) >= 0.35 for c in used]
        amode = "keep" if (has and any(sp)) else "mute"
        st["audio_resolved"] = amode
    cache = os.path.join(work, "render_cache")
    os.makedirs(cache, exist_ok=True)
    segs = edl["segments"]
    n = len(segs)
    jobs = []
    for i, s in enumerate(segs):
        c = clipmap[s["clip"]]
        key = seg_key(s, c, st, i == 0, i == n - 1, amode)
        out = os.path.join(cache, f"{key}.mp4")
        s["_cache"] = out
        if not os.path.exists(out):
            jobs.append((s, c, out, i == 0, i == n - 1))
    t0 = time.time()
    done = 0

    def work_one(j):
        s, c, out, first, last = j
        tmp = out[:-4] + ".part.mp4"
        r = run(seg_cmd(s, c, st, tmp, first, last, amode))
        if r.returncode != 0:
            raise RuntimeError(f"segment {c['id']} {s['in']}-{s['out']} failed: {r.stderr.decode()[-600:]}")
        if amode != "mute":
            os.replace(tmp[:-4] + ".wav", out[:-4] + ".wav")
        os.replace(tmp, out)

    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        it = iter(jobs)
        running = set()
        while True:
            while len(running) < a.jobs and time.time() - t0 < a.budget:
                j = next(it, None)
                if j is None:
                    break
                running.add(ex.submit(work_one, j))
            if not running:
                break
            fin = [f for f in running if f.done()]
            for f in fin:
                running.discard(f)
                f.result()
                done += 1
            if not fin:
                time.sleep(0.2)
    left = len(jobs) - done
    if left:
        print(f"encoded {done} segments, {left} left - NOT DONE, run render again")
        return
    # concat
    lst = os.path.join(cache, "concat.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for s in segs:
            f.write("file '" + s["_cache"].replace("'", "'\\''") + "'\n")
    if a.out:
        out = a.out
    else:
        base = re.sub(r"[^\w\-]+", "_", edl.get("project") or assets.get("project") or "final").strip("_") or "final"
        v = 1
        while os.path.exists(os.path.join(work, f"{base}_v{v}.mp4")):
            v += 1
        out = os.path.join(work, f"{base}_v{v}.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst]
    if amode != "mute":
        alst = os.path.join(cache, "concat_audio.txt")
        with open(alst, "w", encoding="utf-8") as f:
            for s in segs:
                f.write("file '" + (s["_cache"][:-4] + ".wav").replace("'", "'\\''") + "'\n")
        cmd += ["-f", "concat", "-safe", "0", "-i", alst, "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c", "copy"]
    cmd += ["-movflags", "+faststart", out]
    r = run(cmd)
    if r.returncode != 0:
        sys.exit("concat failed: " + r.stderr.decode()[-600:])
    # timeline positions for the edit list
    pos = 0.0
    fpsf = fps_float(st["target"]["fps"])
    for s in segs:
        s.pop("_cache", None)
        d = seg_frames(s, st["target"]["fps"]) / fpsf
        s["t_in"], s["t_out"] = round(pos, 3), round(pos + d, 3)
        pos += d
    edl["output"] = out
    edl["rendered_at"] = time.strftime("%Y-%m-%d %H:%M")
    jsave(edl_path, edl)
    # drop cache entries no longer referenced
    if a.prune:
        keep = {seg_key(s, clipmap[s["clip"]], st, i == 0, i == n - 1, amode) for i, s in enumerate(segs)}
        for f in os.listdir(cache):
            if f.endswith((".mp4", ".wav")) and f[:16] not in keep:
                os.remove(os.path.join(cache, f))
    print(f"OUTPUT={out}")
    print(f"duration {pos:.2f}s  segments {n}  audio {amode}  {st['target']['w']}x{st['target']['h']}@{st['target']['fps']}"
          f"{' HDR' if st['target'].get('hdr') else ''}")
    for w in warns:
        print("WARN", w)


# ----------------------------------------------------------------- check
def cmd_check(a):
    work = os.path.abspath(a.work)
    edl_path = a.edl or os.path.join(work, "edl.json")
    edl = load_edl(edl_path)
    out = edl.get("output")
    if not out or not os.path.exists(out):
        sys.exit("no rendered output in EDL")
    info = probe(out)
    segs = edl["segments"]
    expected = segs[-1]["t_out"] if "t_out" in segs[-1] else sum(s["out"] - s["in"] for s in segs)
    issues = []
    if abs(info["duration"] - expected) > 0.1:
        issues.append(f"duration {info['duration']:.2f}s vs expected {expected:.2f}s")
    r = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json", out])
    sd = {x["codec_type"]: float(x.get("duration", 0)) for x in json.loads(r.stdout or b"{}").get("streams", [])}
    if "audio" in sd and abs(sd["audio"] - sd.get("video", 0)) > 0.06:
        issues.append(f"audio/video length differ: video {sd.get('video', 0):.3f}s audio {sd['audio']:.3f}s")
    # black frames (ignore intended fade at the very start/end)
    r = run(["ffmpeg", "-v", "info", "-i", out, "-vf", "blackdetect=d=0.15:pix_th=0.08", "-an", "-f", "null", "-"])
    edge = float(edl.get("settings", {}).get("fade_edges", 0.5) or 0) + 0.25
    for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr.decode()):
        bs, be = float(m.group(1)), float(m.group(2))
        if bs > edge and be < info["duration"] - edge:
            issues.append(f"black frames {fmt_t(bs)}-{fmt_t(be)}")
    cuts = [s["t_out"] for s in segs[:-1] if "t_out" in s]
    # visual check around cuts + near-duplicate detection + audio pops
    cap = cv2.VideoCapture(out)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    tiles = []
    dup = []
    for k, t in enumerate(cuts, 1):
        a_ = grab(cap, max(0, t - 0.25), fps)
        b_ = grab(cap, t + 0.15, fps)
        if a_ is None or b_ is None:
            issues.append(f"cannot read frames at cut {k} ({fmt_t(t)})")
            continue
        ga = cv2.cvtColor(cv2.resize(a_, (64, 36), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        gb = cv2.cvtColor(cv2.resize(b_, (64, 36), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
        ga -= ga.mean(); gb -= gb.mean()
        zncc = float((ga * gb).sum() / (np.sqrt((ga ** 2).sum() * (gb ** 2).sum()) + 1e-6))
        if zncc > 0.92:                            # same framing on both sides of the cut
            dup.append(k)
            issues.append(f"cut {k} at {fmt_t(t)}: shots look almost identical (jump cut?)")
        th = 120
        tw = int(th * a_.shape[1] / a_.shape[0])
        pair = np.hstack([cv2.resize(a_, (tw, th)), np.full((th, 4, 3), 255, np.uint8), cv2.resize(b_, (tw, th))])
        label(pair, f"cut {k} {fmt_t(t)}", (6, 18), 0.5, (120, 220, 255))
        tiles.append(pair)
    cap.release()
    if info["has_audio"]:
        sr = 16000
        r = run(["ffmpeg", "-v", "error", "-i", out, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"])
        x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768
        for k, t in enumerate(cuts, 1):
            i = int(t * sr)
            near = x[max(0, i - 800):i + 800]
            ctx = x[max(0, i - 16000):i + 16000]
            if near.size and ctx.size:
                pk = float(np.abs(near).max())
                rms = float(np.sqrt((ctx ** 2).mean())) + 1e-6
                if pk > 0.2 and pk / rms > 8:
                    issues.append(f"cut {k} at {fmt_t(t)}: audio spike (possible pop)")
        r = run(["ffmpeg", "-v", "info", "-i", out, "-af", "ebur128", "-f", "null", "-"])
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr.decode())
        loud = float(m[-1]) if m else None
    else:
        loud = None
    sheet = None
    if tiles:
        cols = 3
        rows = []
        for i in range(0, len(tiles), cols):
            row = tiles[i:i + cols]
            h = row[0].shape[0]
            row = [cv2.resize(t, (int(t.shape[1] * h / t.shape[0]), h)) for t in row]
            rows.append(np.hstack(sum([[t, np.full((h, 8, 3), 20, np.uint8)] for t in row], [])))
        width = max(r.shape[1] for r in rows)
        sheet = os.path.join(work, "check_cuts.jpg")
        cv2.imwrite(sheet, stack_rows(rows, width), [cv2.IMWRITE_JPEG_QUALITY, 80])
    rep = {"output": out, "duration": info["duration"], "expected": round(expected, 2),
           "resolution": f"{info['w']}x{info['h']}", "fps": info["fps"], "audio": info["has_audio"],
           "loudness_lufs": loud, "cuts": len(cuts), "issues": issues, "cuts_sheet": sheet}
    jsave(os.path.join(work, "check.json"), rep)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print("PASS" if not issues else f"{len(issues)} ISSUE(S)")


# ----------------------------------------------------------------- CSV edit list
CSV_COLS = {
    "en": ["No", "Clip ID", "File", "In (s)", "Out (s)", "Duration (s)", "Timeline In", "Timeline Out", "Content",
           "Reason", "Mute (yes/no)"],
    "zh": ["序号", "素材ID", "素材文件", "起(秒)", "止(秒)", "时长(秒)", "成片起", "成片止", "画面内容", "选用理由", "静音(是/否)"]}
UNUSED_COLS = {"en": ["Clip ID", "File", "Duration (s)", "Orientation", "Usable (s)", "Why not used"],
               "zh": ["素材ID", "素材文件", "时长(秒)", "方向", "可用秒数", "未使用原因"]}
CSV_NAMES = {"en": ("edit_list.csv", "unused_clips.csv"), "zh": ("剪辑清单.csv", "未使用素材.csv")}
KEYS = ["no", "id", "file", "in", "out", "dur", "t_in", "t_out", "label", "reason", "mute"]
YES = {"yes", "y", "1", "true", "是", "x"}

def cmd_csv(a):
    work = os.path.abspath(a.work)
    assets = load_assets(work)
    clipmap = {c["id"]: c for c in assets["clips"]}
    byname = {c["name"]: c for c in assets["clips"]}
    edl_path = a.edl or os.path.join(work, "edl.json")
    lang = a.lang
    if a.from_csv:
        edl = jload(edl_path, {"version": 1, "settings": {}, "segments": []})
        alias = {}
        for lg in CSV_COLS.values():
            for k, h in zip(KEYS, lg):
                alias[h.strip().lower()] = k
        rows = []
        with open(a.from_csv, encoding="utf-8-sig", newline="") as f:
            for n, raw in enumerate(csv.DictReader(f), 1):
                r = {alias.get((k or "").strip().lower(), k): (v or "").strip() for k, v in raw.items()}
                if not (r.get("id") or r.get("file")) or not r.get("in"):
                    continue
                c = clipmap.get(r.get("id", "")) or byname.get(r.get("file", ""))
                if not c:
                    sys.exit(f"CSV row {n}: unknown clip {r.get('id')} / {r.get('file')}")
                try:
                    order = float(r.get("no") or n)
                except ValueError:
                    order = n
                seg = {"clip": c["id"], "in": round(float(r["in"].replace(",", ".")), 3),
                       "out": round(float(r["out"].replace(",", ".")), 3),
                       "label": r.get("label", ""), "reason": r.get("reason", "")}
                if r.get("mute", "").lower() in YES:
                    seg["mute"] = True
                rows.append((order, n, seg))
        rows.sort(key=lambda x: (x[0], x[1]))
        edl["segments"] = [s for _, _, s in rows]
        jsave(edl_path, edl)
        print(f"EDL updated from CSV: {len(rows)} segments -> {edl_path}")
        return
    edl = load_edl(edl_path)
    n1, n2 = CSV_NAMES[lang]
    out = a.out or os.path.join(work, n1)
    yes = "是" if lang == "zh" else "yes"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS[lang])
        pos = 0.0
        for i, s in enumerate(edl["segments"], 1):
            c = clipmap.get(s["clip"], {})
            d = s["out"] - s["in"]
            t0, t1 = s.get("t_in", pos), s.get("t_out", pos + d)
            w.writerow([i, s["clip"], c.get("name", ""), f"{s['in']:.2f}", f"{s['out']:.2f}", f"{t1 - t0:.2f}",
                        fmt_t(t0), fmt_t(t1), s.get("label", ""), s.get("reason", ""), yes if s.get("mute") else ""])
            pos = t1
    used = {s["clip"] for s in edl["segments"]}
    listed = {u["clip"]: u.get("reason", "") for u in edl.get("unused", [])}
    default_reason = "未选用（同类镜头已有更好的）" if lang == "zh" else "not selected (a better similar shot was used)"
    out2 = os.path.join(os.path.dirname(out), n2)
    with open(out2, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(UNUSED_COLS[lang])
        for c in assets["clips"]:
            if c["id"] in used:
                continue
            an = load_analysis(work, c["id"])
            ori = {"portrait": "竖", "landscape": "横", "square": "方"}[c["orientation"]] if lang == "zh" else c["orientation"]
            w.writerow([c["id"], c["name"], f"{c['duration']:.1f}", ori, an.get("usable_seconds", ""),
                        listed.get(c["id"], default_reason)])
    print(out)
    print(out2)


# ----------------------------------------------------------------- export to editing software
def tc_to_frames(tc, base):
    try:
        hh, mm, ss, ff = [int(x) for x in re.split(r"[:;.]", tc)]
        return ((hh * 60 + mm) * 60 + ss) * base + ff
    except Exception:
        return 0


def frames_to_tc(n, base):
    ff = n % base; n //= base
    ss = n % 60; n //= 60
    return f"{n // 60:02d}:{n % 60:02d}:{ss:02d}:{ff:02d}"


def map_path(p, maps):
    for m in maps or []:
        src, dst = m.split("=", 1)
        if p.startswith(src):
            p = dst + p[len(src):]
            break
    return p


def file_uri(p):
    if re.match(r"^[A-Za-z]:[\\/]", p):                      # Windows drive path
        return "file:///" + urllib.parse.quote(p.replace("\\", "/"), safe="/:")
    return "file://" + urllib.parse.quote(p, safe="/")


def cmd_export(a):
    work = os.path.abspath(a.work)
    assets = load_assets(work)
    clipmap = {c["id"]: c for c in assets["clips"]}
    edl = load_edl(a.edl or os.path.join(work, "edl.json"))
    st = resolve_target(edl, clipmap)
    fps = st["target"]["fps"]
    if "/" in str(fps):
        num, den = [int(x) for x in str(fps).split("/")]
    else:
        num, den = int(round(float(fps) * 1000)), 1000
        g = math.gcd(num, den); num, den = num // g, den // g
    fpsf = num / den
    base = int(round(fpsf))
    name = edl.get("project") or assets.get("project") or "Fullcut"
    segs = edl["segments"]
    # ---- CMX 3600 EDL (Premiere Pro, DaVinci Resolve, Avid)
    rec = tc_to_frames("01:00:00:00", base)
    lines = [f"TITLE: {name[:60]}", "FCM: NON-DROP FRAME", ""]
    for k, s in enumerate(segs, 1):
        c = clipmap[s["clip"]]
        n = seg_frames(s, fps)
        src0 = tc_to_frames(c.get("timecode") or "00:00:00:00", base) + int(round(s["in"] * fpsf))
        ch = "AA/V" if c["has_audio"] and st.get("audio_resolved", st.get("audio")) != "mute" else "V"
        lines.append(f"{k:03d}  {c['id'][:8]:<8} {ch:<5} C        {frames_to_tc(src0, base)} {frames_to_tc(src0 + n, base)} "
                     f"{frames_to_tc(rec, base)} {frames_to_tc(rec + n, base)}")
        lines.append(f"* FROM CLIP NAME: {os.path.basename(c['file'])}")
        if s.get("label"):
            lines.append(f"* COMMENT: {s['label']}")
        lines.append("")
        rec += n
    p_edl = os.path.join(work, "timeline.edl")
    with open(p_edl, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines))
    # ---- FCPXML 1.8 (Final Cut Pro 10.4+, DaVinci Resolve)
    from xml.sax.saxutils import quoteattr
    W, H = st["target"]["w"], st["target"]["h"]

    def rt(frames):
        return f"{frames * den}/{num}s" if frames else "0s"

    x = ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE fcpxml>", '<fcpxml version="1.8">', "  <resources>",
         f'    <format id="r0" frameDuration="{den}/{num}s" width="{W}" height="{H}"/>']
    used = []
    for s in segs:
        if s["clip"] not in used:
            used.append(s["clip"])
    for k, cid in enumerate(used, 1):
        c = clipmap[cid]
        tc0 = tc_to_frames(c.get("timecode") or "00:00:00:00", base)
        x.append(f'    <asset id="a{k}" name={quoteattr(os.path.splitext(os.path.basename(c["file"]))[0])} '
                 f'start="{rt(tc0)}" duration="{rt(int(c["duration"] * fpsf))}" hasVideo="1" '
                 f'hasAudio="{1 if c["has_audio"] else 0}" format="r0"'
                 + (' audioSources="1" audioChannels="2" audioRate="48000"' if c["has_audio"] else "")
                 + f' src={quoteattr(file_uri(map_path(c["file"], a.path_map)))}/>')
    total = sum(seg_frames(s, fps) for s in segs)
    x += ["  </resources>", "  <library>", f"    <event name={quoteattr(name)}>", f"      <project name={quoteattr(name)}>",
          f'        <sequence format="r0" duration="{rt(total)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">',
          "          <spine>"]
    off = 0
    for s in segs:
        c = clipmap[s["clip"]]
        k = used.index(s["clip"]) + 1
        n = seg_frames(s, fps)
        start = tc_to_frames(c.get("timecode") or "00:00:00:00", base) + int(round(s["in"] * fpsf))
        x.append(f'            <asset-clip ref="a{k}" name={quoteattr(s.get("label") or c["id"])} offset="{rt(off)}" '
                 f'start="{rt(start)}" duration="{rt(n)}" format="r0" tcFormat="NDF"'
                 + (' audioRole="dialogue"' if c["has_audio"] else "") + "/>")
        off += n
    x += ["          </spine>", "        </sequence>", "      </project>", "    </event>", "  </library>", "</fcpxml>"]
    p_x = os.path.join(work, "timeline.fcpxml")
    with open(p_x, "w", encoding="utf-8") as f:
        f.write("\n".join(x) + "\n")
    print(p_edl)
    print(p_x)


# ----------------------------------------------------------------- transcription (optional)
def cmd_transcribe(a):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper is not installed. Install it with:  pip install faster-whisper")
    work = os.path.abspath(a.work)
    clips = load_assets(work)["clips"]
    if a.ids:
        want = set(a.ids.split(","))
        clips = [c for c in clips if c["id"] in want]
    elif not a.all:
        clips = [c for c in clips if (load_analysis(work, c["id"]).get("audio") or {}).get("speech_score", 0) >= a.min_speech]
    todo = [c for c in clips if c["has_audio"] and not os.path.exists(os.path.join(work, "analysis", c["id"] + ".words.json"))]
    model = WhisperModel(a.model, device="auto", compute_type="int8") if todo else None
    t0 = time.time()
    for c in todo:
        if time.time() - t0 > a.budget:
            break
        segs, info = model.transcribe(c["file"], language=a.language, word_timestamps=True, vad_filter=True)
        out = {"id": c["id"], "language": info.language, "segments": []}
        for sg in segs:
            out["segments"].append({"start": round(sg.start, 2), "end": round(sg.end, 2), "text": sg.text.strip(),
                                    "words": [{"s": round(w.start, 2), "e": round(w.end, 2), "w": w.word}
                                              for w in (sg.words or [])]})
        jsave(os.path.join(work, "analysis", c["id"] + ".words.json"), out)
    left = [c for c in todo if not os.path.exists(os.path.join(work, "analysis", c["id"] + ".words.json"))]
    # compact transcript for the planner (one line per phrase)
    lines = []
    for c in load_assets(work)["clips"]:
        d = jload(os.path.join(work, "analysis", c["id"] + ".words.json"))
        if not d:
            continue
        lines.append(f"## {c['id']}  {c['name']}  ({c['duration']:.1f}s)")
        for sg in d["segments"]:
            lines.append(f"[{sg['start']:.2f}-{sg['end']:.2f}] {sg['text']}")
        lines.append("")
    with open(os.path.join(work, "transcript.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"transcribed {len(todo) - len(left)}, remaining {len(left)}")
    print("DONE" if not left else "NOT DONE - run transcribe again")
    print(os.path.join(work, "transcript.md"))


# ----------------------------------------------------------------- clean (logo + outro)
CLEAN_PRESETS = {
    "generic":   {"corners": ["br", "bl", "tr", "tl"], "default_tail": 0.0, "max_tail": 12.0},
    "notebooklm": {"corners": ["br"], "default_tail": 2.5, "max_tail": 12.0},
}


def decode_gray(path, w, t0=None, t1=None, fps=2):
    info = probe(path)
    h = int(round(w * info["h"] / info["w"] / 2) * 2)
    cmd = ["ffmpeg", "-v", "error"]
    if t0 is not None:
        cmd += ["-ss", f"{t0:.3f}"]
    cmd += ["-i", path]
    if t1 is not None:
        cmd += ["-t", f"{t1 - (t0 or 0):.3f}"]
    cmd += ["-vf", f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"]
    raw = np.frombuffer(run(cmd).stdout, dtype=np.uint8)
    n = raw.size // (w * h)
    return raw[: n * w * h].reshape(n, h, w), info


def detect_logo(path, corners):
    """Find a static, edge-rich mark in one of the given corners. Returns a relative box or None."""
    W = 640
    info = probe(path)
    dur = info["duration"]
    frames, info = decode_gray(path, W, dur * 0.05, dur * 0.85, fps=max(0.5, 40 / max(1, dur * 0.8)))
    if len(frames) < 8:
        return None
    H = frames.shape[1]
    best = None
    for cn in corners:
        y0, y1 = (int(H * 0.70), H) if cn[0] == "b" else (0, int(H * 0.30))
        x0, x1 = (int(W * 0.60), W) if cn[1] == "r" else (0, int(W * 0.40))
        reg = frames[:, y0:y1, x0:x1].astype(np.float32)
        std = reg.std(0)
        edges = np.mean([np.abs(cv2.Sobel(f, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(f, cv2.CV_32F, 0, 1)) for f in reg], 0)
        # a logo keeps its edges while the picture around it changes
        mask = ((std < 14) & (edges > 22)).astype(np.uint8)
        if float(np.median(std)) < 6:               # whole corner static (still picture) -> no evidence
            continue
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 15), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        for k in range(1, n):
            x, y, w, h, area = stats[k]
            if area < 25 or w < 12 or h < 5 or w > (x1 - x0) * 0.95 or h > (y1 - y0) * 0.8:
                continue
            # prefer big marks close to the frame edge
            ex = (x1 - x0) - (x + w) if cn[1] == "r" else x
            ey = (y1 - y0) - (y + h) if cn[0] == "b" else y
            score = area - 3 * (ex + ey)
            if not best or score > best[0]:
                best = (score, x + x0, y + y0, w, h, cn)
    if not best:
        return None
    _, x, y, w, h, cn = best
    pad = 6
    x, y = max(0, x - pad), max(0, y - pad)
    w, h = min(W - x - 2, w + 2 * pad), min(H - y - 2, h + 2 * pad)
    return {"x": round(x / W, 4), "y": round(y / H, 4), "w": round(w / W, 4), "h": round(h / H, 4), "corner": cn}


def detect_outro(path, box, max_tail=12.0, default_tail=2.5):
    """Return (time where the outro starts, method)."""
    info = probe(path)
    dur = info["duration"]
    t0 = max(0.0, dur - max_tail)
    W = 320
    frames, _ = decode_gray(path, W, t0, dur, fps=10)
    if len(frames) < 5:
        return round(dur - default_tail, 2), "default"
    H = frames.shape[1]
    times = [t0 + i / 10 for i in range(len(frames))]
    if box:                                        # 1) the logo disappears and stays gone until the end
        x, y = int(box["x"] * W), int(box["y"] * H)
        w, h = max(4, int(box["w"] * W)), max(4, int(box["h"] * H))
        ref, _ = decode_gray(path, W, dur * 0.3, dur * 0.6, fps=1)
        if len(ref):
            tpl = np.median(ref[:, y:y + h, x:x + w], 0).astype(np.float32)
            gone = [float(np.abs(f[y:y + h, x:x + w].astype(np.float32) - tpl).mean()) > 18 for f in frames]
            k = len(gone)
            while k > 0 and gone[k - 1]:
                k -= 1
            if k < len(gone) and dur - times[k] >= 0.8:
                return round(times[k], 2), "logo_gone"
    hs = []                                        # 2) last big scene change in the tail
    for f in frames:
        hh = cv2.calcHist([f], [0], None, [32], [0, 256]); cv2.normalize(hh, hh); hs.append(hh)
    ch = [i for i in range(1, len(hs)) if 1 - cv2.compareHist(hs[i - 1], hs[i], cv2.HISTCMP_CORREL) > 0.5]
    ch = [i for i in ch if 0.8 <= dur - times[i] <= 8]
    if ch and default_tail > 0:
        return round(times[ch[-1]], 2), "scene_change"
    return round(dur - default_tail, 2), "default" if default_tail else "none"


def cmd_clean(a):
    preset = CLEAN_PRESETS[a.preset]
    cfg = jload(a.config, {}) if a.config else {}
    pc = cfg.get(a.preset, {})
    src = os.path.abspath(a.input)
    files = [src] if os.path.isfile(src) else sorted(
        os.path.join(src, f) for f in os.listdir(src) if os.path.splitext(f)[1].lower() in VIDEO_EXT)
    outdir = os.path.abspath(a.out or os.path.join(src if os.path.isdir(src) else os.path.dirname(src), "_clean"))
    os.makedirs(outdir, exist_ok=True)
    corners = [a.corner] if a.corner != "auto" else preset["corners"]
    report = []
    for p in files:
        info = probe(p)
        box, how_box = None, None
        if a.box:
            x, y, w, h = [float(v) for v in a.box.split(",")]
            box, how_box = {"x": x, "y": y, "w": w, "h": h}, "manual"
        elif not a.no_logo:
            box = detect_logo(p, corners)
            how_box = "detected" if box else None
            if not box and pc.get("box"):
                box, how_box = pc["box"], "saved"
        if a.no_logo:
            box = None
        if a.tail is not None:
            end, how_end = info["duration"] - a.tail, "manual"
        elif a.no_trim:
            end, how_end = info["duration"], "none"
        else:
            end, how_end = detect_outro(p, box, preset["max_tail"], pc.get("default_tail", preset["default_tail"]))
        W, H = info["w"], info["h"]
        vf = []
        if box:
            x = max(1, int(box["x"] * W)); y = max(1, int(box["y"] * H))
            w = min(W - x - 1, int(box["w"] * W)); h = min(H - y - 1, int(box["h"] * H))
            vf.append(f"delogo=x={x}:y={y}:w={w}:h={h}")
        out = os.path.join(outdir, os.path.splitext(os.path.basename(p))[0] + "_clean.mp4")
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", p, "-t", f"{end:.3f}"]
        if vf:
            cmd += ["-vf", ",".join(vf)]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
        cmd += ["-c:a", "aac", "-b:a", "192k"] if info["has_audio"] else ["-an"]
        cmd += ["-movflags", "+faststart", out]
        r = run(cmd)
        ok = r.returncode == 0
        report.append({"file": p, "output": out if ok else None, "logo_box": box, "logo_source": how_box,
                       "cut_at": round(end, 2), "cut_source": how_end, "removed_tail": round(info["duration"] - end, 2),
                       "error": None if ok else r.stderr.decode()[-300:]})
        if ok and box and how_box == "detected" and a.config:
            cfg.setdefault(a.preset, {})["box"] = box
            jsave(a.config, cfg)
        if ok:                                     # preview frame: check the logo area by eye
            cap = cv2.VideoCapture(out)
            fr = grab(cap, max(0, min(end - 1, info["duration"] * 0.4)), cap.get(cv2.CAP_PROP_FPS) or 30)
            cap.release()
            if fr is not None:
                cv2.imwrite(out[:-4] + "_preview.jpg", cv2.resize(fr, (960, int(960 * fr.shape[0] / fr.shape[1]))))
    print(json.dumps(report, ensure_ascii=False, indent=1))


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="FullcutStudio - AI auto-editing engine")
    ap.add_argument("--version", action="version", version="FullcutStudio 1.0.0")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("scan"); p.add_argument("folder"); p.add_argument("--work"); p.add_argument("--recursive", action="store_true")
    p = sp.add_parser("analyze"); p.add_argument("work"); p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--budget", type=float, default=150, help="seconds before stopping (resumable)")
    p.add_argument("--force", action="store_true"); p.add_argument("--hwaccel", action="store_true")
    p = sp.add_parser("transcribe"); p.add_argument("work"); p.add_argument("--model", default="small")
    p.add_argument("--language"); p.add_argument("--ids"); p.add_argument("--all", action="store_true")
    p.add_argument("--min-speech", type=float, default=0.35); p.add_argument("--budget", type=float, default=150)
    p = sp.add_parser("summary"); p.add_argument("work"); p.add_argument("--table", action="store_true")
    p = sp.add_parser("sheets"); p.add_argument("work"); p.add_argument("--per-sheet", type=int, default=4)
    p.add_argument("--frames", type=int, default=7); p.add_argument("--tile-h", type=int, default=130); p.add_argument("--ids")
    p = sp.add_parser("strip"); p.add_argument("work"); p.add_argument("id"); p.add_argument("--start", type=float)
    p.add_argument("--end", type=float); p.add_argument("--n", type=int, default=12)
    p = sp.add_parser("validate"); p.add_argument("work"); p.add_argument("--edl")
    p = sp.add_parser("render"); p.add_argument("work"); p.add_argument("--edl"); p.add_argument("--out")
    p.add_argument("--jobs", type=int, default=2); p.add_argument("--budget", type=float, default=150); p.add_argument("--prune", action="store_true")
    p = sp.add_parser("check"); p.add_argument("work"); p.add_argument("--edl")
    p = sp.add_parser("csv"); p.add_argument("work"); p.add_argument("--edl"); p.add_argument("--out"); p.add_argument("--from-csv")
    p.add_argument("--lang", choices=["en", "zh"], default="en")
    p = sp.add_parser("export"); p.add_argument("work"); p.add_argument("--edl")
    p.add_argument("--path-map", action="append", help="rewrite file paths, e.g. /vm/mnt/Footage=/Users/me/Footage")
    for name in ("clean", "nlm"):
        p = sp.add_parser(name); p.add_argument("input"); p.add_argument("--out"); p.add_argument("--config")
        p.add_argument("--preset", choices=list(CLEAN_PRESETS), default="notebooklm" if name == "nlm" else "generic")
        p.add_argument("--corner", choices=["auto", "br", "bl", "tr", "tl"], default="auto")
        p.add_argument("--box", help="x,y,w,h relative 0-1"); p.add_argument("--tail", type=float)
        p.add_argument("--no-logo", action="store_true"); p.add_argument("--no-trim", action="store_true")
    a = ap.parse_args()
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"ERROR: {tool} not found on PATH")
    {"scan": cmd_scan, "analyze": cmd_analyze, "transcribe": cmd_transcribe, "summary": cmd_summary, "sheets": cmd_sheets,
     "strip": cmd_strip, "validate": cmd_validate, "render": cmd_render, "check": cmd_check, "csv": cmd_csv,
     "export": cmd_export, "clean": cmd_clean, "nlm": cmd_clean}[a.cmd](a)


if __name__ == "__main__":
    main()
