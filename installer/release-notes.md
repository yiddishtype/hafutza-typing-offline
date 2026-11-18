**Hafutza Typing for Windows** - types up Yiddish (and Hebrew, English, Spanish, French) videos and recordings on your own computer, with no internet, and translates them to Yiddish, English, Hebrew, Spanish and French.

Download **HafutzaTyping-Setup.exe** below and open it. (Have version 1.1 or 1.2? Just press the program's **Update** button. Have version 1.0? Install this one over it. Your typed texts and the downloaded parts are kept.)

New in 1.3:
- The **Update** button now opens a window with two parts: **1. Update - what's new** shows what the newest version adds, with one button to update; **2. Request an update**: write what you want changed or added (in Yiddish or English, with the on-screen Yiddish keyboard if you like) and press **Send**. It reaches us, and the program says "Got it, your request was sent."
- No internet when you press Send? The request is kept on your computer and goes by itself the next time the program is open with the internet on.
- The **Update** button at the top turns **blue** when a new version is ready (it stays plain when you have the newest).

New in 1.2:
- **Watch and fix**: after a video is typed, press **Watch the video with the text on it, and fix the text**. The video plays with the typing and the translation on it, line by line.
- **Play / Pause** (or the space bar), and buttons to go **back or forward 5, 10 or 15 seconds**. Click any line in the list to jump there.
- Fix a line: erase it, type it again, or use the on-screen **Yiddish keyboard**. Press **Save the fix** (or Enter): the .txt and .srt files are written again with the fix.
- **The program learns your fixes**: a word you fix is remembered and fixed by itself in the next videos (in the typing and in the translations). See or delete what it learned under **Learned words**. (The big speech and translation models are not retrained; it is your own word list.)
- **My typed videos**: open any video typed with 1.2 again to watch and fix. (Videos typed before 1.2 have no line timings: type them again to watch them.)
- **Video links now come with the picture** (up to 720p), so a pasted link plays in the player like a dropped file. If a site gives only the sound, the text shows on a dark screen.
- Each typed text is also saved as subtitles (.srt) next to the .txt.

New in 1.1:
- **Update** button (top right): checks for a new version and installs it with one click (downloads only the program, not the big speech parts). It also quietly checks when the program opens.
- Big **drop box**: drop one or more video/audio files on it (or click it to choose them); several files are typed one after another.
- **Paste a video link** (YouTube, Facebook, other sites, or a link to an .mp4/.mp3): the program gets the video (this step needs the internet), then types it as usual. Private or sign-in-only videos can't be fetched: save them and drop the file in.
- Right-click a video or sound file in Windows: **Open with > Hafutza Typing**.

- If Windows says "Windows protected your PC": click **More info**, then **Run anyway**. (The program is new and not signed by a paid certificate, so Windows does not know it yet.)
- The first time it opens it downloads the translation and Hebrew / English / Spanish / French parts once (about 3 GB). After that it works with no internet.

Needs: Windows 10 or 11 (64-bit), about 5 GB of free disk space, 8 GB of memory (4 GB works but slowly).

Files: HafutzaTyping-Setup.exe = the full installer. HafutzaTyping-Update.exe and update.json = used by the Update button.

Models: ivrit-ai Yiddish and Hebrew Whisper turbo (Apache-2.0), OpenAI Whisper large-v3-turbo (MIT), Meta NLLB-200 distilled 1.3B (CC-BY-NC-4.0, non-commercial use). Speech is read by faster-whisper / CTranslate2 (MIT). Video links: yt-dlp (Unlicense).
