"""python tools/make_manifest.py FILE VERSION URL OUT.json [NOTES]  - write update.json for the Update button.
With no NOTES, the notes are what app/whatsnew.py says that version added."""
import hashlib, json, os, sys
f, v, url, out = sys.argv[1:5]
notes = sys.argv[5] if len(sys.argv) > 5 else ""
if not notes:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
    import whatsnew
    notes = whatsnew.text(v)
h = hashlib.sha256()
with open(f, "rb") as fh:
    for b in iter(lambda: fh.read(8 << 20), b""):
        h.update(b)
m = {"version": v, "url": url, "sha256": h.hexdigest(), "size": os.path.getsize(f), "notes": notes}
json.dump(m, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(m, indent=1, ensure_ascii=False).encode("ascii", "backslashreplace").decode())
