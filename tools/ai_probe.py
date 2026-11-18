"""Feasibility probe (not part of the app): can a small local model follow editing
instructions on Yiddish text on a plain Windows PC (CPU only)?
Usage: python ai_probe.py <llama-server.exe> <model.gguf> <out.json> [whisper_dir clip.mp3]"""
import json, os, re, subprocess, sys, threading, time, urllib.request

SERVER, MODEL, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
WDIR = sys.argv[4] if len(sys.argv) > 4 else None
CLIP = sys.argv[5] if len(sys.argv) > 5 else None
NCPU = os.cpu_count() or 4

L7 = "איך לייד פון ענקזייעס ווי, פאביעס ווי נאויסי די, אייביג האב איך מורא. איך בין אזוי נערוועז, א מענדל קעב, איך בין א לוזער לכאורה."
L9 = "נאר עמונה העלפט דעם איד, ווען ער פילט זיך שוואך און מיר, עמונה איז מיין מעדיצין איך האב קיין קשיות נישט, איך האב קיין צייכן נישט, עמונה זאגט מיר וואס פירט איך? א איד דארף איידער ניסטער, דער יארף איידער ניסטער,"
L2 = "איכל נגינה - זעקס - מיט דוד'ס, אנווייזונגען, אינפארמאציע און זיך צו פארבינדן מיט די מערכת, און פאר די לייבה קאפ - דריקסט ניין. ווער באשעפערט מיר אויף? איך בין נישט אליין."
L8 = "דער באשעפער רעט מיר אויס"
EN1 = "Host: A good year, Rabbi Menachem! How are you? What's going on? The public is waiting to hear news from town."

SYS_REWRITE = ("You are the editor inside a Yiddish typing program. The user gives you a text (Yiddish in Hebrew letters, "
               "or its English translation) and an instruction, in English or Yiddish. Carry out exactly the instruction. "
               "Answer with ONLY the full corrected text, nothing before or after it. Do not change anything the instruction does not ask for.")
SYS_JSON = ("You are the editor inside a Yiddish typing program. The user gives you a text (Yiddish in Hebrew letters, or its English "
            "translation) and an instruction, in English or Yiddish. Answer with ONLY a JSON list of the changes to make, like "
            '[{"find": "exact words now in the text", "replace": "new words"}]. "find" must be copied exactly from the text. '
            "Make only the changes the instruction asks for.")

CASES = [
    # name, mode, text, instruction, check(out) -> bool or None (None = judge by eye)
    ("A replace (English order)", "rewrite", L7, "Change 'מענדל קעב' to 'מענטל קעיס'.",
     lambda o: "מענטל קעיס" in o and "מענדל קעב" not in o and "לוזער" in o),
    ("A replace, JSON", "json", L7, "Change 'מענדל קעב' to 'מענטל קעיס'.",
     lambda o: "מענטל קעיס" in o and "מענדל קעב" not in o and "לוזער" in o),
    ("B replace everywhere (Yiddish order)", "rewrite", L9, "טויש אויס 'עמונה' אויף 'אמונה' אומעטום",
     lambda o: o.count("עמונה") == 0 and o.count("אמונה") == 3 and "מעדיצין" in o),
    ("B Yiddish order, JSON", "json", L9, "טויש אויס 'עמונה' אויף 'אמונה' אומעטום",
     lambda o: o.count("עמונה") == 0 and o.count("אמונה") == 3 and "מעדיצין" in o),
    ("C loose order: section name", "rewrite", L2, "The section is called היכל נגינה, fix it.",
     lambda o: "היכל נגינה" in o and "איכל נגינה" not in o and "אינפארמאציע" in o),
    ("D fix spelling by itself", "rewrite", L9, "Fix the spelling mistakes in this line.",
     lambda o: o.count("עמונה") == 0 and "אמונה" in o),
    ("D Yiddish: fix spelling", "rewrite", L9, "פארריכט די טעותים אין די שורה",
     lambda o: o.count("עמונה") == 0 and "אמונה" in o),
    ("E translate short", "rewrite", L8, "Translate this line to English.",
     lambda o: bool(re.search(r"sav|rescu|deliver|redeem", o, re.I))),
    ("F fix the English translation", "rewrite", EN1, "Write 'Reb' not 'Rabbi'.",
     lambda o: "Reb Menachem" in o and "Rabbi" not in o and "news from town" in o),
    ("G translate longer", "rewrite", L7, "Translate this line to English.", None),
    ("H Yiddish: make it read better", "rewrite", L7, "מאך די שורה שענער און ריכטיגער", None),
]


def post(path, body, timeout=900):
    req = urllib.request.Request("http://127.0.0.1:8080" + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def ask(mode, text, instr):
    sysm = SYS_JSON if mode == "json" else SYS_REWRITE
    t = time.time()
    r = post("/v1/chat/completions", {
        "messages": [{"role": "system", "content": sysm},
                     {"role": "user", "content": "TEXT:\n" + text + "\n\nINSTRUCTION: " + instr}],
        "temperature": 0, "max_tokens": 700,
        "chat_template_kwargs": {"enable_thinking": False}})
    out = r["choices"][0]["message"]["content"].strip()
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()
    shown = out
    if mode == "json":
        try:
            m = re.search(r"\[.*\]", out, re.S)
            ch = json.loads(m.group(0))
            res = text
            for c in ch:
                if c.get("find") and c["find"] in res:
                    res = res.replace(c["find"], c.get("replace", ""))
            out = res
        except Exception as e:
            out = "(bad json: %s)" % e
    return out, shown, time.time() - t, r.get("timings", {})


def peak_mem(pid):
    try:
        import psutil
        p = psutil.Process(pid)
        mi = p.memory_info()
        return round(getattr(mi, "peak_wset", mi.rss) / 1e9, 2), round(mi.rss / 1e9, 2)
    except Exception as e:
        return str(e), None


def start_server(threads):
    log = open(OUT + ".server%d.log" % threads, "w", encoding="utf-8")
    p = subprocess.Popen([SERVER, "-m", MODEL, "-c", "4096", "-t", str(threads), "--jinja", "--port", "8080"], stdout=log, stderr=subprocess.STDOUT)
    t0 = time.time()
    while True:
        try:
            urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=5).read()
            break
        except Exception:
            if p.poll() is not None:
                raise SystemExit("server died, see log")
            if time.time() - t0 > 900:
                raise SystemExit("server never came up")
            time.sleep(2)
    return p, time.time() - t0


res = {"model": os.path.basename(MODEL), "size_gb": round(os.path.getsize(MODEL) / 1e9, 2), "cpus": NCPU}
srv, load_s = start_server(NCPU)
res["load_seconds"] = round(load_s, 1)
res["cases"] = []
for name, mode, text, instr, chk in CASES:
    try:
        out, shown, sec, tim = ask(mode, text, instr)
    except Exception as e:
        out, shown, sec, tim = "(error %s)" % e, "", 0, {}
    ok = chk(out) if chk else None
    res["cases"].append({"name": name, "pass": ok, "seconds": round(sec, 1), "answer": out, "raw": shown,
                         "gen_tok_per_s": round(tim.get("predicted_per_second", 0), 1),
                         "prompt_tok_per_s": round(tim.get("prompt_per_second", 0), 1)})
    print(name, ok, round(sec, 1), "s", flush=True)
res["memory_gb_peak_rss"] = peak_mem(srv.pid)
json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# alongside the speech model (as when the program is typing a video)
try:
  if WDIR and CLIP:
      from faster_whisper import WhisperModel, decode_audio
      a = decode_audio(CLIP)[:16000 * 60]

      def typing():
          m = WhisperModel(WDIR, device="cpu", compute_type="int8", cpu_threads=min(8, NCPU), local_files_only=True)
          t = time.time()
          segs, _ = m.transcribe(a, language="yi", beam_size=5)
          list(segs)
          return time.time() - t

      res["typing_60s_alone_seconds"] = round(typing(), 1)
      box = {}
      th = threading.Thread(target=lambda: box.update(t=typing()))
      th.start()
      time.sleep(20)  # whisper is loaded and typing
      both = []
      for name, mode, text, instr, chk in CASES[:3]:
          out, shown, sec, tim = ask(mode, text, instr)
          both.append({"name": name, "pass": chk(out), "seconds": round(sec, 1)})
      th.join()
      res["typing_60s_with_ai_seconds"] = round(box.get("t", 0), 1)
      res["ai_while_typing"] = both
      import psutil
      res["machine_ram_gb"] = round(psutil.virtual_memory().total / 1e9, 1)
except Exception as e:
    res["typing_error"] = repr(e)
srv.kill()
json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False, indent=1))
