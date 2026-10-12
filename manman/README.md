# 慢慢來 (Màn Màn Lái - "take it slow")

A small offline app for practicing Taiwanese Mandarin in short bursts, built for
ADHD-friendly learning: one button to start, 1-6 minute sessions, constantly
changing activities, and no streaks to break.

## Running it

Open `index.html` in Firefox (or any modern browser). That's it - no install,
no account, no internet needed after download.

If something misbehaves when opened as a file, serve the folder instead:

```sh
cd manman
python3 -m http.server 8000
# then visit http://localhost:8000
```

## What's in it

- **Bursts**: 5, 10 or 20 quick cards. Spaced repetition picks words you're
  about to forget first, then mixes in a few new ones across your chosen topics.
- **Activities**: listen and choose, read and choose, pick the characters,
  tone hunt, say it out loud, and shadowing with a pitch graph of your voice.
- **Zhuyin first**: shown above characters and faded out as you learn each word
  (tap to peek). Pinyin is off by default.
- **Scenes**: private roleplay conversations (bubble tea shop, night market,
  family dinner, your classroom, horror movie night, a dungeon crawl). The app
  plays the other person; you can swap roles.
- **Topics**: survival basics, food & drinks, family, classroom, horror movies,
  RPGs & games - 187 words and phrases using Taiwan vocabulary and readings.

Keyboard: `Enter` start/next, `Space` replay, `1`-`4` answer, `R` record, `Esc` stop.

## Audio

Speech uses your computer's built-in voices. For a Taiwan accent install the
Chinese (Taiwan) voice: on Windows add the *Chinese (Traditional, Taiwan)*
language with text-to-speech; on macOS download *Mei-Jia* under Spoken Content.
The in-app Help page has step-by-step instructions.

## Privacy

Everything stays in your browser. Recordings are analyzed in memory and never
saved or uploaded. Use Settings → Export backup to keep a copy of your progress.

## Editing content

Words and scenes live in `js/data.js`, written in numbered pinyin
(`zhen1 zhu1 nai3 cha2`). Zhuyin is generated automatically. After editing, run:

```sh
node manman/tools/validate.js
```

It checks that every character has a matching syllable and that all pinyin is valid.
