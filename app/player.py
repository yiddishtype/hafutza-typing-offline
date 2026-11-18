"""Hafutza Typing: watch a typed video with its text on it, and fix the text.

Play / pause, back and forward 5, 10, 15 seconds, click a line to jump to it, fix a line (with an on-screen
Yiddish keyboard), save. Every fix is saved at once (and the .txt and .srt files are written again) and the
changed words are learned (learn.py) for the next videos.
"""
import os, time, traceback, json, re

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl, QSizeF, QRectF, QPointF, QEvent
from PySide6.QtGui import QFont, QColor, QBrush, QPen, QTextOption, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
                               QSlider, QListWidget, QListWidgetItem, QLineEdit, QCheckBox, QGraphicsView,
                               QGraphicsScene, QGraphicsTextItem, QGraphicsRectItem, QSplitter, QDialog, QTableWidget,
                               QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox, QMessageBox, QFrame,
                               QSizePolicy)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem

import engine, learn, project
from engine import NAME_EN, NAME_YI, log

RTL = ("yi", "he")
SKIPS = (15, 10, 5)


def both(en, yi):
    return en + "\n" + yi


def mmss(sec):
    sec = int(max(0, sec))
    if sec >= 3600:
        return "%d:%02d:%02d" % (sec // 3600, sec // 60 % 60, sec % 60)
    return "%d:%02d" % (sec // 60, sec % 60)


def lang_name(l):
    return "English" if l == "en" else "%s  %s" % (NAME_YI[l], NAME_EN[l])


# ------------------------------------------------------------------ the video with subtitles on it
class VideoView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.setBackgroundBrush(QBrush(QColor("black")))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.NoFocus)
        self.video = QGraphicsVideoItem()
        self.scene_.addItem(self.video)
        self.box = QGraphicsRectItem()
        self.box.setBrush(QBrush(QColor(0, 0, 0, 170)))
        self.box.setPen(QPen(Qt.NoPen))
        self.scene_.addItem(self.box)
        self.sub = QGraphicsTextItem()
        self.sub.setDefaultTextColor(QColor("white"))
        self.scene_.addItem(self.sub)
        self.note = QGraphicsTextItem()
        self.note.setDefaultTextColor(QColor("#bbbbbb"))
        self.scene_.addItem(self.note)
        self.lines = []
        self.setMinimumHeight(260)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.layout_()

    def layout_(self):
        w, h = self.viewport().width(), self.viewport().height()
        self.scene_.setSceneRect(0, 0, w, h)
        self.video.setSize(QSizeF(w, h))
        self.video.setPos(0, 0)
        self.note.setPos(10, 10)
        self.show_lines(self.lines)

    def show_lines(self, lines):
        """lines: [(lang, text)]"""
        self.lines = lines
        w, h = max(100, self.viewport().width()), max(100, self.viewport().height())
        parts = []
        for lang, text in lines:
            if not text:
                continue
            esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            d = "rtl" if lang in RTL else "ltr"
            parts.append('<p dir="%s" align="center" style="margin:2px">%s</p>' % (d, esc))
        if not parts:
            self.sub.hide(); self.box.hide(); return
        f = QFont("Segoe UI")
        f.setPixelSize(max(14, min(40, int(h / 15))))
        f.setBold(True)
        self.sub.setFont(f)
        self.sub.setTextWidth(w * 0.92)
        self.sub.setHtml("".join(parts))
        r = self.sub.boundingRect()
        x, y = w * 0.04, h - r.height() - h * 0.04
        self.sub.setPos(x, y)
        self.box.setRect(QRectF(x - 6, y - 4, r.width() + 12, r.height() + 8))
        self.sub.show(); self.box.show()


# ------------------------------------------------------------------ on-screen Yiddish keyboard
ROWS = [
    ["ק", "ר", "א", "ט", "ו", "ן", "ם", "פ"],
    ["ש", "ד", "ג", "כ", "ע", "י", "ח", "ל", "ך", "ף"],
    ["ז", "ס", "ב", "ה", "נ", "מ", "צ", "ת", "ץ"],
    ["װ", "ױ", "ײ", "ײַ", "אַ", "אָ", "פּ", "פֿ", "כּ", "תּ", "שׂ", "בֿ", "וּ", "יִ"],
    [".", ",", "?", "!", "־", "'", "\""],
]


class Keyboard(QFrame):
    typed = Signal(str)         # a letter
    back = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("kbd")
        self.setStyleSheet("QFrame#kbd { background: #eef1f5; border: 1px solid #c8ccd2; border-radius: 8px; }"
                           "QPushButton { font-size: 17pt; padding: 4px; min-width: 44px; min-height: 40px; }")
        lay = QVBoxLayout(self)
        lay.setSpacing(4)
        self.keys = {}
        for row in ROWS:
            r = QHBoxLayout(); r.setSpacing(4)
            r.addStretch(1)
            for ch in row:
                b = QPushButton(ch)
                b.setFocusPolicy(Qt.NoFocus)
                b.clicked.connect(lambda _=False, c=ch: self.typed.emit(c))
                self.keys[ch] = b
                r.addWidget(b)
            r.addStretch(1)
            lay.addLayout(r)
        r = QHBoxLayout()
        r.addStretch(1)
        sp = QPushButton("space  -  רווח")
        sp.setMinimumWidth(320); sp.setFocusPolicy(Qt.NoFocus)
        sp.clicked.connect(lambda: self.typed.emit(" "))
        bk = QPushButton("⌫  erase one letter")
        bk.setFocusPolicy(Qt.NoFocus)
        bk.clicked.connect(self.back.emit)
        self.keys[" "], self.keys["back"] = sp, bk
        r.addWidget(sp); r.addWidget(bk)
        r.addStretch(1)
        lay.addLayout(r)


# ------------------------------------------------------------------ translate one line again (in the background)
class LineTranslate(QThread):
    got = Signal(dict, str)        # {lang: text}, error

    def __init__(self, text, src, targets):
        super().__init__()
        self.text, self.src, self.targets = text, src, targets

    def run(self):
        out, err = {}, ""
        try:
            miss = engine.missing(engine.needed(self.src, self.targets))
            if miss:
                raise RuntimeError("the translator is not downloaded")
            tr = engine.Translator()
            try:
                for t in self.targets:
                    o = tr.translate(self.text, self.src, t, lambda f: None, lambda: False)
                    out[t] = learn.apply("tr", t, o)[0]
            finally:
                tr.close()
        except Exception as e:
            log("line translate failed: " + traceback.format_exc())
            err = "%s: %s" % (type(e).__name__, e)
        self.got.emit(out, err)


# ------------------------------------------------------------------ the player window
class Player(QWidget):
    saved = Signal(str)            # the video's path, after a fix was saved

    def __init__(self, parent, proj, docs):
        super().__init__(parent, Qt.Window)
        self.proj, self.docs = proj, docs
        self.spoken = proj["spoken"]
        self.langs = [self.spoken] + [t for t in proj["targets"] if t != self.spoken]
        self.cur = -1                # the line now playing
        self.edit_i = -1             # the line in the fix box
        self.base = {}               # lang -> the text the fix box was filled with (what a change is compared to)
        self.dirty = False
        self.frames = 0
        self.errors = []
        self.last_edit = None
        self.tr_job = None
        self.setWindowTitle("%s  -  Hafutza Typing" % proj.get("name", ""))

        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        t = QLabel(proj.get("name", ""))
        f = t.font(); f.setPointSize(14); f.setBold(True); t.setFont(f)
        top.addWidget(t, 1)
        top.addWidget(QLabel("Show on the video:  -  ווייזן אויפן ווידעא:"))
        self.show_box = {}
        for l in self.langs:
            c = QCheckBox(lang_name(l))
            c.setChecked(l == self.langs[0] or len(self.langs) == 2)
            c.setFocusPolicy(Qt.NoFocus)
            c.toggled.connect(lambda _=False: self.refresh_sub(force=True))
            self.show_box[l] = c
            top.addWidget(c)
        lay.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)
        self.view = VideoView()
        ll.addWidget(self.view, 1)
        srow = QHBoxLayout()
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setMinimumWidth(130)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setFocusPolicy(Qt.NoFocus)
        self.slider.sliderMoved.connect(lambda v: self.player.setPosition(v))
        srow.addWidget(self.time_label); srow.addWidget(self.slider, 1)
        ll.addLayout(srow)
        brow = QHBoxLayout()
        brow.addStretch(1)
        self.skip_btn = {}
        for s in SKIPS:
            b = QPushButton("«  %d" % s)
            b.setToolTip("Back %d seconds  -  צוריק %d סעקונדעס" % (s, s))
            b.clicked.connect(lambda _=False, s=s: self.skip(-s))
            self.skip_btn[-s] = b; brow.addWidget(b)
        self.play_btn = QPushButton("▶  Play")
        self.play_btn.setMinimumWidth(170)
        self.play_btn.setObjectName("play")
        self.play_btn.clicked.connect(self.toggle)
        brow.addWidget(self.play_btn)
        for s in reversed(SKIPS):
            b = QPushButton("%d  »" % s)
            b.setToolTip("Forward %d seconds  -  פאראויס %d סעקונדעס" % (s, s))
            b.clicked.connect(lambda _=False, s=s: self.skip(s))
            self.skip_btn[s] = b; brow.addWidget(b)
        brow.addStretch(1)
        for b in list(self.skip_btn.values()) + [self.play_btn]:
            b.setFocusPolicy(Qt.NoFocus)
            b.setMinimumHeight(52)
            fb = b.font(); fb.setPointSize(15); fb.setBold(True); b.setFont(fb)
        ll.addLayout(brow)
        keys = QLabel("Keys: Space = play / pause,  ← → = 5 seconds back / forward  (when not typing)")
        keys.setStyleSheet("color: #5b6470; font-size: 10pt;")
        keys.setAlignment(Qt.AlignCenter)
        ll.addWidget(keys)
        split.addWidget(left)

        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel(both("All the lines (click one to go there):", "אלע שורות (קליקט צו גיין אהין):")))
        self.list = QListWidget()
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(lambda it: self.go_line(self.list.row(it)))
        rl.addWidget(self.list, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 3); split.setStretchFactor(1, 2)
        lay.addWidget(split, 3)

        # fix box
        fix = QFrame(); fix.setObjectName("fix")
        fix.setStyleSheet("QFrame#fix { border: 2px solid #6d9bd1; border-radius: 8px; background: #f7faff; }")
        fl = QVBoxLayout(fix)
        self.fix_title = QLabel("")
        f = self.fix_title.font(); f.setBold(True); self.fix_title.setFont(f)
        fl.addWidget(self.fix_title)
        grid = QGridLayout()
        self.edits, self.erase_btn = {}, {}
        for n, l in enumerate(self.langs):
            grid.addWidget(QLabel(lang_name(l) + (" (typed)" if l == self.spoken else " (translation)")), n, 0)
            e = QLineEdit()
            e.setMinimumHeight(44)
            fe = e.font(); fe.setPointSize(15); e.setFont(fe)
            if l in RTL:
                e.setLayoutDirection(Qt.RightToLeft)
                e.setAlignment(Qt.AlignRight)
            e.textEdited.connect(self.typing)
            e.returnPressed.connect(self.save_fix)
            e.installEventFilter(self)
            self.edits[l] = e
            grid.addWidget(e, n, 1)
            b = QPushButton(both("Erase", "אויסמעקן"))
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, l=l: self.erase(l))
            self.erase_btn[l] = b
            grid.addWidget(b, n, 2)
        grid.setColumnStretch(1, 1)
        fl.addLayout(grid)
        arow = QHBoxLayout()
        self.save_btn = QPushButton(both("✓  Save the fix  (Enter)", "אפהיטן דעם תיקון"))
        self.save_btn.setObjectName("start")
        self.save_btn.setFocusPolicy(Qt.NoFocus)
        self.save_btn.clicked.connect(self.save_fix)
        self.undo_btn = QPushButton(both("Undo my change", "צוריק ווי עס איז געווען"))
        self.undo_btn.setFocusPolicy(Qt.NoFocus)
        self.undo_btn.clicked.connect(lambda: self.load_line(self.edit_i, force=True))
        self.retr_btn = QPushButton(both("Translate this line again", "איבערזעצן די שורה נאכאמאל"))
        self.retr_btn.setFocusPolicy(Qt.NoFocus)
        self.retr_btn.clicked.connect(self.translate_again)
        self.retr_btn.setVisible(len(self.langs) > 1)
        self.kbd_btn = QPushButton(both("Yiddish keyboard", "אידישע קלאוויאטור"))
        self.kbd_btn.setFocusPolicy(Qt.NoFocus)
        self.kbd_btn.setCheckable(True)
        self.kbd_btn.toggled.connect(lambda on: self.kbd.setVisible(on))
        self.learned_btn = QPushButton(both("Learned words", "געלערנטע ווערטער"))
        self.learned_btn.setFocusPolicy(Qt.NoFocus)
        self.learned_btn.clicked.connect(lambda: LearnedDialog(self).exec())
        for b in (self.save_btn, self.undo_btn, self.retr_btn, self.kbd_btn, self.learned_btn):
            b.setMinimumHeight(54)
        arow.addWidget(self.save_btn, 2); arow.addWidget(self.undo_btn); arow.addWidget(self.retr_btn)
        arow.addWidget(self.kbd_btn); arow.addWidget(self.learned_btn)
        fl.addLayout(arow)
        self.saved_label = QLabel("")
        self.saved_label.setWordWrap(True)
        self.saved_label.setStyleSheet("color: #1e7e34; font-weight: bold;")
        fl.addWidget(self.saved_label)
        self.kbd = Keyboard()
        self.kbd.typed.connect(self.kbd_type)
        self.kbd.back.connect(self.kbd_back)
        self.kbd.hide()
        fl.addWidget(self.kbd)
        lay.addWidget(fix)

        # the player
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.view.video)
        self.player.durationChanged.connect(lambda d: self.slider.setRange(0, d))
        self.player.playbackStateChanged.connect(self.state_changed)
        self.player.errorOccurred.connect(self.error)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.view.video.videoSink().videoFrameChanged.connect(self.frame)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)

        self.fill_list()
        if os.path.isfile(proj["video"]):
            self.player.setSource(QUrl.fromLocalFile(proj["video"]))
        else:
            self.view.note.setPlainText("The video file is not there any more: %s" % proj["video"])
        self.load_line(0, force=True)
        self.resize(1250, 900)

    # -- small helpers
    def frame(self, _f):
        self.frames += 1

    def error(self, e, msg=""):
        self.errors.append("%s %s" % (e, msg))
        log("player error %s %s" % (e, msg))
        self.view.note.setPlainText("The video could not be played: %s" % msg)

    def media_status(self, st):
        if st in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia) and not self.player.hasVideo():
            self.view.note.setPlainText("Sound only (no picture in this file)  -  נאר קול")

    def state_changed(self, st):
        if st == QMediaPlayer.PlayingState:
            self.play_btn.setText("❚❚  Pause")
        else:
            self.play_btn.setText("▶  Play")

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def skip(self, sec):
        d = self.player.duration()
        p = self.player.position() + sec * 1000
        p = max(0, min(p, d - 200 if d > 0 else p))
        self.player.setPosition(int(p))
        self.tick()

    def seg_at(self, t):
        segs = self.proj["segments"]
        best = -1
        for i, s in enumerate(segs):
            if s["s"] <= t + 0.05:
                best = i
            else:
                break
        return best

    def tick(self):
        pos = self.player.position()
        d = self.player.duration()
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True); self.slider.setValue(pos); self.slider.blockSignals(False)
        self.time_label.setText("%s / %s" % (mmss(pos / 1000), mmss(d / 1000)))
        i = self.seg_at(pos / 1000)
        if i != self.cur:
            self.cur = i
            if i >= 0:
                self.list.blockSignals(True)
                self.list.setCurrentRow(i)
                self.list.scrollToItem(self.list.item(i), QAbstractItemView.PositionAtCenter)
                self.list.blockSignals(False)
                if not self.dirty:
                    self.load_line(i)
        self.refresh_sub()

    def refresh_sub(self, force=False):
        t = self.player.position() / 1000
        i = self.cur
        lines = []
        if i >= 0:
            s = self.proj["segments"][i]
            if t <= max(s["e"], s["s"] + 1.0) + 0.6 or i == self.edit_i:
                for l in self.langs:
                    if self.show_box[l].isChecked():
                        lines.append((l, s["t"].get(l, "")))
        if force or lines != self.view.lines:
            self.view.show_lines(lines)

    def fill_list(self):
        self.list.clear()
        for i, s in enumerate(self.proj["segments"]):
            txt = "%s   %s" % (mmss(s["s"]), "\n".join(s["t"].get(l, "") for l in self.langs if s["t"].get(l)))
            it = QListWidgetItem(txt)
            self.list.addItem(it)

    def go_line(self, i):
        if i < 0 or i >= len(self.proj["segments"]):
            return
        if self.dirty and i != self.edit_i:
            self.save_fix()
        self.player.setPosition(int(self.proj["segments"][i]["s"] * 1000))
        self.cur = -2
        self.tick()
        self.load_line(i, force=True)

    def load_line(self, i, force=False):
        segs = self.proj["segments"]
        if not segs or i < 0 or i >= len(segs):
            self.fix_title.setText("No lines.")
            return
        if self.dirty and not force:
            return
        self.edit_i = i
        s = segs[i]
        self.fix_title.setText("Fix line %d of %d  (%s - %s)   -   פארריכטן שורה %d"
                               % (i + 1, len(segs), mmss(s["s"]), mmss(s["e"]), i + 1))
        self.base = {}
        for l, e in self.edits.items():
            e.setText(s["t"].get(l, ""))
            e.setCursorPosition(0 if l not in RTL else 0)
            self.base[l] = s["t"].get(l, "")
        self.dirty = False

    # -- typing a fix
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.FocusIn and obj in self.edits.values():
            self.last_edit = obj
        return False

    def typing(self, _=None):
        self.dirty = True
        self.saved_label.setText("")
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()             # stop the video while he types

    def erase(self, l):
        e = self.edits[l]
        e.clear()
        e.setFocus()
        self.last_edit = e
        self.typing()

    def target_edit(self):
        e = self.last_edit or self.edits[self.spoken]
        return e

    def kbd_type(self, ch):
        e = self.target_edit()
        e.insert(ch)
        e.setFocus()
        self.typing()

    def kbd_back(self):
        e = self.target_edit()
        e.backspace()
        e.setFocus()
        self.typing()

    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key_Space:
            self.toggle(); return
        if k == Qt.Key_Left:
            self.skip(-5); return
        if k == Qt.Key_Right:
            self.skip(5); return
        super().keyPressEvent(ev)

    def save_fix(self):
        i = self.edit_i
        if i < 0:
            return []
        s = self.proj["segments"][i]
        learned, changed = [], False
        for l, e in self.edits.items():
            new = " ".join(e.text().split())
            old = s["t"].get(l, "")
            if new == old:
                continue
            changed = True
            kind = "speech" if l == self.spoken else "tr"
            pairs = learn.learn(kind, l, self.base.get(l, old), new)
            learned += [(l, w, r) for w, r in pairs]
            s["t"][l] = new
        self.dirty = False
        if not changed:
            self.saved_label.setText("Nothing was changed in this line.")
            return []
        try:
            project.save(self.proj)
            project.export(self.proj, self.docs)
        except Exception as e:
            log("save fix failed: " + traceback.format_exc())
            QMessageBox.warning(self, "Hafutza Typing", "The fix could not be saved: %s" % e)
            return []
        it = self.list.item(i)
        if it:
            it.setText("%s   %s" % (mmss(s["s"]), "\n".join(s["t"].get(l, "") for l in self.langs if s["t"].get(l))))
        self.load_line(i, force=True)
        msg = "✓ Saved. The .txt and .srt files are updated.   -   אפגעהיטן"
        if learned:
            msg += "\nLearned for next time: " + ";  ".join("%s → %s" % (w, r) for _l, w, r in learned)
        self.saved_label.setText(msg)
        self.refresh_sub(force=True)
        self.saved.emit(self.proj["video"])
        return learned

    def translate_again(self):
        if self.tr_job:
            return
        src = " ".join(self.edits[self.spoken].text().split())
        others = [l for l in self.langs if l != self.spoken]
        if not src or not others:
            return
        self.saved_label.setText("Translating this line ...  -  מען זעצט איבער")
        self.retr_btn.setEnabled(False)
        self.tr_job = LineTranslate(src, self.spoken, others)
        self.tr_job.got.connect(self.translated)
        self.tr_job.start()

    def translated(self, out, err):
        self.tr_job.wait()
        self.tr_job = None
        self.retr_btn.setEnabled(True)
        if err:
            self.saved_label.setText("Could not translate: %s" % err)
            return
        for l, t in out.items():
            self.edits[l].setText(t)
            self.base[l] = t          # the new machine translation: only his own changes after this are learned
        self.dirty = True
        self.saved_label.setText("New translation is in the box. Press Save to keep it.  -  דריקט אפהיטן")

    def closeEvent(self, ev):
        if self.dirty:
            self.save_fix()
        self.player.stop()
        self.timer.stop()
        if self.tr_job:
            self.tr_job.wait()
        super().closeEvent(ev)


# ------------------------------------------------------------------ the learned words
class LearnedDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Learned words  -  געלערנטע ווערטער")
        lay = QVBoxLayout(self)
        info = QLabel("These are the words you fixed. On every new video, the typing and the translations are "
                      "corrected with this list by themselves, and the fixed words are given to the typing as a hint. "
                      "Delete a line if a fix should not be done any more.")
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addWidget(QLabel("אויף יעדן נייעם ווידעא ווערן די ווערטער פארריכט פון זיך אליין"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["In", "Language", "Was typed", "Fixed to", "Times"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.addItem("Typing", "speech"); self.kind.addItem("Translation", "tr")
        self.lang = QComboBox()
        for l in engine.LANGS:
            self.lang.addItem(lang_name(l), l)
        self.wrong = QLineEdit(); self.wrong.setPlaceholderText("was typed")
        self.right = QLineEdit(); self.right.setPlaceholderText("fixed to")
        add = QPushButton("Add")
        add.clicked.connect(self.add)
        for w in (self.kind, self.lang, self.wrong, self.right, add):
            row.addWidget(w)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        dele = QPushButton(both("Delete the chosen lines", "אויסמעקן"))
        dele.clicked.connect(self.delete)
        close = QPushButton(both("Close", "צומאכן"))
        close.clicked.connect(self.accept)
        row2.addWidget(dele); row2.addStretch(1); row2.addWidget(close)
        lay.addLayout(row2)
        self.fill()
        self.resize(900, 560)

    def fill(self):
        self.items = learn.load()["items"]
        self.table.setRowCount(len(self.items))
        for r, it in enumerate(self.items):
            vals = ["Typing" if it["kind"] == "speech" else "Translation", lang_name(it["lang"]), it["wrong"],
                    it["right"], str(it.get("times", 1))]
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(v)
                if it["lang"] in RTL and c in (2, 3):
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, cell)

    def add(self):
        if learn.add(self.kind.currentData(), self.lang.currentData(), self.wrong.text(), self.right.text()):
            self.wrong.clear(); self.right.clear()
            self.fill()

    def delete(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if rows:
            learn.remove(rows)
            self.fill()


# ------------------------------------------------------------------ all typed videos
class VideosDialog(QDialog):
    def __init__(self, win, docs):
        super().__init__(win)
        self.win, self.docs = win, docs
        self.setWindowTitle("My typed videos  -  מיינע אויפגעשריבענע ווידעאס")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(both("Pick a video to watch it with its text and fix the text:",
                                  "קלייבט א ווידעא צו זען און פארריכטן")))
        self.list = QListWidget()
        self.projs = project.all_projects()
        for p in self.projs:
            there = "" if os.path.isfile(p["video"]) else "   (the file is not there any more)"
            self.list.addItem("%s   -   %s   -   %d lines%s" % (p.get("name"), p.get("changed", ""), len(p["segments"]), there))
        if not self.projs:
            self.list.addItem("No videos yet. Videos typed with this version (1.2 and newer) show here.")
        self.list.itemDoubleClicked.connect(lambda _: self.open_())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        op = QPushButton(both("Open", "עפענען"))
        op.clicked.connect(self.open_)
        close = QPushButton(both("Close", "צומאכן"))
        close.clicked.connect(self.reject)
        row.addStretch(1); row.addWidget(op); row.addWidget(close)
        lay.addLayout(row)
        self.resize(800, 500)

    def open_(self):
        i = self.list.currentRow()
        if 0 <= i < len(self.projs):
            self.accept()
            self.win.open_player(self.projs[i]["video"])


# ------------------------------------------------------------------ test for the build machine
def run_steps(gen):
    def tick():
        try:
            ms = next(gen)
        except StopIteration:
            return
        QTimer.singleShot(ms, tick)
    QTimer.singleShot(0, tick)


def player_test(app, win, video, out):
    """Open the player on a typed video and try every button. Writes out/report.json; exit 0 if all good."""
    os.makedirs(out, exist_ok=True)
    rep = {"video": video, "checks": {}}
    ok = rep["checks"]

    def shot(w, name):
        w.grab().save(os.path.join(out, name + ".png"))

    def finish(code):
        rep["errors"] = getattr(rep.get("_p"), "errors", None)
        rep.pop("_p", None)
        rep["all_ok"] = code == 0
        with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        app.exit(code)

    def steps():
        try:
            proj = project.load(video)
            ok["project_saved_with_timings"] = bool(proj and proj["segments"] and all("s" in s for s in proj["segments"]))
            if not proj or len(proj["segments"]) < 2:
                rep["error"] = "no typed project with 2+ lines for this video"
                finish(3); return
            rep["lines"] = len(proj["segments"])
            rep["first_lines"] = proj["segments"][:3]
            p = win.open_player(video)
            rep["_p"] = p
            p.resize(1250, 900)
            yield 1500
            # 1 - play
            p.player.play()
            yield 3500
            pos = p.player.position()
            rep["play"] = {"position_ms": pos, "frames": p.frames, "has_video": p.player.hasVideo(),
                           "errors": list(p.errors), "state": str(p.player.playbackState())}
            ok["plays"] = pos > 2000 and not p.errors
            ok["picture_frames"] = p.frames > 20
            shot(p, "p1-playing")
            # 2 - pause
            p.play_btn.click()
            yield 400
            a = p.player.position()
            yield 1500
            b = p.player.position()
            rep["pause"] = {"at": a, "after_1.5s": b, "state": str(p.player.playbackState())}
            ok["pause"] = abs(b - a) < 150 and p.player.playbackState() != QMediaPlayer.PlayingState
            shot(p, "p2-paused")
            # 3 - the skip buttons, from 10 s
            p.player.setPosition(10000)
            yield 800
            rep["skips"] = []
            good = True
            for d in (5, 10, -15, -5, -10, 15):
                before = p.player.position()
                p.skip_btn[d].click()
                yield 700
                after = p.player.position()
                want = max(0, before + d * 1000)
                fine = abs(after - want) <= 400
                good &= fine
                rep["skips"].append({"button": d, "before": before, "after": after, "want": want, "ok": fine})
            ok["skip_buttons"] = good
            # Space key = play / pause
            p.setFocus()
            from PySide6.QtGui import QKeyEvent
            QApplication.sendEvent(p, QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " "))
            yield 600
            sp1 = p.player.playbackState() == QMediaPlayer.PlayingState
            QApplication.sendEvent(p, QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, " "))
            yield 400
            sp2 = p.player.playbackState() != QMediaPlayer.PlayingState
            ok["space_key"] = sp1 and sp2
            # 4 - click a line: jumps there
            segs = p.proj["segments"]
            k = 1 if len(segs) > 1 else 0
            r = p.list.visualItemRect(p.list.item(k))
            from PySide6.QtTest import QTest
            QTest.mouseClick(p.list.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
            yield 700
            rep["click_line"] = {"line": k, "start": segs[k]["s"], "position_ms": p.player.position(), "fix_box": p.edit_i}
            ok["click_line_jumps"] = abs(p.player.position() - segs[k]["s"] * 1000) <= 400 and p.edit_i == k
            QTest.mouseClick(p.list.viewport(), Qt.LeftButton, Qt.NoModifier, p.list.visualItemRect(p.list.item(0)).center())
            yield 700
            # 5 - fix a word in line 0 with the on-screen keyboard
            sp = p.spoken
            e = p.edits[sp]
            words = [learn._clean(w) for w in e.text().split()]
            W = max(words, key=len)
            rep["fix"] = {"line_before": e.text(), "word": W, "new_word": "האפוצא"}
            p.kbd_btn.click()
            yield 300
            e.setFocus()
            idx = e.text().find(W)
            e.setSelection(idx, len(W))
            e.del_()
            p.typing()
            for ch in "האפוצא":
                p.kbd.keys[ch].click()
            yield 300
            rep["fix"]["line_typed"] = e.text()
            shot(p, "p3-fixing-with-keyboard")
            learned = p.save_fix()
            rep["fix"]["learned"] = learned
            yield 300
            # a translation fix in line 1 (if there is a translation)
            tl = next((l for l in p.langs if l != sp), None)
            if tl:
                QTest.mouseClick(p.list.viewport(), Qt.LeftButton, Qt.NoModifier, p.list.visualItemRect(p.list.item(k)).center())
                yield 700
                te = p.edits[tl]
                tw = [learn._clean(w) for w in te.text().split()]
                TW = max(tw, key=len) if tw else ""
                rep["fix_tr"] = {"lang": tl, "line": k, "before": te.text(), "word": TW, "new_word": "Hafutza"}
                if TW:
                    te.setFocus()
                    te.setText(te.text().replace(TW, "Hafutza", 1))
                    p.typing()
                    QTest.keyClick(te, Qt.Key_Return)          # Enter saves
                    yield 400
                    rep["fix_tr"]["after"] = p.proj["segments"][k]["t"].get(tl)
            # 6 - check what was saved
            disk = project.load(video)
            l0 = disk["segments"][0]["t"][sp]
            rep["saved_line0"] = l0
            ok["fix_saved_in_project"] = "האפוצא" in l0 and not re.search(r"(?<!\w)%s(?!\w)" % re.escape(W), l0)
            d = os.path.join(p.docs, "Hafutza Typing")
            base = project.base_name(disk)
            txt = open(os.path.join(d, "%s - %s.txt" % (base, NAME_EN[sp])), encoding="utf-8-sig").read()
            srt = open(os.path.join(d, "%s - %s.srt" % (base, NAME_EN[sp])), encoding="utf-8-sig").read()
            rep["srt_start"] = srt[:400]
            ok["fix_in_txt"] = "האפוצא" in txt
            ok["fix_in_srt"] = "האפוצא" in srt and "-->" in srt
            items = learn.load()["items"]
            rep["learned_items"] = items
            ok["learned_word"] = any(it["kind"] == "speech" and it["right"] == "האפוצא" and it["wrong"] == W for it in items)
            if tl and rep.get("fix_tr", {}).get("word"):
                ok["translation_fix_saved"] = "Hafutza" in disk["segments"][k]["t"].get(tl, "")
                srt2 = open(os.path.join(d, "%s - %s.srt" % (base, NAME_EN[tl])), encoding="utf-8-sig").read()
                ok["translation_fix_in_srt"] = "Hafutza" in srt2
            # 7 - the fixed line shows on the video
            p.go_line(0)
            yield 1200
            rep["subtitle_shown"] = p.view.sub.toPlainText()
            ok["fixed_subtitle_on_video"] = "האפוצא" in p.view.sub.toPlainText()
            shot(p, "p4-fixed-subtitle")
            p.player.play()
            yield 1500
            shot(p, "p5-playing-again")
            p.player.pause()
            dlg = LearnedDialog(p)
            dlg.show()
            yield 500
            shot(dlg, "p6-learned-words")
            dlg.close()
            vd = VideosDialog(win, p.docs)
            vd.show()
            yield 400
            shot(vd, "p7-my-videos")
            vd.close()
            p.close()
            yield 300
            finish(0 if all(ok.values()) else 2)
        except Exception:
            rep["error"] = traceback.format_exc()
            finish(4)

    run_steps(steps())
