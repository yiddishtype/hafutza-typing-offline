"""How close two typed texts are: share of letters that differ (edit distance over letters, spaces kept as one).
   python tools/compare.py REFERENCE.txt OTHER.txt"""
import re, sys
sys.stdout.reconfigure(encoding="utf-8")
norm = lambda t: re.sub(r"\s+", " ", re.sub(r"[^\w\s']", "", t.replace("\ufeff", ""))).strip()
a, b = (norm(open(p, encoding="utf-8").read()) for p in sys.argv[1:3])
prev = list(range(len(b) + 1))
for i, ca in enumerate(a, 1):
    cur = [i]
    for j, cb in enumerate(b, 1):
        cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
    prev = cur
print("letters: reference %d, this %d; differing %.1f%%" % (len(a), len(b), 100.0 * prev[-1] / max(1, len(a))))
