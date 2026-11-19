"""Typing speed bench (CI): type FILE with one set of faster-whisper settings, write time + text.
   python tools/bench_typing.py MODELDIR FILE OUT.json CONFIG_JSON"""
import json, os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import engine
from faster_whisper import WhisperModel, BatchedInferencePipeline

mdir, f, out, cfg = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
tmp = tempfile.mkdtemp()
t0 = time.time()
x = engine.read_sound(f, tmp, lambda p: None)
RATE = engine.RATE
t_read = time.time() - t0
t0 = time.time()
model = WhisperModel(mdir, device="cpu", compute_type=cfg.get("ct", "int8"), cpu_threads=cfg.get("threads", 4),
                     num_workers=1)
t_load = time.time() - t0
beam = cfg.get("beam", 5)
kw = {}
if "cond" in cfg:
    kw["condition_on_previous_text"] = cfg["cond"]
lines = []
t0 = time.time()
if cfg.get("batch"):
    pipe = BatchedInferencePipeline(model)
    for s0, s1 in engine.pieces(x):
        a = np.asarray(x[s0:s1], dtype=np.float32) / 32768.0
        sub = [(p0, p1) for p0, p1 in engine.pieces(x[s0:s1], window=cfg.get("chunk", 25), seam=5)]
        clips = [{"start": p0 / RATE, "end": p1 / RATE} for p0, p1 in sub]
        segs, info = pipe.transcribe(a, language="yi", beam_size=beam, batch_size=cfg["batch"],
                                     vad_filter=False, clip_timestamps=clips, **kw)
        for s in segs:
            t = " ".join(s.text.split())
            if t:
                lines.append(t)
else:
    for s0, s1 in engine.pieces(x):
        a = np.asarray(x[s0:s1], dtype=np.float32) / 32768.0
        segs, info = model.transcribe(a, language="yi", beam_size=beam, **kw)
        for s in segs:
            t = " ".join(s.text.split())
            if t:
                lines.append(t)
t_type = time.time() - t0
rep = {"cfg": cfg, "file": os.path.basename(f), "sound_seconds": len(x) / RATE, "read": t_read, "load": t_load,
       "typing": t_type, "x_realtime": (len(x) / RATE) / t_type, "lines": len(lines)}
print(json.dumps(rep))
json.dump(rep, open(out, "w"))
open(out[:-5] + ".txt", "w", encoding="utf-8").write("\n".join(lines))
