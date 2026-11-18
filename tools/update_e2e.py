"""End-to-end test of the Update button on the build machine (Windows).
   python tools/update_e2e.py EXE MANIFEST EXPECT OUTDIR [--serve DIR]
     MANIFEST  a URL of update.json, or "real" for the published one
     EXPECT    "newest" | "error" | a version number the program must have afterwards (installed by the Update button)
   Checks: what the program said; for an install: the program closed, the installer put the new version in, the program
   opened again by itself, the downloaded parts (models) and the typed texts in Documents are untouched."""
import functools, glob, http.server, json, os, subprocess, sys, threading, time
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
exe, manifest, expect, out = sys.argv[1:5]
rest = sys.argv[5:]
os.makedirs(out, exist_ok=True)
app = os.path.dirname(exe)
lad = os.path.join(os.environ["LOCALAPPDATA"], "HafutzaTyping")
docs = os.path.join(os.path.expanduser("~"), "Documents", "Hafutza Typing")
if "--serve" in rest:
    d = rest[rest.index("--serve") + 1]
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8000), functools.partial(http.server.SimpleHTTPRequestHandler, directory=d))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("serving", d, "on 8000")


def models():
    return {os.path.relpath(p, app): os.path.getsize(p) for p in glob.glob(os.path.join(app, "models", "*", "model.bin"))}


def texts():
    return sorted(os.listdir(docs)) if os.path.isdir(docs) else []


def ver():
    try:
        return open(os.path.join(app, "version.txt"), encoding="utf-8").read().strip()
    except OSError:
        return None


def reg_version():
    import winreg
    k = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{8E3B6F7A-2C1D-4B8E-9F21-6A5D3C7E1B42}_is1"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, k) as h:
            return winreg.QueryValueEx(h, "DisplayVersion")[0]
    except OSError as e:
        return "not found %r" % e


def running():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq HafutzaTyping.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if "HafutzaTyping.exe" in l]


def logtail(n=4000):
    p = os.path.join(lad, "log.txt")
    return open(p, encoding="utf-8", errors="replace").read()[-n:] if os.path.exists(p) else ""


before = {"version": ver(), "reg": reg_version(), "models": models(), "texts": texts()}
print("before", json.dumps(before, indent=1))
args = [exe, "--update-test", manifest, "--out", out] if manifest != "real" else [exe, "--update-test", "", "--out", out]
t = time.time()
p = subprocess.run(args, timeout=1200)
rep = json.load(open(os.path.join(out, "report.json"), encoding="utf-8"))
print("program said:", rep, "exit", p.returncode, "after %.0f s" % (time.time() - t))
ok = True
if expect == "newest":
    ok = rep["result"] == "newest"
elif expect == "error":
    ok = rep["result"].startswith("error") and ver() == before["version"]
else:
    ok = rep["result"] == "installing " + expect
    t2 = time.time()
    while time.time() - t2 < 300 and ver() != expect:
        time.sleep(2)
    print("version.txt now %s after %.0f s" % (ver(), time.time() - t2))
    t3 = time.time()
    while time.time() - t3 < 120 and not running():
        time.sleep(2)
    print("program running again:", running())
    time.sleep(15)                      # let it draw its window
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(os.path.join(out, "after-update-screen.png"))
    except Exception as e:
        print("screen picture failed", e)
    after = {"version": ver(), "reg": reg_version(), "models": models(), "texts": texts()}
    print("after", json.dumps(after, indent=1))
    il = os.path.join(lad, "update-install-log.txt")
    if os.path.exists(il):
        print("----- installer log (end)"); print(open(il, encoding="utf-8", errors="replace").read()[-2500:])
    lt = logtail()
    reopened = ("start %s," % expect) in lt
    print("program log shows 'start %s': %s" % (expect, reopened))
    checks = {"new version in": after["version"] == expect, "uninstall entry version": after["reg"] == expect,
              "reopened by itself": bool(running()) and reopened, "models kept": after["models"] == before["models"],
              "texts kept": set(before["texts"]) <= set(after["texts"])}
    print("checks", checks)
    ok = ok and all(checks.values())
    subprocess.run(["taskkill", "/IM", "HafutzaTyping.exe", "/F"], capture_output=True)
    time.sleep(3)
print("----- program log (end)"); print(logtail(1500))
print("RESULT", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
