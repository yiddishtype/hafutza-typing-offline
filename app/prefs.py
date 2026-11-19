"""The program's settings (the ⋮ menu > Settings, or by asking the AI): brightness, volume, the font of the words and
its size. Kept in settings.json next to the program's other data, so they stay the same next time.

The fonts are free fonts (SIL Open Font License) that come with the program, in its fonts folder: all show Yiddish
in Hebrew letters. Nothing here needs the internet."""
import json, os, sys

DEFAULTS = {
    # sound and light
    "brightness": 100, "volume": 80,
    # the words: the typed text's font and size, the size of all the program's own words, the big title
    "font": "", "font_size": 14, "ui_size": 12, "title_size": 22,
    # colours ("" = the usual one); any colour name (blue, dark green) or #rrggbb
    "theme": "light", "button_color": "", "button_text_color": "", "background_color": "", "text_color": "",
    "start_color": "", "ai_color": "",
    # sizes and places
    "button_size": 100,            # per cent of the usual button size
    "ai_side": "right",            # the AI ball and the AI panel: right or left of the window
    "ai_width": 0,                 # the AI side panel's width in pixels (0 = about 4 inches)
    "ai_button_pos": "right",      # the "AI" button in the row of buttons at the top: left or right of the others
    "toolbar": "top",              # that row of buttons: top or bottom of the window
    "window": "normal",            # normal, maximized or fullscreen
    # what shows, and what the buttons say
    "hide": [],                    # parts hidden: see PARTS
    "labels": {},                  # part -> his own words for that button
    # typing options (the choices in steps 2 and 3, as they are when the program opens)
    "spoken": "yi", "translate": ["yi"],
}
LIMITS = {"brightness": (40, 100), "volume": (0, 100), "font_size": (9, 36), "ui_size": (9, 20),
          "title_size": (12, 44), "button_size": (60, 220), "ai_width": (0, 1000)}
CHOICES = {"theme": ("light", "dark"), "ai_side": ("right", "left"), "ai_button_pos": ("right", "left"),
           "toolbar": ("top", "bottom"), "window": ("normal", "maximized", "fullscreen")}
COLORS = ("button_color", "button_text_color", "background_color", "text_color", "start_color", "ai_color")
# the parts of the window the AI (or he) may hide or rename
PARTS = {"videos": "My typed videos button", "learned": "Learned words button", "ai_button": "AI button in the top row",
         "update": "Update button", "version": "version number", "title": "big title", "subtitle": "line under the title",
         "ball": "round AI ball", "footer": "line at the bottom", "start": "Start button", "stop": "Stop button",
         "choose": "Choose files button", "watch": "Watch the video button", "link": "video link box"}
NO_HIDE = {"start", "stop", "choose"}           # never hidden: the program would be no use without them
LANG_CODES = ("yi", "en", "he", "hu", "ru", "fr", "es", "de")
# colour names in Yiddish and Hebrew letters -> English colour names
YI_COLORS = {"בלוי": "blue", "רויט": "red", "גרין": "green", "גרינע": "green", "געל": "gold", "שווארץ": "black",
             "ווייס": "white", "גרוי": "gray", "ראזע": "pink", "לילא": "purple", "פיאלעט": "purple", "ברוין": "brown",
             "אראנזש": "orange", "טונקל בלוי": "navy", "כחול": "blue", "אדום": "red", "ירוק": "green", "שחור": "black"}
STANDARD = "Standard"           # the font name shown for "the program's usual font"

_cur = None
_fonts = None                    # family names of the fonts that came with the program


def data_dir():
    d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "HafutzaTyping")
    os.makedirs(d, exist_ok=True)
    return d


def path():
    return os.environ.get("HAFUTZA_SETTINGS") or os.path.join(data_dir(), "settings.json")


def fonts_dir():
    here = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(here, "fonts"), os.path.join(here, "_internal", "fonts")):
        if os.path.isdir(d):
            return d
    return os.path.join(here, "fonts")


def load():
    global _cur
    if _cur is None:
        _cur = dict(DEFAULTS)
        try:
            with open(path(), encoding="utf-8") as f:
                got = json.load(f)
            for k in DEFAULTS:
                if k in got:
                    _cur[k] = got[k]
        except Exception:
            pass
        for k in DEFAULTS:
            v = check(k, _cur[k])
            _cur[k] = DEFAULTS[k] if v is None else v
    return _cur


def get(k):
    return load()[k]


def clamp(k, v):
    try:
        v = int(round(float(v)))
    except Exception:
        v = DEFAULTS[k]
    lo, hi = LIMITS[k]
    return max(lo, min(hi, v))


def color(v):
    """A colour as he or the AI wrote it -> '#rrggbb', '' for the usual one, or None if it is no colour."""
    v = (v or "").strip()
    if v.lower() in ("", "normal", "default", "usual", "standard", "none"):
        return ""
    v = YI_COLORS.get(v, v)
    try:
        from PySide6.QtGui import QColor
        name = v.replace(" ", "").lower()
        c = QColor(name) if QColor.isValidColorName(name) else None
        if c is None and QColor.isValidColorName(v):
            c = QColor(v)
        return c.name() if c is not None and c.isValid() else None
    except Exception:
        return v if v.startswith("#") and len(v) in (4, 7) else None


def check(k, v):
    """v made fit for setting k, or None if it can't be."""
    if k in LIMITS:
        return clamp(k, v)
    if k in CHOICES:
        v = str(v or "").strip().lower()
        v = {"dark mode": "dark", "night": "dark", "light mode": "light", "day": "light", "max": "maximized",
             "big": "maximized", "full": "fullscreen", "full screen": "fullscreen", "end": "bottom"}.get(v, v)
        return v if v in CHOICES[k] else None
    if k in COLORS:
        return color(v)
    if k == "font":
        return match_font(v) if v != "" else ""
    if k == "hide":
        if isinstance(v, str):
            v = [v]
        return sorted({str(p) for p in (v or []) if str(p) in PARTS and str(p) not in NO_HIDE})
    if k == "labels":
        if not isinstance(v, dict):
            return None
        return {str(p): str(t)[:60] for p, t in v.items() if str(p) in PARTS and str(t).strip()}
    if k == "spoken":
        v = str(v or "").strip().lower()[:2]
        return v if v in LANG_CODES else None
    if k == "translate":
        if isinstance(v, str):
            v = [v]
        out = [str(x).strip().lower()[:2] for x in (v or [])]
        out = [x for x in LANG_CODES if x in out]
        return out or None
    return v


def save():
    try:
        with open(path(), "w", encoding="utf-8") as f:
            json.dump(load(), f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def set_many(new):
    """new: {key: value}; numbers may be relative ("+2", "-20"); "show"/"hide_add" lists and "labels" merge in;
    "reset": true puts everything back to normal. -> {key: (old, new)} for what really changed."""
    cur = load()
    done = {}
    new = dict(new or {})
    if new.pop("reset", None) in (True, "true", "yes", 1, "all"):
        for k in DEFAULTS:
            if cur[k] != DEFAULTS[k]:
                done[k] = (cur[k], DEFAULTS[k])
                cur[k] = json.loads(json.dumps(DEFAULTS[k]))
    show = new.pop("show", None)
    if show:
        hid = set(new.get("hide", cur["hide"]) if isinstance(new.get("hide", cur["hide"]), list) else cur["hide"])
        new["hide"] = sorted(hid - set([show] if isinstance(show, str) else show))
    elif "hide" in new and isinstance(new["hide"], (str, list)):
        add = [new["hide"]] if isinstance(new["hide"], str) else new["hide"]
        new["hide"] = sorted(set(cur["hide"]) | set(add))
    if isinstance(new.get("labels"), dict):
        lab = dict(cur["labels"])
        for p, t in new["labels"].items():
            if str(t).strip().lower() in ("", "normal", "default", "usual"):
                lab.pop(p, None)
            else:
                lab[p] = t
        new["labels"] = lab
    for k, v in new.items():
        if k not in DEFAULTS:
            continue
        old = cur[k]
        if k in LIMITS and isinstance(v, str) and v.strip()[:1] in "+-":
            try:
                v = old + float(v.strip().rstrip("%"))
            except Exception:
                continue
        v = check(k, v)
        if v is None:
            continue
        if v != old:
            cur[k] = v
            done[k] = (done[k][0] if k in done else old, v)
    if done:
        save()
    return done


def load_fonts():
    """Register the program's own fonts with Qt (once). -> their family names, sorted."""
    global _fonts
    if _fonts is None:
        from PySide6.QtGui import QFontDatabase
        names = set()
        d = fonts_dir()
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.lower().endswith((".ttf", ".otf")):
                    i = QFontDatabase.addApplicationFont(os.path.join(d, f))
                    if i >= 0:
                        fam = QFontDatabase.applicationFontFamilies(i)
                        if fam:
                            names.add(fam[0])
        _fonts = sorted(names, key=str.lower)
    return _fonts


def match_font(name):
    """A font name as the user or the AI wrote it -> the real family name ("" for the standard font), or None."""
    n = (name or "").strip().lower()
    if not n or n in ("standard", "default", "normal", "usual"):
        return ""
    fams = _fonts or []
    for f in fams:
        if f.lower() == n:
            return f
    for f in fams:
        if n in f.lower() or f.lower() in n:
            return f
    words = set(n.replace("-", " ").split())
    best = [f for f in fams if words & set(f.lower().split()) - {"sans", "serif", "hebrew", "libre", "one", "noto"}]
    return best[0] if len(best) == 1 else None


def text_font(base=None, size=None):
    """The QFont for the words (the typed text, the lines in the player)."""
    from PySide6.QtGui import QFont
    f = QFont(base) if base is not None else QFont()
    fam = get("font")
    if fam:
        f.setFamily(fam)
    f.setPointSize(size or get("font_size"))
    return f


def put_back(done):
    """Undo: set back the old values of a set_many() result."""
    cur = load()
    for k, (old, new) in done.items():
        cur[k] = old
    save()


NAMES = {"brightness": "brightness", "volume": "volume", "font": "font", "font_size": "text size",
         "ui_size": "size of the program's words", "title_size": "title size", "theme": "theme",
         "button_color": "button colour", "button_text_color": "button words colour", "background_color": "background",
         "text_color": "words colour", "start_color": "Start button colour", "ai_color": "AI colour",
         "button_size": "button size", "ai_side": "AI side", "ai_width": "AI panel width",
         "ai_button_pos": "AI button place", "toolbar": "row of buttons", "window": "window", "hide": "hidden parts",
         "labels": "button names", "spoken": "language spoken", "translate": "type it out in"}


def describe(done):
    """{key: (old, new)} -> lines like 'text size: 13 → 15'."""
    def show(k, v):
        if k == "font":
            return v or STANDARD
        if k in COLORS:
            return v or "usual"
        if k == "hide":
            return ", ".join(PARTS[p] for p in v) or "nothing"
        if k == "labels":
            return ", ".join("%s = %s" % (p, t) for p, t in v.items()) or "usual"
        if k in ("brightness", "volume", "button_size"):
            return "%s%%" % v
        if k == "translate":
            return ", ".join(v)
        if k == "ai_width":
            return "%d px" % v if v else "usual"
        return str(v)
    return ["%s: %s → %s" % (NAMES.get(k, k), show(k, o), show(k, n)) for k, (o, n) in done.items()]
