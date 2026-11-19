"""Hafutza Typing (offline): the AI helper that fixes words on request. No window code here.

  The user chats with it in the side panel (English or Yiddish): "change X to Y", "shorten the first line",
  "what is this about?". The AI (Qwen3.5-4B, run on this computer by llama.cpp's llama-server, no internet)
  answers with a reply and a list of changes {find, replace}; the program makes the changes at once and shows
  them in the chat, each with an Undo button.

  The model (2.7 GB) comes with the program's one-time download of its parts (or later from the AI button);
  the program works fully without it.
  llama-server.exe comes with the program, in the folder "llama".
"""
import hashlib, json, os, re, socket, subprocess, sys, threading, time, urllib.request

import engine

MODEL_URL = ("https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/"
             "e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf")
MODEL_FILE = "Qwen3.5-4B-Q4_K_M.gguf"
MODEL_SIZE = 2740937888
MODEL_SHA = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
CTX = 4096

SYS = ("You are the AI helper inside a Yiddish typing program. The user chats with you, in English or Yiddish, about "
       "a typed text (Yiddish in Hebrew letters, or its English or other translation). Answer with ONLY a JSON object: "
       "{\"reply\": \"...\", \"changes\": [{\"find\": \"exact words now in the text\", \"replace\": \"new words\"}]}. "
       "When the user asks for a change to the text (change, fix, correct, spell, shorten, rewrite, translate a part ...), "
       "put each change in \"changes\": \"find\" copied exactly from the text (a word, or a whole sentence to rewrite it), "
       "\"replace\" the new words, and in \"reply\" say in one short sentence what you changed. Make only the changes asked for. "
       "When the user only asks a question or chats, answer it in \"reply\" (short, in the user's language) and give "
       "\"changes\": []. "
       "The message may be in Yiddish even when the text is English: \"טוישט X אויף Y\", \"בייט X צו Y\", "
       "\"מאך X Y\", \"שרייב Y אנשטאט X\" all mean: change X to Y. Copy X and Y exactly as the user wrote them.")

# Short worked examples shown to the AI before the real question (a small model follows examples best).
SHOTS = [
    ("TEXT:\nThe Rebbe tells the story of the old shul.\n\nMESSAGE: טוישט \"shul\" אויף \"synagogue\"",
     '{"reply": "Changed shul to synagogue.", "changes": [{"find": "shul", "replace": "synagogue"}]}'),
    ("TEXT:\nדער רבי האט געזאגט א מעשה פון זיין טאטן.\n\nMESSAGE: the word for story should be מעשׂה",
     '{"reply": "Changed מעשה to מעשׂה.", "changes": [{"find": "מעשה", "replace": "מעשׂה"}]}'),
    ("TEXT:\nWe went to Bnei Brak on Sunday. It was a very very long and tiring trip for all of us.\n\n"
     "MESSAGE: make the second sentence shorter",
     '{"reply": "Shortened the second sentence.", "changes": [{"find": "It was a very very long and tiring trip '
     'for all of us.", "replace": "It was a long trip."}]}'),
    ("TEXT:\nWe went to Bnei Brak on Sunday.\n\nMESSAGE: where did they go?",
     '{"reply": "They went to Bnei Brak, on Sunday.", "changes": []}'),
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
                req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "HafutzaTyping/1.5",
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
        # The typing waits while the AI answers (engine.HOLD), so the AI may use the whole computer:
        # reading the question on every core, writing the answer on one thread per real core.
        nb = max(1, os.cpu_count() or 2)
        n = max(1, nb // 2)
        logf = open(os.path.join(engine.user_dir(), "ai-log.txt"), "w", encoding="utf-8", errors="replace")
        flags = 0x08000000 if sys.platform == "win32" else 0     # CREATE_NO_WINDOW
        self.proc = subprocess.Popen([exe, "-m", model, "-c", str(CTX), "-t", str(n), "-tb", str(nb), "--jinja",
                                      "--host", "127.0.0.1", "--port", str(self.port)],
                                     stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     creationflags=flags, cwd=os.path.dirname(exe))
        engine.log("ai server started, port %d, %d/%d threads" % (self.port, n, nb))
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
                        self._prime()
                        return
            except Exception:
                pass
            time.sleep(0.5)
        self.close()
        raise RuntimeError("The AI took too long to start.")

    def _prime(self):
        """Read the fixed start of every question (rules + examples) once now; llama-server keeps it, so each real
        question only has to read the text and the instruction."""
        try:
            self._post(self._messages("x", "x"), 1)
        except Exception as e:
            engine.log("ai prime failed %r" % e)

    def _messages(self, text, message, history=()):
        """history: earlier (message, answer) pairs of this chat, newest last (only the last few are sent)."""
        shots = []
        for q, a in SHOTS:
            shots += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        past = []
        for q, a in list(history)[-2:]:
            past += [{"role": "user", "content": "MESSAGE: " + q},
                     {"role": "assistant", "content": json.dumps({"reply": a, "changes": []}, ensure_ascii=False)}]
        return [{"role": "system", "content": SYS}] + shots + past + [
            {"role": "user", "content": "TEXT:\n" + text + "\n\nMESSAGE: " + message}]

    def _post(self, messages, max_tokens):
        body = {"messages": messages, "temperature": 0, "max_tokens": max_tokens, "cache_prompt": True,
                "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % self.port,
                                     data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with _LOCAL.open(req, timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"] or ""

    def ask(self, text, instruction, stop=lambda: False):
        """-> (list of (find, replace), raw answer)."""
        reply, ch, out = self.chat(text, instruction, (), stop)
        return ch, out

    def chat(self, text, message, history=(), stop=lambda: False):
        """One chat message about the text. -> (reply words, list of (find, replace), raw answer)."""
        self.start(stop)
        out = self._post(self._messages(text, message, history), 600)
        reply, ch = parse_chat(out)
        return reply, ch, out

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


def parse_chat(out):
    """-> (reply, [(find, replace)]). Takes the JSON object the AI is asked for; a bare list of changes or plain
    words (a small model sometimes slips) work too."""
    out = re.sub(r"<think>.*?</think>", "", out or "", flags=re.S).strip()
    m = re.search(r"\{.*\}", out, re.S)
    if m and not out.lstrip().startswith("["):
        try:
            obj = json.loads(m.group(0))
        except Exception:
            obj = None
        if isinstance(obj, dict) and ("reply" in obj or "changes" in obj):
            reply = obj.get("reply") if isinstance(obj.get("reply"), str) else ""
            ch = parse(json.dumps(obj.get("changes") or [], ensure_ascii=False))
            return reply.strip(), ch
    ch = parse(out)
    if ch or out.lstrip().startswith("["):
        return "", ch
    return re.sub(r"^```\w*|```$", "", out).strip(), []


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


def context(text, instruction, limit=2500):
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
