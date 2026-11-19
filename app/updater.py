"""Hafutza Typing (offline): the Update button's work, no window code here.

  update.json (one fixed address, replaced at every release):
      {"version": "1.2", "url": ".../HafutzaTyping-Update.exe", "sha256": "...", "size": 123, "notes": "..."}
  The update file is a small installer of the program only (no speech models): it installs over the old program
  (same AppId), keeps the downloaded parts in the program's models folder, LOCALAPPDATA\\HafutzaTyping and Documents,
  waits for this program to close, and opens it again.
"""
import hashlib, json, os, subprocess, sys, tempfile, time, urllib.request

import engine
from engine import log

FALLBACK_VERSION = "1.5"
MANIFEST_URL = "https://github.com/yiddishtype/hafutza-typing-offline/releases/download/updates/update.json"
MUTEX = "HafutzaTypingRunning"      # the installer waits until no program holds this
_mutex = None


def version():
    """The version of this program: version.txt next to the program (written by the build), else the built-in one."""
    try:
        with open(os.path.join(engine.app_dir(), "version.txt"), encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except OSError:
        pass
    return FALLBACK_VERSION


def vtuple(v):
    out = []
    for p in str(v).strip().lstrip("vV").split("."):
        n = "".join(c for c in p if c.isdigit())
        out.append(int(n) if n else 0)
    while len(out) > 1 and out[-1] == 0:
        out.pop()
    return tuple(out)


def newer(remote, local):
    return vtuple(remote) > vtuple(local)


def manifest_url():
    return os.environ.get("HAFUTZA_UPDATE_URL") or MANIFEST_URL


def check(url=None, timeout=20):
    """-> the update.json dict (with 'newer': bool). Raises on no internet / bad answer."""
    url = url or manifest_url()
    if url.startswith("http"):
        url += ("&" if "?" in url else "?") + "t=%d" % time.time()     # no stale copy from a cache on the way
    req = urllib.request.Request(url,
                                 headers={"User-Agent": "HafutzaTyping/" + version(), "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        m = json.loads(r.read().decode("utf-8-sig"))
    for k in ("version", "url", "sha256", "size"):
        if k not in m:
            raise RuntimeError("update.json has no %s" % k)
    m["newer"] = newer(m["version"], version())
    log("update check: here %s, newest %s, newer=%s" % (version(), m["version"], m["newer"]))
    return m


def download(m, progress, stop):
    """Fetch the update installer into a temp folder; check its size and sha256. -> path."""
    d = os.path.join(tempfile.gettempdir(), "HafutzaTyping-update")
    os.makedirs(d, exist_ok=True)
    final = os.path.join(d, "HafutzaTyping-Update-%s.exe" % m["version"])
    total = int(m["size"])
    if os.path.exists(final) and os.path.getsize(final) == total and _sha(final) == m["sha256"]:
        return final
    part = final + ".part"
    tries = 0
    while True:
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if have > total:
            os.remove(part); have = 0
        if have < total:
            try:
                req = urllib.request.Request(m["url"], headers={"User-Agent": "HafutzaTyping/" + version(),
                                                                **({"Range": "bytes=%d-" % have} if have else {})})
                r = urllib.request.urlopen(req, timeout=60)
                if have and r.status != 206:
                    have = 0
                with open(part, "ab" if have else "wb") as f:
                    while True:
                        if stop():
                            raise engine.Stopped()
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                        have += len(b)
                        progress(have, total)
                r.close()
            except engine.Stopped:
                raise
            except Exception as e:
                tries += 1
                log("update download broke off at %d: %r" % (have, e))
                if tries >= 6:
                    raise RuntimeError("The download did not work (%s). Is the internet on?" % type(e).__name__)
                time.sleep(min(20, 3 * tries))
                continue
        if os.path.getsize(part) != total:
            tries += 1
            if tries >= 6:
                raise RuntimeError("The download did not finish. Please try again.")
            continue
        if _sha(part) != m["sha256"]:
            os.remove(part)
            tries += 1
            if tries >= 3:
                raise RuntimeError("The downloaded file was damaged. Please try again.")
            continue
        os.replace(part, final)
        return final


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run_installer(path):
    """Start the update installer on its own; it waits for this program to close, installs, and opens it again."""
    logf = os.path.join(engine.user_dir(), "update-install-log.txt")
    args = [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/FROMAPP=1", "/LOG=" + logf]
    log("update: starting %s" % args)
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def hold_mutex():
    """Hold a named mutex for as long as this program runs (Windows only), so the installer can wait for us to close.
    -> True if another Hafutza Typing was already running."""
    global _mutex
    if sys.platform != "win32" or _mutex:
        return False
    try:
        import ctypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.restype = ctypes.c_void_p
        _mutex = k.CreateMutexW(None, False, MUTEX)
        return ctypes.get_last_error() == 183          # ERROR_ALREADY_EXISTS
    except Exception as e:
        log("mutex failed %r" % e)
        return False
