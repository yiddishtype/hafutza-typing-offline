"""Add-ons: new parts the AI (or an online AI) builds for him from fixed building blocks, no code.

An add-on is a small JSON file in <his data folder>/addons/<id>.json:
  {"id", "name", "kind": button | menu | shortcut | panel, "label", "key", "steps": [{"do", "value"}],
   "notes", "items", "on": true}
  button   = a new button in the row of buttons at the top
  menu     = a new item in the three-dots menu
  shortcut = a key on the keyboard (like Ctrl+Shift+T)
  panel    = a small side box with a note and/or a word list (pressing a word adds it to the text)
The steps only name things the program can already do (see STEPS); nothing from an add-on is ever run as code.
check() cleans an add-on and says what is wrong with it. No window code here."""
import json, os, re, time

import engine, prefs

KINDS = ("button", "menu", "shortcut", "panel")
STEPS = ("ai", "replace", "insert", "copy", "save", "open_folder", "settings", "open", "tab", "message")
OPENS = ("settings", "ai", "videos", "learned", "update", "addons")
MOST_STEPS = 12


def folder():
    d = os.path.join(engine.user_dir(), "addons")
    os.makedirs(d, exist_ok=True)
    return d


def _id(name):
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:30] or "addon"
    i, out = 1, base
    while os.path.exists(os.path.join(folder(), out + ".json")):
        i += 1; out = "%s-%d" % (base, i)
    return out


def _key(k):
    """'ctrl+shift+t' -> 'Ctrl+Shift+T'; None if it is no usable key."""
    k = str(k or "").strip()
    if not k:
        return None
    parts = [p.strip() for p in re.split(r"\s*\+\s*", k) if p.strip()]
    mods = {"ctrl": "Ctrl", "control": "Ctrl", "shift": "Shift", "alt": "Alt"}
    out = []
    for p in parts[:-1]:
        m = mods.get(p.lower())
        if not m:
            return None
        out.append(m)
    last = parts[-1] if parts else ""
    if re.fullmatch(r"[A-Za-z0-9]", last):
        last = last.upper()
    elif re.fullmatch(r"[Ff]([1-9]|1[0-2])", last):
        last = last.upper()
    else:
        return None
    if not out and not last.startswith("F"):
        return None                     # a plain letter alone would stop him typing that letter
    return "+".join(out + [last])


def check_step(st):
    """-> (clean step, None) or (None, why it can't be used)."""
    if isinstance(st, str):
        st = {"do": st}
    if not isinstance(st, dict):
        return None, "a step is not readable"
    do = str(st.get("do") or st.get("step") or st.get("action") or "").strip().lower()
    v = st.get("value", st.get("what"))
    if do not in STEPS:
        return None, "it uses a step the program does not have (%s)" % (do or "nothing")
    if do in ("ai", "insert", "message"):
        v = str(v or "").strip()
        if not v:
            return None, "the %s step says nothing" % do
        return {"do": do, "value": v[:2000]}, None
    if do == "replace":
        if not isinstance(v, dict):
            v = {"find": st.get("find"), "replace": st.get("replace")}
        f, r = str(v.get("find") or ""), str(v.get("replace") if v.get("replace") is not None else "")
        if not f or f == r:
            return None, "the replace step has nothing to find"
        return {"do": do, "value": {"find": f[:500], "replace": r[:500]}}, None
    if do == "save":
        v = str(v or "txt").strip().lower().lstrip(".")
        return {"do": do, "value": v if v in ("txt", "docx") else "txt"}, None
    if do == "settings":
        if not isinstance(v, dict) or not v:
            return None, "the settings step changes nothing"
        bad = [k for k in v if k not in prefs.DEFAULTS and k not in ("reset", "show")]
        if bad:
            return None, "it uses settings the program does not have (%s)" % ", ".join(map(str, bad))
        return {"do": do, "value": v}, None
    if do == "open":
        v = str(v or "").strip().lower()
        v = {"setting": "settings", "chat": "ai", "my typed videos": "videos", "learned words": "learned",
             "my add-ons": "addons", "add-ons": "addons"}.get(v, v)
        if v not in OPENS:
            return None, "it opens something the program does not have (%s)" % v
        return {"do": do, "value": v}, None
    if do == "tab":
        v = str(v or "").strip().lower()[:2]
        if v not in prefs.LANG_CODES:
            return None, "it shows a language the program does not type"
        return {"do": do, "value": v}, None
    return {"do": do}, None               # copy, open_folder


def check(obj):
    """An add-on as the AI wrote it -> (clean add-on, None) or (None, why it can't be made, in plain words)."""
    if not isinstance(obj, dict):
        return None, "the answer had no add-on in it"
    kind = str(obj.get("kind") or obj.get("type") or "").strip().lower()
    kind = {"menu item": "menu", "menu_item": "menu", "key": "shortcut", "hotkey": "shortcut", "note": "panel",
            "word list": "panel", "side panel": "panel", "toolbar": "button"}.get(kind, kind)
    if kind not in KINDS:
        return None, "it is not a kind of part the program can add (only buttons, menu items, shortcut keys and side notes)"
    name = str(obj.get("name") or obj.get("label") or "").strip()[:40]
    label = str(obj.get("label") or name).strip()[:40]
    if not name:
        return None, "it has no name"
    raw = obj.get("steps") or []
    if isinstance(raw, dict):
        raw = [raw]
    steps = []
    for st in raw[:MOST_STEPS + 1]:
        c, why = check_step(st)
        if why:
            return None, why
        steps.append(c)
    if len(steps) > MOST_STEPS:
        return None, "it has more than %d steps" % MOST_STEPS
    out = {"name": name, "kind": kind, "label": label, "steps": steps, "on": True}
    if kind == "shortcut":
        k = _key(obj.get("key"))
        if not k:
            return None, "the shortcut needs a key like Ctrl+Shift+T"
        out["key"] = k
    if kind == "panel":
        notes = str(obj.get("notes") or "").strip()[:3000]
        items = obj.get("items") or []
        if isinstance(items, str):
            items = [x for x in re.split(r"[,\n]", items)]
        items = [str(x).strip()[:80] for x in items if str(x).strip()][:200]
        if not notes and not items:
            return None, "the side note has no words in it"
        out["notes"], out["items"] = notes, items
    elif not steps:
        return None, "pressing it would do nothing (no steps)"
    return out, None


def load_all():
    """-> all add-ons, oldest first."""
    out = []
    d = folder()
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                a = json.load(fh)
            c, why = check(a)
            if c:
                c["id"] = f[:-5]
                c["on"] = a.get("on", True) is not False
                c["made"] = a.get("made", "")
                c["by"] = a.get("by", "")
                out.append(c)
        except Exception as e:
            engine.log("add-on %s not readable: %r" % (f, e))
    out.sort(key=lambda a: (a.get("made", ""), a["id"]))
    return out


def save(a, by="AI"):
    """Save a checked add-on (new or changed). -> its id."""
    a = dict(a)
    if not a.get("id"):
        a["id"] = _id(a.get("name"))
        a["made"] = time.strftime("%Y-%m-%d %H:%M:%S")
        a["by"] = by
    p = os.path.join(folder(), a["id"] + ".json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return a["id"]


def get(aid):
    for a in load_all():
        if a["id"] == aid:
            return a
    return None


def delete(aid):
    try:
        os.remove(os.path.join(folder(), aid + ".json"))
        return True
    except Exception:
        return False


def set_on(aid, on):
    a = get(aid)
    if a:
        a["on"] = bool(on)
        save(a)


def all_off():
    """Reset to normal: every add-on is turned off (kept, so he can turn it on again). -> the ids turned off."""
    off = []
    for a in load_all():
        if a["on"]:
            set_on(a["id"], False); off.append(a["id"])
    return off


def describe(a):
    """One plain line on what an add-on is and does."""
    where = {"button": "a button at the top", "menu": "an item in the ⋮ menu", "shortcut": "the key " + a.get("key", ""),
             "panel": "a side note"}[a["kind"]]
    did = []
    for st in a.get("steps", []):
        d, v = st["do"], st.get("value")
        did.append({"ai": lambda: "asks the AI: %s" % v, "replace": lambda: "changes %s to %s" % (v["find"], v["replace"]),
                    "insert": lambda: "adds “%s”" % v[:40], "copy": lambda: "copies the text",
                    "save": lambda: "saves the text (.%s)" % v, "open_folder": lambda: "opens the folder",
                    "settings": lambda: "sets %s" % ", ".join("%s=%s" % kv for kv in v.items()),
                    "open": lambda: "opens %s" % v, "tab": lambda: "shows the %s text" % v,
                    "message": lambda: "shows a message"}[d]())
    if a["kind"] == "panel":
        if a.get("notes"):
            did.insert(0, "a note")
        if a.get("items"):
            did.append("%d words to press" % len(a["items"]))
    return "%s: %s%s" % (a["name"], where, (" — " + "; ".join(did)) if did else "")
