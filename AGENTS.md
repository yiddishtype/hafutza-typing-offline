# Hafutza Typing: guide for any AI

You were sent here by the owner of **Hafutza Typing**, a free Windows program that types out Yiddish (and Hebrew,
English, Spanish, French) videos and audio fully offline, and translates them. Its built-in offline AI could not do
something he asked for. His request is in the message he gave you. Please help him, and answer him in **short, simple
English**: he is not a programmer.

## Two ways to help

**Way 1, quick (a plain chat AI can do this; no GitHub needed).**
If the request can be done with the program's settings, colours, sizes, fonts, or a new button made of its
building blocks, answer with ONE JSON object in the format described by `SPEC_FULL` in `app/ai.py`.
He pastes it into the program (three dots ⋮ > Ask a different AI > paste box > Apply it). The program checks it and
applies it, with Undo. No code runs.

**Way 2, a real change to the program (needs a GitHub account).**
For anything else (a new feature, a change in how it works), change the code and publish an update **in your own
fork**, then give him the fork's link. If you are a plain chat AI with no GitHub account, you can not publish an
update: write the full changed files and tell him plainly that someone with a GitHub account must do the steps
below (or that he can send the request to his assistant with the program's Send to Avi button).

## How to make and publish the change (Way 2)

You can NOT push to that repository and you need no password or key from me. Instead:
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

Rules:
- **Never** put a password, API key or token in the code, the repository, a release or a link. You need none.
- Keep every feature that is there now. Keep `MANIFEST_URL` in `app/updater.py` pointing at
  `yiddishtype/hafutza-typing-offline`, so his normal updates keep coming.
- His typed texts, settings and downloaded parts must be kept by the update.
- The build runs the program's own tests on Windows. Do not give him the link until the run is green.
- The program only accepts a fork of `yiddishtype/hafutza-typing-offline`, and only an update file stored in that
  fork's own releases (`update.json` with `version`, `url`, `sha256`, `size`; the build writes it for you).

## Which file does what

```
- app/hafutza.py    the main window: pick a video, Start, the typed-text tabs, the AI side panel (class AIDialog), the
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
- requirements.txt              the Python parts (Python 3.12)
```

Python 3.12 + PySide6, built with PyInstaller and Inno Setup on GitHub's Windows computers
(`.github/workflows/build.yml`). The offline AI is Qwen3.5-4B run by llama-server; the AI and speech models are
downloaded once by the program from this repository's `models-v1` release.

Tests you can run on any computer (from `app/`): `python3 hafutza.py --ui-test --out <folder>` (with
`QT_QPA_PLATFORM=offscreen`), results in `<folder>/result.txt`. A few checks there need the internet.
