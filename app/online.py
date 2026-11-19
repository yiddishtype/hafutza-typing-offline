"""'Ask a different AI': send his request (never his typed text) to a bigger online AI he picked in Settings.

Needs internet. His key is kept only on this computer, in <his data folder>/online.json; nothing is in the installer.
The online AI gets the request plus ai.SPEC_FULL (what the program can change and add) and answers in the same JSON
as the offline AI; the window then checks and applies it with Undo the same way.
No key: build_request() makes a ready request to paste into a free AI website, and the answer is pasted back.
No window code here."""
import json, os, urllib.request, urllib.error

import engine, prefs, ai

PROVIDERS = {
    "gemini": {"name": "Google Gemini (free key from a Google account)", "model": "gemini-2.5-flash",
               "key_page": "https://aistudio.google.com/apikey", "site": "https://gemini.google.com/app"},
    "openai": {"name": "OpenAI ChatGPT (your own key)", "model": "gpt-4.1-mini",
               "key_page": "https://platform.openai.com/api-keys", "site": "https://chatgpt.com/"},
    "claude": {"name": "Anthropic Claude (your own key)", "model": "claude-opus-5-5",
               "key_page": "https://console.anthropic.com/settings/keys", "site": "https://claude.ai/new"},
}
FREE_SITE = PROVIDERS["gemini"]["site"]


def _file():
    return os.path.join(engine.user_dir(), "online.json")


def load():
    c = {"provider": "gemini", "key": "", "model": ""}
    try:
        with open(_file(), encoding="utf-8") as f:
            c.update({k: v for k, v in json.load(f).items() if k in c})
    except Exception:
        pass
    if c["provider"] not in PROVIDERS:
        c["provider"] = "gemini"
    return c


def save(provider, key, model=""):
    p = _file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"provider": provider if provider in PROVIDERS else "gemini", "key": (key or "").strip(),
                   "model": (model or "").strip()}, f)
    os.replace(tmp, p)


def has_key():
    return bool(load()["key"]) or bool(os.environ.get("HAFUTZA_ONLINE_URL"))


def _fonts():
    """The font names, without touching Qt unless a window program is running (Qt fonts need one)."""
    if prefs._fonts is not None:
        return prefs._fonts
    try:
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.instance():
            return prefs.load_fonts()
    except Exception:
        pass
    return []


def spec():
    return ai.SPEC_FULL.replace("{FONTS}", ", ".join(_fonts()) or "any of the program's fonts (Settings shows them)")


def build_request(request):
    """The whole message for the copy-and-paste road (a free AI website)."""
    return spec() + "\n\nThe user's request:\n" + request.strip() + "\n\nAnswer with the JSON only."


def _post(url, body, headers, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers=dict({"Content-Type": "application/json"}, **headers))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8", "replace"))
            msg = (msg.get("error") or {}).get("message") if isinstance(msg.get("error"), dict) else msg.get("error") or msg
        except Exception:
            msg = ""
        if e.code in (401, 403):
            raise RuntimeError("the online AI did not take your key (%s). Check it in Settings." % e.code)
        if e.code == 429:
            raise RuntimeError("the online AI says too many requests or no credit left on this key; try later.")
        raise RuntimeError("the online AI answered with an error %s %s" % (e.code, str(msg)[:200]))
    except urllib.error.URLError:
        raise RuntimeError("no internet: asking a different AI needs internet.")


def ask(request):
    """-> the online AI's answer text (raw). Raises RuntimeError with a plain reason."""
    c = load()
    prov, key = c["provider"], c["key"]
    model = c["model"] or PROVIDERS[prov]["model"]
    system, user = spec(), "The user's request:\n" + request.strip()
    mock = os.environ.get("HAFUTZA_ONLINE_URL")
    if mock:                                          # tests: a local stand-in that answers like the real ones
        d = _post(mock, {"provider": prov, "model": model, "system": system, "request": request}, {}, 30)
        return d.get("text", "")
    if not key:
        raise RuntimeError("no key set for the online AI (Settings).")
    if prov == "gemini":
        d = _post("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model,
                  {"systemInstruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": user}]}],
                   "generationConfig": {"responseMimeType": "application/json"}},
                  {"x-goog-api-key": key})
        try:
            return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        except Exception:
            raise RuntimeError("the online AI gave no answer (it may have refused).")
    if prov == "openai":
        d = _post("https://api.openai.com/v1/chat/completions",
                  {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "response_format": {"type": "json_object"}},
                  {"Authorization": "Bearer " + key})
        try:
            return d["choices"][0]["message"]["content"] or ""
        except Exception:
            raise RuntimeError("the online AI gave no answer.")
    d = _post("https://api.anthropic.com/v1/messages",
              {"model": model, "max_tokens": 4000, "system": system, "messages": [{"role": "user", "content": user}],
               "output_config": {"effort": "low"}},
              {"x-api-key": key, "anthropic-version": "2023-06-01"})
    if d.get("stop_reason") == "refusal":
        raise RuntimeError("the online AI refused this request.")
    return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
