"""What each version added, in plain words (shown by the Update button, and written into update.json)."""

NOTES = {
    "1.3": [
        "The Update button now has two parts: 1) Update - see what is new and update with one press; "
        "2) Request an update - write what you want changed or added, press Send, and it reaches us.",
        "No internet when you send a request? It is kept and goes by itself the next time the internet is on.",
        "The Update button turns blue when a new version is ready.",
    ],
    "1.2": [
        "Watch a typed video with the text on it, and fix the text.",
        "Play / Pause, and go back or forward 5, 10 or 15 seconds.",
        "Fix a line: erase it, type it again or use the Yiddish keyboard. The .txt and .srt are saved with the fix.",
        "The program learns your fixes: a word you fix is fixed by itself in the next videos (see Learned words).",
        "My typed videos: open a typed video again to watch and fix it.",
        "Video links now come with the picture (up to 720p).",
    ],
    "1.1": [
        "Update button: checks for a new version and installs it with one press.",
        "Big drop box: drop one or more files; they are typed one after another.",
        "Paste a video link (YouTube, Facebook, other sites) and it is typed.",
    ],
}


def text(version):
    lines = NOTES.get(str(version))
    return "\n".join("- " + l for l in lines) if lines else ""
