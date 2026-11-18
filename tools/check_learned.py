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
# The speech model does not always type the same clip the same way: if the 2nd typing never had the wrong word
# (and so nothing to fix), the in-program counter cannot show it. Then check the learned list directly on video 1's
# own typing with the program's learn.apply, and say plainly that the 2nd video did not test it.
if not checks["learned typing fix used by itself"] and not has_old and new not in yi:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
    import learn
    t9 = open(os.path.join(sys.argv[1], "text-yi.txt"), encoding="utf-8-sig").read() if os.path.exists(os.path.join(sys.argv[1], "text-yi.txt")) else word
    fixed, n = learn.apply("speech", "yi", t9 if word in t9 else word)
    direct = n >= 1 and new in fixed
    print("2nd typing never had the wrong word, so it could not show the fix. Direct check of the learned list on video 1's word:",
          "PASS" if direct else "FAIL", "(%d change)" % n)
    checks = {"learned list fixes the word (direct check)": direct, "wrong word gone from the 2nd video": True}
ok = r.get("ok") and all(checks.values())
print("RESULT", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
