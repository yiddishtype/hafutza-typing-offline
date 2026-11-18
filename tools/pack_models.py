"""Build-time helper: fetch the speech and translation models from Hugging Face and pack the speech ones to int8.

Writes  out/<key>/  (all small files + model.bin) for each model and  out/models.json  (sizes + sha256 of every model.bin).
The int8 packing (from ~/agent/skills/transcribe.py, pack_int8) halves the 1.6 GB float16 Whisper weights to ~0.8 GB with
per-row scales, the same thing CTranslate2 does itself when a float16 model is loaded with compute_type="int8".

    python tools/pack_models.py out
"""
import hashlib, json, os, struct, sys, urllib.request

MODELS = {
    "yi": ("ivrit-ai/yi-whisper-large-v3-turbo-ct2", True),
    "he": ("ivrit-ai/whisper-large-v3-turbo-ct2", True),
    "multi": ("deepdml/faster-whisper-large-v3-turbo-ct2", True),
    "nllb": ("JustFrederik/nllb-200-distilled-1.3B-ct2-int8", False),
}
SMALL = {
    True: ["config.json", "preprocessor_config.json", "tokenizer.json", "vocabulary.json"],
    False: ["config.json", "sentencepiece.bpe.model", "shared_vocabulary.txt"],
}


class Stream:
    def __init__(self, f):
        self.f, self.n, self.h = f, 0, hashlib.sha256()

    def read(self, k):
        out = bytearray()
        while len(out) < k:
            b = self.f.read(min(k - len(out), 8 << 20))
            if not b:
                raise IOError("download ended early (%d bytes in)" % (self.n + len(out)))
            out += b
        self.n += k
        return bytes(out)


def pack_int8(src, dst):
    import numpy as np
    DT = ["float32", "int8", "int16", "int32", "float16", "bfloat16"]
    rd = lambda fmt: struct.unpack(fmt, src.read(struct.calcsize(fmt)))

    def rstr():
        (l,) = rd("H")
        return src.read(l)[:-1].decode()

    out = open(dst, "wb")

    def wstr(s):
        b = s.encode()
        out.write(struct.pack("H", len(b) + 1)); out.write(b); out.write(b"\0")

    def head(n, shape, dt, nb):
        wstr(n); out.write(struct.pack("B", len(shape)))
        for d in shape:
            out.write(struct.pack("I", d))
        out.write(struct.pack("B", dt)); out.write(struct.pack("I", nb))

    ver, = rd("I"); name = rstr(); rev, = rd("I"); nvar, = rd("I")
    out.write(struct.pack("I", ver)); wstr(name); out.write(struct.pack("I", rev))
    at = out.tell(); out.write(struct.pack("I", 0)); count = 0
    for _ in range(nvar):
        n = rstr(); (rank,) = rd("B"); shape = rd("I" * rank) if rank else (); (dt,) = rd("B"); (nb,) = rd("I")
        if n.split("/")[-1] == "weight" and len(shape) >= 2 and DT[dt] in ("float16", "float32"):
            it = np.dtype(DT[dt]); row = nb // shape[0]
            scale = np.empty(shape[0], np.float32)
            head(n, shape, 1, nb // it.itemsize)
            for r in range(0, shape[0], 256):
                k = min(256, shape[0] - r)
                a = np.frombuffer(src.read(k * row), dtype=it).reshape(k, -1).astype(np.float32)
                amax = np.abs(a).max(axis=1); amax[amax == 0] = 127.0
                sc = (127.0 / amax).astype(np.float32); scale[r:r + k] = sc
                out.write(np.rint(a * sc[:, None]).astype(np.int8).tobytes())
            head(n + "_scale", (shape[0],), 0, scale.nbytes); out.write(scale.tobytes()); count += 2
        else:
            head(n, shape, dt, nb); left = nb
            while left:
                b = src.read(min(left, 8 << 20)); out.write(b); left -= len(b)
            count += 1
    na, = rd("I"); out.write(struct.pack("I", na))
    for _ in range(na):
        wstr(rstr()); wstr(rstr())
    out.seek(at); out.write(struct.pack("I", count)); out.close()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(outdir):
    info = {}
    for key, (repo, pack) in MODELS.items():
        d = os.path.join(outdir, key)
        os.makedirs(d, exist_ok=True)
        url = lambda f: "https://huggingface.co/%s/resolve/main/%s" % (repo, f)
        for f in SMALL[pack]:
            urllib.request.urlretrieve(url(f), os.path.join(d, f))
        dst = os.path.join(d, "model.bin")
        print("fetching", repo, flush=True)
        r = urllib.request.urlopen(url("model.bin"), timeout=300)
        if pack:
            src = Stream(r)
            pack_int8(src, dst + ".tmp")
            if r.read(1):
                raise IOError("download longer than the model")
        else:
            with open(dst + ".tmp", "wb") as f:
                for b in iter(lambda: r.read(8 << 20), b""):
                    f.write(b)
        os.replace(dst + ".tmp", dst)
        info[key] = {"repo": repo, "size": os.path.getsize(dst), "sha256": sha256(dst)}
        print(key, info[key], flush=True)
    with open(os.path.join(outdir, "models.json"), "w") as f:
        json.dump(info, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
