"""Hafutza Typing (offline): the AI helper that fixes words on request. No window code here.

  The user writes an instruction (English or Yiddish): "change X to Y", "the hall is called ..., fix it".
  The AI (Qwen3.5-4B, run on this computer by llama.cpp's llama-server, no internet) answers with a list of
  word changes {find, replace}; the program shows them and the user presses OK. Nothing changes without OK.

  The model (2.7 GB) is an optional, separate download: the program works fully without it.
  llama-server.exe comes with the program, in the folder "llama".
"""
import hashlib, json, os, re, socket, subprocess, sys, threading, time, urllib.request

import engine

MODEL_URL = ("https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/"
             "e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf")
MODEL_FILE = "Qwen3.5-4B-Q4_K_M.gguf"
MODEL_SIZE = 2740937888
MODEL_SHA = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
CTX = 8192

SYS = ("You are the editor inside a Yiddish typing program. The user gives you a text (Yiddish in Hebrew letters, "
       "or its English or other translation) and an instruction, in English or Yiddish. Answer with ONLY a JSON list "
       "of the changes to make, like [{\"find\": \"exact words now in the text\", \"replace\": \"new words\"}]. "
       "\"find\" must be copied exactly from the text. Make only the changes the instruction asks for. "
       "The instruction may be in Yiddish even when the text is English: \"טוישט X אויף Y\", \"בייט X צו Y\", "
       "\"מאך X Y\", \"שרייב Y אנשטאט X\" all mean: change X to Y. Copy X and Y exactly as the user wrote them. "
       "If the instruction asks for no change you can make, answer [].")

# Short worked examples shown to the AI before the real question (a small model follows examples best).
SHOTS = [
    ("TEXT:\nThe Rebbe tells the story of the old shul.\n\nINSTRUCTION: טוישט \"shul\" אויף \"synagogue\"",
     '[{"find": "shul", "replace": "synagogue"}]'),
    ("TEXT:\nדער רבי האט געזאגט א מעשה פון זיין טאטן.\n\nINSTRUCTION: the word for story should be מעשׂה",
     '[{"find": "מעשה", "replace": "מעשׂה"}]'),
    ("TEXT:\nWe went to Bnei Brak on Sunday.\n\nINSTRUCTION: בייט \"Sunday\" צו \"Monday\"",
     '[{"find": "Sunday", "replace": "Monday"}]'),
]

_Q = r'["\u201c\u201d\u201e\u05f4]([^"\u201c\u201d\u201e\u05f4]+)["\u201c\u201d\u201e\u05f4]'


def quoted(instruction):
    """(X, Y) when the instruction names exactly two words in quotes, like: change "X" to "Y" (any language).
    Used only when the AI suggests nothing: the user still sees it and presses OK."""
    m = re.findall(_Q, instruction)
    if len(m) == 2 and m[0].strip() and m[0] != m[1]:
        return m[0], m[1]
    return None


# ------------------------------------------------------------------ places
def _dirs():
    return [os.path.join(engine.app_dir(), "models", "ai"), os.path.join(engine.user_dir(), "models", "ai")]


def model_file():
    """The model file if it is fully here, else None."""
    for d in _dirs():
        p = os.path.join(d, MODEL_FILE)
        if os.path.exists(p) and os.path.getsize(p) == MODEL_SIZE:
            return p
    return None


def server_exe():
    for name in ("llama-server.exe", "llama-server"):
        p = os.path.join(engine.app_dir(), "llama", name)
        if os.path.exists(p):
            return p
    return None


def ram_gb():
    """Total memory of this computer in GB (0 if unknown)."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS(); m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 2 ** 30
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except Exception:
        return 0


def download(progress, stop):
    """Fetch the model (resumable, checked by size and sha256). progress(done, total); stop() -> True to stop."""
    dst = next((d for d in _dirs() if engine._writable(d)), None)
    if not dst:
        raise RuntimeError("No folder to save the AI model in.")
    final = os.path.join(dst, MODEL_FILE)
    part = final + ".part"
    total = MODEL_SIZE
    tries = 0
    while True:
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if have > total:
            os.remove(part); have = 0
        if have < total:
            try:
                req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "HafutzaTyping/1.4",
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
                engine.log("ai download broke off at %d: %r" % (have, e))
                if tries >= 10:
                    raise RuntimeError("The download did not work (%s). Is the internet on?" % type(e).__name__)
                time.sleep(min(30, 3 * tries))
                continue
        if os.path.getsize(part) != total:
            tries += 1
            if tries >= 10:
                raise RuntimeError("The download did not finish. Please try again.")
            continue
        h = hashlib.sha256()
        with open(part, "rb") as f:
            for b in iter(lambda: f.read(8 << 20), b""):
                if stop():
                    raise engine.Stopped()
                h.update(b)
        if h.hexdigest() != MODEL_SHA:
            os.remove(part)
            tries += 1
            if tries >= 3:
                raise RuntimeError("The downloaded file was damaged. Please try again.")
            continue
        os.replace(part, final)
        return final


# ------------------------------------------------------------------ the server
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never send 127.0.0.1 through a proxy

class Server:
    """llama-server on 127.0.0.1, started on first use, stopped when the program closes."""

    def __init__(self):
        self.proc = None
        self.port = None
        self.lock = threading.Lock()

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, stop=lambda: False):
        with self.lock:
            self._start(stop)

    def _start(self, stop):
        if self.running():
            return
        exe, model = server_exe(), model_file()
        if not exe:
            raise RuntimeError("The AI part of the program is missing: please install Hafutza Typing again.")
        if not model:
            raise RuntimeError("The AI model is not downloaded yet.")
        s = socket.socket(); s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]; s.close()
        n = max(1, (os.cpu_count() or 2) // 2)   # leave half the computer to the typing
        logf = open(os.path.join(engine.user_dir(), "ai-log.txt"), "w", encoding="utf-8", errors="replace")
        flags = 0x08000000 if sys.platform == "win32" else 0     # CREATE_NO_WINDOW
        self.proc = subprocess.Popen([exe, "-m", model, "-c", str(CTX), "-t", str(n), "--jinja",
                                      "--host", "127.0.0.1", "--port", str(self.port)],
                                     stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     creationflags=flags, cwd=os.path.dirname(exe))
        engine.log("ai server started, port %d, %d threads" % (self.port, n))
        t0 = time.time()
        while time.time() - t0 < 300:
            if stop():
                self.close(); raise engine.Stopped()
            if self.proc.poll() is not None:
                self.proc = None
                raise RuntimeError("The AI could not start (not enough memory?). Details in ai-log.txt.")
            try:
                with _LOCAL.open("http://127.0.0.1:%d/health" % self.port, timeout=5) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
            time.sleep(0.5)
        self.close()
        raise RuntimeError("The AI took too long to start.")

    def ask(self, text, instruction, stop=lambda: False):
        """-> (list of (find, replace), raw answer)."""
        self.start(stop)
        shots = []
        for q, a in SHOTS:
            shots += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        body = {"messages": [{"role": "system", "content": SYS}] + shots + [
                             {"role": "user", "content": "TEXT:\n" + text + "\n\nINSTRUCTION: " + instruction}],
                "temperature": 0, "max_tokens": 800, "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % self.port,
                                     data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with _LOCAL.open(req, timeout=600) as r:
            out = json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"] or ""
        return parse(out), out

    def close(self):
        if self.proc is not None:
            try:
                self.proc.kill(); self.proc.wait(10)
            except Exception:
                pass
        self.proc = None


# ------------------------------------------------------------------ text helpers
def parse(out):
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S)
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except Exception:
        return []
    res = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and isinstance(it.get("find"), str) and isinstance(it.get("replace"), str):
            f, r = it["find"], it["replace"]
            if f and f != r and (f, r) not in res:
                res.append((f, r))
    return res


def count(text, find):
    return text.count(find)


def apply(text, changes):
    """changes: list of (find, replace). Returns (new text, number of places changed)."""
    n = 0
    for f, r in changes:
        if f and f != r:
            c = text.count(f)
            if c:
                text = text.replace(f, r); n += c
    return text, n


def context(text, instruction, limit=6000):
    """The part of the text to show the AI: lines with words from the instruction first, then the start, up to
    about `limit` characters (the AI reads at most a few thousand words at a time)."""
    if len(text) <= limit:
        return text
    lines = text.split("\n")
    words = [w for w in re.findall(r"\w+", instruction) if len(w) > 2]
    pick = []
    for i, ln in enumerate(lines):
        if any(w in ln for w in words):
            pick.append(i)
    keep, size = set(), 0
    for i in pick + list(range(len(lines))):
        if i in keep:
            continue
        if size + len(lines[i]) + 1 > limit:
            if i in pick:
                continue
            break
        keep.add(i); size += len(lines[i]) + 1
    return "\n".join(lines[i] for i in sorted(keep))
