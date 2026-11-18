"""Hafutza Typing: what the program learns from his fixes.

Every time he fixes a line (in the video player), the words he changed are remembered:
  "speech"  wrong word(s) the typing gave -> the right word(s)      (per spoken language)
  "tr"      wrong word(s) in a translation -> the right word(s)     (per language translated to)
On the next video, the typing and the translations are corrected with that list by themselves, and the right words
of the typing list are given to the speech model as hint words. The list can be seen and changed in "Learned words".
(The speech and translation models themselves are not retrained: that needs a big graphics card for days.)
Stored in %LOCALAPPDATA%\\HafutzaTyping\\learned.json.
"""
import difflib, json, os, re, threading, time

import engine

_lock = threading.Lock()
MARKS = "֑-ׇיִ-ﭏ"          # Hebrew/Yiddish points and joined letters count as part of a word
PUNCT = ".,!?;:\"'()[]{}־׳״“”„‘’-–—…"


def path():
    return os.path.join(engine.user_dir(), "learned.json")


def load():
    try:
        with open(path(), encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("items", [])
        return d
    except Exception:
        return {"items": []}


def save(d):
    p = path()
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(p + ".tmp", p)


def _clean(w):
    return w.strip(PUNCT)


def diff_pairs(old, new, most=4):
    """The words that were changed: [(wrong, right)], phrases up to `most` words each side."""
    a, b = old.split(), new.split()
    out = []
    sm = difflib.SequenceMatcher(a=[_clean(w) for w in a], b=[_clean(w) for w in b], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "replace":
            continue
        if i2 - i1 > most or j2 - j1 > most:
            continue
        wrong = " ".join(_clean(w) for w in a[i1:i2]).strip()
        right = " ".join(_clean(w) for w in b[j1:j2]).strip()
        if wrong and right and wrong != right:
            out.append((wrong, right))
    return out


def learn(kind, lang, old, new):
    """Remember the changes between old and new. -> the (wrong, right) pairs learned."""
    pairs = diff_pairs(old, new)
    if not pairs:
        return []
    with _lock:
        d = load()
        for wrong, right in pairs:
            hit = next((it for it in d["items"] if it["kind"] == kind and it["lang"] == lang and it["wrong"] == wrong), None)
            if hit:
                if hit["right"] == right:
                    hit["times"] = hit.get("times", 1) + 1
                else:
                    hit["right"], hit["times"] = right, 1
                hit["when"] = time.strftime("%Y-%m-%d %H:%M")
            else:
                d["items"].append({"kind": kind, "lang": lang, "wrong": wrong, "right": right, "times": 1,
                                   "when": time.strftime("%Y-%m-%d %H:%M")})
        save(d)
    engine.log("learned %s %s: %s" % (kind, lang, pairs))
    return pairs


def add(kind, lang, wrong, right):
    wrong, right = " ".join(wrong.split()), " ".join(right.split())
    if not wrong or not right or wrong == right:
        return False
    with _lock:
        d = load()
        d["items"] = [it for it in d["items"] if not (it["kind"] == kind and it["lang"] == lang and it["wrong"] == wrong)]
        d["items"].append({"kind": kind, "lang": lang, "wrong": wrong, "right": right, "times": 1,
                           "when": time.strftime("%Y-%m-%d %H:%M")})
        save(d)
    return True


def remove(indexes):
    with _lock:
        d = load()
        d["items"] = [it for i, it in enumerate(d["items"]) if i not in set(indexes)]
        save(d)


def _pattern(wrong):
    words = [re.escape(w) for w in wrong.split()]
    return re.compile(r"(?<![\w%s])%s(?![\w%s])" % (MARKS, r"\s+".join(words), MARKS))


def rules(kind, lang):
    items = [it for it in load()["items"] if it["kind"] == kind and it["lang"] == lang]
    items.sort(key=lambda it: -len(it["wrong"]))          # longer phrases first
    return items


def apply(kind, lang, text):
    """Correct a text with the learned list. -> (text, number of changes)."""
    n = 0
    for it in rules(kind, lang):
        text, k = _pattern(it["wrong"]).subn(lambda m, r=it["right"]: r, text)
        n += k
    return text, n


def hotwords(lang, most_words=40):
    """The right words of his typing fixes for this language, newest first: a hint for the speech model."""
    items = [it for it in load()["items"] if it["kind"] == "speech" and it["lang"] == lang]
    items.sort(key=lambda it: it.get("when", ""), reverse=True)
    words, seen = [], set()
    for it in items:
        for w in it["right"].split():
            if w not in seen:
                seen.add(w); words.append(w)
    return " ".join(words[:most_words]) or None
