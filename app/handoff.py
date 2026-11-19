"""When the program's own AI can't do what he asked: a ready package he can give to ANY other AI (ChatGPT, Gemini,
Claude, ...). It holds his request and everything that AI needs: the two ways it can help (an answer the program
applies by itself, or a change to the program's code), where the code is, which file does what, and how to build and
publish a new version. No internet needed to make it; nothing of his typed text or his data goes in it.
No window code here."""
import datetime, os, re

import ai

REPO = "https://github.com/yiddishtype/hafutza-typing-offline"
GUIDE = REPO + "/blob/main/AGENTS.md"

FILES = """- app/hafutza.py    the main window: pick a video, Start, the typed-text tabs, the AI side panel (class AIDialog), the
                    Update window, the one-time download of parts, the program's self-tests (--selftest, --ai-test)
- app/extras.py     the three-dots menu, Settings window, the look of the window (apply_prefs, style_sheet), add-ons,
                    Undo / Reset to normal, "Ask a different AI", what the AI chat does with an answer (apply_answer),
                    the --ui-test
- app/ai.py         the built-in offline AI (Qwen3.5-4B run by llama-server): its instructions (SYS), examples (SHOTS),
                    reading its answers (parse_answer), applying text changes
- app/handoff.py    this package
- app/prefs.py      every setting (DEFAULTS), checking and saving them (settings.json)
- app/addons.py     add-ons: new buttons / menu items / shortcuts / side notes made from fixed steps (checked, no code)
- app/online.py     asking an online AI with his own key
- app/engine.py     the typing itself: reading sound (PyAV), faster-whisper, translation (NLLB), where data is kept
- app/player.py     watching a typed video with its text, fixing lines
- app/learn.py      words learned from his fixes;  app/project.py  a typed video kept with its timings
- app/links.py      getting a video from a link (yt-dlp);  app/updater.py  the Update button (update.json)
- app/whatsnew.py   what each version added (shown by the Update button)
- installer/hafutza.iss         the Windows installer (Inno Setup);  installer/release-notes.md  the release page text
- .github/workflows/build.yml   builds, tests and publishes everything on GitHub's own Windows computers
- requirements.txt              the Python parts (Python 3.12)"""

BUILD = """You can NOT push to that repository and you need no password or key from me. Instead:
1. Fork it (your own copy on GitHub; a GitHub account is all you need).
2. Change the code in app/ (Python 3.12 + PySide6). Keep every feature that is there now. Never put a password, key
   or token in the program or the repository.
3. Pick a new version number higher than mine (if I have 1.6, use 1.6.1). Add a line for it to app/whatsnew.py (NOTES)
   and installer/release-notes.md, and set FALLBACK_VERSION in app/updater.py to it.
4. In your fork: Actions tab > enable workflows > build > Run workflow, with
   release = "v<number>" (like v1.6.1), version = "<number>", replace_v10 = "no", long_tests = "no".
   It builds the installer and the update on GitHub's Windows computers, runs every test, and publishes a release
   in your fork with HafutzaTyping-Update.exe and update.json.
5. When it is green, give me the link to your fork (https://github.com/<you>/hafutza-typing-offline).
   I paste it in the program: Update window > "Install an update another AI made". The program checks that the fork
   really comes from Hafutza Typing and that the file is in it, then installs it. My texts and settings stay.
6. Please also open a pull request from your fork to yiddishtype/hafutza-typing-offline, so the change stays in the
   next normal updates too.
Full guide: """ + GUIDE


def link_text(request, version=""):
    """-> the short message with THE LINK: what he pastes to any AI (ChatGPT, Claude, Gemini, ...)."""
    return ("Please change my program Hafutza Typing (version %s) for me.\n\n"
            "What I want: %s\n\n"
            "The program's code and a full guide for you (how it is built, how to make the change and get it to me "
            "as an update, no password needed): %s\n\n"
            "Answer me in short simple English and tell me what I must do."
            % (version or "?", request.strip(), GUIDE))


def package(request, version="", ai_reply=""):
    """-> the whole text to give another AI."""
    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    spec = ai.SPEC_FULL.replace("{FONTS}", "any of the program's fonts (Settings shows them)")
    parts = [
        "HAFUTZA TYPING: A REQUEST FOR ANY AI",
        "",
        "The program's code and the full guide for you: " + GUIDE,
        "",
        "I use \"Hafutza Typing\" (version %s), a free Windows program that types out Yiddish (and other) videos and "
        "audio, fully offline. Its built-in offline AI could not do what I want, so I am asking you." % (version or "?"),
        "",
        "WHAT I WANT:",
        request.strip(),
        "",
    ]
    if ai_reply:
        parts += ["(The built-in AI said: %s)" % ai_reply.strip(), ""]
    parts += [
        "Please help in ONE of these two ways, whichever can do it:",
        "",
        "WAY 1 (quick, if it can be done with the program's settings or a new part made of its building blocks):",
        "answer with one JSON object as described below. I paste it into the program (three dots > Ask a different AI >",
        "paste box > Apply it); the program checks it and applies it, with Undo.",
        "",
        spec,
        "",
        "WAY 2 (anything else: a new feature, a change in how it works):",
        "the program is open source: " + REPO,
        "Change its code there. Which file does what:",
        FILES,
        "",
        "How to build and publish a new version:",
        BUILD,
        "",
        "Tell me plainly which way you used and what I must do next, in short simple English.",
        "",
        "(Made by the program on %s.)" % when,
    ]
    return "\n".join(parts) + "\n"


def slug(request):
    s = re.sub(r"[^A-Za-z0-9֐-׿]+", " ", request).strip()
    return ("-".join(s.split()[:6]) or "request")[:50]


def save(text, folder, request):
    """Write the package as a .txt file (Notepad-friendly) in folder; -> its path."""
    os.makedirs(folder, exist_ok=True)
    name = "For any AI - %s - %s.txt" % (datetime.datetime.now().strftime("%Y-%m-%d %H%M%S"), slug(request))
    p = os.path.join(folder, name)
    with open(p, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(text)
    return p
