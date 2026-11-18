"""Run the installed program's self-test, showing its log as it goes; on a hang take a picture of the screen and stop it.
   python tools/run_selftest.py EXE FILE SPOKEN TARGETS OUTDIR [--download] [--timeout MIN] [--quiet MIN]"""
import json, os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
exe, f, spoken, targets, out = sys.argv[1:6]
rest = sys.argv[6:]
opt = lambda k, d: float(rest[rest.index(k) + 1]) if k in rest else d
timeout, quiet = 60 * opt("--timeout", 60), 60 * opt("--quiet", 6)
os.makedirs(out, exist_ok=True)
args = [exe, "--selftest", f, "--spoken", spoken, "--targets", targets, "--out", out]
if "--download" in rest:
    args.append("--download")
log = os.path.join(os.environ.get("LOCALAPPDATA", ""), "HafutzaTyping", "log.txt")
seen = os.path.getsize(log) if os.path.exists(log) else 0
t = last = time.time()
p = subprocess.Popen(args)
code = None
while True:
    try:
        code = p.wait(timeout=5)
        break
    except subprocess.TimeoutExpired:
        pass
    if os.path.exists(log) and os.path.getsize(log) > seen:
        with open(log, "rb") as fh:
            fh.seek(seen); new = fh.read(); seen += len(new)
        print(new.decode("utf-8", "replace"), end="")
        last = time.time()
    if time.time() - last > quiet or time.time() - t > timeout:
        print("!! no progress for %.0f s (or over time): screen picture saved, stopping it" % (time.time() - last))
        try:
            from PIL import ImageGrab
            ImageGrab.grab().save(os.path.join(out, "hang-screen.png"))
        except Exception as e:
            print("screen picture failed", e)
        p.kill(); code = "hung"
        break
took = time.time() - t
if os.path.exists(log) and os.path.getsize(log) > seen:
    with open(log, "rb") as fh:
        fh.seek(seen); print(fh.read().decode("utf-8", "replace"), end="")
print("exit code", code, "after %.0f s" % took)
rp = os.path.join(out, "report.json")
if os.path.exists(rp):
    r = json.load(open(rp, encoding="utf-8"))
    r["wall_seconds"] = took
    json.dump(r, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in r.items() if k != "texts"}, ensure_ascii=False, indent=1))
    for k, v in r.get("texts", {}).items():
        print("=====", k); print(v[:1500])
cr = os.path.join(os.environ.get("LOCALAPPDATA", ""), "HafutzaTyping", "crash.txt")
if os.path.exists(cr):
    print("----- crash.txt"); print(open(cr, encoding="utf-8").read())
sys.exit(0 if code == 0 else 1)
