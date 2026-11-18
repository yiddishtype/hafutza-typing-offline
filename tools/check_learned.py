"""After the player test fixed a word in video 1, type a 2nd video and check the fix was used by itself.
   python tools/check_learned.py PLAYER_REPORT_DIR SECOND_SELFTEST_DIR"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
p = json.load(open(os.path.join(sys.argv[1], "report.json"), encoding="utf-8"))
r = json.load(open(os.path.join(sys.argv[2], "report.json"), encoding="utf-8"))
word, new = p["fix"]["word"], p["fix"]["new_word"]
yi = open(os.path.join(sys.argv[2], "text-yi.txt"), encoding="utf-8-sig").read()
en_path = os.path.join(sys.argv[2], "text-en.txt")
en = open(en_path, encoding="utf-8-sig").read() if os.path.exists(en_path) else ""
t = r.get("times", {})
import re
marks = "֑-ׇיִ-ﭏ"
has_old = bool(re.search(r"(?<![\w%s])%s(?![\w%s])" % (marks, re.escape(word), marks), yi))
checks = {
    "learned typing fix used by itself": (t.get("learned_fixes_typing") or 0) >= 1,
    "fixed word in the 2nd video's typing": new in yi,
    "wrong word gone from the 2nd video": not has_old,
}
soft = {"translation fixes used": t.get("learned_fixes_en"),
        "translation fix word in English": p["fix_tr"]["new_word"] in en}
print("fixed in video 1:", word, "->", new)
print("checks", json.dumps(checks, ensure_ascii=False))
print("not blocking", json.dumps(soft, ensure_ascii=False))
print("2nd video Yiddish (start):", yi[:600])
ok = r.get("ok") and all(checks.values())
print("RESULT", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
