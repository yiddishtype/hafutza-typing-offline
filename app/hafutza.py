"""Hafutza Typing (offline) - the window.

Pick a video or audio file, the language spoken in it, the languages to type it out in; press Start.
Everything runs on this computer; nothing is sent anywhere. (The only internet use: the one-time download of the parts
for translation and Hebrew / English / Spanish / French speech, if they are not here yet.)

Self-test (used by the build machine):
  HafutzaTyping.exe --selftest FILE [--more FILE ...] [--drop] --spoken yi --targets yi,en,he,es,fr --out DIR [--download]
  HafutzaTyping.exe --update-test MANIFEST_URL --out DIR       (presses Update by itself; installs if newer)
  HafutzaTyping.exe --badge-test MANIFEST_URL --expect blue|plain --out DIR  (start look: Update button blue only if newer)
"""
import os, sys

if sys.stdout is None:          # a windowed .exe has no console: give libraries somewhere to write
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import argparse, json, tempfile, shutil, time, traceback


def _crash_file():
    d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "HafutzaTyping")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "crash.txt")


def _excepthook(t, v, tb):
    try:
        with open(_crash_file(), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "".join(traceback.format_exception(t, v, tb)) + "\n")
    except Exception:
        pass


sys.excepthook = _excepthook
try:
    from PySide6.QtCore import Qt, QThread, Signal, QTimer, QStandardPaths, QMimeData, QUrl, QPointF
    from PySide6.QtGui import QFont, QTextOption, QIcon, QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import (QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel,
                                   QPushButton, QRadioButton, QCheckBox, QButtonGroup, QProgressBar, QTabWidget,
                                   QPlainTextEdit, QFileDialog, QMessageBox, QGroupBox, QScrollArea, QDialog, QFrame,
                                   QComboBox, QLineEdit)

    import engine
    import updater
    import links
    import learn
    import project
    import whatsnew
    import requests_out
    import ai
    from engine import LANGS, NAME_YI, NAME_EN, log
except Exception:
    _excepthook(*sys.exc_info())
    raise

TITLE = "Hafutza Typing"
VERSION = updater.version()
RTL = ("yi", "he")
FILE_TYPES = ("Video and audio files (*.mp4 *.mov *.mkv *.avi *.wmv *.webm *.m4v *.3gp *.flv *.mpg *.mpeg *.ts *.mts "
              "*.mp3 *.m4a *.wav *.ogg *.oga *.opus *.flac *.aac *.wma *.amr *.aiff *.aif *.mka);;All files (*.*)")

STYLE = """
QWidget { font-size: 12pt; }
QGroupBox { font-weight: bold; border: 1px solid #c8ccd2; border-radius: 8px; margin-top: 14px; padding: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
QPushButton { padding: 8px 16px; border-radius: 6px; border: 1px solid #9aa3ad; background: #f4f6f8; }
QPushButton:hover { background: #e8ecf0; }
QPushButton:disabled { color: #9aa3ad; }
QPushButton#start { background: #1e7e34; color: white; font-size: 16pt; font-weight: bold; border: none; min-height: 56px; }
QPushButton#start:hover { background: #19692c; }
QPushButton#start:disabled { background: #9cc5a6; }
QPushButton#stop { background: #b02a37; color: white; font-size: 14pt; font-weight: bold; border: none; min-height: 56px; }
QPushButton#choose { font-size: 14pt; min-height: 56px; background: #e7f0fb; border: 1px solid #6d9bd1; }
QRadioButton, QCheckBox { font-size: 13pt; padding: 4px 10px 4px 0; spacing: 8px; }
QRadioButton::indicator, QCheckBox::indicator { width: 22px; height: 22px; }
QProgressBar { min-height: 26px; border: 1px solid #9aa3ad; border-radius: 6px; text-align: center; }
QProgressBar::chunk { background: #2f7bd0; border-radius: 5px; }
QPlainTextEdit { font-size: 14pt; }
QTabBar::tab { font-size: 13pt; padding: 8px 18px; }
QFrame#drop { border: 3px dashed #6d9bd1; border-radius: 12px; background: #f3f8fe; min-height: 130px; }
QFrame#drop[hot="true"] { border: 3px solid #1e7e34; background: #e3f6e8; }
QFrame#drop:disabled { border-color: #c8ccd2; background: #f6f7f8; }
QPushButton#update { font-size: 11pt; padding: 6px 12px; }
QPushButton#update[news="true"] { background: #2f7bd0; color: white; border: 2px solid #1d5ea8; font-weight: bold; }
QPushButton#update[news="true"]:hover { background: #2569b8; }
"""


def both(en, yi):
    """A label of an English line and a right-to-left Yiddish line."""
    return en + "\n" + yi


class RTLLabel(QLabel):
    def __init__(self, text, size=None, bold=False):
        super().__init__(text)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setWordWrap(True)
        if size or bold:
            f = self.font()
            if size:
                f.setPointSize(size)
            f.setBold(bold)
            self.setFont(f)


# ------------------------------------------------------------------ background work
class Job(QThread):
    status = Signal(str)
    progress = Signal(float)
    partial = Signal(str)
    result = Signal(str, str)
    done = Signal(bool, str)

    def __init__(self, path, spoken, targets, rules=None):
        super().__init__()
        self.path, self.spoken, self.targets = path, spoken, targets
        self.rules = rules if rules is not None else {}     # lang -> [(find, replace)] from the AI helper, while typing
        self.applied = {}       # lang -> how many of rules[lang] are already in self.texts[lang]
        self.emitted = {}       # lang -> how many were in the text when it was sent to the window
        self.made = None        # lang -> how many were in the saved timings file
        self._stop = False
        self.times = {}
        self.docs = docs_dir()
        self.segments, self.texts = [], {}

    def stop(self):
        self._stop = True

    def fix_ai(self, lang, lines):
        allr = list(self.rules.get(lang, []))
        rules = allr[self.applied.get(lang, 0):]
        self.applied[lang] = len(allr)
        if not rules:
            return lines
        out, n = [], 0
        for l in lines:
            l, k = ai.apply(l, rules)
            out.append(l); n += k
        self.times["ai_fixes_" + lang] = self.times.get("ai_fixes_" + lang, 0) + n
        return out

    def run(self):
        stop = lambda: self._stop
        tmp = tempfile.mkdtemp(prefix="hafutza-")
        engine.keep_awake(True)
        t0 = time.time()
        try:
            log("job start %r spoken=%s targets=%s" % (self.path, self.spoken, self.targets))
            self.status.emit(both("Step 1: reading the sound out of the file ...", "שריט 1: מען ליינט דעם קול פונעם פייל"))
            x = engine.read_sound(self.path, tmp, lambda f: self.progress.emit(f), stop)
            dur = len(x) / engine.RATE
            self.times["sound_seconds"] = dur
            self.times["read"] = time.time() - t0
            t1 = time.time()
            self.status.emit(both("Step 2: typing (%s of sound) ..." % hms(dur), "שריט 2: מען שרייבט אויף"))
            self.progress.emit(0.0)

            def prog(f, lines):
                self.progress.emit(f)
                el = time.time() - t1
                left = ""
                if f > 0.03 and el > 20:
                    left = "  -  about %s left" % hms(el / f * (1 - f))
                self.status.emit(both("Step 2: typing ... %s of %s done%s" % (hms(f * dur), hms(dur), left),
                                      "שריט 2: מען שרייבט אויף"))
                self.partial.emit("\n".join(lines))

            # His learned words are NOT given to the speech model as hint words: on the build machine that made the
            # real model write a mix of scripts and made the typing much worse. The learned list fixes the text after.
            hot = None
            self.times["hint_words"] = ""
            segs = []
            text = engine.transcribe(x, self.spoken, prog, stop, hotwords=hot, segments=segs)
            self.times["typing"] = time.time() - t1
            del x
            if not text:
                self.done.emit(False, both("No speech could be heard in this file.", "מען האט נישט געהערט קיין רעדן אין דעם פייל"))
                return
            lines = [t for _s, _e, t in segs]
            fixed = 0
            try:                    # his earlier fixes (learned words), done by themselves
                for i, l in enumerate(lines):
                    lines[i], n = learn.apply("speech", self.spoken, l)
                    fixed += n
            except Exception as e:
                log("learned fixes not done: %r" % e)
            self.times["learned_fixes_typing"] = fixed
            lines = self.fix_ai(self.spoken, lines)
            self.segments = [(s, e) for s, e, _t in segs]
            self.texts = {self.spoken: lines}
            text = "\n".join(lines)
            if self.spoken in self.targets:
                self.emitted[self.spoken] = self.applied.get(self.spoken, 0)
                self.result.emit(self.spoken, text)
            others = [t for t in self.targets if t != self.spoken]
            if others:
                self.status.emit(both("Step 3: getting the translator ready ...", "שריט 3: מען גרייט צו דעם איבערזעצער"))
                self.progress.emit(0.0)
                tr = engine.Translator()
                try:
                    for n, tgt in enumerate(others, 1):
                        t2 = time.time()
                        msg = both("Step 3: translating to %s (%d of %d) ..." % (NAME_EN[tgt], n, len(others)),
                                   "שריט 3: מען זעצט איבער אויף %s" % NAME_YI[tgt])
                        self.status.emit(msg)
                        out = tr.translate(text, self.spoken, tgt, lambda f: self.progress.emit(f), stop)
                        tl = out.split("\n")
                        if len(tl) != len(lines):
                            log("translation lines %d != %d" % (len(tl), len(lines)))
                            tl = (tl + [""] * len(lines))[:len(lines)]
                        n = 0
                        try:
                            for i, l in enumerate(tl):
                                tl[i], k = learn.apply("tr", tgt, l)
                                n += k
                        except Exception as e:
                            log("learned translation fixes not done: %r" % e)
                        self.times["learned_fixes_" + tgt] = n
                        tl = self.fix_ai(tgt, tl)
                        self.texts[tgt] = tl
                        self.emitted[tgt] = self.applied.get(tgt, 0)
                        self.result.emit(tgt, "\n".join(tl))
                        self.times["translate_" + tgt] = time.time() - t2
                finally:
                    tr.close()
            for l in list(self.texts):  # AI fixes he pressed OK on while this was running
                self.texts[l] = self.fix_ai(l, self.texts[l])
            try:                    # keep the timings, for watching the video with its text and fixing it
                proj = project.make(self.path, self.spoken, self.targets, self.segments, self.texts)
                project.save(proj)
                self.made = {l: self.applied.get(l, 0) for l in self.texts}
                project.export(proj, self.docs)
                self.times["project"] = len(proj["segments"])
            except Exception as e:
                log("project not saved: " + traceback.format_exc())
            self.times["total"] = time.time() - t0
            log("job done %s" % self.times)
            self.done.emit(True, both("Done! It took %s." % hms(time.time() - t0), "פארטיג"))
        except engine.Stopped:
            self.done.emit(False, both("Stopped.", "אפגעשטעלט"))
        except engine.NoSound as e:
            log("no sound: %s" % e)
            self.done.emit(False, both("This file has no sound that could be read. Is it a video or audio file?",
                                       "מען קען נישט ליינען קיין קול פון דעם פייל"))
        except Exception as e:
            log("job failed: " + traceback.format_exc())
            self.done.emit(False, both("Something went wrong (%s: %s)." % (type(e).__name__, str(e)[:200]),
                                       "עפעס איז נישט געגאנגען גוט"))
        finally:
            engine.keep_awake(False)
            shutil.rmtree(tmp, ignore_errors=True)


def part_size(k):
    return ai.MODEL_SIZE if k == "ai" else engine.manifest()[k]["size"]


def all_missing():
    """Every part not here yet: the typing/translation models and the AI, so one download brings everything."""
    miss = engine.missing()
    if ai.server_exe() and not ai.model_file():
        miss.append("ai")
    return miss


class Fetch(QThread):
    progress = Signal(str, float)
    done = Signal(bool, str)

    def __init__(self, keys):
        super().__init__()
        self.keys = keys
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            for n, k in enumerate(self.keys, 1):
                what = "%s (%d of %d, %.1f GB)" % (engine.MODEL_WHAT[k], n, len(self.keys), part_size(k) / 1e9)
                self.progress.emit(what, 0.0)
                mark = [0]

                def prog(d, t, what=what, mark=mark):
                    self.progress.emit(what, d / t)
                    if d / t >= mark[0] + 0.1:
                        mark[0] += 0.1
                        log("download %s %.0f%%" % (k, 100 * d / t))
                if k == "ai":
                    ai.download(prog, lambda: self._stop)
                else:
                    engine.download(k, prog, lambda: self._stop)
                log("downloaded %s" % k)
            self.done.emit(True, "")
        except engine.Stopped:
            self.done.emit(False, "stopped")
        except Exception as e:
            log("download failed: " + traceback.format_exc())
            self.done.emit(False, str(e))


class FetchDialog(QDialog):
    """The one-time download of the parts that did not fit in the installer."""

    def __init__(self, parent, keys, auto=False):
        super().__init__(parent)
        self.keys, self.ok = keys, False
        self.setWindowTitle(TITLE + " - one-time download")
        self.setMinimumWidth(620)
        gb = sum(part_size(k) for k in keys) / 1e9
        lay = QVBoxLayout(self)
        what = ", ".join(engine.MODEL_WHAT[k] for k in keys)
        t = QLabel("One time only: Hafutza Typing needs to download the parts for %s (%.1f GB).\n"
                   "Keep the internet on until it finishes. After that it works with no internet." % (what, gb))
        t.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(RTLLabel("איין מאל: מען דארף אראפנעמען נאך טיילן (%.1f GB). לאזט די אינטערנעט אן ביז עס ענדיגט. "
                               "דערנאך ארבעט עס אן אינטערנעט." % gb))
        self.what = QLabel("")
        lay.addWidget(self.what)
        self.bar = QProgressBar(); self.bar.setRange(0, 1000)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.go = QPushButton(both("Download now", "אראפנעמען יעצט")); self.go.setObjectName("start")
        self.later = QPushButton(both("Later", "שפעטער"))
        row.addWidget(self.go, 2); row.addWidget(self.later, 1)
        lay.addLayout(row)
        self.go.clicked.connect(self.start)
        self.later.clicked.connect(self.cancel)
        self.th = None
        if auto:
            QTimer.singleShot(200, self.start)

    def start(self):
        self.go.setEnabled(False)
        self.later.setText(both("Stop", "אפשטעלן"))
        self.th = Fetch(self.keys)
        self.th.progress.connect(self.on_progress)   # bound methods (not lambdas): Qt then runs them in the window's thread
        self.th.done.connect(self.finished_)
        self.th.start()

    def on_progress(self, w, f):
        self.what.setText("Downloading " + w + "  -  %d%%" % (f * 100))
        self.bar.setValue(int(f * 1000))

    def finished_(self, ok, msg):
        self.th.wait()
        self.th = None
        if ok:
            self.ok = True
            self.accept()
        else:
            self.go.setEnabled(True)
            self.later.setText(both("Later", "שפעטער"))
            if msg != "stopped":
                self.what.setText("Not finished: " + msg + "\nPress Download now to go on where it stopped.")

    def cancel(self):
        if self.th:
            self.th.stop()
            return
        self.reject()

    def closeEvent(self, e):
        if self.th:
            self.th.stop(); self.th.wait()
        super().closeEvent(e)


# ------------------------------------------------------------------ update
class UpdateCheck(QThread):
    """Ask update.json what the newest version is (in the background)."""
    done = Signal(object, str)

    def __init__(self, url=None):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.done.emit(updater.check(self.url), "")
        except Exception as e:
            log("update check failed %r" % e)
            self.done.emit(None, "%s: %s" % (type(e).__name__, str(e)[:150]))
            return
        try:
            requests_out.flush(VERSION)       # requests written with no internet go now
        except Exception as e:
            log("kept requests: %r" % e)


class UpdateFetch(QThread):
    progress = Signal(float)
    done = Signal(str, str)

    def __init__(self, m):
        super().__init__()
        self.m = m
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            p = updater.download(self.m, lambda d, t: self.progress.emit(d / t), lambda: self._stop)
            self.done.emit(p, "")
        except engine.Stopped:
            self.done.emit("", "stopped")
        except Exception as e:
            log("update download failed %r" % e)
            self.done.emit("", str(e))


class RequestSend(QThread):
    done = Signal(str, str)

    def __init__(self, text):
        super().__init__()
        self.text = text

    def run(self):
        try:
            self.done.emit(*requests_out.send(self.text, VERSION))
        except Exception as e:
            log("request send: %r" % e)
            self.done.emit("error", str(e)[:150])


class RequestPage(QWidget):
    """Update window, part 2: write what you want changed, press Send; it reaches us (kept and sent later if offline)."""

    def __init__(self, dlg):
        super().__init__()
        self.dlg, self.th, self.kb, self.result = dlg, None, None, ""
        lay = QVBoxLayout(self)
        t = QLabel(both("Write what you want changed or added in the program (Yiddish or English), then press Send. It reaches us.",
                        "שרייבט וואס איר ווילט טוישן אדער צולייגן אינעם פראגראם, און דרוקט שיקן"))
        t.setWordWrap(True)
        f = t.font(); f.setPointSize(13); t.setFont(f)
        lay.addWidget(t)
        self.box = QPlainTextEdit()
        f = self.box.font(); f.setPointSize(15); self.box.setFont(f)
        self.box.setMinimumHeight(150)
        lay.addWidget(self.box)
        self.kb_btn = QPushButton(both("Show the Yiddish keyboard", "אידישע קלאוויאטור"))
        self.kb_btn.clicked.connect(self.toggle_kb)
        lay.addWidget(self.kb_btn)
        self.kb_spot = QVBoxLayout(); lay.addLayout(self.kb_spot)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        f = self.status.font(); f.setPointSize(13); self.status.setFont(f)
        lay.addWidget(self.status)
        n = len(requests_out.pending())
        if n:
            self.status.setText(both("%d request(s) written earlier are waiting for the internet; they go by themselves." % n,
                                     "פריערדיגע בקשות ווארטן אויף אינטערנעט"))
        row = QHBoxLayout()
        self.send_btn = QPushButton(both("Send", "שיקן")); self.send_btn.setObjectName("start")
        self.close_btn = QPushButton(both("Close", "צומאכן"))
        row.addWidget(self.send_btn, 2); row.addWidget(self.close_btn, 1)
        lay.addLayout(row)
        self.send_btn.clicked.connect(self.send)
        self.close_btn.clicked.connect(dlg.cancel)

    def toggle_kb(self):
        if self.kb is None:
            import player
            self.kb = player.Keyboard()
            self.kb.typed.connect(lambda c: (self.box.insertPlainText(c), self.box.setFocus()))
            self.kb.back.connect(lambda: self.box.textCursor().deletePreviousChar())
            self.kb_spot.addWidget(self.kb)
            self.kb_btn.setText(both("Hide the keyboard", "באהאלטן די קלאוויאטור"))
            return
        show = not self.kb.isVisible()
        self.kb.setVisible(show)
        self.kb_btn.setText(both("Hide the keyboard", "באהאלטן די קלאוויאטור") if show
                            else both("Show the Yiddish keyboard", "אידישע קלאוויאטור"))

    def send(self):
        text = self.box.toPlainText().strip()
        if not text:
            self.status.setText(both("Please write what you want first.", "ביטע שרייבט קודם וואס איר ווילט"))
            return
        self.send_btn.setEnabled(False)
        self.status.setText(both("Sending ...", "מען שיקט ..."))
        self.th = RequestSend(text)
        self.th.done.connect(self.sent)
        self.th.start()

    def sent(self, kind, info):
        self.th.wait(); self.th = None
        self.send_btn.setEnabled(True)
        self.result = kind
        self.box.clear()
        if kind == "sent":
            self.status.setText(both("✓ Got it, your request was sent.", "✓ באקומען, אייער בקשה איז געשיקט געווארן"))
        else:
            self.status.setText(both("No internet right now, so your request is kept on this computer. "
                                     "It goes by itself the next time the program is open with the internet on.",
                                     "קיין אינטערנעט יעצט: די בקשה ווערט אפגעהיטן און גייט אוועק ווען די אינטערנעט איז אן"))


class UpdateDialog(QDialog):
    """Update button: two parts. 1) Update: what is new + update with one press (or "You have the newest version").
    2) Request an update: write what you want changed and send it."""

    def __init__(self, parent, url=None, auto=False, known=None):
        super().__init__(parent)
        self.url, self.auto, self.m, self.th = url, auto, None, None
        self.result_text = ""
        self.setWindowTitle(TITLE + " - Update")
        self.setMinimumWidth(760)
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        f = self.tabs.font(); f.setPointSize(13); self.tabs.setFont(f)
        outer.addWidget(self.tabs)
        page = QWidget()
        lay = QVBoxLayout(page)
        self.msg = QLabel(both("Checking for a new version ...", "מען קוקט צי ס'איז דא א נייע ווערסיע"))
        self.msg.setWordWrap(True)
        f = self.msg.font(); f.setPointSize(13); self.msg.setFont(f)
        lay.addWidget(self.msg)
        self.bar = QProgressBar(); self.bar.setRange(0, 0)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.go = QPushButton(both("Update now", "דערהיינטיקן יעצט")); self.go.setObjectName("start"); self.go.hide()
        self.close_btn = QPushButton(both("Close", "צומאכן"))
        row.addWidget(self.go, 2); row.addWidget(self.close_btn, 1)
        lay.addStretch(1)
        lay.addLayout(row)
        self.req = RequestPage(self)
        self.tabs.addTab(page, "1. Update - what's new  -  דערהיינטיקן")
        self.tabs.addTab(self.req, "2. Request an update  -  בעטן א טויש")
        self.go.clicked.connect(self.fetch)
        self.close_btn.clicked.connect(self.cancel)
        if known:
            QTimer.singleShot(0, lambda: self.checked(known, ""))
        else:
            self.chk = UpdateCheck(url)
            self.chk.done.connect(self.checked)
            self.chk.start()

    def checked(self, m, err):
        if getattr(self, "chk", None):
            self.chk.wait()
        self.bar.setRange(0, 1000); self.bar.setValue(0)
        if m is None:
            self.result_text = "error: " + err
            self.bar.hide()
            self.msg.setText(both("Could not check for a new version. Is the internet on?\n(%s)" % err,
                                  "מען האט נישט געקענט קוקן. איז די אינטערנעט אן?"))
            self.done_auto(5)
        elif not m["newer"]:
            self.result_text = "newest"
            self.bar.hide()
            added = whatsnew.text(VERSION)
            self.msg.setText(both("You have the newest version (%s)." % VERSION,
                                  "איר האט די נייסטע ווערסיע (%s)" % VERSION)
                             + (("\n\nWhat version %s added:\n" % VERSION) + added if added else ""))
            self.done_auto(0)
        else:
            self.m = m
            self.bar.hide()
            notes = m.get("notes") or whatsnew.text(m["version"])
            notes = ("\n\nWhat's new in %s:\n%s\n" % (m["version"], notes)) if notes else ""
            self.msg.setText(both("A new version is ready: %s (you have %s). Download %.0f MB and install it?%s\n"
                                  "Your typed texts and the downloaded parts are kept. The program closes and opens again by itself."
                                  % (m["version"], VERSION, m["size"] / 1e6, notes),
                                  "ס'איז דא א נייע ווערסיע %s. דערהיינטיקן?" % m["version"]))
            self.go.show()
            self.close_btn.setText(both("Later", "שפעטער"))
            if self.auto:
                QTimer.singleShot(500, self.fetch)

    def fetch(self):
        self.go.setEnabled(False)
        self.close_btn.setText(both("Stop", "אפשטעלן"))
        self.bar.show()
        self.msg.setText(both("Downloading version %s ..." % self.m["version"], "מען נעמט אראפ די נייע ווערסיע"))
        self.th = UpdateFetch(self.m)
        self.th.progress.connect(lambda f: self.bar.setValue(int(f * 1000)))
        self.th.done.connect(self.fetched)
        self.th.start()

    def fetched(self, path, err):
        self.th.wait(); self.th = None
        if not path:
            self.go.setEnabled(True)
            self.close_btn.setText(both("Later", "שפעטער"))
            if err != "stopped":
                self.msg.setText(both("The download did not finish: %s\nPress Update now to try again." % err,
                                      "עס האט נישט געארבעט. פרובירט נאכאמאל"))
                self.result_text = "error: " + err
                self.done_auto(6)
            return
        self.msg.setText(both("Installing version %s. The program closes now and opens again by itself in a minute."
                              % self.m["version"], "מען שטעלט איין די נייע ווערסיע. עס עפנט זיך באלד ווידער"))
        self.go.hide(); self.close_btn.setEnabled(False)
        self.result_text = "installing " + self.m["version"]
        QApplication.processEvents()
        try:
            updater.run_installer(path)
        except Exception as e:
            log("update: could not start installer %r" % e)
            self.result_text = "error: could not start installer: %r" % e
            self.msg.setText(both("Could not start the installer (%s)." % e, "עס האט נישט געארבעט"))
            self.close_btn.setEnabled(True)
            self.done_auto(7)
            return
        self.installing = True
        QTimer.singleShot(2500, self.quit_all)

    def quit_all(self):
        w = self.parent()
        if getattr(w, "link_job", None):
            w.link_job.stop(); w.link_job.wait(5000)
        if self.auto and hasattr(self, "on_auto_done"):
            self.on_auto_done(self.result_text, 0)
        QApplication.instance().exit(0)

    def done_auto(self, code):
        if self.auto and hasattr(self, "on_auto_done"):
            QTimer.singleShot(1500, lambda: self.on_auto_done(self.result_text, code))

    def cancel(self):
        if getattr(self, "req", None) and self.req.th:
            return
        if self.th:
            self.th.stop()
            return
        self.reject()

    def closeEvent(self, e):
        if getattr(self, "installing", False):
            e.ignore(); return
        if self.th:
            self.th.stop(); self.th.wait()
        super().closeEvent(e)


# ------------------------------------------------------------------ video links
class LinkFetch(QThread):
    """Download one or more video links (with their picture where the site has one), one after another."""
    progress = Signal(str, float)
    got = Signal(str)
    failed = Signal(str, str)
    done = Signal()

    def __init__(self, urls):
        super().__init__()
        self.urls = list(urls)
        self._stop = False

    def stop(self):
        self._stop = True

    def add(self, urls):
        self.urls.extend(u for u in urls if u not in self.urls)

    def run(self):
        i = 0
        while i < len(self.urls) and not self._stop:
            u = self.urls[i]; i += 1
            short = u if len(u) < 70 else u[:67] + "..."
            try:
                self.progress.emit(short, -1.0)
                p = links.download(u, lambda f, t, short=short: self.progress.emit("%s  (%s)" % (short, t), f),
                                   lambda: self._stop)
                self.got.emit(p)
            except engine.Stopped:
                break
            except links.LinkError as e:
                self.failed.emit(u, str(e))
            except Exception as e:
                log("link fetch failed: " + traceback.format_exc())
                self.failed.emit(u, "Could not get the video from this link (%s)." % type(e).__name__)
        self.done.emit()


def dropped_links(md):
    """Links in something dragged in (a link from a browser's address bar, a page, a chat)."""
    out = [u.toString() for u in md.urls() if not u.isLocalFile() and u.scheme() in ("http", "https")]
    if not out and md.hasText():
        out = links.find_links(md.text())
    return out


# ------------------------------------------------------------------ the drop box
class DropBox(QFrame):
    """Big box: drop one or more video/audio files (or a video link) here, or click it to choose them."""
    files = Signal(list)
    urls = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        a = QLabel("Drop video or audio files here  (one or more)")
        f = a.font(); f.setPointSize(16); f.setBold(True); a.setFont(f)
        a.setAlignment(Qt.AlignCenter)
        b = QLabel("שלעפט אריין פיילס אהער  (איינס אדער מערערע)")
        b.setFont(f); b.setAlignment(Qt.AlignCenter); b.setLayoutDirection(Qt.RightToLeft)
        c = QLabel("or click here to choose them   -   אדער קליקט דא צו אויסקלייבן")
        c.setAlignment(Qt.AlignCenter)
        c.setStyleSheet("color: #3d5f87;")
        for w in (a, b, c):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            w.setStyleSheet(w.styleSheet() + "background: transparent; border: none;")
            lay.addWidget(w)

    def _hot(self, on):
        self.setProperty("hot", "true" if on else "false")
        self.style().unpolish(self); self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction(); self._hot(True)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._hot(False)

    def dropEvent(self, e):
        self._hot(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        paths = [p for p in paths if os.path.isfile(p)]
        if paths:
            e.acceptProposedAction()
            self.files.emit(paths)
            return
        us = dropped_links(e.mimeData())
        if us:
            e.acceptProposedAction()
            self.urls.emit(us)

    def mouseReleaseEvent(self, e):
        # one click or a double click: the file browser opens once (not again for the double click's second click)
        if e.button() != Qt.LeftButton or not self.isEnabled():
            return
        if getattr(self, "_busy", False) or time.time() - getattr(self, "_closed", 0) < 0.6:
            return
        self._busy = True
        try:
            self.files.emit([])          # empty = "open the file picker"
        finally:
            self._busy = False
            self._closed = time.time()

    def mouseDoubleClickEvent(self, e):
        e.accept()


# ------------------------------------------------------------------ the window
class ResultTab(QWidget):
    def __init__(self, win, lang):
        super().__init__()
        self.win, self.lang = win, lang
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.copy = QPushButton(both("Copy", "קאפירן"))
        self.save = QPushButton(both("Save as .txt file", "אפהיטן אלס טעקסט פייל"))
        for b in (self.copy, self.save):
            b.setMinimumHeight(54)
        row.addWidget(self.copy); row.addWidget(self.save); row.addStretch(1)
        lay.addLayout(row)
        self.edit = QPlainTextEdit()
        self.edit.setMinimumHeight(220)
        if lang in RTL:
            self.edit.setLayoutDirection(Qt.RightToLeft)
            opt = QTextOption(Qt.AlignRight)
            opt.setTextDirection(Qt.RightToLeft)
            opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            self.edit.document().setDefaultTextOption(opt)
        lay.addWidget(self.edit)
        self.copy.clicked.connect(self.do_copy)
        self.save.clicked.connect(self.do_save)

    def do_copy(self):
        QApplication.clipboard().setText(self.edit.toPlainText())
        self.copy.setText(both("Copied!", "קאפירט"))
        QTimer.singleShot(2500, lambda: self.copy.setText(both("Copy", "קאפירן")))

    def do_save(self):
        shown = self.win.shown_path()
        start = os.path.join(os.path.dirname(shown or "") or docs_dir(), self.win.file_name(self.lang, shown))
        p, _ = QFileDialog.getSaveFileName(self, "Save", start, "Text file (*.txt)")
        if p:
            if not p.lower().endswith(".txt"):
                p += ".txt"
            write_text(p, self.edit.toPlainText())
            self.save.setText(both("Saved", "אפגעהיטן"))
            QTimer.singleShot(2500, lambda: self.save.setText(both("Save as .txt file", "אפהיטן אלס טעקסט פייל")))


def docs_dir():
    d = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser("~")
    return d


def write_text(path, text):
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:   # BOM + Windows line ends: Notepad and Word read it right
        f.write(text + "\n")


def hms(t):
    t = int(round(t))
    if t < 60:
        return "%d seconds" % t
    if t < 3600:
        return "%d:%02d minutes" % (t // 60, t % 60)
    return "%d:%02d hours" % (t // 3600, t // 60 % 60)


# ------------------------------------------------------------------ the AI helper (fix words on request)
class AIFetch(QThread):
    progress = Signal(float, float)
    done = Signal(bool, str)

    def __init__(self):
        super().__init__()
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            mark = [0]

            def prog(d, t):
                self.progress.emit(d, t)
                if d / t >= mark[0] + 0.1:
                    mark[0] += 0.1
                    log("ai download %.0f%%" % (100 * d / t))
            ai.download(prog, lambda: self._stop)
            log("ai model downloaded")
            self.done.emit(True, "")
        except engine.Stopped:
            self.done.emit(False, "stopped")
        except Exception as e:
            log("ai download failed: " + traceback.format_exc())
            self.done.emit(False, str(e))


class AIAsk(QThread):
    """One question to the AI, in the background. instruction None = only start the AI (warm it up)."""
    done = Signal(object, str, str, float)     # changes [(find, replace)], raw answer, error, seconds

    def __init__(self, server, text, instruction):
        super().__init__()
        self.server, self.text, self.instruction = server, text, instruction
        self.by = ""

    def run(self):
        t = time.time()
        try:
            if self.instruction is None:
                self.server.start()
                self.done.emit([], "", "", time.time() - t)
                return
            self.server.start()                # starting is mostly reading the file: the typing need not wait for it
            engine.HOLD.set()
            try:
                ch, raw = self.server.ask(ai.context(self.text, self.instruction), self.instruction)
            finally:
                engine.HOLD.clear()
            log("ai answer %.1f s: %s" % (time.time() - t, raw[:500].replace("\n", " ")))
            self.by = "ai"
            q = ai.quoted(self.instruction)
            if not ch and q and q[0] in self.text:
                ch, self.by = [q], "quotes"
                log("ai suggested nothing; using the quoted words %r" % (q,))
            self.done.emit(ch, raw, "", time.time() - t)
        except Exception as e:
            log("ai failed: " + traceback.format_exc())
            self.done.emit([], "", str(e), time.time() - t)


class AIDialog(QDialog):
    """Write what to fix (English or Yiddish); the AI suggests word changes; tick them and press OK.
    Not modal: the typing goes on while it is open. Nothing changes in the text without OK."""

    def __init__(self, win):
        super().__init__(win)
        self.win, self.th, self.fetch, self.kb, self.changes, self.boxes = win, None, None, None, [], []
        self.setWindowTitle(TITLE + " - AI: fix words")
        self.setMinimumWidth(720)
        self.setModal(False)
        lay = QVBoxLayout(self)
        t = QLabel(both("Write what to fix, in Yiddish or English. For example: change אמונה to עמונה,  or: write Reb not Rabbi.\n"
                        "The AI shows the changes; nothing changes until you press OK. It works on this computer, no internet.",
                        "שרייבט וואס צו פארריכטן, אויף אידיש אדער ענגליש. דער AI ווייזט די ענדערונגען; גארנישט טוישט זיך ביז איר דרוקט OK."))
        t.setWordWrap(True)
        lay.addWidget(t)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Fix the text in:  -  פארריכטן דעם טעקסט אין:"))
        self.lang = QComboBox(); self.lang.setMinimumHeight(40)
        prow.addWidget(self.lang, 1)
        lay.addLayout(prow)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(110)
        lay.addWidget(self.log)
        self.box = QPlainTextEdit(); self.box.setMaximumHeight(90)
        f = self.box.font(); f.setPointSize(15); self.box.setFont(f)
        lay.addWidget(self.box)
        krow = QHBoxLayout()
        self.kb_btn = QPushButton(both("Show the Yiddish keyboard", "אידישע קלאוויאטור"))
        self.kb_btn.clicked.connect(self.toggle_kb)
        self.send_btn = QPushButton(both("Ask the AI", "פרעגן דעם AI")); self.send_btn.setObjectName("start")
        self.send_btn.clicked.connect(self.send)
        krow.addWidget(self.kb_btn, 1); krow.addWidget(self.send_btn, 2)
        lay.addLayout(krow)
        self.kb_spot = QVBoxLayout(); lay.addLayout(self.kb_spot)
        self.status = QLabel(""); self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.bar = QProgressBar(); self.bar.setRange(0, 1000); self.bar.hide()
        lay.addWidget(self.bar)
        self.list_box = QGroupBox("Suggested changes  -  פארגעשלאגענע ענדערונגען")
        self.list_lay = QVBoxLayout(self.list_box)
        self.list_box.hide()
        lay.addWidget(self.list_box)
        self.remember = QCheckBox(both("Also remember these for the next videos (Learned words)", "געדענקען אויך פאר די קומענדיגע ווידעאס"))
        self.remember.hide()
        lay.addWidget(self.remember)
        brow = QHBoxLayout()
        self.ok_btn = QPushButton("OK  -  פארריכטן"); self.ok_btn.setObjectName("start")
        self.ok_btn.clicked.connect(self.apply)
        self.no_btn = QPushButton(both("Don't change", "נישט טוישן"))
        self.no_btn.clicked.connect(self.clear_changes)
        self.ok_btn.hide(); self.no_btn.hide()
        brow.addWidget(self.ok_btn, 2); brow.addWidget(self.no_btn, 1)
        lay.addLayout(brow)
        self.dl_btn = QPushButton(both("Download the AI (2.7 GB, one time)", "אראפנעמען דעם AI (2.7 GB, איין מאל)"))
        self.dl_btn.setObjectName("choose")
        self.dl_btn.clicked.connect(self.download)
        lay.addWidget(self.dl_btn)
        self.close_btn = QPushButton(both("Close", "צומאכן"))
        self.close_btn.clicked.connect(self.close)
        lay.addWidget(self.close_btn)
        self.refresh()

    # -- what is there
    def refresh(self):
        langs = self.win.ai_langs()
        if langs != [self.lang.itemData(i) for i in range(self.lang.count())]:
            cur = self.lang.currentData()
            self.lang.blockSignals(True)
            self.lang.clear()
            for l in langs:
                self.lang.addItem("%s  %s" % (NAME_YI[l], NAME_EN[l]) if l != "en" else "English", l)
            i = self.lang.findData(cur)
            self.lang.setCurrentIndex(i if i >= 0 else 0)
            self.lang.blockSignals(False)
        have = ai.model_file() is not None
        exe = ai.server_exe() is not None
        self.dl_btn.setVisible(not have and exe and self.fetch is None)
        self.send_btn.setEnabled(have and exe and self.th is None and self.lang.count() > 0)
        was = getattr(self, "problem", False)
        self.problem = True
        if not exe:
            self.status.setText(both("The AI part is missing from this copy of the program: please install it again.",
                                     "דער AI טייל פעלט: ביטע אינסטאלירט נאכאמאל"))
        elif not have and self.fetch is None:
            gb = ai.ram_gb()
            warn = ""
            if gb and gb < 7.5:
                warn = ("\nThis computer has %.0f GB of memory; the AI needs about 5 GB, so it may be slow or not start "
                        "while typing runs." % gb)
            self.status.setText(both("The AI is not downloaded yet. It is an extra 2.7 GB, downloaded once; after that it "
                                     "works with no internet. The rest of the program works without it." + warn,
                                     "דער AI איז נאך נישט אראפגענומען (2.7 GB, איין מאל)"))
        elif self.lang.count() == 0:
            self.status.setText(both("There is no text yet. Type a video first (or wait for the first lines).",
                                     "נאך קיין טעקסט נישטא"))
        else:
            self.problem = False
            if was:
                self.status.setText("")

    def toggle_kb(self):
        if self.kb is None:
            import player
            self.kb = player.Keyboard()
            self.kb.typed.connect(lambda c: (self.box.insertPlainText(c), self.box.setFocus()))
            self.kb.back.connect(lambda: self.box.textCursor().deletePreviousChar())
            self.kb_spot.addWidget(self.kb)
            self.kb_btn.setText(both("Hide the keyboard", "באהאלטן די קלאוויאטור"))
            return
        show = not self.kb.isVisible()
        self.kb.setVisible(show)
        self.kb_btn.setText(both("Hide the keyboard", "באהאלטן די קלאוויאטור") if show
                            else both("Show the Yiddish keyboard", "אידישע קלאוויאטור"))

    # -- download
    def download(self):
        self.dl_btn.hide()
        self.bar.setValue(0); self.bar.show()
        self.status.setText(both("Downloading the AI ... keep the internet on.", "מען נעמט אראפ דעם AI"))
        self.fetch = AIFetch()
        self.fetch.progress.connect(self.on_fetch)
        self.fetch.done.connect(self.fetched)
        self.fetch.start()

    def on_fetch(self, d, t):
        self.bar.setValue(int(1000 * d / t))
        self.status.setText(both("Downloading the AI ... %.1f of %.1f GB" % (d / 1e9, t / 1e9), "מען נעמט אראפ דעם AI"))

    def fetched(self, ok, msg):
        self.fetch.wait(); self.fetch = None
        self.bar.hide()
        self.refresh()
        if ok:
            self.status.setText(both("✓ The AI is ready. Write what to fix and press Ask the AI.", "✓ דער AI איז גרייט"))
        elif msg != "stopped":
            self.status.setText(both("The download did not finish: %s\nPress the button again to go on where it stopped." % msg,
                                     "עס האט נישט געענדיגט"))

    # -- ask
    def warm(self):
        """Start the AI in the background now, so the first answer comes quicker."""
        if self.th is None and ai.model_file() and ai.server_exe() and not self.win.ai_server.running():
            self.th = AIAsk(self.win.ai_server, "", None)
            self.th.done.connect(self.warmed)
            self.send_btn.setEnabled(False)
            self.status.setText(both("Starting the AI ...", "דער AI הייבט אן ..."))
            self.th.start()

    def warmed(self, ch, raw, err, secs):
        self.th.wait(); self.th = None
        log("ai warm-up %.1f s %s" % (secs, err))
        self.status.setText(both("The AI could not start: " + err, "דער AI האט נישט אנגעהויבן") if err else
                            both("✓ The AI is ready.", "✓ דער AI איז גרייט"))
        self.refresh()

    def send(self, _=None, text=None):
        instr = (text if text is not None else self.box.toPlainText()).strip()
        lang = self.lang.currentData()
        if not instr or not lang or self.th is not None:
            return False
        src = self.win.ai_text(lang)
        if not src.strip():
            self.status.setText(both("There is no text in this language yet.", "נאך קיין טעקסט נישטא"))
            return False
        self.clear_changes()
        self.ask_lang = lang
        self.log.appendPlainText("You: " + instr)
        self.box.clear()
        self.send_btn.setEnabled(False)
        self.status.setText(both("The AI is thinking ... (usually 10-40 seconds%s)" %
                                 ("; the first time it also starts up" if not self.win.ai_server.running() else ""),
                                 "דער AI טראכט ..."))
        self.bar.setRange(0, 0); self.bar.show()
        self.th = AIAsk(self.win.ai_server, src, instr)
        self.th.done.connect(self.answered)
        self.th.start()
        return True

    def answered(self, ch, raw, err, secs):
        self.th.wait(); self.last_by = self.th.by; self.th = None
        self.bar.hide(); self.bar.setRange(0, 1000)
        self.last_seconds = secs
        self.refresh()
        if err:
            self.log.appendPlainText("AI: (did not work: %s)" % err)
            self.status.setText(both("The AI did not answer: " + err, "דער AI האט נישט געענטפערט"))
            return
        text = self.win.ai_text(self.ask_lang)
        typing = self.win.job is not None
        self.changes = []
        for f, r in ch:
            n = text.count(f)
            if n or typing:        # while typing runs, a word may still come in later lines
                self.changes.append((f, r, n))
        if not self.changes:
            self.log.appendPlainText("AI: no change to suggest.")
            self.status.setText(both("The AI found nothing to change for that. Try naming the exact word, "
                                     "like: change X to Y.", "דער AI האט נישט געפונען וואס צו טוישן"))
            return
        self.log.appendPlainText("AI: %d change(s) suggested (%.0f s)." % (len(self.changes), secs))
        for f, r, n in self.changes:
            where = ("%d place(s)" % n) if n else "not in the text yet; will be fixed when it comes"
            b = QCheckBox("%s   →   %s     (%s)" % (f, r, where))
            b.setChecked(True)
            b.setLayoutDirection(Qt.RightToLeft if self.ask_lang in RTL else Qt.LeftToRight)
            self.list_lay.addWidget(b)
            self.boxes.append(b)
        self.list_box.show(); self.remember.show(); self.ok_btn.show(); self.no_btn.show()
        self.status.setText(both("Untick any you don't want, then press OK.", "נעמט אראפ דעם צייכן פון וואס איר ווילט נישט, און דרוקט OK"))

    def clear_changes(self):
        for b in self.boxes:
            b.setParent(None); b.deleteLater()
        self.boxes, self.changes = [], []
        self.list_box.hide(); self.remember.hide(); self.ok_btn.hide(); self.no_btn.hide()

    def apply(self):
        pick = [(f, r) for (f, r, _n), b in zip(self.changes, self.boxes) if b.isChecked()]
        lang = self.ask_lang
        n = self.win.ai_apply(lang, pick, remember=self.remember.isChecked())
        self.log.appendPlainText("Done: %d change(s), %d place(s) fixed%s." %
                                 (len(pick), n, "; later lines are fixed as they come" if self.win.job else ""))
        self.clear_changes()
        self.status.setText(both("✓ Fixed. Write the next fix, or Close.", "✓ פארריכט"))
        self.last_applied = (lang, pick, n)
        return n

    def closeEvent(self, e):
        if self.fetch:
            self.fetch.stop(); self.fetch.wait(); self.fetch = None
        super().closeEvent(e)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.files = []          # the chosen files, in order
        self.queue = []          # files still to type in this run
        self.path = None         # the file being typed now
        self.results = {}        # path -> {lang: text}
        self.problems = {}       # path -> message, for files that did not work
        self.job = None
        self.tabs_by_lang = {}
        self.update_info = None
        self.ai_rules = {}       # lang -> [(find, replace)] the AI helper changes he pressed OK on, for this run
        self.ai_server = ai.Server()
        self.ai_dlg = None
        self.partial_raw = ""
        self.setAcceptDrops(True)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setSpacing(10)
        head = QHBoxLayout()
        t = QLabel(TITLE)
        f = t.font(); f.setPointSize(22); f.setBold(True); t.setFont(f)
        head.addWidget(t)
        head.addStretch(1)
        self.version_label = QLabel("Version %s" % VERSION)
        self.version_label.setStyleSheet("color: #5b6470; font-size: 10pt;")
        head.addWidget(self.version_label)
        self.update_btn = QPushButton("Update  -  דערהיינטיקן")
        self.update_btn.setObjectName("update")
        self.update_btn.setToolTip("Check for a new version of Hafutza Typing and install it")
        self.update_btn.clicked.connect(self.do_update)
        head.addWidget(self.update_btn)
        lay.addLayout(head)
        hrow = QHBoxLayout()
        self.videos_btn = QPushButton(both("My typed videos (watch and fix)", "מיינע ווידעאס (זען און פארריכטן)"))
        self.videos_btn.clicked.connect(self.my_videos)
        self.learned_btn = QPushButton(both("Learned words", "געלערנטע ווערטער"))
        self.learned_btn.clicked.connect(self.learned_words)
        self.ai_btn = QPushButton(both("AI: fix words", "AI: פארריכטן ווערטער"))
        self.ai_btn.setToolTip("Write what to fix (English or Yiddish); the AI suggests the changes; press OK")
        self.ai_btn.clicked.connect(self.open_ai)
        hrow.addWidget(self.videos_btn); hrow.addWidget(self.learned_btn); hrow.addWidget(self.ai_btn); hrow.addStretch(1)
        lay.addLayout(hrow)
        sub = QHBoxLayout()
        sub.addWidget(QLabel("Video or recording in, typed text out. No internet needed."))
        sub.addStretch(1)
        sub.addWidget(RTLLabel("א ווידעא אדער רעקארדירונג אריין, געשריבענע טעקסט ארויס"))
        lay.addLayout(sub)

        # 1 - the files
        g1 = QGroupBox("1.  The files  -  די פיילס")
        l1 = QVBoxLayout(g1)
        self.dropbox = DropBox()
        self.dropbox.files.connect(self.dropped)
        self.dropbox.urls.connect(self.get_links)
        l1.addWidget(self.dropbox)
        lrow = QHBoxLayout()
        lrow.addWidget(QLabel("Or paste a video link:\nאדער לייגט אריין א לינק:"))
        self.link_edit = QLineEdit()
        self.link_edit.setPlaceholderText("https://...   (YouTube, Facebook, Instagram, Vimeo, other sites, or a link to an .mp4 / .mp3)")
        self.link_edit.setMinimumHeight(44)
        self.link_edit.returnPressed.connect(self.link_go)
        lrow.addWidget(self.link_edit, 1)
        self.link_btn = QPushButton(both("Get the video", "אראפנעמען"))
        self.link_btn.setMinimumHeight(56)
        self.link_btn.clicked.connect(self.link_go)
        lrow.addWidget(self.link_btn)
        l1.addLayout(lrow)
        self.link_status = QLabel("")
        self.link_status.setWordWrap(True)
        self.link_status.hide()
        l1.addWidget(self.link_status)
        self.link_bar = QProgressBar(); self.link_bar.setRange(0, 1000); self.link_bar.hide()
        l1.addWidget(self.link_bar)
        self.link_job = None
        self.link_errors = {}
        row1 = QHBoxLayout()
        self.choose = QPushButton(both("Choose video or audio files ...", "קלייבט אויס ווידעא אדער קול פיילס"))
        self.choose.setObjectName("choose")
        self.choose.clicked.connect(self.pick)
        self.clear_btn = QPushButton(both("Clear the list", "אויסמעקן די ליסטע"))
        self.clear_btn.setMinimumHeight(56)
        self.clear_btn.clicked.connect(self.clear_files)
        self.clear_btn.hide()
        row1.addWidget(self.choose, 3); row1.addWidget(self.clear_btn, 1)
        l1.addLayout(row1)
        self.file_label = QLabel("No file chosen yet.")
        self.file_label.setWordWrap(True)
        l1.addWidget(self.file_label)
        lay.addWidget(g1)

        # 2 - spoken language
        g2 = QGroupBox("2.  Language spoken in it  -  וועלכע שפראך רעדט מען")
        l2 = QHBoxLayout(g2)
        self.spoken = QButtonGroup(self)
        self.spoken_btn = {}
        for code in LANGS:
            b = QRadioButton("%s  %s" % (NAME_YI[code], NAME_EN[code]) if code != "en" else "English")
            self.spoken.addButton(b)
            self.spoken_btn[code] = b
            l2.addWidget(b)
        self.spoken_btn["yi"].setChecked(True)
        l2.addStretch(1)
        lay.addWidget(g2)

        # 3 - output languages
        g3 = QGroupBox("3.  Type it out in (one or more)  -  אויף וועלכע שפראכן צו שרייבן")
        l3 = QHBoxLayout(g3)
        self.target_box = {}
        for code in LANGS:
            b = QCheckBox("%s  %s" % (NAME_YI[code], NAME_EN[code]) if code != "en" else "English")
            self.target_box[code] = b
            l3.addWidget(b)
        self.target_box["yi"].setChecked(True)
        l3.addStretch(1)
        lay.addWidget(g3)

        # start / stop
        row = QHBoxLayout()
        self.start_btn = QPushButton("Start   -   אנהייבן")
        self.start_btn.setObjectName("start")
        self.start_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Stop   -   אפשטעלן")
        self.stop_btn.setObjectName("stop")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.hide()
        row.addWidget(self.start_btn, 3)
        row.addWidget(self.stop_btn, 1)
        lay.addLayout(row)

        self.queue_label = QLabel("")
        self.queue_label.setWordWrap(True)
        f = self.queue_label.font(); f.setPointSize(13); f.setBold(True); self.queue_label.setFont(f)
        self.queue_label.hide()
        lay.addWidget(self.queue_label)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        f = self.status.font(); f.setPointSize(13); self.status.setFont(f)
        lay.addWidget(self.status)
        self.bar = QProgressBar(); self.bar.setRange(0, 1000); self.bar.hide()
        lay.addWidget(self.bar)
        self.partial = QPlainTextEdit(); self.partial.setReadOnly(True); self.partial.setMaximumHeight(130)
        self.partial.setLayoutDirection(Qt.RightToLeft)
        self.partial.hide()
        lay.addWidget(self.partial)

        self.view_row = QWidget()
        vr = QHBoxLayout(self.view_row); vr.setContentsMargins(0, 0, 0, 0)
        vr.addWidget(QLabel("Show the text of:  -  ווייזן דעם טעקסט פון:"))
        self.view_pick = QComboBox()
        self.view_pick.setMinimumHeight(40)
        self.view_pick.currentIndexChanged.connect(self.show_file)
        vr.addWidget(self.view_pick, 1)
        self.view_row.hide()
        lay.addWidget(self.view_row)

        self.watch_btn = QPushButton(both("▶   Watch the video with the text on it, and fix the text",
                                          "זען דעם ווידעא מיטן טעקסט, און פארריכטן דעם טעקסט"))
        self.watch_btn.setObjectName("watch")
        self.watch_btn.setStyleSheet("QPushButton#watch { background: #2f7bd0; color: white; font-size: 14pt; font-weight: bold;"
                                     " border: none; min-height: 56px; } QPushButton#watch:hover { background: #2568b3; }")
        self.watch_btn.clicked.connect(lambda: self.open_player(self.shown_path()))
        self.watch_btn.hide()
        lay.addWidget(self.watch_btn)
        self.players = {}

        self.tabs = QTabWidget()
        self.tabs.hide()
        lay.addWidget(self.tabs, 1)

        foot = QLabel("Everything stays on this computer. A copy of every text is also kept in: "
                      + os.path.join(docs_dir(), "Hafutza Typing"))
        foot.setWordWrap(True)
        foot.setStyleSheet("color: #5b6470; font-size: 10pt;")
        lay.addWidget(foot)

        self.scroll = scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(body)
        self.setCentralWidget(scroll)
        self.resize(1000, 900)

    def fit_screen(self):
        """Show the window whole on a small laptop screen: there it opens filling the screen."""
        scr = self.screen().availableGeometry() if self.screen() else None
        if scr is not None and (scr.height() < 940 or scr.width() < 1040):
            self.showMaximized()
        else:
            self.show()

    # -- update
    def do_update(self, _=None, url=None, auto=False):
        if self.job:
            QMessageBox.information(self, TITLE, both("Please update when the typing has finished (or press Stop first).",
                                                      "ביטע דערהיינטיקט ווען עס האט געענדיגט"))
            return None
        d = UpdateDialog(self, url=url, auto=auto, known=self.update_info if not url else None)
        if auto:
            return d
        d.exec()
        return d

    def quiet_check(self, url=None):
        """A quiet look at start: if there is a newer version, the Update button turns blue and says so. No internet = nothing happens."""
        self._qc = UpdateCheck(url)
        self._qc.done.connect(self.quiet_checked)
        self._qc.start()

    def quiet_checked(self, m, err):
        self._qc.wait()
        if m and m.get("newer"):
            self.update_info = m
            self.update_btn.setText("New version %s - Update  -  דערהיינטיקן" % m["version"])
            self.update_btn.setProperty("news", "true")
            self.update_btn.style().unpolish(self.update_btn); self.update_btn.style().polish(self.update_btn)

    # -- files
    def pick(self):
        """The normal Windows file browser (This PC, drives, Downloads, Desktop, Videos, USB), several files allowed."""
        last = self.files[-1] if self.files else getattr(self, "last_dir", None)
        start = os.path.dirname(last) if last and os.path.isfile(last) else last
        if not start or not os.path.isdir(start):
            vids = QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)
            dls = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
            try:
                has_vids = bool(vids and os.path.isdir(vids) and [f for f in os.listdir(vids) if not f.startswith(".")
                                                                  and f.lower() != "desktop.ini"])
            except OSError:
                has_vids = False
            start = vids if has_vids else (dls if dls and os.path.isdir(dls) else docs_dir())
        ps, _ = QFileDialog.getOpenFileNames(self, "Choose video or audio files (one or more)", start, FILE_TYPES)
        if ps:
            self.last_dir = os.path.dirname(ps[0])
        if ps:
            self.add_files(ps)

    # -- links
    def link_go(self):
        us = links.find_links(self.link_edit.text())
        if not us:
            t = self.link_edit.text().strip()
            if t and "." in t and " " not in t:
                us = ["https://" + t]
        if not us:
            QMessageBox.information(self, TITLE, both("Paste a link to a video first (it starts with https://).",
                                                      "לייגט אריין א לינק צו א ווידעא"))
            return
        self.link_edit.clear()
        self.get_links(us)

    def get_links(self, us):
        if self.link_job:
            self.link_job.add(us)
            return
        self.link_job = LinkFetch(us)
        self.link_job.progress.connect(self.link_progress)
        self.link_job.got.connect(self.link_got)
        self.link_job.failed.connect(self.link_failed)
        self.link_job.done.connect(self.link_done)
        self.link_status.setStyleSheet("")
        self.link_status.setText(both("Getting the video from the link (needs the internet for this step) ...",
                                      "מען נעמט אראפ דעם ווידעא פונעם לינק"))
        self.link_status.show(); self.link_bar.show(); self.link_bar.setRange(0, 0)
        self.link_btn.setText(both("Stop getting it", "אפשטעלן")); self.link_btn.clicked.disconnect()
        self.link_btn.clicked.connect(lambda: self.link_job and self.link_job.stop())
        self.link_job.start()

    def link_progress(self, what, f):
        self.link_status.setText(both("Getting the video: %s" % what, "מען נעמט אראפ דעם ווידעא"))
        if f < 0:
            self.link_bar.setRange(0, 0)
        else:
            self.link_bar.setRange(0, 1000); self.link_bar.setValue(int(f * 1000))

    def link_got(self, path):
        self.add_files([path])

    def link_failed(self, url, msg):
        self.link_errors[url] = msg
        log("link failed %s: %s" % (url, msg))

    def link_done(self):
        self.link_job.wait()
        self.link_job = None
        self.link_bar.hide()
        self.link_btn.setText(both("Get the video", "אראפנעמען")); self.link_btn.clicked.disconnect()
        self.link_btn.clicked.connect(self.link_go)
        if self.link_errors:
            self.link_status.setStyleSheet("color: #b02a37;")
            self.link_status.setText("\n".join("%s\n   %s" % (u if len(u) < 80 else u[:77] + "...", m)
                                               for u, m in self.link_errors.items()))
            self.link_errors = {}
        else:
            self.link_status.setStyleSheet("color: #1e7e34;")
            self.link_status.setText(both("Got it - the video is in the list above, ready to type.",
                                          "פארטיג - דער ווידעא איז אין דער ליסטע"))

    def dropped(self, paths):
        if paths:
            self.add_files(paths)
        else:
            self.pick()

    def set_file(self, p):
        """One file (the v1.0 way): the list becomes just this file."""
        self.files = []
        self.add_files([p])

    def add_files(self, paths):
        new = []
        for p in paths:
            p = os.path.abspath(p)
            if os.path.isfile(p) and p not in self.files:
                self.files.append(p); new.append(p)
        if self.job:                 # typing already: the new ones wait their turn
            self.queue.extend(n for n in new if n not in self.queue)
            self.show_queue()
        self.show_files()
        if new:
            log("files added: %d (now %d)" % (len(new), len(self.files)))

    def clear_files(self):
        if self.job:
            return
        self.files = []
        self.show_files()

    def show_files(self):
        if not self.files:
            self.file_label.setText("No file chosen yet.")
            self.clear_btn.hide()
            return
        self.clear_btn.setVisible(len(self.files) > 1 or bool(self.results))
        lines = []
        for n, p in enumerate(self.files, 1):
            mb = os.path.getsize(p) / 1e6 if os.path.exists(p) else 0
            size = "%.0f MB" % mb if mb >= 1 else "%.0f KB" % (mb * 1000)
            mark = ""
            if p in self.problems:
                mark = "   - did not work"
            elif p == self.path and self.job:
                mark = "   - typing now"
            elif p in self.results:
                mark = "   - done"
            lines.append("%d.  %s   (%s)%s" % (n, os.path.basename(p), size, mark))
        head = "Chosen:" if len(self.files) == 1 else "%d files chosen - they are typed one after another:" % len(self.files)
        self.file_label.setText(head + "\n" + "\n".join(lines))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        urls = [u for u in urls if os.path.isfile(u)]
        if urls:
            self.add_files(urls)
            return
        us = dropped_links(e.mimeData())
        if us:
            self.get_links(us)

    def file_name(self, lang, path=None):
        base = os.path.splitext(os.path.basename(path or self.path or "text"))[0]
        return "%s - %s.txt" % (base, NAME_EN[lang])

    # -- the AI helper
    def open_ai(self):
        if self.ai_dlg is None:
            self.ai_dlg = AIDialog(self)
        self.ai_dlg.refresh()
        self.ai_dlg.show(); self.ai_dlg.raise_(); self.ai_dlg.activateWindow()
        self.ai_dlg.warm()
        return self.ai_dlg

    def ai_langs(self):
        """The languages there is text in now (the spoken one while it is being typed too)."""
        out = [l for l, t in self.tabs_by_lang.items() if t.edit.toPlainText().strip()]
        if self.job and self.run_spoken not in out and self.partial_raw.strip():
            out.insert(0, self.run_spoken)
        return out

    def ai_text(self, lang):
        tab = self.tabs_by_lang.get(lang)
        t = tab.edit.toPlainText() if tab else ""
        if not t.strip() and self.job and lang == self.run_spoken:
            t = self.partial.toPlainText()
        return t

    def ai_apply(self, lang, changes, remember=False):
        """He pressed OK: change the shown text, the saved files and (while typing) every line still to come.
        -> number of places changed now."""
        changes = [(f, r) for f, r in changes if f and f != r]
        if not changes:
            return 0
        log("ai apply %s %r (typing: %s)" % (lang, changes, bool(self.job)))
        n = 0
        if self.job:
            self.ai_rules.setdefault(lang, []).extend(changes)      # the job reads these for the lines to come
            if lang == self.run_spoken:
                n += sum(self.partial_raw.count(f) for f, _r in changes)
                self.show_partial(self.partial_raw)
        path = self.shown_path()
        tab = self.tabs_by_lang.get(lang)
        if tab and tab.edit.toPlainText():
            new, k = ai.apply(tab.edit.toPlainText(), changes)
            if k:
                tab.edit.setPlainText(new)
                if path in self.results:
                    self.results[path][lang] = new
                try:
                    d = os.path.join(docs_dir(), "Hafutza Typing")
                    os.makedirs(d, exist_ok=True)
                    write_text(os.path.join(d, self.file_name(lang, path)), new)
                except Exception as e:
                    log("ai autosave failed %r" % e)
            n = max(n, k)
        if not self.job and path:
            try:
                self.ai_fix_project(path, {lang: changes})
            except Exception:
                log("ai project fix failed: " + traceback.format_exc())
        if remember:
            spoken = self.run_spoken if getattr(self, "run_spoken", None) else None
            for f, r in changes:
                try:
                    learn.add("speech" if lang == spoken else "tr", lang, f, r)
                except Exception as e:
                    log("ai remember failed %r" % e)
        return n

    def ai_fix_project(self, path, rules):
        """Apply the changes to the saved timings file (for watching with the text) and its .txt/.srt files."""
        if not path or not any(rules.values()):
            return
        proj = project.load(path)
        if not proj:
            return
        langs, k = [], 0
        for seg in proj.get("segments", []):
            for l, ch in rules.items():
                if ch and l in seg.get("t", {}):
                    seg["t"][l], c = ai.apply(seg["t"][l], ch)
                    if c and l not in langs:
                        langs.append(l)
                    k += c
        if k:
            project.save(proj)
            project.export(proj, docs_dir(), langs=langs)
            log("ai project fix: %d places in %s" % (k, langs))

    # -- run
    def choice(self):
        spoken = next(c for c, b in self.spoken_btn.items() if b.isChecked())
        targets = [c for c, b in self.target_box.items() if b.isChecked()]
        return spoken, targets

    def start(self, _=None, auto=False):
        self.files = [p for p in self.files if os.path.isfile(p)]
        if not self.files:
            self.show_files()
            QMessageBox.information(self, TITLE, both("First choose a video or audio file (step 1).",
                                                      "קלייבט קודם אויס א פייל"))
            return False
        spoken, targets = self.choice()
        if not targets:
            QMessageBox.information(self, TITLE, both("Tick at least one language to type it out in (step 3).",
                                                      "צייכנט אן כאטש איין שפראך"))
            return False
        miss = engine.missing(engine.needed(spoken, targets))
        if miss:
            d = FetchDialog(self, miss, auto=auto)
            if not d.exec() or engine.missing(miss):
                return False
        self.run_spoken, self.run_targets = spoken, targets
        self.queue = list(self.files)
        self.results, self.problems = {}, {}
        self.ai_rules = {}
        self.run_t0 = time.time()
        self.all_times = {}
        self.view_pick.blockSignals(True); self.view_pick.clear(); self.view_pick.blockSignals(False)
        self.view_row.hide()
        self.start_btn.hide(); self.stop_btn.show()
        for w in (*self.spoken_btn.values(), *self.target_box.values(), self.clear_btn):
            w.setEnabled(False)
        self.next_file()
        return True

    def next_file(self):
        self.path = self.queue.pop(0)
        spoken, targets = self.run_spoken, self.run_targets
        self.results[self.path] = {}
        self.make_tabs(targets)
        self.tabs.hide()
        self.watch_btn.hide()
        self.partial.clear(); self.partial.show()
        rtl = spoken in RTL
        self.partial.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
        opt = QTextOption(Qt.AlignRight if rtl else Qt.AlignLeft)
        opt.setTextDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.partial.document().setDefaultTextOption(opt)
        self.bar.setValue(0); self.bar.show()
        self.partial_raw = ""
        self.job = Job(self.path, spoken, targets, self.ai_rules)
        self.show_queue()
        self.show_files()
        self.job.status.connect(self.status.setText)
        self.job.progress.connect(self.on_progress)
        self.job.partial.connect(self.show_partial)
        self.job.result.connect(self.got)
        self.job.done.connect(self.finished_)
        self.job.start()

    def show_queue(self):
        total = len(self.results) + len(self.queue)
        if total > 1 and self.path:
            n = len(self.results)
            self.queue_label.setText("File %d of %d:  %s   -   פייל %d פון %d"
                                     % (n, total, os.path.basename(self.path), n, total))
            self.queue_label.show()
        else:
            self.queue_label.hide()

    def make_tabs(self, targets, texts=None):
        self.tabs.clear()
        self.tabs_by_lang = {}
        for t in targets:
            tab = ResultTab(self, t)
            self.tabs_by_lang[t] = tab
            self.tabs.addTab(tab, "%s  %s" % (NAME_YI[t], NAME_EN[t]) if t != "en" else "English")
            if texts and texts.get(t):
                tab.edit.setPlainText(texts[t])

    def shown_path(self):
        if self.job:
            return self.path
        i = self.view_pick.currentIndex()
        if self.view_row.isVisible() and i >= 0:
            return self.view_pick.itemData(i)
        return self.path

    def show_file(self, i):
        if self.job or i < 0:
            return
        p = self.view_pick.itemData(i)
        self.make_tabs(self.run_targets, self.results.get(p, {}))
        self.tabs.setCurrentIndex(0)
        self.tabs.show()
        self.show_watch()

    def on_progress(self, f):
        if f <= 0:
            self.bar.setRange(0, 0)          # moving "busy" bar until the first real progress comes in
        else:
            if self.bar.maximum() == 0:
                self.bar.setRange(0, 1000)
            self.bar.setValue(int(f * 1000))

    def show_partial(self, text):
        self.partial_raw = text
        rules = self.ai_rules.get(self.run_spoken)
        self.partial.setPlainText(ai.apply(text, rules)[0] if rules else text)
        if self.ai_dlg is not None:
            self.ai_dlg.refresh()

    def got(self, lang, text):
        if self.job is not None:     # AI fixes he pressed OK on after the job made this text
            text = ai.apply(text, self.ai_rules.get(lang, [])[self.job.emitted.get(lang, 0):])[0]
        if self.path in self.results:
            self.results[self.path][lang] = text
        tab = self.tabs_by_lang.get(lang)
        if tab:
            tab.edit.setPlainText(text)
            self.tabs.show()
            try:
                d = os.path.join(docs_dir(), "Hafutza Typing")
                os.makedirs(d, exist_ok=True)
                write_text(os.path.join(d, self.file_name(lang)), text)
            except Exception as e:
                log("autosave failed %r" % e)

    def finished_(self, ok, msg):
        self.job.wait()
        try:                     # an OK pressed in the last moments, after the job wrote its files
            if self.job.made is not None:
                self.ai_fix_project(self.path, {l: r[self.job.made.get(l, 0):] for l, r in self.ai_rules.items()})
        except Exception:
            log("ai project fix failed: " + traceback.format_exc())
        self.last_times = dict(self.job.times)
        self.all_times[os.path.basename(self.path)] = dict(self.job.times)
        stopped = self.job._stop
        self.job = None
        if not ok:
            self.problems[self.path] = msg.splitlines()[0] if msg else "did not work"
        if self.queue and not stopped:
            self.status.setText(msg)
            self.next_file()
            return
        # all done (or stopped)
        self.path_last = self.path
        n_files = len(self.results)
        good = [p for p in self.results if p not in self.problems]
        if n_files > 1:
            took = hms(time.time() - self.run_t0)
            if stopped:
                msg = both("Stopped. %d of %d files were typed." % (len(good), n_files + len(self.queue)), "אפגעשטעלט")
            elif self.problems:
                bad = ", ".join(os.path.basename(p) for p in self.problems)
                msg = both("Done: %d of %d files typed in %s. Did not work: %s" % (len(good), n_files, took, bad),
                           "פארטיג. %d פון %d פיילס" % (len(good), n_files))
            else:
                msg = both("Done! All %d files were typed (%s). Pick a file below to see its text." % (n_files, took),
                           "פארטיג! אלע %d פיילס זענען אויפגעשריבן" % n_files)
            self.view_pick.blockSignals(True)
            self.view_pick.clear()
            for p in self.results:
                self.view_pick.addItem(os.path.basename(p) + ("   (did not work)" if p in self.problems else ""), p)
            self.view_pick.setCurrentIndex(self.view_pick.findData(self.path))
            self.view_pick.blockSignals(False)
            self.view_row.show()
        self.queue = []
        self.status.setText(msg)
        self.queue_label.hide()
        self.bar.hide(); self.partial.hide()
        self.stop_btn.hide(); self.start_btn.show()
        for w in (*self.spoken_btn.values(), *self.target_box.values(), self.clear_btn):
            w.setEnabled(True)
        self.show_files()
        self.show_watch()
        if self.ai_dlg is not None:
            self.ai_dlg.refresh()
        if self.tabs.count() and any(t.edit.toPlainText() for t in self.tabs_by_lang.values()):
            self.tabs.show()
            self.tabs.setCurrentIndex(0)
            QTimer.singleShot(100, lambda: self.scroll.ensureWidgetVisible(self.tabs, 0, 0))
        self.last_ok = ok if n_files <= 1 else (not stopped and not self.problems)

    # -- the video player
    def show_watch(self):
        p = self.shown_path()
        self.watch_btn.setVisible(bool(p and not self.job and project.load(p)))

    def open_player(self, video):
        try:
            import player
        except Exception as e:
            log("player not loaded: " + traceback.format_exc())
            QMessageBox.warning(self, TITLE, "The video player could not start (%s)." % e)
            return None
        proj = project.load(video) if video else None
        if not proj:
            QMessageBox.information(self, TITLE, both("This file has no saved timings. Type it again with this version to watch it with its text.",
                                                      "טייפט עס נאכאמאל מיט די נייע ווערסיע"))
            return None
        if not os.path.isfile(proj["video"]):
            QMessageBox.information(self, TITLE, both("The video file is not there any more:\n" + proj["video"],
                                                      "דער פייל איז נישטא מער"))
            return None
        old = self.players.get(proj["video"])
        if old is not None:
            try:
                old.showNormal(); old.raise_(); old.activateWindow()
                return old
            except RuntimeError:
                pass
        w = player.Player(self, proj, docs_dir())
        w.setAttribute(Qt.WA_DeleteOnClose)
        w.saved.connect(self.player_saved)
        w.destroyed.connect(lambda _=None, k=proj["video"]: self.players.pop(k, None))
        self.players[proj["video"]] = w
        w.show()
        return w

    def player_saved(self, video):
        proj = project.load(video)
        if not proj:
            return
        key = next((p for p in self.results if os.path.abspath(p) == os.path.abspath(video)), None)
        if key is None:
            return
        for l in self.results[key]:
            self.results[key][l] = project.text_of(proj, l)
        if self.shown_path() and os.path.abspath(self.shown_path()) == os.path.abspath(video):
            for l, tab in self.tabs_by_lang.items():
                if l in self.results[key]:
                    tab.edit.setPlainText(self.results[key][l])

    def my_videos(self):
        try:
            import player
            player.VideosDialog(self, docs_dir()).exec()
        except Exception as e:
            log("videos dialog: " + traceback.format_exc())
            QMessageBox.warning(self, TITLE, str(e))

    def learned_words(self):
        try:
            import player
            player.LearnedDialog(self).exec()
        except Exception as e:
            log("learned dialog: " + traceback.format_exc())
            QMessageBox.warning(self, TITLE, str(e))

    def stop(self):
        if self.job:
            self.job.stop()
            self.status.setText(both("Stopping ...", "מען שטעלט אפ"))

    def closeEvent(self, e):
        if self.job:
            r = QMessageBox.question(self, TITLE, both("It is still working. Stop and close?", "עס ארבעט נאך. אפשטעלן און צומאכן?"))
            if r != QMessageBox.Yes:
                e.ignore(); return
            self.job.stop(); self.job.wait()
        if self.link_job:
            self.link_job.stop(); self.link_job.wait()
        if self.ai_dlg is not None:
            self.ai_dlg.close()
        self.ai_server.close()
        super().closeEvent(e)


def first_start_offer(win):
    """On the first start (or any start while parts are missing), offer the one-time download."""
    try:
        miss = all_missing()
    except Exception as e:
        QMessageBox.warning(win, TITLE, str(e))
        return
    if miss:
        FetchDialog(win, miss, auto=True).exec()     # starts by itself: one download brings every part


# ------------------------------------------------------------------ self-test for the build machine
def selftest(app, win, a):
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    rep = {"file": a.selftest, "spoken": a.spoken, "targets": a.targets.split(","), "threads": engine.threads(),
           "cpu_count": os.cpu_count(), "app_dir": engine.app_dir()}
    shot = lambda name: win.grab().save(os.path.join(out, name + ".png"))

    def go():
        try:
            allf = [a.selftest] + list(a.more)
            if a.drop:              # a real drop of all the files onto the drop box, as from Windows Explorer
                md = QMimeData()
                md.setUrls([QUrl.fromLocalFile(os.path.abspath(f)) for f in allf])
                pos = QPointF(win.dropbox.width() / 2, win.dropbox.height() / 2)
                de = QDragEnterEvent(pos.toPoint(), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)
                QApplication.sendEvent(win.dropbox, de)
                rep["drag_highlight"] = win.dropbox.property("hot")
                shot("0-drag-over")
                QApplication.sendEvent(win.dropbox, QDropEvent(pos, Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier))
            else:
                win.set_file(a.selftest)
                win.add_files(a.more)
            rep["files_listed"] = list(win.files)
            win.spoken_btn[a.spoken].setChecked(True)
            for c, b in win.target_box.items():
                b.setChecked(c in rep["targets"])
            rep["missing_before"] = engine.missing()
            log("selftest: ready, missing %s" % rep["missing_before"])
            shot("1-ready")
            rep["all_missing_before"] = all_missing()
            if a.download and all_missing():
                d = FetchDialog(win, all_missing(), auto=True)
                QTimer.singleShot(4000, lambda: d.grab().save(os.path.join(out, "0-download.png")))
                t = time.time()
                d.exec()
                rep["download_seconds"] = time.time() - t
            rep["missing_after"] = engine.missing()
            rep["all_missing_after"] = all_missing()
            rep["ai_model_after"] = ai.model_file()
            log("selftest: missing after download %s; starting" % rep["missing_after"])
            if not win.start(auto=True):
                rep["error"] = "did not start"
                finish(3); return
            QTimer.singleShot(15000, lambda: shot("2-working"))
            poll = QTimer(win)        # watch from the window's own thread for the job to end

            def check():
                if win.job is None:
                    poll.stop()
                    after(getattr(win, "last_ok", False), win.status.text())
            poll.timeout.connect(check)
            poll.start(1000)
        except Exception:
            rep["error"] = traceback.format_exc()
            finish(4)

    def after(ok, msg):
        log("selftest: finished ok=%s %s" % (ok, msg.splitlines()[0] if msg else ""))
        rep["ok"], rep["message"] = ok, msg
        rep["times"] = getattr(win, "last_times", {})
        try:
            pr = project.load(win.path_last)
            rep["project_lines"] = len(pr["segments"]) if pr else 0
            rep["project_first"] = pr["segments"][:2] if pr else None
            rep["srt_saved"] = all(os.path.exists(os.path.join(docs_dir(), "Hafutza Typing", win.file_name(l, win.path_last)[:-4] + ".srt"))
                                   for l in rep["targets"])
            shot("5-watch-button")
            rep["watch_button"] = win.watch_btn.isVisible()
        except Exception:
            rep["project_error"] = traceback.format_exc()
        rep["texts"] = {}
        for i, (lang, tab) in enumerate(win.tabs_by_lang.items()):
            win.tabs.setCurrentIndex(i)
            app.processEvents()
            shot("3-done-%s" % lang)
            txt = tab.edit.toPlainText()
            rep["texts"][lang] = txt
            write_text(os.path.join(out, "text-%s.txt" % lang), txt)
        good = ok and all(rep["texts"].get(t, "").strip() for t in rep["targets"])
        if len(win.results) > 1 or a.more:
            rep["all_times"] = getattr(win, "all_times", {})
            rep["per_file"] = {}
            for n, (p, texts) in enumerate(win.results.items(), 1):
                rep["per_file"][os.path.basename(p)] = {l: len(t) for l, t in texts.items()}
                for l, t in texts.items():
                    write_text(os.path.join(out, "text-%d-%s.txt" % (n, l), ), t)
                saved = [os.path.exists(os.path.join(docs_dir(), "Hafutza Typing", win.file_name(l, p))) for l in rep["targets"]]
                rep["per_file"][os.path.basename(p)]["saved_in_documents"] = all(saved)
            win.view_pick.setCurrentIndex(0); app.processEvents(); shot("4-pick-file-1")
            rep["problems"] = win.problems
            good = (not win.problems and len(win.results) == len(rep["files_listed"]) and
                    all(all(v.get(t) for t in rep["targets"]) and v["saved_in_documents"] for v in rep["per_file"].values()))
        finish(0 if good else 2)

    def finish(code):
        with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        app.exit(code)

    QTimer.singleShot(1500, go)


PIPE = "HafutzaTyping-open-files"


def send_to_running(files):
    """Another Hafutza Typing is open: hand it these files (it adds them to its list). -> True if it took them."""
    from PySide6.QtNetwork import QLocalSocket
    msg = json.dumps([os.path.abspath(f) for f in files]).encode("utf-8")
    for _ in range(40):                       # the first window may still be starting: try for ~10 s
        s = QLocalSocket()
        s.connectToServer(PIPE)
        if s.waitForConnected(250):
            n = s.write(msg + b"\n")
            s.flush()
            if s.bytesToWrite():
                s.waitForBytesWritten(3000)
            answered = s.waitForReadyRead(5000) and bytes(s.readAll()).startswith(b"ok")
            log("hand-over: wrote %s of %d bytes, answer %s" % (n, len(msg) + 1, answered))
            s.disconnectFromServer()
            return answered or n == len(msg) + 1
        time.sleep(0.25)
    return False


def listen_for_files(win):
    """Files opened later ("Open with Hafutza Typing" on a video) come to this window."""
    from PySide6.QtNetwork import QLocalServer
    srv = QLocalServer(win)
    QLocalServer.removeServer(PIPE)
    if not srv.listen(PIPE):
        log("listen failed: %s" % srv.errorString())
        return None

    def take():
        while srv.hasPendingConnections():
            c = srv.nextPendingConnection()
            buf = bytearray()

            def read(c=c, buf=buf):
                buf.extend(bytes(c.readAll()))
                if buf.endswith(b"\n"):
                    try:
                        files = json.loads(buf.decode("utf-8"))
                        log("files from another start: %s" % files)
                        win.add_files(files)
                        win.showNormal() if win.isMinimized() else None
                        win.raise_(); win.activateWindow()
                    except Exception as e:
                        log("bad message %r" % e)
                    c.write(b"ok"); c.flush(); c.disconnectFromServer()
            c.readyRead.connect(read)
    srv.newConnection.connect(take)
    return srv


def click_test(app, win, a):
    """Build-machine test: a double click on the drop box opens the file browser once, and the chosen file is listed."""
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)
    calls = []

    def fake(*args, **kw):
        calls.append(args[2] if len(args) > 2 else "")
        return ([os.path.abspath(a.click_test)], "")
    QFileDialog.getOpenFileNames = staticmethod(fake)
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent

    def go():
        box = win.dropbox
        pos = QPointF(box.width() / 2, box.height() / 2)
        gpos = QPointF(box.mapToGlobal(pos.toPoint()))
        ev = lambda t: QMouseEvent(t, pos, gpos, Qt.LeftButton, Qt.LeftButton if t != QEvent.MouseButtonRelease
                                   else Qt.NoButton, Qt.NoModifier)
        for t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick, QEvent.MouseButtonRelease):
            QApplication.sendEvent(box, ev(t))
            app.processEvents()
        win.grab().save(os.path.join(out, "click-test.png"))
        rep = {"dialog_opened": len(calls), "start_folder": calls[0] if calls else None, "files": win.files,
               "label": win.file_label.text()}
        json.dump(rep, open(os.path.join(out, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log("click test: %s" % rep)
        app.exit(0 if len(calls) == 1 and win.files == [os.path.abspath(a.click_test)] else 2)
    QTimer.singleShot(1500, go)


def link_test(app, win, a):
    """Build-machine test: the first link is dropped onto the box (as dragged from a browser), the others pasted
    into the link box; report which became files (and how long their sound is) and which gave which message."""
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)
    us = a.link_test.split()
    errors = {}
    orig = win.link_failed

    def failed(u, m):
        errors[u] = m; orig(u, m)
    win.link_failed = failed

    def go():
        md = QMimeData(); md.setUrls([QUrl(us[0])])
        pos = QPointF(win.dropbox.width() / 2, win.dropbox.height() / 2)
        QApplication.sendEvent(win.dropbox, QDragEnterEvent(pos.toPoint(), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier))
        QApplication.sendEvent(win.dropbox, QDropEvent(pos, Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier))
        if len(us) > 1:
            win.link_edit.setText("  ".join(us[1:])); win.link_go()
        t = time.time()
        poll = QTimer(win)

        def check():
            if win.link_job is None or time.time() - t > 600:
                poll.stop()
                win.grab().save(os.path.join(out, "links.png"))
                rep = {"links": us, "files": [], "errors": errors, "seconds": time.time() - t}
                for f in win.files:
                    try:
                        x = engine.read_sound(f, tempfile.mkdtemp(), lambda v: None, lambda: False)
                        secs = len(x) / engine.RATE
                    except Exception as e:
                        secs = "unreadable: %r" % e
                    try:
                        import av
                        with av.open(f) as c:
                            vs = [v for v in c.streams.video]
                            pic = "%dx%d" % (vs[0].codec_context.width, vs[0].codec_context.height) if vs else "none"
                    except Exception as e:
                        pic = "unreadable: %r" % e
                    rep["files"].append({"name": os.path.basename(f), "bytes": os.path.getsize(f), "sound_seconds": secs,
                                         "picture": pic})
                json.dump(rep, open(os.path.join(out, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                log("link test: %s" % rep)
                app.exit(0)
        poll.timeout.connect(check); poll.start(1000)
    QTimer.singleShot(1500, go)


def update_test(app, win, a):
    """Build-machine test: press Update by itself against a test update.json; report what happened."""
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)

    def report(text, code):
        rep = {"version": VERSION, "result": text}
        json.dump(rep, open(os.path.join(out, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log("update test: %s" % rep)
        try:
            d.grab().save(os.path.join(out, "update-dialog.png"))
        except Exception:
            pass
        app.exit(code)

    d = win.do_update(url=a.update_test or None, auto=True)     # "" = the published update.json
    d.on_auto_done = report
    QTimer.singleShot(4000, lambda: d.grab().save(os.path.join(out, "update-dialog-4s.png")))
    d.show()


def badge_test(app, win, a):
    """Build-machine test: the start look against a test update.json; the Update button must be blue only when newer."""
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)

    def rep():
        b = win.update_btn
        img = b.grab().toImage()
        c = img.pixelColor(4, img.height() // 2)
        blue = c.blue() > c.red() + 60 and c.blue() > 150
        r = {"version": VERSION, "news": b.property("news") == "true", "blue": blue, "text": b.text(),
             "pixel": [c.red(), c.green(), c.blue()]}
        json.dump(r, open(os.path.join(out, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        b.grab().save(os.path.join(out, "button.png")); win.grab().save(os.path.join(out, "window.png"))
        log("badge test: %s" % r)
        want = a.expect == "blue"
        app.exit(0 if (r["news"] == want and blue == want) else 1)

    win.quiet_check(a.badge_test)
    QTimer.singleShot(int((a.report_after or 8) * 1000), rep)


def request_test(app, win, a):
    """Build-machine test of Update -> Request an update: 1) no internet: the request is kept;
    2) internet back: the kept one goes; 3) a new one is sent and "Got it" shows. Exit 0 only if all three held."""
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)
    rep = {"version": VERSION}
    d = UpdateDialog(win, known={"version": VERSION, "newer": False, "url": "", "sha256": "", "size": 0})
    d.show()
    rp = d.req
    tag = a.request_test

    def shot(name):
        try:
            d.grab().save(os.path.join(out, name))
        except Exception as e:
            log("shot %r" % e)

    def finish(code):
        rep["pending_end"] = len(requests_out.pending())
        rep["code"] = code
        json.dump(rep, open(os.path.join(out, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log("request test: %s" % rep)
        app.exit(code)

    def wait_send(then):
        t = QTimer(d)
        def chk():
            if rp.th is None and rp.result:
                t.stop(); then()
        t.timeout.connect(chk); t.start(300)

    def step1():
        shot("update-tab.png")
        d.tabs.setCurrentIndex(1)
        rp.kb_btn.click()
        letters = [k for k in rp.kb.keys if len(k) == 1 and k != " "][:3]
        for k in letters:
            rp.kb.keys[k].click()
        rp.kb.keys["back"].click()
        rep["keyboard_typed"] = rp.box.toPlainText()
        rep["keyboard_ok"] = rp.box.toPlainText() == "".join(letters[:2])
        rp.box.insertPlainText(" CI TEST 1 (no internet) %s" % tag)
        os.environ["HAFUTZA_REQUEST_URL"] = "http://127.0.0.1:9/nothing"
        rp.result = ""
        rp.send_btn.click()
        wait_send(step2)

    def step2():
        rep["first"] = rp.result
        rep["pending_after_first"] = len(requests_out.pending())
        rep["first_status"] = rp.status.text()
        shot("request-kept.png")
        os.environ.pop("HAFUTZA_REQUEST_URL", None)
        try:
            rep["flushed"] = requests_out.flush(VERSION)
        except Exception as e:
            rep["flushed"] = "error %r" % e
        rep["pending_after_flush"] = len(requests_out.pending())
        rp.box.setPlainText("CI TEST 2 (internet on) %s" % tag)
        rp.result = ""
        rp.send_btn.click()
        wait_send(step3)

    def step3():
        rep["second"] = rp.result
        rep["second_status"] = rp.status.text()
        shot("request-sent.png")
        ok = (rep["first"] == "kept" and rep["pending_after_first"] == 1 and rep["flushed"] == 1
              and rep["pending_after_flush"] == 0 and rep["second"] == "sent" and "Got it" in rep["second_status"]
              and rep["keyboard_ok"])
        finish(0 if ok else 1)

    QTimer.singleShot(1500, step1)
    QTimer.singleShot(120000, lambda: finish(2))


def ai_test(app, win, a):
    """Build-machine test of the AI helper.
    Model missing: the window opens, the AI button shows the one-time download offer (exit 0 with --ai-expect-missing).
    Model there: start typing; while it types, ask (in English) to change a word that is in the typed lines, press OK,
    and check every later line, the tab, the saved .txt and the timings file have the change; then ask (in Yiddish)
    for a change in the English translation and check it too. Exit 0 only if all held."""
    import re as _re
    from collections import Counter
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)
    rep = {"version": VERSION, "file": a.ai_test, "model": ai.model_file(), "server": ai.server_exe(),
           "ram_gb": round(ai.ram_gb(), 1), "steps": []}
    st = {"t0": time.time()}
    targets = a.targets.split(",")

    def note(s):
        rep["steps"].append("%6.1f  %s" % (time.time() - st["t0"], s))
        log("ai test: " + s)

    def shot(w, name):
        try:
            w.grab().save(os.path.join(out, name + ".png"))
        except Exception as e:
            log("shot %r" % e)

    def finish(code):
        rep["code"] = code
        rep["seconds"] = round(time.time() - st["t0"], 1)
        try:
            rep["times"] = getattr(win, "last_times", {})
        except Exception:
            pass
        with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        win.ai_server.close()
        app.exit(code)

    def every(ms, fn):
        t = QTimer(win)
        def tick():
            try:
                if fn():
                    t.stop()
            except Exception:
                t.stop()
                rep["error"] = traceback.format_exc()
                finish(4)
        t.timeout.connect(tick); t.start(ms)

    def start():
        win.set_file(a.ai_test)
        win.spoken_btn[a.spoken].setChecked(True)
        for c, b in win.target_box.items():
            b.setChecked(c in targets)
        shot(win, "ai-0-window")
        d = win.open_ai()
        app.processEvents()
        shot(d, "ai-1-dialog")
        rep["button"] = win.ai_btn.isVisible() and win.ai_btn.text()
        rep["download_offer"] = d.dl_btn.isVisible()
        rep["dialog_status"] = d.status.text()
        if not ai.model_file():
            note("model missing; download offer shown: %s" % rep["download_offer"])
            ok = rep["download_offer"] and bool(rep["server"]) and a.ai_expect_missing
            # the program still works without it: a short typing run
            if not win.start(auto=True):
                rep["typing_without_ai"] = "did not start"; finish(3); return
            def done0():
                if win.job is None:
                    rep["typing_without_ai"] = bool(getattr(win, "last_ok", False)) and \
                        all(t.edit.toPlainText().strip() for t in win.tabs_by_lang.values())
                    note("typing without the AI ok: %s" % rep["typing_without_ai"])
                    finish(0 if ok and rep["typing_without_ai"] else 1)
                    return True
            every(1000, done0)
            return
        if a.ai_expect_missing:
            rep["error"] = "the model was expected to be missing"; finish(5); return
        note("model there; warming the AI")

        def warmed():
            if d.th is None:
                rep["warm_ok"] = win.ai_server.running()
                rep["warm_status"] = d.status.text()
                note("warm-up done, running %s" % rep["warm_ok"])
                if not rep["warm_ok"]:
                    finish(6); return True
                if not win.start(auto=True):
                    rep["error"] = "typing did not start"; finish(3); return True
                note("typing started")
                every(1000, wait_lines)
                return True
        every(500, warmed)

    def wait_lines():
        if win.job is None:
            rep["error"] = "typing ended before 3 lines came"; finish(7); return True
        lines = [l for l in win.partial_raw.split("\n") if l.strip()]
        if len(lines) < 3:
            return False
        words = [w for w in _re.findall(r"[א-תװ-״יִ-ﭏ]+", win.partial_raw) if len(w) >= 4]
        if not words:
            return False
        W = Counter(words).most_common(1)[0][0]
        R = "הפצה־טעסט"
        st["W"], st["R"] = W, R
        rep["yi_word"], rep["yi_new"] = W, R
        rep["yi_word_count_at_ask"] = win.partial_raw.count(W)
        d = win.ai_dlg
        d.refresh()
        d.lang.setCurrentIndex(d.lang.findData(a.spoken))
        instr = 'Change "%s" to "%s" everywhere.' % (W, R)
        rep["yi_instruction"] = instr
        rep["yi_lines_at_ask"] = len(lines)
        note("asking during typing (%d lines typed): %s" % (len(lines), instr))
        st["ask_t"] = time.time()
        if not d.send(text=instr):
            rep["error"] = "could not ask"; finish(8); return True
        shot(d, "ai-2-thinking")
        every(500, yi_answered)
        return True

    def yi_answered():
        d = win.ai_dlg
        if d.th is not None:
            return False
        rep["yi_answer_seconds"] = round(time.time() - st["ask_t"], 1)
        rep["yi_suggested"] = [list(c) for c in d.changes]
        rep["yi_by"] = getattr(d, "last_by", "")
        rep["yi_log"] = d.log.toPlainText()
        shot(d, "ai-3-suggested")
        note("AI suggested %s in %.0f s" % (d.changes, rep["yi_answer_seconds"]))
        if not any(f == st["W"] for f, _r, _n in d.changes):
            rep["error"] = "the AI did not suggest the asked change"; finish(9); return True
        rep["typing_when_ok_pressed"] = win.job is not None
        rep["typing_progress_at_ok"] = win.bar.value() / 1000.0
        n = d.apply()
        rep["yi_places_fixed_at_ok"] = n
        rep["partial_after_ok_has_old"] = st["W"] in win.partial.toPlainText()
        rep["partial_after_ok_has_new"] = st["R"] in win.partial.toPlainText()
        shot(win, "ai-4-after-ok-while-typing")
        note("pressed OK while typing: %s; %d places" % (rep["typing_when_ok_pressed"], n))
        every(2000, typing_done)
        return True

    def typing_done():
        if win.job is not None:
            return False
        rep["typing_ok"] = bool(getattr(win, "last_ok", False))
        note("typing finished ok=%s" % rep["typing_ok"])
        W, R = st["W"], st["R"]
        sp = a.spoken
        tab = win.tabs_by_lang[sp].edit.toPlainText()
        pr = project.load(win.path_last) or {"segments": []}
        ptxt = project.text_of(pr, sp)
        try:
            dtxt = open(os.path.join(docs_dir(), "Hafutza Typing", win.file_name(sp, win.path_last)), encoding="utf-8").read()
        except Exception as e:
            dtxt = "(missing %r)" % e
        rep["yi_check"] = {"tab_old": tab.count(W), "tab_new": tab.count(R), "project_old": ptxt.count(W),
                           "project_new": ptxt.count(R), "docs_old": dtxt.count(W), "docs_new": dtxt.count(R),
                           "job_fixed_later_lines": getattr(win, "last_times", {}).get("ai_fixes_" + sp, 0)}
        write_text(os.path.join(out, "ai-text-%s.txt" % sp), tab)
        c = rep["yi_check"]
        rep["yi_ok"] = (rep["typing_ok"] and c["tab_old"] == 0 and c["project_old"] == 0 and c["docs_old"] == 0
                        and c["tab_new"] > 0 and c["project_new"] > 0 and c["docs_new"] > 0)
        note("Yiddish fix check %s" % c)
        others = [t for t in targets if t != sp]
        if not others:
            finish(0 if rep["yi_ok"] else 1); return True
        tl = others[0]
        st["tl"] = tl
        ttxt = win.tabs_by_lang[tl].edit.toPlainText()
        stop = {"which", "there", "their", "about", "would", "these", "those", "where", "being", "other", "because"}
        ws = [w for w in _re.findall(r"[A-Za-z]+", ttxt) if len(w) >= 5 and w.lower() not in stop]
        if not ws:
            rep["error"] = "no words in the translation"; finish(10); return True
        w = Counter(ws).most_common(1)[0][0]
        st["w"], st["r"] = w, "Hafutza"
        rep["tr_word"] = w
        rep["tr_word_count"] = ttxt.count(w)
        d = win.ai_dlg
        d.refresh()
        d.lang.setCurrentIndex(d.lang.findData(tl))
        instr = 'טוישט "%s" אויף "Hafutza"' % w
        rep["tr_instruction"] = instr
        note("asking in Yiddish about the %s text: %s" % (tl, instr))
        st["ask_t"] = time.time()
        if not d.send(text=instr):
            rep["error"] = "could not ask (2)"; finish(8); return True
        every(500, tr_answered)
        return True

    def tr_answered():
        d = win.ai_dlg
        if d.th is not None:
            return False
        rep["tr_answer_seconds"] = round(time.time() - st["ask_t"], 1)
        rep["tr_suggested"] = [list(c) for c in d.changes]
        rep["tr_by"] = getattr(d, "last_by", "")
        shot(d, "ai-5-suggested-translation")
        note("AI suggested %s in %.0f s" % (d.changes, rep["tr_answer_seconds"]))
        w, r, tl = st["w"], st["r"], st["tl"]
        if not any(f == w for f, _r, _n in d.changes):
            rep["error"] = "the AI did not suggest the asked change (translation)"; finish(9); return True
        n = d.apply()
        tab = win.tabs_by_lang[tl].edit.toPlainText()
        pr = project.load(win.path_last) or {"segments": []}
        ptxt = project.text_of(pr, tl)
        try:
            dtxt = open(os.path.join(docs_dir(), "Hafutza Typing", win.file_name(tl, win.path_last)), encoding="utf-8").read()
        except Exception as e:
            dtxt = "(missing %r)" % e
        rep["tr_check"] = {"fixed": n, "tab_old": tab.count(w), "tab_new": tab.count(r), "project_old": ptxt.count(w),
                           "project_new": ptxt.count(r), "docs_old": dtxt.count(w), "docs_new": dtxt.count(r)}
        write_text(os.path.join(out, "ai-text-%s.txt" % tl), tab)
        shot(win, "ai-6-after-ok-translation")
        c = rep["tr_check"]
        rep["tr_ok"] = (n > 0 and c["tab_old"] == 0 and c["project_old"] == 0 and c["docs_old"] == 0
                        and c["tab_new"] > 0 and c["project_new"] > 0 and c["docs_new"] > 0)
        note("translation fix check %s" % c)
        good = rep["yi_ok"] and rep["tr_ok"] and rep.get("typing_when_ok_pressed")
        finish(0 if good else 1)
        return True

    QTimer.singleShot(1500, start)
    QTimer.singleShot(int(a.ai_timeout * 1000), lambda: (rep.__setitem__("error", "timed out"), finish(11)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--selftest"); ap.add_argument("--spoken", default="yi"); ap.add_argument("--targets", default="yi")
    ap.add_argument("--out", default="selftest"); ap.add_argument("--download", action="store_true")
    ap.add_argument("--more", action="append", default=[]); ap.add_argument("--drop", action="store_true")
    ap.add_argument("--update-test"); ap.add_argument("--click-test"); ap.add_argument("--link-test"); ap.add_argument("--report-after", type=float)
    ap.add_argument("--player-test"); ap.add_argument("--request-test"); ap.add_argument("--badge-test"); ap.add_argument("--expect", default="blue")
    ap.add_argument("--ai-test"); ap.add_argument("--ai-expect-missing", action="store_true"); ap.add_argument("--ai-timeout", type=float, default=3600)
    a, _ = ap.parse_known_args()
    files = [f for f in a.files if os.path.isfile(f)]
    test = bool(a.selftest or a.update_test is not None or a.click_test or a.link_test or a.player_test or a.request_test or a.ai_test)
    other = updater.hold_mutex()
    app = QApplication(sys.argv)
    app.setApplicationName(TITLE)
    if other and files and not test and sys.platform == "win32":
        if send_to_running(files):
            log("files handed to the open window: %s" % files)
            os._exit(0)          # end at once (a normal Python/Qt shutdown here could hang on Windows)
    f = QFont("Segoe UI", 12)
    app.setFont(f)
    app.setStyleSheet(STYLE)
    ico = os.path.join(engine.app_dir(), "hafutza.ico")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    log("start %s, %s threads, app dir %s, files %s" % (VERSION, engine.threads(), engine.app_dir(), files))
    win = Window()
    win.fit_screen()
    if not test:
        win._srv = listen_for_files(win)
    if files:
        win.add_files(files)
    if a.selftest:
        selftest(app, win, a)
    elif a.update_test is not None:
        update_test(app, win, a)
    elif a.click_test:
        click_test(app, win, a)
    elif a.link_test:
        link_test(app, win, a)
    elif a.request_test:
        request_test(app, win, a)
    elif a.ai_test:
        ai_test(app, win, a)
    elif a.badge_test:
        badge_test(app, win, a)
    elif a.player_test:
        import player
        player.player_test(app, win, a.player_test, os.path.abspath(a.out))
    elif a.report_after:
        def rep():
            out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)
            json.dump({"version": VERSION, "files": win.files, "update_button": win.update_btn.text()}, open(os.path.join(out, "report.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            win.grab().save(os.path.join(out, "files.png"))
            app.exit(0)
        QTimer.singleShot(int(a.report_after * 1000), rep)
        QTimer.singleShot(1000, win.quiet_check)
    else:
        QTimer.singleShot(600, lambda: first_start_offer(win))
        QTimer.singleShot(3000, win.quiet_check)
    rc = app.exec()
    log("exit %s" % rc)
    if sys.platform == "win32":
        os._exit(rc)             # be really gone: the update installer waits for this program to close
    return rc


if __name__ == "__main__":
    sys.exit(main())
