"""Hafutza Typing (offline) - the window.

Pick a video or audio file, the language spoken in it, the languages to type it out in; press Start.
Everything runs on this computer; nothing is sent anywhere. (The only internet use: the one-time download of the parts
for translation and Hebrew / English / Spanish / French speech, if they are not here yet.)

Self-test (used by the build machine):
  HafutzaTyping.exe --selftest FILE --spoken yi --targets yi,en,he,es,fr --out DIR [--download]
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
    from PySide6.QtCore import Qt, QThread, Signal, QTimer, QStandardPaths
    from PySide6.QtGui import QFont, QTextOption, QIcon
    from PySide6.QtWidgets import (QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel,
                                   QPushButton, QRadioButton, QCheckBox, QButtonGroup, QProgressBar, QTabWidget,
                                   QPlainTextEdit, QFileDialog, QMessageBox, QGroupBox, QScrollArea, QDialog, QFrame)

    import engine
    from engine import LANGS, NAME_YI, NAME_EN, log
except Exception:
    _excepthook(*sys.exc_info())
    raise

TITLE = "Hafutza Typing"
VERSION = "1.0"
RTL = ("yi", "he")
FILE_TYPES = ("Video or audio (*.mp4 *.mov *.mkv *.avi *.wmv *.webm *.m4v *.3gp *.flv *.mpg *.mpeg *.ts *.mts "
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

    def __init__(self, path, spoken, targets):
        super().__init__()
        self.path, self.spoken, self.targets = path, spoken, targets
        self._stop = False
        self.times = {}

    def stop(self):
        self._stop = True

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

            text = engine.transcribe(x, self.spoken, prog, stop)
            self.times["typing"] = time.time() - t1
            del x
            if not text:
                self.done.emit(False, both("No speech could be heard in this file.", "מען האט נישט געהערט קיין רעדן אין דעם פייל"))
                return
            if self.spoken in self.targets:
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
                        self.result.emit(tgt, out)
                        self.times["translate_" + tgt] = time.time() - t2
                finally:
                    tr.close()
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
                what = "%s (%d of %d, %.1f GB)" % (engine.MODEL_WHAT[k], n, len(self.keys), engine.manifest()[k]["size"] / 1e9)
                self.progress.emit(what, 0.0)
                mark = [0]

                def prog(d, t, what=what, mark=mark):
                    self.progress.emit(what, d / t)
                    if d / t >= mark[0] + 0.1:
                        mark[0] += 0.1
                        log("download %s %.0f%%" % (k, 100 * d / t))
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
        gb = sum(engine.manifest()[k]["size"] for k in keys) / 1e9
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
        start = os.path.join(os.path.dirname(self.win.path or "") or docs_dir(), self.win.file_name(self.lang))
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


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.path = None
        self.job = None
        self.tabs_by_lang = {}
        self.setAcceptDrops(True)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setSpacing(10)
        head = QHBoxLayout()
        t = QLabel(TITLE)
        f = t.font(); f.setPointSize(22); f.setBold(True); t.setFont(f)
        head.addWidget(t)
        head.addStretch(1)
        lay.addLayout(head)
        sub = QHBoxLayout()
        sub.addWidget(QLabel("Video or recording in, typed text out. No internet needed."))
        sub.addStretch(1)
        sub.addWidget(RTLLabel("א ווידעא אדער רעקארדירונג אריין, געשריבענע טעקסט ארויס"))
        lay.addLayout(sub)

        # 1 - the file
        g1 = QGroupBox("1.  The file  -  דער פייל")
        l1 = QVBoxLayout(g1)
        self.choose = QPushButton(both("Choose a video or audio file ...", "קלייבט אויס א ווידעא אדער קול פייל"))
        self.choose.setObjectName("choose")
        self.choose.clicked.connect(self.pick)
        l1.addWidget(self.choose)
        self.file_label = QLabel("No file chosen yet. (You can also drag a file onto this window.)")
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
        self.resize(1000, 860)

    def fit_screen(self):
        """Show the window whole on a small laptop screen: there it opens filling the screen."""
        scr = self.screen().availableGeometry() if self.screen() else None
        if scr is not None and (scr.height() < 900 or scr.width() < 1040):
            self.showMaximized()
        else:
            self.show()

    # -- file
    def pick(self):
        start = os.path.dirname(self.path) if self.path else (
            QStandardPaths.writableLocation(QStandardPaths.MoviesLocation) or docs_dir())
        p, _ = QFileDialog.getOpenFileName(self, "Choose a video or audio file", start, FILE_TYPES)
        if p:
            self.set_file(p)

    def set_file(self, p):
        self.path = os.path.abspath(p)
        mb = os.path.getsize(self.path) / 1e6
        self.file_label.setText("Chosen:  %s   (%s)" % (os.path.basename(self.path),
                                                       "%.0f MB" % mb if mb >= 1 else "%.0f KB" % (mb * 1000)))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls and os.path.isfile(urls[0]):
            self.set_file(urls[0])

    def file_name(self, lang):
        base = os.path.splitext(os.path.basename(self.path or "text"))[0]
        return "%s - %s.txt" % (base, NAME_EN[lang])

    # -- run
    def choice(self):
        spoken = next(c for c, b in self.spoken_btn.items() if b.isChecked())
        targets = [c for c, b in self.target_box.items() if b.isChecked()]
        return spoken, targets

    def start(self, _=None, auto=False):
        if not self.path or not os.path.isfile(self.path):
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
        self.tabs.clear()
        self.tabs_by_lang = {}
        for t in targets:
            tab = ResultTab(self, t)
            self.tabs_by_lang[t] = tab
            self.tabs.addTab(tab, "%s  %s" % (NAME_YI[t], NAME_EN[t]) if t != "en" else "English")
        self.tabs.hide()
        self.partial.clear(); self.partial.show()
        rtl = spoken in RTL
        self.partial.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
        opt = QTextOption(Qt.AlignRight if rtl else Qt.AlignLeft)
        opt.setTextDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.partial.document().setDefaultTextOption(opt)
        self.bar.setValue(0); self.bar.show()
        self.start_btn.hide(); self.stop_btn.show()
        for w in (self.choose, *self.spoken_btn.values(), *self.target_box.values()):
            w.setEnabled(False)
        self.job = Job(self.path, spoken, targets)
        self.job.status.connect(self.status.setText)
        self.job.progress.connect(self.on_progress)
        self.job.partial.connect(self.partial.setPlainText)
        self.job.result.connect(self.got)
        self.job.done.connect(self.finished_)
        self.job.start()
        return True

    def on_progress(self, f):
        if f <= 0:
            self.bar.setRange(0, 0)          # moving "busy" bar until the first real progress comes in
        else:
            if self.bar.maximum() == 0:
                self.bar.setRange(0, 1000)
            self.bar.setValue(int(f * 1000))

    def got(self, lang, text):
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
        self.last_times = dict(self.job.times)
        self.job = None
        self.status.setText(msg)
        self.bar.hide(); self.partial.hide()
        self.stop_btn.hide(); self.start_btn.show()
        for w in (self.choose, *self.spoken_btn.values(), *self.target_box.values()):
            w.setEnabled(True)
        if self.tabs.count() and any(t.edit.toPlainText() for t in self.tabs_by_lang.values()):
            self.tabs.show()
            self.tabs.setCurrentIndex(0)
            QTimer.singleShot(100, lambda: self.scroll.ensureWidgetVisible(self.tabs, 0, 0))
        self.last_ok = ok

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
        super().closeEvent(e)


def first_start_offer(win):
    """On the first start (or any start while parts are missing), offer the one-time download."""
    try:
        miss = engine.missing()
    except Exception as e:
        QMessageBox.warning(win, TITLE, str(e))
        return
    if miss:
        FetchDialog(win, miss).exec()


# ------------------------------------------------------------------ self-test for the build machine
def selftest(app, win, a):
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    rep = {"file": a.selftest, "spoken": a.spoken, "targets": a.targets.split(","), "threads": engine.threads(),
           "cpu_count": os.cpu_count(), "app_dir": engine.app_dir()}
    shot = lambda name: win.grab().save(os.path.join(out, name + ".png"))

    def go():
        try:
            win.set_file(a.selftest)
            win.spoken_btn[a.spoken].setChecked(True)
            for c, b in win.target_box.items():
                b.setChecked(c in rep["targets"])
            rep["missing_before"] = engine.missing()
            log("selftest: ready, missing %s" % rep["missing_before"])
            shot("1-ready")
            if a.download and engine.missing():
                d = FetchDialog(win, engine.missing(), auto=True)
                QTimer.singleShot(4000, lambda: d.grab().save(os.path.join(out, "0-download.png")))
                t = time.time()
                d.exec()
                rep["download_seconds"] = time.time() - t
            rep["missing_after"] = engine.missing()
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
        rep["texts"] = {}
        for i, (lang, tab) in enumerate(win.tabs_by_lang.items()):
            win.tabs.setCurrentIndex(i)
            app.processEvents()
            shot("3-done-%s" % lang)
            txt = tab.edit.toPlainText()
            rep["texts"][lang] = txt
            write_text(os.path.join(out, "text-%s.txt" % lang), txt)
        good = ok and all(rep["texts"].get(t, "").strip() for t in rep["targets"])
        finish(0 if good else 2)

    def finish(code):
        with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        app.exit(code)

    QTimer.singleShot(1500, go)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest"); ap.add_argument("--spoken", default="yi"); ap.add_argument("--targets", default="yi")
    ap.add_argument("--out", default="selftest"); ap.add_argument("--download", action="store_true")
    a, _ = ap.parse_known_args()
    app = QApplication(sys.argv)
    app.setApplicationName(TITLE)
    f = QFont("Segoe UI", 12)
    app.setFont(f)
    app.setStyleSheet(STYLE)
    ico = os.path.join(engine.app_dir(), "hafutza.ico")
    if os.path.exists(ico):
        app.setWindowIcon(QIcon(ico))
    log("start %s, %s threads, app dir %s" % (VERSION, engine.threads(), engine.app_dir()))
    win = Window()
    win.fit_screen()
    if a.selftest:
        selftest(app, win, a)
    else:
        QTimer.singleShot(600, lambda: first_start_offer(win))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
