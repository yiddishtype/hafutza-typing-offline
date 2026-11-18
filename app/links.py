"""Hafutza Typing (offline): get a video from a link (YouTube, Facebook, Instagram, Vimeo, any site yt-dlp
knows, or a direct .mp4/.mp3 link). Only this step needs the internet; the typing stays on the computer.

The video comes with its picture (a modest one, up to 720p) so it plays in the player with its text. There is no
ffmpeg program here to join a separate picture and sound, so only files that already hold both are taken; when a
site has none, the sound alone is fetched (the player then shows the text on a dark screen).
"""
import os, re

import engine
from engine import log

AUDIO_FIRST = "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio/best[height<=480]/best"
MAX_H = 720


class LinkError(Exception):
    pass


def find_links(text):
    """All http(s) links in a piece of pasted text."""
    out = []
    for m in re.finditer(r"https?://[^\s<>\"']+", text or ""):
        u = m.group(0).rstrip(").,;]")
        if u not in out:
            out.append(u)
    return out


def folder():
    from PySide6.QtCore import QStandardPaths
    d = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser("~")
    d = os.path.join(d, "Hafutza Typing", "From links")
    os.makedirs(d, exist_ok=True)
    return d


def _plain(msg):
    """yt-dlp's error -> a short plain sentence."""
    m = (msg or "").lower()
    if "http error 404" in m or "http error 410" in m or "video unavailable" in m or "has been removed" in m \
            or "no longer available" in m:
        return "This video is not there any more (or the link is wrong)."
    if "not a bot" in m or "not a robot" in m:
        return ("The site asked this computer to prove it is not a robot, so the program can't get the video now. "
                "Try again later, or save the video on your computer and drop the file in.")
    if any(k in m for k in ("login", "log in", "sign in", "signin", "cookies", "private video", "registered users",
                            "members-only", "age-restricted", "inappropriate", "authentication",
                            "requires authentication", "you need to log")):
        return ("This link needs a sign-in (it is private, members-only, or the site wants you logged in), so the "
                "program can't get it. Save the video on your computer (or drag it out of WhatsApp) and drop the file in.")
    if "unsupported url" in m or "no video formats" in m or "no media" in m or "cannot parse" in m \
            or "no video could be found" in m:
        return ("The program could not find a video at this link. If the video only shows when you are logged in, "
                "save it on your computer first and drop the file in.")
    if any(k in m for k in ("getaddrinfo", "timed out", "name resolution", "urlopen error", "connection refused",
                            "connection reset", "network is unreachable", "temporary failure")):
        return "Could not reach the site. Is the internet on?"
    return "Could not get the video from this link."


def _has(f, kind):
    c = f.get(kind)
    return bool(c) and c != "none"


def _plan(info):
    """-> ("both", id) | ("join", video id, sound id) | ("sound", None), from the formats the site offers.
    A file that holds picture and sound is best; else an mp4 picture and an m4a sound joined here (no re-encoding);
    else the sound alone."""
    fs = [f for f in (info.get("formats") or []) if (f.get("protocol") or "https").startswith(("http", "m3u8"))]
    plain = lambda f: (f.get("protocol") or "https").startswith("http")
    hgt = lambda f: f.get("height") or 0
    both = [f for f in fs if _has(f, "vcodec") and _has(f, "acodec") and hgt(f) <= MAX_H]
    if not both and fs and not any(_has(f, "vcodec") or _has(f, "acodec") for f in fs):
        both = [f for f in fs if 0 < hgt(f) <= MAX_H]       # sites that don't say the codecs
    if both:
        both.sort(key=lambda f: (plain(f), f.get("ext") == "mp4", hgt(f), f.get("tbr") or 0))
        return ("both", both[-1]["format_id"])
    vids = [f for f in fs if _has(f, "vcodec") and not _has(f, "acodec") and plain(f) and f.get("ext") == "mp4"
            and str(f.get("vcodec")).startswith(("avc1", "h264")) and 0 < hgt(f) <= MAX_H]
    snds = [f for f in fs if _has(f, "acodec") and not _has(f, "vcodec") and plain(f)
            and f.get("ext") in ("m4a", "mp4") and "drc" not in str(f.get("format_id"))]
    if vids and snds:
        vids.sort(key=lambda f: (hgt(f), f.get("tbr") or 0))
        snds.sort(key=lambda f: f.get("abr") or f.get("tbr") or 0)
        return ("join", vids[-1]["format_id"], snds[-1]["format_id"])
    return ("sound", None)


def join(video, sound, out):
    """Put an mp4 picture and an m4a sound into one mp4, copying both as they are (PyAV; no ffmpeg program)."""
    import av
    tmp = out + ".part.mp4"
    with av.open(video) as vi, av.open(sound) as si, av.open(tmp, "w", format="mp4") as o:
        vs = vi.streams.video[0]
        ss = si.streams.audio[0]
        ov = o.add_stream_from_template(vs)
        oa = o.add_stream_from_template(ss)
        for src, dst in ((vi.demux(vs), ov), (si.demux(ss), oa)):
            for pk in src:
                if pk.dts is None:
                    continue
                pk.stream = dst
                o.mux(pk)
    os.replace(tmp, out)
    return out


def _is_stop(e):
    return "Stopped" in type(e).__name__ or isinstance((getattr(e, "exc_info", None) or [None, None])[1],
                                                        engine.Stopped)


def download(url, progress, stop, dest=None):
    """-> path of the downloaded video (with its picture when the site has one, else the sound alone).
    progress(fraction or -1, text); stop() -> True to stop."""
    import copy
    import yt_dlp
    from yt_dlp.utils import DownloadError

    dest = dest or folder()
    seen = {"path": None, "part": ""}

    def hook(d):
        if stop():
            raise engine.Stopped()
        if d.get("status") == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            got = d.get("downloaded_bytes") or 0
            progress(got / tot if tot else -1.0, "%s%.1f MB" % (seen["part"], got / 1e6))
        elif d.get("status") == "finished":
            seen["path"] = d.get("filename")

    class Quiet:
        def debug(self, m):
            pass

        def info(self, m):
            pass

        def warning(self, m):
            log("link warning: %s" % m[:300])

        def error(self, m):
            log("link error: %s" % m[:500])

    def opts(fmt, tmpl="%(title).70B [%(id)s].%(ext)s"):
        return {
            "format": fmt,
            "outtmpl": os.path.join(dest, tmpl),
            "windowsfilenames": True,
            "noplaylist": True,
            "playlist_items": "1",
            "fixup": "never",            # no ffmpeg program here; PyAV reads and joins the files
            "postprocessors": [],
            "progress_hooks": [hook],
            "logger": Quiet(),
            "quiet": True,
            "noprogress": True,
            "socket_timeout": 30,
            "retries": 5,
            "fragment_retries": 5,
            "overwrites": False,
            "continuedl": True,
            "cachedir": os.path.join(engine.user_dir(), "yt-dlp-cache"),
        }

    def fetch(fmt, info, tmpl=None):
        seen["path"] = None
        with yt_dlp.YoutubeDL(opts(fmt, tmpl) if tmpl else opts(fmt)) as y:
            r = y.process_ie_result(copy.deepcopy(info), download=True)
            p = None
            for q in (r or {}).get("requested_downloads") or []:
                p = q.get("filepath") or q.get("filename") or p
            p = p or seen["path"] or y.prepare_filename(r or info)
        if not p or not os.path.isfile(p):
            raise LinkError("The download did not finish. Please try again.")
        return p

    log("link: %s" % url)
    try:
        with yt_dlp.YoutubeDL(opts(AUDIO_FIRST)) as y:
            info = y.extract_info(url, download=False)
            if info is None:
                raise LinkError(_plain("no media"))
            if info.get("_type") == "playlist":
                ents = [e for e in (info.get("entries") or []) if e]
                if not ents:
                    raise LinkError(_plain("no media"))
                info = ents[0]
            base = os.path.splitext(y.prepare_filename(info))[0]
        plan = _plan(info)
        log("link plan: %s" % (plan,))
        path = None
        if plan[0] == "both":
            try:
                path = fetch(plan[1], info)
            except (engine.Stopped, LinkError):
                raise
            except Exception as e:
                if _is_stop(e):
                    raise engine.Stopped()
                log("link picture failed, getting the sound: %r" % e)
        elif plan[0] == "join":
            final = base + ".mp4"
            if os.path.isfile(final):
                path = final
            else:
                try:
                    seen["part"] = "picture "
                    v = fetch(plan[1], info, "%(title).70B [%(id)s].picture.%(ext)s")
                    seen["part"] = "sound "
                    a = fetch(plan[2], info, "%(title).70B [%(id)s].sound.%(ext)s")
                    seen["part"] = ""
                    progress(-1.0, "joining picture and sound")
                    path = join(v, a, final)
                    for f in (v, a):
                        try:
                            os.remove(f)
                        except OSError:
                            pass
                except (engine.Stopped, LinkError):
                    raise
                except Exception as e:
                    if _is_stop(e):
                        raise engine.Stopped()
                    log("link picture failed, getting the sound: %r" % e)
                    path = None
        if path is None:
            seen["part"] = ""
            path = fetch(AUDIO_FIRST, info)
    except engine.Stopped:
        raise
    except DownloadError as e:
        if _is_stop(e):
            raise engine.Stopped()
        log("link failed: %s" % e)
        raise LinkError(_plain(str(e)))
    except LinkError:
        raise
    except Exception as e:
        if _is_stop(e):
            raise engine.Stopped()
        log("link failed: %r" % e)
        raise LinkError(_plain(str(e)))
    if not path or not os.path.isfile(path):
        raise LinkError("The download did not finish. Please try again.")
    log("link done: %s (%d bytes)" % (path, os.path.getsize(path)))
    return path
