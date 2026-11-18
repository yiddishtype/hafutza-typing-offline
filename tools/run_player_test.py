"""Run the installed program's video player test (play, pause, skip 5/10/15, click a line, fix with the keyboard,
   learn), with a time limit; print its report.
   python tools/run_player_test.py EXE VIDEO OUTDIR"""
import json, os, subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
exe, video, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
t = time.time()
try:
    code = subprocess.run([exe, "--player-test", video, "--out", out], timeout=400).returncode
except subprocess.TimeoutExpired:
    code = "hung"
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(os.path.join(out, "hang-screen.png"))
    except Exception as e:
        print("screen picture failed", e)
    subprocess.run(["taskkill", "/IM", "HafutzaTyping.exe", "/F"], capture_output=True)
print("exit code", code, "after %.0f s" % (time.time() - t))
rp = os.path.join(out, "report.json")
if os.path.exists(rp):
    print(open(rp, encoding="utf-8").read())
log = os.path.join(os.environ.get("LOCALAPPDATA", ""), "HafutzaTyping", "log.txt")
if os.path.exists(log):
    print("----- program log (end)"); print(open(log, encoding="utf-8", errors="replace").read()[-2500:])
sys.exit(0 if code == 0 else 1)
