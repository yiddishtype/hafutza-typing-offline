"""Run the installed program's self-test and print what it reported.
   python tools/run_selftest.py EXE FILE SPOKEN TARGETS OUTDIR [--download] [--timeout MIN]"""
import json, os, subprocess, sys, time
exe, f, spoken, targets, out = sys.argv[1:6]
rest = sys.argv[6:]
timeout = 60 * float(rest[rest.index("--timeout") + 1]) if "--timeout" in rest else 3600
args = [exe, "--selftest", f, "--spoken", spoken, "--targets", targets, "--out", out]
if "--download" in rest:
    args.append("--download")
t = time.time()
try:
    code = subprocess.run(args, timeout=timeout).returncode
except subprocess.TimeoutExpired:
    code = "timeout"
took = time.time() - t
print("exit code", code, "after %.0f s" % took)
rp = os.path.join(out, "report.json")
if os.path.exists(rp):
    r = json.load(open(rp, encoding="utf-8"))
    r["wall_seconds"] = took
    json.dump(r, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({k: v for k, v in r.items() if k != "texts"}, ensure_ascii=False, indent=1))
    for k, v in r.get("texts", {}).items():
        print("=====", k); print(v[:1500])
log = os.path.join(os.environ.get("LOCALAPPDATA", ""), "HafutzaTyping", "log.txt")
if os.path.exists(log):
    print("----- log tail"); print("".join(open(log, encoding="utf-8").readlines()[-30:]))
sys.exit(0 if code == 0 else 1)
