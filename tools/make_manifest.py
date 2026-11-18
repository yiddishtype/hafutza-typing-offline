"""python tools/make_manifest.py FILE VERSION URL OUT.json [NOTES]  - write update.json for the Update button"""
import hashlib, json, os, sys
f, v, url, out = sys.argv[1:5]
notes = sys.argv[5] if len(sys.argv) > 5 else ""
h = hashlib.sha256()
with open(f, "rb") as fh:
    for b in iter(lambda: fh.read(8 << 20), b""):
        h.update(b)
m = {"version": v, "url": url, "sha256": h.hexdigest(), "size": os.path.getsize(f), "notes": notes}
json.dump(m, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(m, indent=1))
