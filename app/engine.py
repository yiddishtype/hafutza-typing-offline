"""Hafutza Typing (offline): the work itself, no window code here.

  read_sound   any video/audio file -> 16 kHz mono samples (PyAV, which carries its own ffmpeg)
  transcribe   faster-whisper, the same settings as the Hafutza Typing website: one pass, beam 5, int8, ten-minute windows
               cut at a quiet moment, no VAD (VAD dropped half the speech of an old recording in our tests)
  translate    NLLB-200 distilled 1.3B (int8, CTranslate2), line by line
  models       which model files are here, and the one-time download of the missing ones (resumable, checked by sha256)
"""
import gc, hashlib, json, os, sys, time, urllib.request

LANGS = ["yi", "en", "he", "es", "fr"]
NAME_YI = {"yi": "אידיש", "en": "ענגליש", "he": "עברית", "es": "שפאניש", "fr": "פראנצויזיש"}
NAME_EN = {"yi": "Yiddish", "en": "English", "he": "Hebrew", "es": "Spanish", "fr": "French"}
NLLB_CODE = {"yi": "ydd_Hebr", "he": "heb_Hebr", "en": "eng_Latn", "es": "spa_Latn", "fr": "fra_Latn"}
SPEECH_MODEL = {"yi": "yi", "he": "he", "en": "multi", "es": "multi", "fr": "multi"}
MODEL_WHAT = {"yi": "Yiddish speech", "he": "Hebrew speech", "multi": "English / Spanish / French speech",
              "nllb": "translation"}
RELEASE = "https://github.com/yiddishtype/hafutza-typing-offline/releases/download/models-v1/"
RATE = 16000


class Stopped(Exception):
    pass


class NoSound(Exception):
    pass


# ------------------------------------------------------------------ places
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def user_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    d = os.path.join(base, "HafutzaTyping")
    os.makedirs(d, exist_ok=True)
    return d


def manifest():
    for d in (os.path.join(app_dir(), "models"), os.path.join(user_dir(), "models")):
        p = os.path.join(d, "models.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    raise RuntimeError("models.json is missing: please install Hafutza Typing again")


def _places():
    return [os.path.join(app_dir(), "models"), os.path.join(user_dir(), "models")]


def model_path(key):
    """The folder of a model that is fully here, else None."""
    size = manifest()[key]["size"]
    for d in _places():
        p = os.path.join(d, key)
        mb = os.path.join(p, "model.bin")
        if os.path.exists(mb) and os.path.getsize(mb) == size:
            return p
    return None


def missing(keys=None):
    keys = keys or ["yi", "nllb", "he", "multi"]
    return [k for k in keys if model_path(k) is None]


def needed(spoken, targets):
    keys = [SPEECH_MODEL[spoken]]
    if any(t != spoken for t in targets):
        keys.append("nllb")
    return keys


def _writable(d):
    try:
        os.makedirs(d, exist_ok=True)
        t = os.path.join(d, ".w")
        with open(t, "w") as f:
            f.write("x")
        os.remove(t)
        return True
    except OSError:
        return False


def download(key, progress, stop):
    """Fetch one model.bin into the first writable models folder. progress(done_bytes, total_bytes); stop() -> True to stop.
    Resumes a broken download; checks the sha256 at the end."""
    info = manifest()[key]
    src_dir = None
    for d in _places():   # the small files (tokenizer, config) come with the program
        if os.path.exists(os.path.join(d, key, "config.json")):
            src_dir = os.path.join(d, key)
            break
    dst_root = next(d for d in _places() if _writable(d))
    dst = os.path.join(dst_root, key)
    os.makedirs(dst, exist_ok=True)
    if src_dir and os.path.abspath(src_dir) != os.path.abspath(dst):
        import shutil
        for f in os.listdir(src_dir):
            if f != "model.bin" and not os.path.exists(os.path.join(dst, f)):
                shutil.copy2(os.path.join(src_dir, f), os.path.join(dst, f))
    final = os.path.join(dst, "model.bin")
    part = final + ".part"
    total = info["size"]
    url = RELEASE + key + "-model.bin"
    tries = 0
    while True:
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if have > total:
            os.remove(part); have = 0
        if have < total:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "HafutzaTyping/1.0",
                                                           **({"Range": "bytes=%d-" % have} if have else {})})
                r = urllib.request.urlopen(req, timeout=60)
                if have and r.status != 206:
                    have = 0
                with open(part, "ab" if have else "wb") as f:
                    while True:
                        if stop():
                            raise Stopped()
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                        have += len(b)
                        progress(have, total)
                r.close()
            except Stopped:
                raise
            except Exception as e:
                tries += 1
                log("download %s broke off at %d: %r" % (key, have, e))
                if tries >= 8:
                    raise RuntimeError("The download did not work (%s). Is the internet on?" % type(e).__name__)
                time.sleep(min(30, 3 * tries))
                continue
        if os.path.getsize(part) != total:
            tries += 1
            if tries >= 8:
                raise RuntimeError("The download did not finish. Please try again.")
            continue
        h = hashlib.sha256()
        with open(part, "rb") as f:
            for b in iter(lambda: f.read(8 << 20), b""):
                h.update(b)
        if h.hexdigest() != info["sha256"]:
            os.remove(part)
            tries += 1
            if tries >= 3:
                raise RuntimeError("The downloaded file was damaged. Please try again.")
            continue
        os.replace(part, final)
        return final


# ------------------------------------------------------------------ log
_LOG = None


def log(msg):
    global _LOG
    try:
        if _LOG is None:
            _LOG = os.path.join(user_dir(), "log.txt")
            if os.path.exists(_LOG) and os.path.getsize(_LOG) > 2_000_000:
                os.replace(_LOG, _LOG + ".old")
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


def threads():
    return max(1, min(8, os.cpu_count() or 2))


def keep_awake(on):
    """Stop Windows from going to sleep in the middle of a long recording."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
    except Exception:
        pass


# ------------------------------------------------------------------ sound
def read_sound(path, tmpdir, progress, stop):
    """Write the file's sound as 16 kHz mono 16-bit samples to a temp file and return them (a memory map: low memory
    even for a 4-hour file). progress(fraction)."""
    import av, numpy as np
    raw = os.path.join(tmpdir, "sound.raw")
    try:
        c = av.open(path, metadata_errors="ignore")
    except Exception as e:
        raise NoSound(str(e))
    with c:
        if not c.streams.audio:
            raise NoSound("no sound track")
        st = c.streams.audio[0]
        dur = (c.duration / 1e6) if c.duration else (float(st.duration * st.time_base) if st.duration else 0)
        rs = av.AudioResampler(format="s16", layout="mono", rate=RATE)
        n, last = 0, 0.0
        with open(raw, "wb") as f:
            for packet in c.demux(st):
                if stop():
                    raise Stopped()
                try:
                    frames = packet.decode()
                except Exception:
                    continue      # one broken packet: skip it, keep the rest
                for frame in frames:
                    for fr in rs.resample(frame):
                        b = fr.to_ndarray().astype(np.int16).tobytes()
                        f.write(b); n += len(b) // 2
                    if dur and frame.time is not None and time.time() - last > 0.3:
                        last = time.time()
                        progress(min(1.0, frame.time / dur))
            for fr in rs.resample(None):
                b = fr.to_ndarray().astype(np.int16).tobytes()
                f.write(b); n += len(b) // 2
    if n < RATE // 2:
        raise NoSound("no sound in the file")
    return np.memmap(raw, dtype=np.int16, mode="r")


def pieces(x, window=600, seam=30):
    """(start, end) sample spans of about ten minutes, each cut at the quietest half second in its last 30 seconds."""
    import numpy as np
    n, w, out, s = len(x), window * RATE, [], 0
    while n - s > w + seam * RATE:
        lo, hi = s + w - seam * RATE, s + w
        q = np.asarray(x[lo:hi], dtype=np.float32)
        step = RATE // 2
        e = np.add.reduceat(q * q, np.arange(0, len(q), step))
        cut = lo + int(np.argmin(e[:-1] if len(e) > 1 else e)) * step + step // 2
        out.append((s, cut)); s = cut
    out.append((s, n))
    return out


# ------------------------------------------------------------------ typing
def transcribe(x, spoken, progress, stop, hotwords=None, segments=None):
    """progress(fraction, last_lines) as it goes. Returns the text, one line per stretch of speech.
    segments: a list that gets one (start_seconds, end_seconds, text) per line (for the video player).
    hotwords: words he taught it (his fixes), given to the speech model as a hint."""
    from faster_whisper import WhisperModel
    import numpy as np
    path = model_path(SPEECH_MODEL[spoken])
    log("loading %s with %d threads" % (path, threads()))
    model = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=threads(), local_files_only=True)
    dur = len(x) / RATE
    lines = []
    segs = segments if segments is not None else []
    said = time.time()
    kw = {"hotwords": hotwords} if hotwords else {}
    if hotwords:
        log("hint words for the speech model: %s" % hotwords)
    try:
        for s0, s1 in pieces(x):
            log("typing %.0f-%.0f s of %.0f" % (s0 / RATE, s1 / RATE, dur))
            a = np.asarray(x[s0:s1], dtype=np.float32) / 32768.0
            segs_, info = model.transcribe(a, language=spoken, beam_size=5, **kw)
            for s in segs_:
                if stop():
                    raise Stopped()
                t = " ".join(s.text.split())
                if t:
                    lines.append(t)
                    segs.append((round(s0 / RATE + s.start, 2), round(s0 / RATE + s.end, 2), t))
                progress(min(0.999, (s0 / RATE + s.end) / max(dur, 1)), lines[-6:])
                if time.time() - said > 60:
                    said = time.time()
                    log("typed up to %.0f s of %.0f" % (s0 / RATE + s.end, dur))
            del a
    finally:
        del model
        gc.collect()
    return "\n".join(lines).strip()


# ------------------------------------------------------------------ translating
class Translator:
    def __init__(self):
        import ctranslate2, sentencepiece as spm
        p = model_path("nllb")
        self.tr = ctranslate2.Translator(p, device="cpu", compute_type="int8", intra_threads=threads())
        self.sp = spm.SentencePieceProcessor(model_file=os.path.join(p, "sentencepiece.bpe.model"))

    def translate(self, text, src, tgt, progress, stop):
        log("translating %s -> %s" % (src, tgt))
        lines = text.split("\n")
        idx = [i for i, l in enumerate(lines) if l.strip()]
        out = list(lines)
        for k in range(0, len(idx), 8):
            if stop():
                raise Stopped()
            part = idx[k:k + 8]
            toks = [[NLLB_CODE[src]] + self.sp.encode(lines[i], out_type=str)[:400] + ["</s>"] for i in part]
            res = self.tr.translate_batch(toks, target_prefix=[[NLLB_CODE[tgt]]] * len(toks), beam_size=4,
                                          max_decoding_length=300, repetition_penalty=1.1, no_repeat_ngram_size=4)
            for i, r in zip(part, res):
                out[i] = " ".join(self.sp.decode([t for t in r.hypotheses[0] if t not in (NLLB_CODE[tgt], "</s>")]).split())
            progress(min(1.0, (k + len(part)) / max(1, len(idx))))
        return "\n".join(out)

    def close(self):
        del self.tr
        gc.collect()
