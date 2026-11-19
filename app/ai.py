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

import engine, prefs

MODEL_URL = ("https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/"
             "e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf")
MODEL_FILE = "Qwen3.5-4B-Q4_K_M.gguf"
MODEL_SIZE = 2740937888
MODEL_SHA = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
CTX = 6144

SYS = ("You are the AI helper inside a Yiddish typing program. The user chats with you, in English, Yiddish or Hebrew, about "
       "a typed text (Yiddish in Hebrew letters, or its English or other translation). Answer with ONLY a JSON object: "
       "{\"reply\": \"...\", \"changes\": [{\"find\": \"exact words now in the text\", \"replace\": \"new words\"}]}. "
       "When the user asks for a change to the text (change, fix, correct, spell, shorten, rewrite, translate a part ...), "
       "put each change in \"changes\": \"find\" copied exactly from the text (a word, or a whole sentence to rewrite it), "
       "\"replace\" the new words, and in \"reply\" say in one short sentence what you changed. Make only the changes asked for. "
       "When the user only asks a question or chats, answer it in \"reply\" (short, in the user's language) and give "
       "\"changes\": []. "
       "The message may be in Yiddish even when the text is English: \"טוישט X אויף Y\", \"בייט X צו Y\", "
       "\"מאך X Y\", \"שרייב Y אנשטאט X\" all mean: change X to Y. Copy X and Y exactly as the user wrote them.  "
       "The message may also be in Hebrew: \"תחליף X ב-Y\", \"שנה את X ל-Y\", \"במקום X תכתוב Y\", \"תקן X ל-Y\" "
       "all mean: change X to Y (leave out the little ב- or ל- in front of Y). Write \"reply\" in the language of the "
       "MESSAGE: Hebrew when the message is Hebrew (words like את, של, תשנה, אני, זה), Yiddish when it is Yiddish, "
       "English when it is English. "
       "When the user asks to change how the PROGRAM looks, sounds or is laid out, do not change the text: give "
       "\"changes\": [] and add \"settings\" with only what was asked. Settings: font_size (\"+2\", \"-2\" or 9-36, the "
       "letters of the text), font (a font name), brightness (\"-20\" or 40-100), volume (\"+20\" or 0-100), theme (light "
       "or dark), button_color, button_text_color, background_color, text_color, start_color, ai_color (a colour name), "
       "button_size (per cent: \"+30\" bigger, \"-20\" smaller), ui_size (the program's own words, 9-20), title_size, "
       "ai_side (left or right: the AI ball and panel), ai_button_pos (left or right: the AI button in the top row), "
       "toolbar (top or bottom), window (normal, maximized, fullscreen), hide or show (a part: videos, learned, ai_button, "
       "update, version, title, subtitle, ball, footer, watch, link), labels ({\"part\": \"new words on it\"}), spoken "
       "and translate (yi en he hu ru fr es de), reset (true = everything back to normal). "
       "When the user asks for a NEW part (a new button, a menu item, a shortcut key, a side note or a word list) made of "
       "things the program can already do, give \"changes\": [] and add \"addon\": {\"name\": \"...\", \"kind\": \"button\" "
       "or \"menu\" or \"shortcut\" or \"panel\", \"label\": \"words on it\", \"key\": \"Ctrl+T\" (shortcut only), "
       "\"steps\": [{\"do\": \"...\", \"value\": \"...\"}], \"notes\": \"words of a note\" (panel), \"items\": [\"words\"] "
       "(panel word list)}. Steps (\"do\"): ai (value: what to ask the AI to do to the text), replace (value: {\"find\": "
       "\"..\", \"replace\": \"..\"}), insert (value: words to add at the end), copy, save (value: txt or docx), "
       "open_folder, settings (value: settings as above), open (value: settings, ai, videos, learned, update or addons), "
       "tab (value: yi en he ...), message (value: words to show). "
       "When the user asks for something none of this can do (a new feature, the internet, changing the program's code, "
       "anything not listed), do every part you CAN do (changes, settings or addon) and add \"too_big\": true for the rest; say in "
       "\"reply\" in one short sentence what you did and that the rest you can't build yourself, so you are giving him a "
       "ready request for any other AI.")

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
    ("TEXT:\nדער רבי האט געזאגט א מעשה.\n\nMESSAGE: make the letters bigger and the program darker",
     '{"reply": "Made the letters bigger and the program darker.", "changes": [], '
     '"settings": {"font_size": "+2", "brightness": "-20"}}'),
    ("TEXT:\nWe went to Bnei Brak.\n\nMESSAGE: make the buttons green and smaller, put the AI on the left and hide the title",
     '{"reply": "Made the buttons green and smaller, moved the AI to the left and hid the title.", "changes": [], '
     '"settings": {"button_color": "green", "button_size": "-20", "ai_side": "left", "hide": "title"}}'),
    ("TEXT:\nWe went to Bnei Brak.\n\nMESSAGE: add a button Translate that turns the text into English",
     '{"reply": "Added a Translate button at the top.", "changes": [], "addon": {"name": "Translate", "kind": "button", '
     '"label": "Translate", "steps": [{"do": "ai", "value": "translate the whole text into English"}]}}'),
    ("TEXT:\nדער רבי האט געזאגט א מעשה פון זיין טאטן.\n\nMESSAGE: תחליף את המילה טאטן ב-פאטער",
     '{"reply": "החלפתי את טאטן ב-פאטער.", "changes": [{"find": "טאטן", "replace": "פאטער"}]}'),
    ("TEXT:\nWe went to Bnei Brak on Sunday.\n\nMESSAGE: על מה מדובר בטקסט?",
     '{"reply": "הטקסט מספר שהם נסעו לבני ברק ביום ראשון.", "changes": []}'),
    ("TEXT:\nWe went to Bnei Brak.\n\nMESSAGE: תגדיל את האותיות ותעשה את הכפתורים כחולים",
     '{"reply": "הגדלתי את האותיות וצבעתי את הכפתורים בכחול.", "changes": [], '
     '"settings": {"font_size": "+2", "button_color": "blue"}}'),
    ("TEXT:\nWe went to Bnei Brak.\n\nMESSAGE: make it send the text to my WhatsApp every night",
     '{"reply": "I can\'t build that myself: it needs a new feature. Here is a ready request for any other AI.", '
     '"changes": [], "too_big": true}'),
]

# Everything an online AI needs to know to build a settings change or an add-on (the "Ask a different AI" road).
SPEC_FULL = """You are helping the user of "Hafutza Typing", a Windows program that types out Yiddish (and other) videos.
The program cannot run code from you. It can only take ONE JSON object, which it checks and applies (with Undo):

{"reply": "one short sentence for the user",
 "settings": { ...only the settings to change... },
 "addon": { ...one new part, or leave this out... },
 "too_big": true   (only if none of this can do what he asks)}

SETTINGS (leave out what he did not ask for):
- font_size: letters of the typed text, 9 to 36, or "+2" / "-2"
- font: the typed text's font name, one of: {FONTS}
- ui_size: the program's own words, 9 to 20;  title_size: the big title, 12 to 44
- brightness: 40 to 100 (or "-20");  volume: 0 to 100 (or "+20")
- theme: "light" or "dark"
- button_color, button_text_color, background_color, text_color, start_color, ai_color: a colour name or #rrggbb ("" = usual)
- button_size: per cent of the usual size, 60 to 220, or "+30" / "-20"
- ai_side: "left" or "right" (the round AI ball and the AI panel)
- ai_width: AI panel width in pixels (0 = usual, about 4 inches)
- ai_button_pos: "left" or "right" (the AI button in the row of buttons at the top)
- toolbar: "top" or "bottom" (that row of buttons)
- window: "normal", "maximized" or "fullscreen"
- hide: a part name or a list;  show: a part name or a list. Parts: videos (My typed videos button), learned (Learned words
  button), ai_button, update, version, title, subtitle, ball (round AI ball), footer, watch (Watch the video button), link
  (video link box)
- labels: {"part": "new words on that button"}
- spoken: language spoken, one of yi en he hu ru fr es de;  translate: list of languages to type it out in
- reset: true puts everything back to normal

ADDON (one new part, made from these blocks only):
{"name": "short name", "kind": "button" | "menu" | "shortcut" | "panel",
 "label": "words on the button or menu item", "key": "Ctrl+Shift+T" (kind shortcut only),
 "steps": [ {"do": "<step>", "value": ...}, ... ]   (run in order when it is pressed),
 "notes": "words for a side note" (kind panel), "items": ["words", "for", "a word list"] (kind panel: pressing one adds it to the text)}
button = a new button in the row at the top; menu = a new item in the three-dots menu; shortcut = a key on the keyboard;
panel = a small side box with a note and/or a word list.
Steps:
- {"do": "ai", "value": "what the program's own AI should do to the shown text"}  e.g. "fix the spelling"
- {"do": "replace", "value": {"find": "old words", "replace": "new words"}}
- {"do": "insert", "value": "words to add at the end of the text"}
- {"do": "copy"}  (copies the shown text)
- {"do": "save", "value": "txt" or "docx"}  (saves the shown text into the program's documents folder)
- {"do": "open_folder"}  (opens that folder)
- {"do": "settings", "value": { ...settings as above... }}
- {"do": "open", "value": "settings" | "ai" | "videos" | "learned" | "update" | "addons"}
- {"do": "tab", "value": "yi" | "en" | "he" | ...}  (shows that language's text)
- {"do": "message", "value": "words to show in a box"}

It can NOT: run code or scripts, reach the internet or other programs, send mail or messages, change how typing or the AI
works inside, or add a new kind of part or step. If he asks for that, answer {"reply": "...why...", "too_big": true}.
Answer with the JSON object only, no other words."""

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


def _obj(out):
    """The JSON object in an answer (also inside ```json fences), or {}."""
    out = re.sub(r"<think>.*?</think>", "", out or "", flags=re.S)
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


SETTING_KEYS = set(prefs.DEFAULTS) | {"reset", "show"}


def parse_settings(out):
    """The "settings" part of the AI's answer -> dict of known setting keys only (or {})."""
    st = _obj(out).get("settings")
    if not isinstance(st, dict):
        return {}
    return {k: v for k, v in st.items() if k in SETTING_KEYS and v not in (None, "", [], {})}


def parse_answer(out):
    """Everything in one answer: {reply, changes [(find, replace)], settings {}, addon {} or None, too_big}."""
    reply, ch = parse_chat(out)
    obj = _obj(out)
    addon = obj.get("addon") if isinstance(obj.get("addon"), dict) else None
    return {"reply": reply, "changes": ch, "settings": parse_settings(out), "addon": addon,
            "too_big": obj.get("too_big") in (True, "true", "yes", 1)}


# words that ask for a setting, when the AI itself left "settings" out (English, Yiddish and Hebrew)
_SET_WORDS = [
    ("font_size", "+2", r"\b(bigger|larger|enlarge|increase (the )?(font|letters|text))\b|גרעסער|גרויסער|תגדיל|להגדיל|הגדל|יותר גדול|גדולות יותר|גדולים יותר"),
    ("font_size", "-2", r"\b(smaller|tinier|decrease (the )?(font|letters|text))\b|קלענער|תקטין|להקטין|הקטן|יותר קטן|קטנות יותר|קטנים יותר"),
    ("brightness", "-20", r"\b(darker|dimmer|dim)\b|טונקעלער|פינצטערער|יותר כהה|כהה יותר|תחשיך|חשוך יותר"),
    ("brightness", "+20", r"\b(brighter|lighter)\b|העלער|ליכטיקער|יותר בהיר|בהיר יותר|תבהיר"),
    ("volume", "+20", r"\b(louder|volume up|turn up)\b|העכער|הויכער|יותר חזק|חזק יותר|תגביר"),
    ("volume", "-20", r"\b(quieter|softer|volume down|turn down)\b|שטילער|נידעריקער|יותר שקט|שקט יותר|תנמיך"),
    ("theme", "dark", r"\bdark (mode|theme)\b|\bnight mode\b|מצב כהה|מצב לילה"),
    ("theme", "light", r"\blight (mode|theme)\b|\bday mode\b|מצב בהיר|מצב יום"),
    ("reset", True, r"\b(reset|back to normal|as it was at first)\b|תחזיר הכל|כמו שהיה|לאפס"),
]
_COLOR_RX = (r"\b(blue|red|green|yellow|orange|purple|pink|gray|grey|black|white|brown|gold|navy|teal|"
             r"dark ?blue|dark ?green|light ?blue)\b")


_HE_COLORS = {"כחול": "blue", "אדום": "red", "ירוק": "green", "צהוב": "yellow", "כתום": "orange", "סגול": "purple",
              "ורוד": "pink", "אפור": "gray", "שחור": "black", "לבן": "white", "חום": "brown", "זהב": "gold"}


def settings_hint(message, fonts=()):
    """Settings asked for in plain words (a safety net under the AI): -> dict like parse_settings."""
    low = (message or "").lower()
    st = {}
    buttons = re.search(r"\bbuttons?\b|קנעפ|כפתור", low)
    letters = re.search(r"\b(letters?|font|text|words?)\b|אותיות|בוכשטאבן|גופן|פונט|טקסט", low)
    for key, val, rx in _SET_WORDS:
        if key.startswith("font_size") and buttons and not letters:
            key = "button_size"; val = "+30" if val == "+2" else "-20"
        if key not in st and re.search(rx, low):
            st[key] = val
    if buttons:
        c = re.search(r"buttons?\s+(?:to\s+|in\s+)?" + _COLOR_RX + "|" + _COLOR_RX + r"\s+buttons?|buttons?\b[^.]*?\b" +
                      _COLOR_RX, low)
        if c:
            st["button_color"] = next(g for g in c.groups() if g)
        if "button_color" not in st:
            for he, en in _HE_COLORS.items():
                if he in low:
                    st["button_color"] = en
                    break
    m2 = re.search(r"(כפתור ה)?(בינה המלאכותית|הבינה|ai|AI)[^.]*?(שמאל|ימין)", message or "")
    if m2:
        st["ai_button_pos" if m2.group(1) else "ai_side"] = "left" if m2.group(3) == "שמאל" else "right"
    m = re.search(r"\bai( button)?\b[^.]*?\b(left|right)\b", low)
    if m:
        st["ai_button_pos" if m.group(1) else "ai_side"] = m.group(2)
    for f in sorted(fonts, key=len, reverse=True):     # a font named in the message
        if f and f.lower() in low:
            st["font"] = f
            break
    return st


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
