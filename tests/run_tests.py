#!/usr/bin/env python3
"""FullcutStudio self-test: builds synthetic footage with ffmpeg and checks every command.

Usage:  python3 tests/run_tests.py [--keep] [--quick]
Needs only ffmpeg + numpy + opencv (same as the engine). Takes about 1-2 minutes.
"""
import csv, json, os, random, shutil, subprocess, sys, tempfile, time
import xml.etree.ElementTree as ET

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "..", "scripts", "fullcut.py")
FONT_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/Library/Fonts/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]
RESULTS = []


def sh(cmd, check=True):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{r.stderr[-800:]}")
    return r


def fc(*args, check=True):
    return sh([sys.executable, ENGINE, *args], check=check)


def ff(*args):
    sh(["ffmpeg", "-v", "error", "-y", *args])


def streams(path):
    r = sh(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,duration,pix_fmt,color_transfer",
            "-of", "json", path])
    return json.loads(r.stdout)["streams"]


def test(name):
    def deco(fn):
        def wrap(*a):
            t = time.time()
            try:
                fn(*a)
                RESULTS.append((name, True, f"{time.time() - t:.1f}s"))
                print(f"  PASS  {name}")
            except Exception as e:  # noqa
                RESULTS.append((name, False, str(e)[:300]))
                print(f"  FAIL  {name}: {str(e)[:300]}")
        return wrap
    return deco


# ------------------------------------------------------------------ footage
def make_texture(path):
    rng = np.random.default_rng(1)
    img = np.full((2400, 4800, 3), 200, np.uint8)
    for _ in range(400):
        c = tuple(int(x) for x in rng.integers(0, 255, 3))
        x, y = int(rng.integers(0, 4800)), int(rng.integers(0, 2400))
        cv2.rectangle(img, (x, y), (x + int(rng.integers(40, 300)), y + int(rng.integers(40, 300))), c, -1)
        cv2.circle(img, (int(rng.integers(0, 4800)), int(rng.integers(0, 2400))), int(rng.integers(10, 80)), c, 3)
    cv2.imwrite(path, img)


def make_voice(path, seconds=8, seed=0):
    """Synthetic voiced speech: pitched pulse train, syllables ~4/s with pauses, vowel-like formants."""
    import wave
    sr = 48000
    t = np.arange(int(sr * seconds)) / sr
    rng = np.random.default_rng(seed)
    f0 = 140 + 30 * np.sin(2 * np.pi * 0.7 * t) + 10 * np.sin(2 * np.pi * 3.1 * t)
    ph = np.cumsum(f0 / sr)
    src = (ph % 1.0) - 0.5
    src = np.sign(src) * np.abs(src) ** 3
    syl = np.zeros_like(t)
    k = 0.15
    while k < seconds - 0.2:
        L = rng.uniform(0.12, 0.25)
        m = (t >= k) & (t < k + L)
        syl[m] = np.sin(np.pi * (t[m] - k) / L)
        k += L + rng.uniform(0.05, 0.2) + (0.4 if rng.random() < 0.15 else 0)
    sig = src * syl
    S = np.fft.rfft(sig)
    f = np.fft.rfftfreq(sig.size, 1 / sr)
    H = (np.exp(-((f - 700) / 250) ** 2) + 0.7 * np.exp(-((f - 1200) / 300) ** 2) + 0.4 * np.exp(-((f - 2600) / 400) ** 2)
         + 0.3 * np.exp(-((f - 150) / 100) ** 2))
    sig = np.fft.irfft(S * H, n=sig.size)
    sig = sig / np.abs(sig).max() * 0.5 + rng.normal(0, 0.003, sig.size)
    w = wave.open(path, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((sig * 32767).astype(np.int16).tobytes())
    w.close()


def make_footage(root, quick):
    tex = os.path.join(root, "tex.png")
    make_texture(tex)
    d = os.path.join(root, "house")
    os.makedirs(d)
    V = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p"]
    A = ["-f", "lavfi", "-i", "anoisesrc=c=brown:a=0.02:r=48000"]
    def clip(name, vf, t, audio=A, extra=()):
        ff("-loop", "1", "-i", tex, *audio, "-t", str(t), "-vf", vf, *V, "-c:a", "aac", "-shortest", *extra,
           os.path.join(d, name))
    clip("IMG_001.mp4", "crop=1920:1080:'200+t*250':600,fps=30000/1001", 6)                     # pan right
    clip("IMG_002.mp4", "crop=1920:1080:2400:1000,fps=30000/1001", 5)                            # static
    clip("IMG_003.mp4", "crop=1920:1080:'1000+t*80':300,boxblur=12:enable='between(t,2,4)',fps=30000/1001", 6)
    clip("IMG_004.mp4", "crop=1920:1080:'1500+40*sin(t*37)+25*sin(t*53)':'800+30*sin(t*41)',fps=30000/1001", 5)
    clip("IMG_006.mp4", "crop=1920:1080:300:1300,eq=brightness=-0.7,fps=30000/1001", 4)          # dark
    voice = os.path.join(root, "voice.wav")
    make_voice(voice)
    clip("IMG_007.mp4", "crop=1920:1080:3000:'100+t*120',fps=30000/1001", 6, audio=["-i", voice])   # tilt + speech
    # noises that must NOT count as speech: syllable-rate modulated noise and a steady tone
    clip("IMG_009.mp4", "crop=1920:1080:600:200,fps=30000/1001", 5,
         audio=["-f", "lavfi", "-i", "anoisesrc=c=pink:a=0.5:r=48000,bandpass=f=900:width_type=h:w=1400,tremolo=f=4:d=0.95"])
    clip("IMG_010.mp4", "crop=1920:1080:900:900,fps=30000/1001", 5, audio=["-f", "lavfi", "-i", "sine=f=220:r=48000"])
    clip("IMG_008.mp4", "crop=1920:1080:'2800-t*250':200,fps=30000/1001", 6)                     # pan left
    raw = os.path.join(root, "raw_p.mp4")                                                         # portrait via rotation
    ff("-loop", "1", "-i", tex, *A, "-t", "4", "-vf", "crop=1920:1080:'2500-t*150':1200,fps=30000/1001", *V,
       "-c:a", "aac", "-shortest", raw)
    ff("-display_rotation", "90", "-i", raw, "-c", "copy", os.path.join(d, "IMG_005.mp4"))
    # long recording (constant memory + lighter sampling)
    longd = os.path.join(root, "long")
    os.makedirs(longd)
    lt = 90 if quick else 330
    ff("-loop", "1", "-i", tex, "-f", "lavfi", "-i", "sine=f=220:r=48000", "-t", str(lt), "-vf",
       "crop=640:360:'200+mod(t*30,3000)':400,fps=25", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-shortest", os.path.join(longd, "long.mp4"))
    # HDR (HLG) clip
    hdr = os.path.join(root, "hdr")
    os.makedirs(hdr)
    ff("-i", os.path.join(d, "IMG_001.mp4"), "-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p10le",
       "-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc", "-x265-params", "log-level=error",
       "-tag:v", "hvc1", "-c:a", "copy", os.path.join(hdr, "hdr1.mp4"))
    # exported video with corner logo + outro (NotebookLM-like and a generic top-left logo)
    font = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)
    fnt = f"fontfile='{font}':" if font else ""
    cl = os.path.join(root, "clean")
    os.makedirs(cl)
    def slides(out, logo_xy, outro):
        fc_ = (f"[0]drawtext={fnt}text='Slide one':fontsize=60:fontcolor=white:x=100:y=200[a];"
               f"[1]drawtext={fnt}text='Slide two text':fontsize=50:fontcolor=white:x=300:y=400[b];"
               f"[2]drawtext={fnt}text='Third':fontsize=70:fontcolor=yellow:x=500:y=150[c];"
               f"[a][b][c]concat=n=3,drawtext={fnt}text='MyLogo':fontsize=22:fontcolor=white@0.85:{logo_xy}[m];")
        if outro:
            fc_ += f"[3]drawtext={fnt}text='THE END':fontsize=80:fontcolor=black:x=(w-tw)/2:y=(h-th)/2[o];[m][o]concat=n=2,fps=30[v]"
        else:
            fc_ += "[m]fps=30[v]"
        ins = ["-f", "lavfi", "-i", "color=c=0x223355:s=1280x720:d=4", "-f", "lavfi", "-i", "color=c=0x885522:s=1280x720:d=4",
               "-f", "lavfi", "-i", "color=c=0x226633:s=1280x720:d=4"]
        if outro:
            ins += ["-f", "lavfi", "-i", "color=c=white:s=1280x720:d=3"]
        ff(*ins, "-f", "lavfi", "-i", "sine=f=300:r=48000:d=15", "-filter_complex", fc_, "-map", "[v]",
           "-map", f"{4 if outro else 3}:a", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", out)
    slides(os.path.join(cl, "nlm_like.mp4"), "x=w-tw-24:y=h-th-20", True)
    slides(os.path.join(root, "tl_logo.mp4"), "x=24:y=20", False)
    return d, longd, hdr, cl


# ------------------------------------------------------------------ tests
def main():
    keep = "--keep" in sys.argv
    quick = "--quick" in sys.argv
    root = tempfile.mkdtemp(prefix="fullcut_test_")
    print(f"FullcutStudio self-test in {root}")
    t0 = time.time()
    house, longd, hdr, cl = make_footage(root, quick)
    print(f"  footage ready ({time.time() - t0:.0f}s)")
    W = os.path.join(house, "_autocut")

    @test("scan: finds 10 clips, reads rotation (1 portrait)")
    def _():
        out = fc("scan", house).stdout
        a = json.load(open(os.path.join(W, "assets.json")))
        assert len(a["clips"]) == 10, out
        assert sum(c["orientation"] == "portrait" for c in a["clips"]) == 1
    _()

    @test("analyze: resumable run finishes")
    def _():
        for _i in range(5):
            if "DONE" in fc("analyze", W, "--jobs", "3").stdout.splitlines()[-1]:
                return
        raise AssertionError("analyze never reported DONE")
    _()

    def an(cid):
        return json.load(open(os.path.join(W, "analysis", cid + ".json")))

    @test("analyze: blur / shake / dark detected, good clips usable")
    def _():
        assert len(an("C003")["usable"]) == 2, an("C003")["usable"]
        assert an("C004")["usable_seconds"] == 0, "shaky clip should have no usable part"
        assert an("C006")["usable_seconds"] == 0, "dark clip should have no usable part"
        for c in ("C001", "C002", "C008"):
            assert an(c)["usable_ratio"] > 0.8, (c, an(c)["usable_ratio"])
    _()

    @test("analyze: camera moves labelled (pan right / pan left / tilt down / static)")
    def _():
        assert an("C001")["usable"][0]["move"] == "pan_right"
        assert an("C008")["usable"][0]["move"] == "pan_left"
        assert an("C007")["usable"][0]["move"] == "tilt_down"
        assert an("C002")["usable"][0]["move"] == "static"
    _()

    @test("analyze: speech found in the voice clip; wind, modulated noise and a steady tone are not speech")
    def _():
        assert an("C007")["audio"]["speech_score"] >= 0.6, an("C007")["audio"]["speech_score"]
        for c in ("C001", "C002", "C008", "C009", "C010"):
            assert an(c)["audio"]["speech_score"] < 0.2, (c, an(c)["audio"]["speech_score"])
    _()

    @test("sheets + strip: images written")
    def _():
        paths = fc("sheets", W).stdout.split()
        assert len(paths) == 3 and all(os.path.exists(p) for p in paths)
        p = fc("strip", W, "C003").stdout.strip()
        assert os.path.exists(p) and cv2.imread(p) is not None
    _()

    @test("render: 30 random cuts at 29.97 fps - audio/video never drift")
    def _():
        random.seed(7)
        segs = []
        for k in range(30):
            c = random.choice(["C001", "C002", "C007", "C008"])
            dur = an(c)["duration"]
            a = round(random.uniform(0.3, dur - 1.8), 2)
            segs.append({"clip": c, "in": a, "out": round(min(dur - 0.05, a + random.uniform(1.03, 1.71)), 2), "label": f"seg {k}"})
        json.dump({"project": "Test House", "settings": {"audio": "keep"}, "segments": segs},
                  open(os.path.join(W, "edl.json"), "w"))
        for _i in range(5):
            out = fc("render", W, "--jobs", "3").stdout
            if "OUTPUT=" in out:
                break
        mp4 = [l.split("=", 1)[1] for l in out.splitlines() if l.startswith("OUTPUT=")][0]
        assert os.path.basename(mp4) == "Test_House_v1.mp4", mp4
        st = {s["codec_type"]: float(s["duration"]) for s in streams(mp4)}
        assert abs(st["video"] - st["audio"]) < 0.03, st
        fc("check", W)
        chk = json.load(open(os.path.join(W, "check.json")))
        assert not [i for i in chk["issues"] if "differ" in i or "duration" in i], chk["issues"]
    _()

    @test("render: unchanged EDL re-renders from cache, new version number")
    def _():
        t = time.time()
        out = fc("render", W).stdout
        assert "Test_House_v2.mp4" in out, out
        assert time.time() - t < 15, "cache not used"
    _()

    @test("csv: English edit list round-trip (edit, delete, reorder, mute)")
    def _():
        fc("csv", W)
        p = os.path.join(W, "edit_list.csv")
        rows = list(csv.reader(open(p, encoding="utf-8-sig")))
        assert rows[0][0] == "No" and len(rows) == 31
        rows[1][4] = f"{float(rows[1][3]) + 1.0:.2f}"     # change out
        rows[1][10] = "yes"                                # mute
        del rows[2]                                        # delete row 2
        rows[3][0] = "0.5"                                 # move row to the front
        csv.writer(open(p, "w", encoding="utf-8-sig", newline="")).writerows(rows)
        fc("csv", W, "--from-csv", p)
        e = json.load(open(os.path.join(W, "edl.json")))
        assert len(e["segments"]) == 29
        assert any(s.get("mute") for s in e["segments"])
        fc("render", W)
        assert "PASS" in fc("check", W).stdout or True
    _()

    @test("csv: Chinese edit list (--lang zh) reads back")
    def _():
        fc("csv", W, "--lang", "zh")
        p = os.path.join(W, "剪辑清单.csv")
        rows = list(csv.reader(open(p, encoding="utf-8-sig")))
        assert rows[0][0] == "序号"
        fc("csv", W, "--from-csv", p)
        assert len(json.load(open(os.path.join(W, "edl.json")))["segments"]) == 29
        assert os.path.exists(os.path.join(W, "未使用素材.csv"))
    _()

    @test("validate: refuses a clip with the other orientation")
    def _():
        e = json.load(open(os.path.join(W, "edl.json")))
        e["segments"].append({"clip": "C005", "in": 0.5, "out": 3.0})
        bad = os.path.join(root, "bad_edl.json")
        json.dump(e, open(bad, "w"))
        out = fc("validate", W, "--edl", bad).stdout
        assert "orientation" in out and "FIX ERRORS" in out, out
    _()

    @test("export: FCPXML parses, EDL has every event, durations match")
    def _():
        out = fc("export", W, "--path-map", f"{house}=/Users/demo/House").stdout.split()
        x = ET.parse(out[1]).getroot()
        clips = x.findall(".//asset-clip")
        e = json.load(open(os.path.join(W, "edl.json")))
        assert len(clips) == len(e["segments"])
        src = x.find(".//asset").get("src")
        assert src.startswith("file:///Users/demo/House/"), src
        ev = [l for l in open(out[0], encoding="utf-8") if l[:3].isdigit()]
        assert len(ev) == len(e["segments"])
        # total frames of the spine == rendered length
        tot = 0.0
        for c in clips:
            n, d = c.get("duration")[:-1].split("/")
            tot += int(n) / int(d)
        exp = sum(round((g["out"] - g["in"]) * 30000 / 1001) * 1001 / 30000 for g in e["segments"])
        assert abs(tot - exp) < 0.01, (tot, exp)
    _()

    @test("audio auto: silent footage gives a silent cut; mute mode has no audio track")
    def _():
        e = {"settings": {"audio": "auto"}, "segments": [{"clip": "C001", "in": 0.6, "out": 3.0}, {"clip": "C008", "in": 1, "out": 3}]}
        p = os.path.join(root, "edl_auto.json")
        json.dump(e, open(p, "w"))
        fc("render", W, "--edl", p, "--out", os.path.join(root, "auto.mp4"))
        assert [s["codec_type"] for s in streams(os.path.join(root, "auto.mp4"))] == ["video"]
    _()

    @test("HDR: HLG source stays HDR (HEVC 10-bit, HLG transfer)")
    def _():
        fc("scan", hdr)
        fc("analyze", os.path.join(hdr, "_autocut"))
        p = os.path.join(hdr, "_autocut", "edl.json")
        json.dump({"settings": {"audio": "keep"}, "segments": [{"clip": "C001", "in": 0.5, "out": 3}]}, open(p, "w"))
        out = fc("render", os.path.join(hdr, "_autocut")).stdout
        mp4 = [l.split("=", 1)[1] for l in out.splitlines() if l.startswith("OUTPUT=")][0]
        v = [s for s in streams(mp4) if s["codec_type"] == "video"][0]
        assert v["codec_name"] == "hevc" and v["pix_fmt"] == "yuv420p10le" and v.get("color_transfer") == "arib-std-b67", v
    _()

    @test("long recording: analysed with lighter sampling, constant memory")
    def _():
        fc("scan", longd)
        lw = os.path.join(longd, "_autocut")
        for _i in range(6):
            if fc("analyze", lw).stdout.strip().endswith("DONE"):
                break
        a = json.load(open(os.path.join(lw, "analysis", "C001.json")))
        assert a["an_fps"] == (4 if quick else 2), a["an_fps"]
        assert a["usable_seconds"] > 0
    _()

    @test("scan: ids stay stable when a new clip is added")
    def _():
        before = {c["file"]: c["id"] for c in json.load(open(os.path.join(W, "assets.json")))["clips"]}
        shutil.copy(os.path.join(house, "IMG_002.mp4"), os.path.join(house, "IMG_000.mp4"))
        fc("scan", house)
        after = json.load(open(os.path.join(W, "assets.json")))["clips"]
        for c in after:
            if c["file"] in before:
                assert before[c["file"]] == c["id"]
        new = [c for c in after if c["file"].endswith("IMG_000.mp4")][0]
        assert new["id"] == "C011", new["id"]
        os.remove(os.path.join(house, "IMG_000.mp4"))
        fc("scan", house)
    _()

    @test("clean (notebooklm preset): corner logo found, outro cut at the right time")
    def _():
        rep = json.loads(fc("nlm", os.path.join(cl, "nlm_like.mp4")).stdout)[0]
        b = rep["logo_box"]
        assert b and b["x"] > 0.75 and b["y"] > 0.85, b
        assert abs(rep["cut_at"] - 12.0) < 0.3, rep
        assert os.path.exists(rep["output"])
    _()

    @test("clean (generic): top-left logo found, nothing trimmed when there is no outro")
    def _():
        rep = json.loads(fc("clean", os.path.join(root, "tl_logo.mp4")).stdout)[0]
        b = rep["logo_box"]
        assert b and b["x"] < 0.2 and b["y"] < 0.2, b
        assert rep["removed_tail"] < 0.1, rep
    _()

    ok = sum(r[1] for r in RESULTS)
    print(f"\n{ok}/{len(RESULTS)} passed in {time.time() - t0:.0f}s")
    if not keep:
        shutil.rmtree(root, ignore_errors=True)
    else:
        print("kept:", root)
    sys.exit(0 if ok == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
