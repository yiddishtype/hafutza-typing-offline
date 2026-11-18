"""Hafutza Typing (offline): get the sound of a video from a link (YouTube, Facebook, Instagram, Vimeo, any site yt-dlp
knows, or a direct .mp4/.mp3 link). Only this step needs the internet; the typing stays on the computer.

Only the sound is downloaded (smaller, faster, and needs no ffmpeg program: PyAV reads it as it is).
"""
import os, re

import engine
from engine import log

AUDIO_FIRST = "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio/best[height<=480]/best"


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
    if any(k in m for k in ("login", "log in", "sign in", "signin", "cookies", "private video", "registered users",
                            "members-only", "age-restricted", "inappropriate", "not a bot", "authentication",
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


def download(url, progress, stop, dest=None):
    """-> path of the downloaded sound file. progress(fraction or -1, text); stop() -> True to stop."""
    import yt_dlp
    from yt_dlp.utils import DownloadError

    dest = dest or folder()
    seen = {"path": None}

    def hook(d):
        if stop():
            raise engine.Stopped()
        if d.get("status") == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            got = d.get("downloaded_bytes") or 0
            progress(got / tot if tot else -1.0, "%.1f MB" % (got / 1e6))
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

    opts = {
        "format": AUDIO_FIRST,
        "outtmpl": os.path.join(dest, "%(title).70B [%(id)s].%(ext)s"),
        "windowsfilenames": True,
        "noplaylist": True,
        "playlist_items": "1",
        "fixup": "never",            # no ffmpeg program here; PyAV reads the file as it comes
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
    log("link: %s" % url)
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
            if info is None:
                raise LinkError(_plain("no media"))
            if info.get("_type") == "playlist":
                ents = [e for e in (info.get("entries") or []) if e]
                if not ents:
                    raise LinkError(_plain("no media"))
                info = ents[0]
            path = None
            for r in info.get("requested_downloads") or []:
                path = r.get("filepath") or r.get("filename") or path
            path = path or seen["path"] or y.prepare_filename(info)
    except engine.Stopped:
        raise
    except DownloadError as e:
        if isinstance(getattr(e, "exc_info", [None, None])[1], engine.Stopped):
            raise engine.Stopped()
        log("link failed: %s" % e)
        raise LinkError(_plain(str(e)))
    except LinkError:
        raise
    except Exception as e:
        if "Stopped" in type(e).__name__:
            raise engine.Stopped()
        log("link failed: %r" % e)
        raise LinkError(_plain(str(e)))
    if not path or not os.path.isfile(path):
        raise LinkError("The download did not finish. Please try again.")
    log("link done: %s (%d bytes)" % (path, os.path.getsize(path)))
    return path
