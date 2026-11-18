"""The Update window's "Request an update" box: send what the user wrote to us (no window code here).
No internet -> the request is kept in pending-requests.json and sent by itself later (flush())."""
import json, os, time, urllib.request

import engine
from engine import log

URL = "https://yiddishtype--hafutza-typing.modal.run/api/offline/request"
KEY = "1m-KbO4eo5-zlHfeuncNdRGxMny2KoZq"


def _file():
    return os.path.join(engine.user_dir(), "pending-requests.json")


def pending():
    try:
        with open(_file(), encoding="utf-8") as f:
            return [r for r in json.load(f) if r.get("text")]
    except Exception:
        return []


def _save(items):
    p = _file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def _post(r, version, timeout=20):
    url = os.environ.get("HAFUTZA_REQUEST_URL") or URL
    body = {"text": r["text"], "version": version, "written": r.get("written", "")}
    if os.environ.get("HAFUTZA_REQUEST_TEST"):
        body["test"] = True
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "X-Hafutza-Key": KEY,
                                          "User-Agent": "HafutzaTyping/" + version})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    if not out.get("ok"):
        raise RuntimeError(str(out)[:200])
    return out.get("id", "")


def send(text, version):
    """-> ("sent", id) or ("kept", reason). Never loses the text: on any failure it is kept for later."""
    r = {"text": text.strip(), "written": time.strftime("%Y-%m-%d %H:%M")}
    try:
        rid = _post(r, version)
        log("request sent: %s" % rid)
        flush(version)
        return "sent", rid
    except Exception as e:
        log("request kept for later: %r" % e)
        _save(pending() + [r])
        return "kept", "%s" % (str(e)[:150] or type(e).__name__)


def flush(version):
    """Send the kept requests. -> how many went."""
    items = pending()
    if not items:
        return 0
    left, sent = [], 0
    for r in items:
        try:
            _post(r, version)
            sent += 1
        except Exception as e:
            log("kept request still not sent: %r" % e)
            left.append(r)
    _save(left)
    log("kept requests sent: %d, still kept: %d" % (sent, len(left)))
    return sent
