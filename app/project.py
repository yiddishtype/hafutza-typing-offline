"""Hafutza Typing: a typed video kept with its timings, so it can be watched with subtitles and fixed.

Kept in %LOCALAPPDATA%\\HafutzaTyping\\videos\\<key>.json:
  {"video": path, "name": file name, "spoken": "yi", "targets": [...],
   "segments": [{"s": start sec, "e": end sec, "t": {lang: text}}], "made": ..., "changed": ...}
The .txt and .srt files in Documents\\Hafutza Typing are written again from it after every fix.
"""
import hashlib, json, os, time

import engine
from engine import NAME_EN

RTL = ("yi", "he")


def folder():
    d = os.path.join(engine.user_dir(), "videos")
    os.makedirs(d, exist_ok=True)
    return d


def key(video):
    p = os.path.abspath(video)
    if os.name == "nt":
        p = p.lower()
    return hashlib.sha1(p.encode("utf-8")).hexdigest()[:12]


def file_of(video):
    return os.path.join(folder(), key(video) + ".json")


def make(video, spoken, targets, segs, texts):
    """segs: [(start, end)], texts: {lang: [line per segment]}"""
    segments = []
    for i, (s, e) in enumerate(segs):
        segments.append({"s": float(s), "e": float(e), "t": {l: (texts[l][i] if i < len(texts[l]) else "") for l in texts}})
    now = time.strftime("%Y-%m-%d %H:%M")
    return {"video": os.path.abspath(video), "name": os.path.basename(video), "spoken": spoken,
            "targets": list(targets), "segments": segments, "made": now, "changed": now}


def save(proj):
    proj["changed"] = time.strftime("%Y-%m-%d %H:%M")
    p = file_of(proj["video"])
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(proj, f, ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)
    return p


def load(video):
    try:
        with open(file_of(video), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def all_projects():
    out = []
    for n in os.listdir(folder()):
        if n.endswith(".json"):
            try:
                with open(os.path.join(folder(), n), encoding="utf-8") as f:
                    out.append(json.load(f))
            except Exception:
                pass
    out.sort(key=lambda p: p.get("changed", ""), reverse=True)
    return out


def text_of(proj, lang):
    return "\n".join(s["t"].get(lang, "") for s in proj["segments"]).strip()


def _write(path, text):
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(text + "\n")


def srt_time(t):
    ms = int(round(max(0.0, t) * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def srt_of(proj, lang):
    out, n = [], 0
    for s in proj["segments"]:
        t = s["t"].get(lang, "").strip()
        if not t:
            continue
        n += 1
        if lang in RTL:
            t = "‏" + t             # right-to-left mark: players show the line the right way round
        out.append("%d\n%s --> %s\n%s\n" % (n, srt_time(s["s"]), srt_time(max(s["e"], s["s"] + 0.5)), t))
    return "\n".join(out)


def base_name(proj):
    return os.path.splitext(proj.get("name") or os.path.basename(proj["video"]))[0]


def export(proj, docs, langs=None):
    """Write '<name> - <Language>.txt' and '.srt' for each language. -> the files written."""
    d = os.path.join(docs, "Hafutza Typing")
    os.makedirs(d, exist_ok=True)
    done = []
    for l in langs or proj["targets"]:
        b = os.path.join(d, "%s - %s" % (base_name(proj), NAME_EN[l]))
        _write(b + ".txt", text_of(proj, l))
        _write(b + ".srt", srt_of(proj, l))
        done += [b + ".txt", b + ".srt"]
    return done
