"""The ⋮ menu and everything behind it: Settings (remembered), the window's look (applied live), add-ons built from
blocks, Undo / Reset to normal, "Send to Avi" and "Ask a different AI", and the --ui-test.

hafutza.py sets extras.H = itself before use (so this file can use its window classes without a circular import)."""
import copy, json, os, re, threading, time, traceback, zipfile
from xml.sax.saxutils import escape

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QUrl, QObject, QEvent
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut, QColor, QGuiApplication
from PySide6.QtWidgets import (QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
                               QLabel, QPushButton, QToolButton, QMenu, QComboBox, QSpinBox, QSlider, QCheckBox,
                               QLineEdit, QPlainTextEdit, QGroupBox, QScrollArea, QFrame, QMessageBox, QSizePolicy)

import prefs, addons, online, requests_out, ai, engine, handoff

H = None                         # the hafutza module
BALL_COLOR = "#6a3fd0"
IMPERATIVE = re.compile(r"\b(make|set|change|put|move|turn|hide|show|use|switch|reset|give|let|can you|please|i want|"
                        r"bigger|smaller|darker|brighter|louder|quieter)\b|מאך|שטעל|טויש|באהאלט|ווייז|"
                        r"תעשה|תעשי|תשנה|תשים|תגדיל|תקטין|תסתיר|תראה|תחליף|תזיז|תצבע|אני רוצה|בבקשה|תחזיר", re.I)


def log(s):
    try:
        engine.log(s)
    except Exception:
        pass


def both(en, yi):
    return H.both(en, yi) if yi else en


# ------------------------------------------------------------------ undo (settings and add-ons)
def push_undo(win, label, fn):
    rec = {"label": label, "fn": fn, "done": False, "button": None}
    win.undo_stack.append(rec)
    del win.undo_stack[:-30]
    return rec


def run_undo(win, rec):
    if rec["done"]:
        return False
    try:
        rec["fn"]()
    except Exception:
        log("undo failed: " + traceback.format_exc())
    rec["done"] = True
    if rec in win.undo_stack:
        win.undo_stack.remove(rec)
    b = rec.get("button")
    if b is not None:
        try:
            b.setEnabled(False); b.setText("Undone · צוריק")
        except RuntimeError:
            pass
    return True


def undo_button(win, rec):
    b = QPushButton("↶ " + both("Undo", "צוריק")); b.setObjectName("undo")
    b.clicked.connect(lambda _=False: run_undo(win, rec))
    rec["button"] = b
    return b


# ------------------------------------------------------------------ the window's look, from the settings
def _ball_css(c):
    c = c or BALL_COLOR
    hov = QColor(c).darker(125).name()
    opn = QColor(c).darker(170).name()
    return ("QPushButton#aiball { background: %s; color: white; font-size: 15pt; font-weight: bold; border: 3px solid white;"
            " border-radius: %dpx; min-height: 0; min-width: 0; padding: 0; }"
            " QPushButton#aiball:hover { background: %s; }"
            " QPushButton#aiball[open=\"true\"] { background: %s; }" % (c, H.BALL // 2, hov, opn))


def _text_on(c):
    q = QColor(c)
    return "white" if q.lightness() < 140 else "black"


def parts(win):
    return {"videos": win.videos_btn, "learned": win.learned_btn, "ai_button": win.ai_btn, "update": win.update_btn,
            "version": win.version_label, "title": win.title_label, "subtitle": win.sub_w, "ball": win.ai_ball,
            "footer": win.foot, "start": win.start_btn, "stop": win.stop_btn, "choose": win.choose,
            "watch": win.watch_btn, "link": win.link_w}


def style_sheet(p):
    css = H.STYLE.replace("QWidget { font-size: 12pt; }", "QWidget { font-size: %dpt; }" % p["ui_size"])
    x = []
    if p["theme"] == "dark":
        x.append("QMainWindow, QWidget#body, QDialog, QScrollArea, QTabWidget::pane, QWidget#aiside { background: #1f2329; color: #e8eaed; }"
                 " QLabel, QRadioButton, QCheckBox, QGroupBox { color: #e8eaed; }"
                 " QPlainTextEdit, QLineEdit, QComboBox, QSpinBox { background: #2b3038; color: #f1f3f4; border: 1px solid #4a515c; }"
                 " QPushButton { background: #3a404a; color: #f1f3f4; border: 1px solid #5a626e; }"
                 " QPushButton:hover { background: #474e5a; } QFrame#drop { background: #262b33; }"
                 " QTabBar::tab { background: #2b3038; color: #e8eaed; } QMenu { background: #2b3038; color: #f1f3f4; }")
    bs = p["button_size"] / 100.0
    if bs != 1:
        x.append("QPushButton { padding: %dpx %dpx; font-size: %dpt; min-height: %dpx; }"
                 " QPushButton#start, QPushButton#stop, QPushButton#choose { min-height: %dpx; font-size: %dpt; }"
                 " QPushButton#update { font-size: %dpt; padding: %dpx %dpx; }"
                 % (round(8 * bs), round(16 * bs), round(p["ui_size"] * bs), round(34 * bs),
                    round(56 * bs), round(15 * bs), round(11 * bs), round(6 * bs), round(12 * bs)))
    if p["button_color"]:
        c = p["button_color"]
        t = p["button_text_color"] or _text_on(c)
        x.append("QPushButton { background: %s; color: %s; border: 1px solid %s; }"
                 " QPushButton:hover { background: %s; }" % (c, t, QColor(c).darker(130).name(), QColor(c).darker(115).name()))
    elif p["button_text_color"]:
        x.append("QPushButton { color: %s; }" % p["button_text_color"])
    if p["background_color"]:
        x.append("QMainWindow, QWidget#body, QWidget#aiside { background: %s; }" % p["background_color"])
    if p["text_color"]:
        x.append("QLabel, QRadioButton, QCheckBox, QGroupBox { color: %s; }" % p["text_color"])
    if p["start_color"]:
        x.append("QPushButton#start { background: %s; color: %s; } QPushButton#start:hover { background: %s; }"
                 % (p["start_color"], _text_on(p["start_color"]), QColor(p["start_color"]).darker(115).name()))
    # the small round buttons of the AI chat (close, keyboard, send) stay 40 px whatever the button size,
    # or the sign on them is cut off
    x.append("QPushButton#aix, QPushButton#kb, QPushButton#send { padding: 0px; min-height: 40px; max-height: 40px;"
             " min-width: 40px; max-width: 40px; font-size: 14pt; }")
    fam = p["font"]
    x.append("QPlainTextEdit#typed { font-size: %dpt;%s }" % (p["font_size"], (' font-family: "%s";' % fam) if fam else ""))
    return css + "\n" + "\n".join(x)


class _Dim(QObject):
    """Keeps the brightness cover the size of the window."""
    def __init__(self, win):
        super().__init__(win)
        self.win = win

    def eventFilter(self, o, e):
        if e.type() in (QEvent.Resize, QEvent.Show):
            cover = getattr(self.win, "dim", None)
            if cover is not None:
                cover.setGeometry(self.win.rect()); cover.raise_()
        return False


def apply_prefs(win):
    """Make the window look the way the settings say (called at the start and after every change)."""
    try:
        prefs.load_fonts()
    except Exception:
        pass
    p = prefs.load()
    app = QApplication.instance()
    app.setStyleSheet(style_sheet(p))
    # the big title
    f = win.title_label.font(); f.setPointSize(p["title_size"]); f.setBold(True); win.title_label.setFont(f)
    win.ai_ball.setStyleSheet(_ball_css(p["ai_color"]))
    # brightness: a see-through dark cover over the whole window (mouse clicks go through it)
    if win.dim is None:
        win.dim = QWidget(win); win.dim.setObjectName("dim")
        win.dim.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        win.dim.setAttribute(Qt.WA_StyledBackground, True)
        win.dim.setFocusPolicy(Qt.NoFocus)
        win._dimf = _Dim(win); win.installEventFilter(win._dimf)
    b = p["brightness"]
    if b < 100:
        win.dim.setStyleSheet("background: rgba(0, 0, 0, %d);" % round((100 - b) * 2.4))
        win.dim.setGeometry(win.rect()); win.dim.show(); win.dim.raise_()
    else:
        win.dim.hide()
    # what shows, and what it says
    hide = set(p["hide"]); labels = p["labels"]
    for k, w in parts(win).items():
        if hasattr(w, "setText") and hasattr(w, "text"):
            if w.property("orig") is None:
                w.setProperty("orig", w.text())
            w.setText(labels.get(k) or w.property("orig"))
        if k in ("stop", "watch"):
            continue                         # these show and hide by themselves as typing goes on
        if k == "ball":
            w.setVisible(k not in hide)
            continue
        w.setVisible(k not in hide)
    try:
        win.show_watch()
    except Exception:
        pass
    # the row of buttons: top or bottom, and the AI button's place in it
    lay = win.lay
    at = lay.indexOf(win.hrow_w)
    if at != (1 if p["toolbar"] == "top" else lay.indexOf(win.foot) - 1):
        lay.removeWidget(win.hrow_w)
        lay.insertWidget(1 if p["toolbar"] == "top" else lay.indexOf(win.foot), win.hrow_w)
    hr = win.hrow
    hr.removeWidget(win.ai_btn)
    hr.insertWidget(0 if p["ai_button_pos"] == "left" else hr.indexOf(win.learned_btn) + 1, win.ai_btn)
    # the AI side: right or left
    left = p["ai_side"] == "left"
    if (win.cl.indexOf(win.ai_panel) == 0) != left:
        win.cl.removeWidget(win.ai_panel)
        win.cl.insertWidget(0 if left else 1, win.ai_panel)
    win.ai_panel.setStyleSheet("QScrollArea#aipanel { border: none; border-%s: 2px solid #c8ccd2; background: #f7f9fc; }"
                               % ("right" if left else "left") if p["theme"] != "dark" else
                               "QScrollArea#aipanel { border: none; border-%s: 2px solid #4a515c; background: #1f2329; }"
                               % ("right" if left else "left"))
    m = win.lay.contentsMargins()
    side = H.BALL + 18
    win.lay.setContentsMargins(side if left else 12, m.top(), 12 if left else side, m.bottom())
    if win.ai_panel.isVisible() and not win.ai_full:
        win.ai_panel.setFixedWidth(win.ai_panel_width())
    # the typed text's font
    for t in win.tabs_by_lang.values():
        t.edit.setObjectName("typed")
    apply_window(win)
    QTimer.singleShot(0, win.place_ball)


def apply_window(win, first=False):
    w = prefs.get("window")
    if not win.isVisible() or (first and w == "normal"):
        return
    if w == getattr(win, "_win_state", None):
        return
    win._win_state = w
    if w == "maximized":
        win.showMaximized()
    elif w == "fullscreen":
        win.showFullScreen()
    elif not first:
        win.showNormal()


# ------------------------------------------------------------------ AI side panel: width, ball, full window
def panel_width(win, usual):
    w = prefs.get("ai_width") or usual
    cw = win.centralWidget().width() if win.centralWidget() else 1000
    return max(300, min(w, max(300, cw - 320), 1000))


def place_ball(win):
    c = win.centralWidget()
    if c is None or not hasattr(win, "ai_ball"):
        return
    left = prefs.get("ai_side") == "left"
    B = H.BALL
    if win.ai_panel.isVisible() and not win.ai_full:
        x = (win.ai_panel.x() + win.ai_panel.width() - B // 2) if left else (win.ai_panel.x() - B // 2)
    elif win.ai_panel.isVisible():
        x = (c.width() - B - 6) if not left else 6
    else:
        sb = win.scroll.verticalScrollBar()
        x = 6 if left else c.width() - B - 6 - (sb.width() if sb.isVisible() else 0)
    win.ai_ball.move(max(0, x), max(0, (c.height() - B) // 2))
    win.ai_ball.raise_()
    if win.dim is not None and win.dim.isVisible():
        win.dim.raise_()


def set_full(win, full):
    """The AI as the whole window (⋮ > AI in the full window), or back at the side. The ball stays either way."""
    win.ai_full = bool(full)
    win.show_ai(True)
    if full:
        win.scroll.hide()
        win.ai_panel.setMinimumWidth(0); win.ai_panel.setMaximumWidth(16777215)
        win.cl.setStretchFactor(win.ai_panel, 1)
    else:
        win.scroll.show()
        win.cl.setStretchFactor(win.ai_panel, 0)
        win.ai_panel.setFixedWidth(win.ai_panel_width())
    QTimer.singleShot(0, win.place_ball)


# ------------------------------------------------------------------ the ⋮ menu
def make_menu_button(win):
    b = QToolButton()
    b.setText("⋮")
    b.setObjectName("dots")
    b.setToolTip("Menu: settings, add-ons, update, ask a different AI  -  מעניו")
    b.setPopupMode(QToolButton.InstantPopup)
    b.setStyleSheet("QToolButton#dots { font-size: 20pt; font-weight: bold; padding: 0 12px; border: none; }"
                    " QToolButton#dots::menu-indicator { image: none; width: 0; }")
    m = QMenu(b)
    m.aboutToShow.connect(lambda: fill_menu(win, m))
    b.setMenu(m)
    win.menu = m           # filled each time it opens (the window is not built yet here)
    return b


def menu_items(win):
    """[(text, function)]; None = a line between groups."""
    it = [("Settings…  -  איינשטעלונגען", lambda: open_settings(win)),
          (("AI as a side panel  -  AI אין דער זייט" if getattr(win, "ai_full", False) else "AI in the full window  -  AI איבערן גאנצן פענצטער"),
           lambda: set_full(win, not win.ai_full)),
          None,
          ("My typed videos  -  מיינע ווידעאס", win.my_videos),
          ("Learned words  -  געלערנטע ווערטער", win.learned_words),
          ("Check for update  -  זוכן א נייע ווערסיע", win.do_update),
          None,
          ("My add-ons…  -  מיינע צוגאבן", lambda: open_addons(win))]
    for a in addons.load_all():
        if a["on"] and a["kind"] == "menu":
            it.append(("   " + a["label"], lambda _=False, a=a: run_steps(win, a["steps"], a["name"])))
    it += [("Ask a different AI…  -  פרעגן אן אנדערע AI", lambda: open_online(win)),
           None]
    if win.undo_stack:
        it.append(("Undo: %s  -  צוריק" % short(win.undo_stack[-1]["label"], 40), lambda: run_undo(win, win.undo_stack[-1])))
    it.append(("Reset to normal  -  צוריק ווי געווען", lambda: reset_normal(win)))
    return it


def fill_menu(win, m):
    m.clear()
    for item in menu_items(win):
        if item is None:
            m.addSeparator()
        else:
            act = m.addAction(item[0])
            act.triggered.connect(lambda _=False, fn=item[1]: fn())


def short(s, most=60):
    s = " ".join(str(s).split())
    return s if len(s) <= most else s[:most - 1] + "…"


def reset_normal(win):
    """Every setting back to normal and every add-on off (kept: he can turn them on again). Undo puts it back."""
    done = prefs.set_many({"reset": True})
    off = addons.all_off()
    apply_prefs(win); refresh_addons(win)

    def back():
        prefs.put_back(done)
        for aid in off:
            addons.set_on(aid, True)
        apply_prefs(win); refresh_addons(win)
    rec = push_undo(win, "Reset to normal", back)
    log("reset to normal: %d settings, %d add-ons off" % (len(done), len(off)))
    return rec


# ------------------------------------------------------------------ add-ons at work
def refresh_addons(win):
    for w in win.addon_widgets:
        w.setParent(None)
    for s in win.addon_keys:
        s.setEnabled(False); s.setParent(None)
    win.addon_widgets, win.addon_keys = [], []
    for a in addons.load_all():
        if not a["on"]:
            continue
        run = (lambda _=False, a=a: run_steps(win, a["steps"], a["name"]))
        if a["kind"] == "button":
            b = QPushButton(a["label"])
            b.setProperty("addon", a["id"])
            b.setToolTip(addons.describe(a))
            b.clicked.connect(run)
            win.hrow.insertWidget(win.hrow.count() - 1, b)        # before the stretch at the end
            win.addon_widgets.append(b)
        elif a["kind"] == "shortcut":
            s = QShortcut(QKeySequence(a["key"]), win)
            s.activated.connect(run)
            win.addon_keys.append(s)
        elif a["kind"] == "panel":
            g = QGroupBox(a["name"]); g.setProperty("addon", a["id"])
            v = QVBoxLayout(g)
            if a.get("notes"):
                lb = QLabel(a["notes"]); lb.setWordWrap(True)
                lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
                v.addWidget(lb)
            if a.get("items"):
                grid = QGridLayout(); v.addLayout(grid)
                for i, word in enumerate(a["items"]):
                    wb = QPushButton(word)
                    wb.clicked.connect(lambda _=False, w=word: insert_word(win, w))
                    grid.addWidget(wb, i // 5, i % 5)
            if a.get("steps"):
                go = QPushButton(both("Do it", "טון")); go.clicked.connect(run); v.addWidget(go)
            win.lay.insertWidget(win.lay.indexOf(win.tabs), g)
            win.addon_widgets.append(g)
    apply_prefs_light(win)


def apply_prefs_light(win):
    """Add-on buttons take the AI button's place rules too."""
    hr = win.hrow
    p = prefs.load()
    hr.removeWidget(win.ai_btn)
    hr.insertWidget(0 if p["ai_button_pos"] == "left" else hr.indexOf(win.learned_btn) + 1, win.ai_btn)


def current_tab(win):
    t = win.tabs.currentWidget() if win.tabs.count() else None
    return t if t is not None and hasattr(t, "edit") else None


def insert_word(win, word):
    t = current_tab(win)
    if t is None:
        say(win, "There is no typed text yet to add it to.")
        return
    t.edit.insertPlainText(word + " ")
    t.edit.setFocus()


def say(win, text):
    win.last_message = text
    if win.quiet:
        log("message: " + text)
        return
    QMessageBox.information(win, H.TITLE, text)


def write_docx(path, text, rtl=False):
    """A plain Word file, one paragraph a line (no extra library needed)."""
    bidi = "<w:pPr><w:bidi/><w:jc w:val=\"right\"/></w:pPr>" if rtl else ""
    rr = "<w:rPr><w:rtl/></w:rPr>" if rtl else ""
    paras = "".join("<w:p>%s<w:r>%s<w:t xml:space=\"preserve\">%s</w:t></w:r></w:p>" % (bidi, rr, escape(ln))
                    for ln in text.split("\n"))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>%s</w:body></w:document>'
           % paras)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
                   'wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                   'officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)


def run_steps(win, steps, name=""):
    """Press an add-on: do its steps in order, with things the program already does. -> what was done (for tests)."""
    did = []
    log("add-on %s: %s" % (name, steps))
    for st in steps:
        do, v = st["do"], st.get("value")
        tab = current_tab(win)
        text = tab.edit.toPlainText() if tab else ""
        needs = do in ("replace", "copy", "save", "insert")
        if needs and tab is None:
            say(win, "There is no typed text yet. Type a video first.  -  נאך קיין טעקסט נישטא")
            return did
        try:
            if do == "ai":
                d = win.show_ai(True)
                if not d.send(text=v):
                    d.box.setPlainText(v)
            elif do == "replace":
                win.ai_apply(tab.lang, [(v["find"], v["replace"])])
            elif do == "insert":
                c = tab.edit.textCursor(); c.movePosition(c.MoveOperation.End); tab.edit.setTextCursor(c)
                tab.edit.insertPlainText(v)
            elif do == "copy":
                QApplication.clipboard().setText(text)
            elif do == "save":
                d = os.path.join(H.docs_dir(), "Hafutza Typing"); os.makedirs(d, exist_ok=True)
                fn = win.file_name(tab.lang, win.shown_path())
                p = os.path.join(d, fn[:-4] + "." + v)
                if v == "docx":
                    write_docx(p, text, tab.lang in H.RTL)
                else:
                    H.write_text(p, text)
                win.last_saved = p
                say(win, "Saved: " + p)
            elif do == "open_folder":
                d = os.path.join(H.docs_dir(), "Hafutza Typing"); os.makedirs(d, exist_ok=True)
                if not win.quiet:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(d))
            elif do == "settings":
                done = prefs.set_many(v)
                if done:
                    apply_prefs(win)
                    push_undo(win, "%s: settings" % (name or "add-on"), lambda done=done: (prefs.put_back(done), apply_prefs(win)))
            elif do == "open":
                {"settings": lambda: open_settings(win), "ai": lambda: win.show_ai(True), "videos": win.my_videos,
                 "learned": win.learned_words, "update": win.do_update, "addons": lambda: open_addons(win)}[v]()
            elif do == "tab":
                t = win.tabs_by_lang.get(v)
                if t is not None:
                    win.tabs.setCurrentWidget(t)
            elif do == "message":
                say(win, v)
            did.append(do)
        except Exception:
            log("add-on step %s failed: %s" % (do, traceback.format_exc()))
            say(win, "This add-on's step “%s” did not work." % do)
            return did
    return did


# ------------------------------------------------------------------ answers from an AI: settings, add-ons, too big
def apply_settings(chat, st, reply, by="AI"):
    win = chat.win
    done = prefs.set_many(st)
    if not done:
        chat.bubble("bot", (reply + "\n" if reply else "") + both("That is already how it is set.", "עס איז שוין אזוי"))
        return None
    apply_prefs(win)
    rec = push_undo(win, "settings by the %s" % by, lambda: (prefs.put_back(done), apply_prefs(win)))
    chat.bubble("chg", (reply or both("Done.", "געטוישט.")) + "\n" + "\n".join(prefs.describe(done)), undo_button(win, rec))
    log("%s settings: %s" % (by, done))
    return rec


def make_addon(chat, obj, reply, instr, by="AI"):
    win = chat.win
    clean, why = addons.check(obj)
    if why:
        give_package(chat, instr, (reply + "\n" if reply else "") + both("I could not add that: %s." % why, ""), by)
        return None
    aid = addons.save(clean, by=by)
    refresh_addons(win)
    a = addons.get(aid) or clean
    rec = push_undo(win, "add-on “%s”" % a["name"], lambda: (addons.delete(aid), refresh_addons(win)))
    chat.bubble("chg", (reply or both("Added.", "צוגעלייגט.")) + "\n" + both("New: ", "נייע: ") + addons.describe(a) +
                "\n" + both("(⋮ > My add-ons turns it off or deletes it.)", ""), undo_button(win, rec))
    log("%s add-on %s: %s" % (by, aid, clean))
    return rec


def package_folder():
    return os.path.join(H.docs_dir(), "Hafutza Typing", "For any AI")


def make_package(win, instr, reply=""):
    """-> (text, path): the ready request for any other AI, also saved as a .txt file ("" if it could not be saved)."""
    text = handoff.package(instr, H.VERSION, reply)
    try:
        path = handoff.save(text, package_folder(), instr)
    except Exception as e:
        log("package save: %r" % e)
        path = ""
    win.last_package = (text, path)
    win.last_link = handoff.link_text(instr, H.VERSION)
    log("package for any AI: %s" % (path or "(not saved)"))
    return text, path


def give_package(chat, instr, reply="", by="AI"):
    """The AI could not do it here: hand him, in the chat, a ready request he can give ANY other AI (copy + saved file),
    and a place to paste that AI's answer back. Send to Avi stays as a small extra."""
    win = chat.win
    text, path = make_package(win, instr, reply)
    w = QWidget(); g = QGridLayout(w); g.setContentsMargins(0, 0, 0, 0); g.setSpacing(6)
    link = win.last_link
    cp = QPushButton("🔗 " + both("Copy the link for any AI", "קאפירן דעם לינק")); cp.setObjectName("pkg_copy")

    def copy(_=False):
        QApplication.clipboard().setText(link)
        cp.setText("✓ " + both("Copied", "קאפירט"))
        win.package_copied = True
    cp.clicked.connect(copy)
    g.addWidget(cp, 0, 0)
    op = QPushButton(both("Open the full guide (file)", "עפענען די טעקע")); op.setObjectName("pkg_open")
    op.setEnabled(bool(path))
    op.clicked.connect(lambda _=False: None if win.quiet else QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
    g.addWidget(op, 0, 1)
    if by == "AI":
        pa = QPushButton(both("Paste its answer here", "אריינלייגן דעם ענטפער")); pa.setObjectName("other")
        pa.clicked.connect(lambda _=False: open_online(win, instr))
        g.addWidget(pa, 1, 0)
    av = QPushButton(both("Or send to Avi (internet)", "אדער שיקן צו אבי")); av.setObjectName("toavi")
    av.setFlat(True)
    av.clicked.connect(lambda _=False: send_to_avi(chat, instr, av))
    g.addWidget(av, 1, 1)
    head = (reply.strip() + "\n\n") if reply.strip() else \
        both("I can't do that here by myself, so here is a link for any other AI.",
             "איך קען דאס נישט אליין, האב איך געמאכט א לינק פאר יעדן אנדערן AI") + "\n\n"
    msg = head + both("Press “Copy the link”, paste it into any AI (ChatGPT, Claude, Gemini ...) and send. The link opens "
                      "the program's code and a guide, so that AI can change the program and make you an update. "
                      "When it gives you back a GitHub link, paste it in Update > “Install an update another AI made”.",
                      "") + \
        ("\n" + "Also saved as a file: " + path if path else "") + \
        ("\n" + both("If that AI answers with a code in { }, press “Paste its answer here” and I'll apply it.", "")
         if by == "AI" else "")
    chat.bubble("bot", msg, w)
    win.last_help = w
    return w


def help_buttons(chat, instr, by="AI"):
    """(Kept for older callers.) Same as give_package, without a bubble text of its own."""
    return give_package(chat, instr, "", by)


def send_to_avi(chat, instr, btn=None):
    win = chat.win
    if btn is not None:
        btn.setEnabled(False)
    th = H.RequestSend("[From the AI chat] " + instr)
    win.req_threads.append(th)

    def done(kind, info):
        th.wait()
        if th in win.req_threads:
            win.req_threads.remove(th)
        win.last_avi = kind
        if kind == "sent":
            chat.bubble("bot", both("✓ Sent to Avi. When he has built it, ⋮ > Check for update brings it.",
                                    "✓ געשיקט צו אבי"))
        else:
            chat.bubble("bot", both("No internet right now: your request is kept on this computer and goes to Avi by itself "
                                    "when the internet is on.", "קיין אינטערנעט יעצט: עס ווערט אפגעהיטן און גייט אוועק שפעטער"))
        if btn is not None:
            try:
                btn.setText("✓ " + both("Sent", "געשיקט") if kind == "sent" else both("Kept, goes later", "אפגעהיטן"))
            except RuntimeError:
                pass
    th.done.connect(done)
    th.start()
    return th


def apply_answer(chat, p, instr, by="AI", hint=False):
    """p = ai.parse_answer(...). Settings and add-ons are checked and applied with Undo. -> True if it handled the answer."""
    st = dict(p.get("settings") or {})
    addon = p.get("addon")
    if hint and not addon and IMPERATIVE.search(instr or ""):
        try:
            fonts = prefs.load_fonts()
        except Exception:
            fonts = []
        for k, v in ai.settings_hint(instr, fonts).items():
            st.setdefault(k, v)
    if not st and not addon and not p.get("too_big"):
        return False
    reply = p.get("reply") or ""
    if st:
        apply_settings(chat, st, reply, by)
        reply = ""
    if addon:
        make_addon(chat, addon, reply, instr, by)
    elif p.get("too_big"):              # also after the part it could do (settings): the rest goes to any AI
        give_package(chat, instr, reply, by)
    return True


def handle(dlg, p, instr, ch):
    """Called by the AI chat for every answer. Text changes go the usual way (False); else settings/add-on/too big."""
    if ch:
        return False
    return apply_answer(dlg, p, instr, "AI", hint=True)


# ------------------------------------------------------------------ requests waiting for the internet
def start_flusher(win):
    def go():
        if not requests_out.pending() or getattr(win, "_flushing", False):
            return
        win._flushing = True

        def run():
            try:
                n = requests_out.flush(H.VERSION)
                if n:
                    log("sent %d waiting request(s)" % n)
            except Exception as e:
                log("flush: %r" % e)
            win._flushing = False
        threading.Thread(target=run, daemon=True).start()
    win.flusher = QTimer(win); win.flusher.timeout.connect(go); win.flusher.start(10 * 60 * 1000)
    QTimer.singleShot(20000, go)
    return go


# ------------------------------------------------------------------ Settings window
COLOR_CHOICES = ["usual", "blue", "dark blue", "light blue", "green", "dark green", "red", "purple", "orange", "pink",
                 "gray", "black", "white", "brown", "gold", "teal", "navy"]


class SettingsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Settings  -  איינשטעלונגען")
        self.snap = copy.deepcopy(prefs.load())
        self.ctl = {}
        outer = QVBoxLayout(self)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame); sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget(); sc.setWidget(inner)
        v = QVBoxLayout(inner)
        outer.addWidget(sc, 1)
        p = prefs.load()

        g = QGroupBox("Light, sound and words  -  ליכט, קול און ווערטער"); f = QFormLayout(g); v.addWidget(g)
        self.slider(f, "brightness", "Brightness  -  ליכטיקייט")
        self.slider(f, "volume", "Volume (watching videos)  -  קול")
        fc = QComboBox(); fc.addItem(prefs.STANDARD, "")
        try:
            for n in prefs.load_fonts():
                fc.addItem(n, n)
        except Exception:
            pass
        i = fc.findData(p["font"]); fc.setCurrentIndex(max(0, i))
        fc.currentIndexChanged.connect(lambda _i: self.put("font", fc.currentData()))
        f.addRow("Font of the typed words  -  שריפט", fc); self.ctl["font"] = fc
        self.spin(f, "font_size", "Size of the typed words")
        self.spin(f, "ui_size", "Size of the program's words")
        self.spin(f, "title_size", "Size of the big title")

        g = QGroupBox("Colours and look  -  פארבן"); f = QFormLayout(g); v.addWidget(g)
        self.combo(f, "theme", "Light or dark", prefs.CHOICES["theme"])
        for k, t in (("button_color", "Buttons"), ("button_text_color", "Words on the buttons"),
                     ("background_color", "Background"), ("text_color", "Words"), ("start_color", "Start button"),
                     ("ai_color", "AI ball")):
            self.color(f, k, t)
        self.spin(f, "button_size", "Button size (%)")

        g = QGroupBox("Places  -  ערטער"); f = QFormLayout(g); v.addWidget(g)
        self.combo(f, "ai_side", "AI ball and AI panel", prefs.CHOICES["ai_side"])
        self.spin(f, "ai_width", "AI panel width in pixels (0 = usual, about 4 inches)")
        self.combo(f, "ai_button_pos", "AI button in the top row", prefs.CHOICES["ai_button_pos"])
        self.combo(f, "toolbar", "Row of buttons", prefs.CHOICES["toolbar"])
        self.combo(f, "window", "Window", prefs.CHOICES["window"])

        g = QGroupBox("Hide parts  -  באהאלטן"); gl = QGridLayout(g); v.addWidget(g)
        self.hide_box = {}
        for i, (k, t) in enumerate((k, t) for k, t in prefs.PARTS.items() if k not in prefs.NO_HIDE):
            cb = QCheckBox(t); cb.setChecked(k in p["hide"])
            cb.toggled.connect(lambda on, k=k: self.put("hide", k) if on else self.put("show", k))
            gl.addWidget(cb, i // 2, i % 2); self.hide_box[k] = cb

        g = QGroupBox("Ask a different AI (online)  -  אן אנדערע AI"); f = QFormLayout(g); v.addWidget(g)
        note = QLabel("This needs internet. Only your request is sent (never your typed text), to the AI you pick here. "
                      "Your key stays on this computer only.  -  דאס דארף אינטערנעט")
        note.setWordWrap(True); f.addRow(note)
        c = online.load()
        self.prov = QComboBox()
        for k, d in online.PROVIDERS.items():
            self.prov.addItem(d["name"], k)
        self.prov.setCurrentIndex(max(0, self.prov.findData(c["provider"])))
        self.key = QLineEdit(c["key"]); self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("paste your key here (none = copy and paste by hand)")
        self.model = QLineEdit(c["model"])
        self.key_link = QLabel(); self.key_link.setOpenExternalLinks(True); self.key_link.setWordWrap(True)
        f.addRow("Online AI", self.prov); f.addRow("Your key", self.key); f.addRow("Model (empty = usual)", self.model)
        f.addRow(self.key_link)
        for w in (self.key, self.model):
            w.editingFinished.connect(self.save_online)
        self.prov.currentIndexChanged.connect(lambda _i: self.save_online())
        self.show_key_link()

        row = QHBoxLayout()
        r = QPushButton("Reset to normal  -  צוריק ווי געווען"); r.clicked.connect(self.reset)
        c = QPushButton(both("Close", "צומאכן")); c.clicked.connect(self.accept)
        row.addWidget(r); row.addStretch(1); row.addWidget(c)
        outer.addLayout(row)
        self.resize(720, 760)

    def show_key_link(self):
        d = online.PROVIDERS[self.prov.currentData()]
        self.key_link.setText('Get a key: <a href="%s">%s</a>  (model: %s)' % (d["key_page"], d["key_page"], d["model"]))

    def save_online(self):
        online.save(self.prov.currentData(), self.key.text(), self.model.text())
        self.show_key_link()

    def put(self, k, v):
        done = prefs.set_many({k: v})
        if done:
            apply_prefs(self.win)
        return done

    def slider(self, f, k, t):
        s = QSlider(Qt.Horizontal); lo, hi = prefs.LIMITS[k]; s.setRange(lo, hi); s.setValue(prefs.get(k))
        lb = QLabel("%d%%" % prefs.get(k))
        s.valueChanged.connect(lambda x, k=k, lb=lb: (lb.setText("%d%%" % x), self.put(k, x)))
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.addWidget(s, 1); h.addWidget(lb)
        f.addRow(t, w); self.ctl[k] = s

    def spin(self, f, k, t):
        s = QSpinBox(); lo, hi = prefs.LIMITS[k]; s.setRange(lo, hi); s.setValue(prefs.get(k))
        s.valueChanged.connect(lambda x, k=k: self.put(k, x))
        f.addRow(t, s); self.ctl[k] = s

    def combo(self, f, k, t, items):
        c = QComboBox()
        for x in items:
            c.addItem(x, x)
        c.setCurrentIndex(max(0, c.findData(prefs.get(k))))
        c.currentIndexChanged.connect(lambda _i, k=k, c=c: self.put(k, c.currentData()))
        f.addRow(t, c); self.ctl[k] = c

    def color(self, f, k, t):
        c = QComboBox(); c.setEditable(True); c.addItems(COLOR_CHOICES)
        cur = prefs.get(k)
        c.setCurrentText(cur or "usual")
        c.currentTextChanged.connect(lambda x, k=k: self.put(k, x) if prefs.color(x) is not None else None)
        f.addRow(t, c); self.ctl[k] = c

    def reset(self):
        rec = reset_normal(self.win)
        self.done_reset = rec
        self.accept()

    def done(self, r):
        cur = prefs.load()
        changed = {k: (self.snap[k], cur[k]) for k in prefs.DEFAULTS if cur[k] != self.snap[k]}
        if changed and not getattr(self, "done_reset", None):
            push_undo(self.win, "Settings window changes", lambda: (prefs.put_back(changed), apply_prefs(self.win)))
        super().done(r)


def open_settings(win):
    d = SettingsDialog(win)
    win.settings_dlg = d
    if win.quiet:
        d.show()
        return d
    d.exec()
    return d


# ------------------------------------------------------------------ My add-ons window
class AddonsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("My add-ons  -  מיינע צוגאבן")
        self.v = QVBoxLayout(self)
        top = QLabel("New buttons, menu items, keys and side notes the AI made for you. Turn each on or off, or delete it.\n"
                     "To get a new one, ask the AI, e.g. “add a button that copies the text”.")
        top.setWordWrap(True); self.v.addWidget(top)
        self.list = QVBoxLayout(); self.v.addLayout(self.list)
        self.v.addStretch(1)
        c = QPushButton(both("Close", "צומאכן")); c.clicked.connect(self.accept); self.v.addWidget(c)
        self.fill()
        self.resize(620, 420)

    def fill(self):
        while self.list.count():
            w = self.list.takeAt(0).widget()
            if w:
                w.setParent(None)
        al = addons.load_all()
        if not al:
            self.list.addWidget(QLabel("No add-ons yet."))
        for a in al:
            w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox(); cb.setChecked(a["on"])
            cb.toggled.connect(lambda on, aid=a["id"]: (addons.set_on(aid, on), refresh_addons(self.win)))
            lb = QLabel(addons.describe(a) + ("  (made by the %s)" % a["by"] if a.get("by") else "")); lb.setWordWrap(True)
            d = QPushButton(both("Delete", "אויסמעקן"))
            d.clicked.connect(lambda _=False, aid=a["id"]: self.delete(aid))
            h.addWidget(cb); h.addWidget(lb, 1); h.addWidget(d)
            self.list.addWidget(w)

    def delete(self, aid):
        a = addons.get(aid)
        addons.delete(aid)
        refresh_addons(self.win)
        if a:
            push_undo(self.win, "delete add-on “%s”" % a["name"],
                      lambda: (addons.save(a, by=a.get("by") or "AI"), refresh_addons(self.win)))
        self.fill()


def open_addons(win):
    d = AddonsDialog(win)
    win.addons_dlg = d
    if win.quiet:
        d.show()
        return d
    d.exec()
    return d


# ------------------------------------------------------------------ Ask a different AI
class OnlineAsk(QThread):
    done = Signal(str, str)

    def __init__(self, request):
        super().__init__()
        self.request = request

    def run(self):
        try:
            self.done.emit(online.ask(self.request), "")
        except Exception as e:
            self.done.emit("", str(e)[:300])


class OnlineDialog(QDialog):
    """His request goes to a bigger online AI (his key), or by copy and paste to a free AI website. The answer is
    checked and applied here with Undo, the same way as the offline AI's."""

    def __init__(self, win, request=""):
        super().__init__(win)
        self.win, self.th = win, None
        self.setWindowTitle("Ask a different AI  -  פרעגן אן אנדערע AI")
        v = QVBoxLayout(self)
        n = QLabel("This needs internet. Only what you write here is sent (never your typed text). "
                   "The answer is checked by the program and can be undone.  -  דאס דארף אינטערנעט")
        n.setWordWrap(True); v.addWidget(n)
        v.addWidget(QLabel("What do you want? (English or Yiddish)"))
        self.box = QPlainTextEdit(request); self.box.setMaximumHeight(110); v.addWidget(self.box)
        c = online.load()
        self.ask_btn = QPushButton("Ask %s" % online.PROVIDERS[c["provider"]]["name"].split(" (")[0])
        self.ask_btn.setObjectName("start")
        self.ask_btn.clicked.connect(self.ask)
        if online.has_key():
            v.addWidget(self.ask_btn)
            v.addWidget(QLabel("Or by hand, with a free AI website:"))
        else:
            self.ask_btn.hide()
            l = QLabel("No online AI key is set (⋮ > Settings, at the bottom). You can do it by hand with a free AI website:")
            l.setWordWrap(True); v.addWidget(l)
        self.copy_btn = QPushButton("1.  Copy the request and open a free AI website")
        self.copy_btn.clicked.connect(self.copy_open); v.addWidget(self.copy_btn)
        v.addWidget(QLabel("2.  Paste the website AI's whole answer here:"))
        self.paste = QPlainTextEdit(); self.paste.setMaximumHeight(120); v.addWidget(self.paste)
        self.apply_btn = QPushButton("3.  Apply it"); self.apply_btn.clicked.connect(self.apply_paste); v.addWidget(self.apply_btn)
        self.msgs = QVBoxLayout(); v.addLayout(self.msgs)
        v.addStretch(1)
        cl = QPushButton(both("Close", "צומאכן")); cl.clicked.connect(self.accept); v.addWidget(cl)
        self.resize(620, 640)

    def bubble(self, who, text, extra=None):
        fr = QFrame(); fr.setObjectName(who)
        fr.setStyleSheet("QFrame#%s { background: %s; border-radius: 8px; }" %
                         (who, {"chg": "#e3f6e8", "bot": "#eef0f3", "me": "#ece6fb"}.get(who, "#eef0f3")))
        h = QVBoxLayout(fr); lb = QLabel(text); lb.setWordWrap(True); h.addWidget(lb)
        if extra is not None:
            h.addWidget(extra, 0, Qt.AlignLeft)
        self.msgs.addWidget(fr)
        fr.label = lb
        self.last = fr
        return fr

    def request(self):
        return self.box.toPlainText().strip()

    def ask(self):
        r = self.request()
        if not r or self.th is not None:
            return False
        self.ask_btn.setEnabled(False)
        self.bubble("bot", "… asking the online AI")
        self.th = OnlineAsk(r)
        self.th.done.connect(self.answered)
        self.th.start()
        return True

    def answered(self, text, err):
        self.th.wait(); self.th = None
        self.ask_btn.setEnabled(True)
        if err:
            self.bubble("bot", "That did not work: " + err)
            return
        self.use(text)

    def copy_open(self):
        r = self.request()
        if not r:
            self.bubble("bot", "Please write what you want first.")
            return
        QApplication.clipboard().setText(online.build_request(r))
        site = online.PROVIDERS[online.load()["provider"]]["site"] if online.load()["key"] else online.FREE_SITE
        self.bubble("bot", "Copied. In the website, paste it (Ctrl+V) and send; then copy its whole answer back here.")
        if not self.win.quiet:
            QDesktopServices.openUrl(QUrl(site))
        self.opened = site

    def apply_paste(self):
        t = self.paste.toPlainText().strip()
        if not t:
            self.bubble("bot", "Paste the answer first.")
            return False
        return self.use(t)

    def use(self, text):
        p = ai.parse_answer(text)
        r = self.request()
        if apply_answer(self, p, r, by="online AI"):
            return True
        give_package(self, r, (p.get("reply") + "\n" if p.get("reply") else "") +
                     "The answer had no setting or add-on in it that the program can use. If that AI changed the "
                     "program's code instead, the new version comes with ⋮ > Check for update once it is published.",
                     "online AI")
        return False


def open_online(win, request=""):
    d = OnlineDialog(win, request)
    win.online_dlg = d
    if win.quiet:
        d.show()
        return d
    d.exec()
    return d


# ------------------------------------------------------------------ set up a window
def setup(win, quiet=False):
    win.undo_stack, win.addon_widgets, win.addon_keys, win.req_threads = [], [], [], []
    win.dim, win.ai_full, win.quiet, win.last_message = None, False, quiet, ""
    apply_prefs(win)
    refresh_addons(win)


# ------------------------------------------------------------------ --ui-test: settings, the AI changing settings and
# adding a button, Undo, Reset, full/side AI, Send to Avi (kept, then sent), Ask a different AI (mocked) - no model needed
CANNED_BLUE = ('{"reply": "Done: blue, bigger buttons, AI button on the left.", "changes": [], '
               '"settings": {"button_color": "blue", "button_size": "+30", "ai_button_pos": "left"}}')
CANNED_COPY = ('{"reply": "Here is a Copy all button.", "changes": [], "addon": {"kind": "button", "name": "Copy all", '
               '"label": "Copy all", "steps": [{"do": "copy"}, {"do": "message", "value": "Copied."}]}}')
CANNED_BAD = ('{"reply": "I tried.", "changes": [], "addon": {"kind": "robot", "name": "Email me", "steps": []}}')
CANNED_ONLINE = ('{"reply": "A button that saves a Word file.", "changes": [], "addon": {"kind": "button", '
                 '"name": "Save Word", "label": "Save Word", "steps": [{"do": "save", "value": "docx"}]}}')
CANNED_PASTE = 'Sure! Here it is:\n```json\n{"reply": "Dark look.", "changes": [], "settings": {"theme": "dark"}}\n```'


class _Mock:
    """A local stand-in for the request endpoint and for an online AI."""
    def __init__(self):
        import http.server
        mock = self
        self.fail, self.got, self.asked = True, [], []

        class Hd(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if self.path.startswith("/online"):
                    mock.asked.append(body)
                    out, code = {"text": CANNED_ONLINE}, 200
                elif mock.fail:
                    out, code = {"error": "down"}, 503
                else:
                    mock.got.append(body)
                    out, code = {"ok": True, "id": "t%d" % len(mock.got)}, 200
                b = json.dumps(out).encode()
                self.send_response(code); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hd)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


def ui_test(app, win, a):
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)
    win.quiet = True
    rep = {"version": H.VERSION, "checks": {}, "notes": {}}
    ok = rep["checks"]
    mock = _Mock()
    os.environ["HAFUTZA_REQUEST_URL"] = mock.url + "/request"
    os.environ["HAFUTZA_REQUEST_TEST"] = "1"

    def wait(cond, secs=20):
        end = time.time() + secs
        while time.time() < end:
            app.processEvents()
            if cond():
                return True
            time.sleep(0.05)
        return False

    def shot(name, w=None):
        app.processEvents()
        try:
            (w or win).grab().save(os.path.join(out, name + ".png"))
        except Exception:
            pass

    def body():
        prefs.set_many({"reset": True})
        for x in addons.load_all():
            addons.delete(x["id"])
        apply_prefs(win); refresh_addons(win)
        win.make_tabs(["yi"], {"yi": "שלום עליכם, דאס איז א פראבע.\nא צווייטע שורה."})
        win.tabs.show()
        wait(lambda: False, 0.5)
        shot("01-start")
        rep["notes"]["fonts"] = len(prefs.load_fonts())
        ok["fonts_bundled_20_plus"] = rep["notes"]["fonts"] >= 20

        # 1. Settings window: brightness, volume, font, remembered on disk
        d = open_settings(win)
        d.ctl["brightness"].setValue(70)
        d.ctl["volume"].setValue(55)
        d.ctl["font"].setCurrentIndex(2 if d.ctl["font"].count() > 2 else 0)
        d.ctl["font_size"].setValue(18)
        wait(lambda: False, 0.3)
        shot("02-settings", d)
        d.accept()
        disk = json.load(open(prefs.path(), encoding="utf-8"))
        rep["notes"]["saved_settings"] = {k: disk.get(k) for k in ("brightness", "volume", "font", "font_size")}
        ok["settings_saved"] = disk.get("brightness") == 70 and disk.get("volume") == 55 and disk.get("font_size") == 18 \
            and bool(disk.get("font"))
        ok["brightness_cover_on"] = win.dim is not None and win.dim.isVisible()
        ok["typed_font_used"] = disk.get("font", "") in app.styleSheet()
        shot("03-dimmed")
        ok["settings_window_undo"] = bool(win.undo_stack) and win.undo_stack[-1]["label"] == "Settings window changes"
        run_undo(win, win.undo_stack[-1])
        ok["settings_undo_back"] = prefs.get("brightness") == 100 and not win.dim.isVisible()

        # 2. The AI chat: "make the buttons blue and bigger and move the AI button to the left"
        chat = win.show_ai(True)
        instr = "make the buttons blue and bigger and move the AI button to the left"
        chat.bubble("me", instr)
        handled = handle(chat, ai.parse_answer(CANNED_BLUE), instr, [])
        ok["ai_blue_bigger_left"] = handled and prefs.get("button_color") in ("blue", "#0000ff") and prefs.get("button_size") == 130 \
            and prefs.get("ai_button_pos") == "left" and win.hrow.indexOf(win.ai_btn) == 0
        rep["notes"]["after_blue"] = {k: prefs.get(k) for k in ("button_color", "button_size", "ai_button_pos")}
        wait(lambda: False, 0.3)
        shot("04-blue-bigger-left")
        # the same from the plain words alone (when the AI's answer leaves the settings out)
        run_undo(win, win.undo_stack[-1])
        ok["ai_undo"] = prefs.get("button_color") == "" and prefs.get("button_size") == 100 and win.hrow.indexOf(win.ai_btn) != 0
        handle(chat, ai.parse_answer('{"reply": "OK.", "changes": []}'), instr, [])
        ok["words_alone_work_too"] = prefs.get("button_color") in ("blue", "#0000ff") and prefs.get("ai_button_pos") == "left"

        # 3. Reset to normal (and its Undo)
        prefs.set_many({"theme": "dark", "hide": ["footer"]}); apply_prefs(win)
        rec = reset_normal(win)
        ok["reset_normal"] = prefs.load() == prefs.DEFAULTS or all(prefs.get(k) == v for k, v in prefs.DEFAULTS.items())
        run_undo(win, rec)
        ok["reset_undo"] = prefs.get("theme") == "dark" and "footer" in prefs.get("hide")
        reset_normal(win)
        ok["menu_has_items"] = all(any(t and t[0].startswith(x) for t in menu_items(win))
                                   for x in ("Settings", "AI in the full window", "Check for update", "My add-ons",
                                             "Ask a different AI", "Reset to normal"))
        rep["notes"]["menu"] = [t[0] for t in menu_items(win) if t]

        # 4. AI panel: side (about 400 px) and full window; the ball stays
        win.resize(1300, 900); wait(lambda: False, 0.3)
        set_full(win, False); wait(lambda: False, 0.3)
        rep["notes"]["side_width"] = win.ai_panel.width()
        ok["side_about_400"] = 340 <= win.ai_panel.width() <= 560 and win.scroll.isVisible()
        shot("05-ai-side")
        set_full(win, True); wait(lambda: False, 0.3)
        rep["notes"]["full_width"] = win.ai_panel.width()
        ok["full_window"] = (not win.scroll.isVisible()) and win.ai_panel.width() >= win.centralWidget().width() - 5 \
            and win.ai_ball.isVisible()
        shot("06-ai-full")
        set_full(win, False); wait(lambda: False, 0.3)
        ok["back_to_side"] = win.scroll.isVisible() and win.ai_panel.width() < 600

        # 5. Add-on: a chat request makes a working "Copy all" button
        chat.bubble("me", "add a button that copies all the text")
        handle(chat, ai.parse_answer(CANNED_COPY), "add a button that copies all the text", [])
        btns = [w for w in win.addon_widgets if isinstance(w, QPushButton)]
        ok["addon_button_made"] = len(btns) == 1 and btns[0].text() == "Copy all"
        al = addons.load_all()
        ok["addon_file_saved"] = len(al) == 1 and os.path.isfile(os.path.join(addons.folder(), al[0]["id"] + ".json")) \
            if hasattr(addons, "folder") else len(al) == 1
        QApplication.clipboard().setText("")
        if btns:
            btns[0].click()
        clip = QApplication.clipboard().text()
        ok["addon_button_works"] = clip.startswith("שלום עליכם") and win.last_message == "Copied."
        shot("07-addon-button")
        aid = al[0]["id"] if al else ""
        addons.set_on(aid, False); refresh_addons(win)
        off = not [w for w in win.addon_widgets if isinstance(w, QPushButton)]
        addons.set_on(aid, True); refresh_addons(win)
        on = len([w for w in win.addon_widgets if isinstance(w, QPushButton)]) == 1
        dlg = open_addons(win); shot("08-my-addons", dlg)
        dlg.delete(aid); dlg.accept()
        gone = not addons.load_all() and not win.addon_widgets
        run_undo(win, win.undo_stack[-1])          # undo the delete: it comes back
        back = len(addons.load_all()) == 1
        ok["addon_off_on_delete_undo"] = off and on and gone and back
        rec = reset_normal(win)
        ok["reset_turns_addons_off"] = not win.addon_widgets
        run_undo(win, rec)
        ok["reset_undo_addons_on"] = len(win.addon_widgets) == 1

        # 6. Something it can't build: plain reason, "Send to Avi" and "Ask a different AI"
        win.last_help = None
        handle(chat, ai.parse_answer(CANNED_BAD), "email me the text every morning", [])
        names = {b.objectName() for b in win.last_help.findChildren(QPushButton)} if win.last_help is not None else set()
        ok["cant_build_offers_help"] = names == {"pkg_copy", "pkg_open", "other", "toavi"}
        pk = getattr(win, "last_package", None)
        ptext = open(pk[1], encoding="utf-8-sig").read() if pk and pk[1] and os.path.exists(pk[1]) else ""
        ok["package_file_saved"] = bool(ptext) and "email me the text every morning" in ptext and \
            handoff.REPO in ptext and "app/extras.py" in ptext and "Run workflow" in ptext and \
            os.path.dirname(pk[1]) == package_folder()
        rep["notes"]["package_path"] = pk[1] if pk else ""
        QApplication.clipboard().setText("")
        cb = [b for b in win.last_help.findChildren(QPushButton) if b.objectName() == "pkg_copy"]
        if cb:
            cb[0].click()
        ok["package_copy_button"] = QApplication.clipboard().text() == getattr(win, "last_link", None) and \
            handoff.GUIDE in QApplication.clipboard().text() and \
            "email me the text every morning" in QApplication.clipboard().text()
        win.last_help = None
        handle(chat, ai.parse_answer('{"reply": "That needs the internet and a mail account.", "changes": [], "too_big": true}'),
               "email me the text every morning", [])
        ok["too_big_offers_help"] = win.last_help is not None
        shot("09-cant-build")
        # part done, part not: the settings are applied AND he gets the package for the rest
        win.last_help = None
        before = prefs.load().get("font_size")
        handle(chat, ai.parse_answer('{"reply": "I made the letters bigger. Sending email I can not build.", "changes": [], '
                                     '"settings": {"font_size": 22}, "too_big": true}'),
               "bigger letters and email me the text", [])
        ok["partial_then_package"] = win.last_help is not None and prefs.load().get("font_size") == 22
        rep["notes"]["partial_font_before"] = before
        if win.undo_stack:
            run_undo(win, win.undo_stack[-1])
        ok["partial_undo"] = prefs.load().get("font_size") == before

        # 6b. Hebrew answers show right-to-left; the Update window takes a link from another AI (checked first)
        chat.bubble("bot", "שיניתי את הצבע של הכפתורים לכחול.\n2 שינויים נעשו.")
        lbs = [l for l in chat.findChildren(QLabel) if hasattr(l, "rtl")]
        ok["hebrew_bubble_rtl"] = bool(lbs) and lbs[-1].rtl and lbs[-1].text().startswith("\u200f") and \
            "\n\u200f2" in lbs[-1].text()
        import updater
        ok["link_parse"] = updater.parse_link("https://github.com/someone/hafutza-typing-offline/releases/tag/v1.6.1") == \
            ("someone/hafutza-typing-offline", "v1.6.1")
        base = "https://github.com/someone/hafutza-typing-offline/releases/download/"

        def fake(u, bad_url=False, other=False):
            if u.endswith("/repos/someone/hafutza-typing-offline"):
                return {"full_name": "someone/hafutza-typing-offline",
                        "parent": {"full_name": "x/y" if other else updater.HOME_REPO}}
            if u.endswith("/releases/latest"):
                return {"tag_name": "v1.6.1"}
            if u == base + "v1.6.1/update.json":
                return {"version": "1.6.1", "sha256": "0" * 64, "size": 5,
                        "url": ("https://example.com/x.exe" if bad_url else base + "v1.6.1/HafutzaTyping-Update.exe")}
            raise OSError("404")

        def refused(**kw):
            try:
                updater.from_link("https://github.com/someone/hafutza-typing-offline", lambda u: fake(u, **kw))
                return False
            except RuntimeError:
                return True
        good = updater.from_link("https://github.com/someone/hafutza-typing-offline", fake)
        ok["link_checks"] = good["version"] == "1.6.1" and refused(other=True) and refused(bad_url=True)
        ud = H.UpdateDialog(win, known={"version": H.VERSION, "url": "", "sha256": "", "size": 1, "newer": False})
        QApplication.processEvents()
        ud.link_in.setText("https://example.com/not-github")
        ud.from_link(ask=False); ud.lchk.wait(); QApplication.processEvents()
        bad_msg = "not a GitHub link" in ud.msg.text()
        real_from, fetched = updater.from_link, []
        updater.from_link = lambda link: dict(good)
        ud.fetch = lambda: fetched.append(ud.m["version"])
        ud.link_in.setText("https://github.com/someone/hafutza-typing-offline")
        ud.from_link(ask=False); ud.lchk.wait(); QApplication.processEvents()
        updater.from_link = real_from
        ok["update_from_link"] = bad_msg and fetched == ["1.6.1"]
        ud.close()

        # 7. Send to Avi: no internet -> kept; internet back -> sent by itself
        for f in (requests_out._file(),):
            if os.path.exists(f):
                os.remove(f)
        mock.fail = True
        win.last_avi = None
        send_to_avi(chat, "email me the text every morning")
        wait(lambda: win.last_avi is not None, 30)
        ok["avi_kept_offline"] = win.last_avi == "kept" and len(requests_out.pending()) == 1
        mock.fail = False
        go = start_flusher(win); go()
        wait(lambda: not requests_out.pending() and not win._flushing, 30)
        ok["avi_sent_when_online"] = not requests_out.pending() and len(mock.got) == 1 and \
            mock.got[0]["text"].endswith("email me the text every morning") and mock.got[0]["version"] == H.VERSION
        win.last_avi = None
        send_to_avi(chat, "a second request")
        wait(lambda: win.last_avi is not None, 30)
        ok["avi_sent_online"] = win.last_avi == "sent" and len(mock.got) == 2
        rep["notes"]["avi_bodies"] = mock.got
        shot("10-sent-to-avi")

        # 8. Ask a different AI, with a (mocked) online AI: it answers an add-on, checked and applied with Undo
        os.environ["HAFUTZA_ONLINE_URL"] = mock.url + "/online"
        od = open_online(win, "add a button that saves the text as a Word file")
        od.ask()
        wait(lambda: od.th is None and len(mock.asked) == 1, 30)
        names = [x["name"] for x in addons.load_all()]
        ok["online_ai_addon"] = "Save Word" in names and "copy" not in json.dumps(mock.asked[0].get("request", "")) \
            and "settings" in mock.asked[0].get("system", "")
        ok["online_request_has_no_typed_text"] = "שלום" not in json.dumps(mock.asked, ensure_ascii=False)
        sw = [w for w in win.addon_widgets if isinstance(w, QPushButton) and w.text() == "Save Word"]
        if sw:
            sw[0].click()
        ok["online_addon_works"] = bool(getattr(win, "last_saved", "")) and os.path.isfile(win.last_saved) and \
            zipfile.is_zipfile(win.last_saved)
        shot("11-online-ai", od)
        run_undo(win, win.undo_stack[-1])
        ok["online_undo"] = "Save Word" not in [x["name"] for x in addons.load_all()]
        od.accept()

        # 9. No key: copy a ready request for a free AI website, paste the answer back
        del os.environ["HAFUTZA_ONLINE_URL"]
        online.save("gemini", "", "")
        od = open_online(win, "make it dark")
        ok["no_key_hides_ask"] = not od.ask_btn.isVisible() or od.ask_btn.isHidden()
        od.copy_open()
        clip = QApplication.clipboard().text()
        ok["copied_request"] = "make it dark" in clip and "settings" in clip and getattr(od, "opened", "").startswith("https://")
        od.paste.setPlainText(CANNED_PASTE)
        od.apply_paste()
        ok["paste_back_applied"] = prefs.get("theme") == "dark"
        shot("12-paste-back", od)
        run_undo(win, win.undo_stack[-1])
        ok["paste_undo"] = prefs.get("theme") == "light"
        od.accept()

        # 10. Saved between runs: what is on disk loads again
        prefs.set_many({"button_color": "green"})
        prefs._cur = None
        ok["remembered_between_runs"] = prefs.load()["button_color"] in ("green", prefs.color("green"))
        reset_normal(win)
        for x in addons.load_all():
            addons.delete(x["id"])
        refresh_addons(win)

    try:
        body()
    except Exception:
        rep["error"] = traceback.format_exc()
        log("ui test: " + rep["error"])
    rep["pass"] = bool(ok) and all(ok.values()) and "error" not in rep
    rep["failed"] = [k for k, v in ok.items() if not v]
    json.dump(rep, open(os.path.join(out, "report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(out, "result.txt"), "w", encoding="utf-8") as f:
        f.write(("PASS" if rep["pass"] else "FAIL") + "\n" + "\n".join("%s %s" % ("ok  " if v else "FAIL", k) for k, v in ok.items())
                + ("\n" + rep.get("error", "")))
    mock.srv.shutdown()
    QTimer.singleShot(100, lambda: app.exit(0 if rep["pass"] else 1))
