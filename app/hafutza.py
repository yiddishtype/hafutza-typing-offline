"""Hafutza Typing (offline) - the window.

Pick a video or audio file, the language spoken in it, the languages to type it out in; press Start.
Everything runs on this computer; nothing is sent anywhere. (The only internet use: the one-time download of the parts
for translation and Hebrew / English / Spanish / French speech, if they are not here yet.)

Self-test (used by the build machine):
  HafutzaTyping.exe --selftest FILE [--more FILE ...] [--drop] --spoken yi --targets yi,en,he,es,fr --out DIR [--download]
  HafutzaTyping.exe --update-test MANIFEST_URL --out DIR       (presses Update by itself; installs if newer)
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
QPushButton#update[news="true"] { background: #fff3cd; border: 2px solid #d39e00; font-weight: bold; }
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


class UpdateDialog(QDialog):
    """Update button: check -> "You have the newest version" or download + install + open again."""

    def __init__(self, parent, url=None, auto=False, known=None):
        super().__init__(parent)
        self.url, self.auto, self.m, self.th = url, auto, None, None
        self.result_text = ""
        self.setWindowTitle(TITLE + " - Update")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
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
        lay.addLayout(row)
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
            self.msg.setText(both("You have the newest version (%s)." % VERSION,
                                  "איר האט די נייסטע ווערסיע (%s)" % VERSION))
            self.done_auto(0)
        else:
            self.m = m
            self.bar.hide()
            notes = ("\n" + m["notes"]) if m.get("notes") else ""
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
    """Download the sound of one or more video links, one after another."""
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

    def quiet_check(self):
        """A quiet look at start: if there is a newer version, the Update button says so. No internet = nothing happens."""
        self._qc = UpdateCheck()
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
        self.partial.clear(); self.partial.show()
        rtl = spoken in RTL
        self.partial.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
        opt = QTextOption(Qt.AlignRight if rtl else Qt.AlignLeft)
        opt.setTextDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.partial.document().setDefaultTextOption(opt)
        self.bar.setValue(0); self.bar.show()
        self.show_queue()
        self.show_files()
        self.job = Job(self.path, spoken, targets)
        self.job.status.connect(self.status.setText)
        self.job.progress.connect(self.on_progress)
        self.job.partial.connect(self.partial.setPlainText)
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

    def on_progress(self, f):
        if f <= 0:
            self.bar.setRange(0, 0)          # moving "busy" bar until the first real progress comes in
        else:
            if self.bar.maximum() == 0:
                self.bar.setRange(0, 1000)
            self.bar.setValue(int(f * 1000))

    def got(self, lang, text):
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
        if self.tabs.count() and any(t.edit.toPlainText() for t in self.tabs_by_lang.values()):
            self.tabs.show()
            self.tabs.setCurrentIndex(0)
            QTimer.singleShot(100, lambda: self.scroll.ensureWidgetVisible(self.tabs, 0, 0))
        self.last_ok = ok if n_files <= 1 else (not stopped and not self.problems)

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
                    rep["files"].append({"name": os.path.basename(f), "bytes": os.path.getsize(f), "sound_seconds": secs})
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--selftest"); ap.add_argument("--spoken", default="yi"); ap.add_argument("--targets", default="yi")
    ap.add_argument("--out", default="selftest"); ap.add_argument("--download", action="store_true")
    ap.add_argument("--more", action="append", default=[]); ap.add_argument("--drop", action="store_true")
    ap.add_argument("--update-test"); ap.add_argument("--click-test"); ap.add_argument("--link-test"); ap.add_argument("--report-after", type=float)
    a, _ = ap.parse_known_args()
    files = [f for f in a.files if os.path.isfile(f)]
    test = bool(a.selftest or a.update_test is not None or a.click_test or a.link_test)
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
