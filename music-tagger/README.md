# TagFixer

A simple app for fixing messy music tags in bulk. It looks every album up on
[MusicBrainz](https://musicbrainz.org) (the free, community-run music
database), shows you exactly what will change, and writes the correct tags
when you press **Apply**. Soundtracks and various-artist compilations are
tagged so that Plex and Plexamp file them properly.

Works with MP3, FLAC, M4A/AAC/ALAC, Ogg Vorbis, Opus, AIFF and WAV.

## Installing

You need Python 3.8 or newer ([python.org](https://www.python.org/downloads/)).
Then, in a terminal, from this `music-tagger` folder:

```
pip install -r requirements.txt
```

That installs one library, [mutagen](https://mutagen.readthedocs.io), which
reads and writes the tags.

## Using it

```
python -m tagfixer
```

Your browser opens on the app (if it doesn't, go to http://localhost:8765).

1. **Pick your music folder** (type the path or press *Browse…*) and press
   **Scan & look up**. MusicBrainz allows about one request per second, so a
   big library takes a while. Albums appear as they're looked up, and you can
   start reviewing straight away. Lookups are cached, so a second scan is fast.
2. **Review.** Each row shows the album now and what it will become. Albums
   marked *Ready* (85%+ confidence) are ticked automatically. Click any row to see:
   - the changes that apply to every track, and the per-track changes
   - other editions MusicBrainz knows about. Press *Use this* to switch, or
     paste a link to the exact release from musicbrainz.org.
3. **Apply.** Only ticked albums are written. **Undo last batch** puts the old
   tags back, and you can undo again to go further back.

Filters at the top show what needs attention: *Needs a look* (a weaker match),
*Local fix* (not found online, but the album artist/compilation tags can still
be fixed from the files), *Not found*.

### What it changes

- Title, artist, album, album artist, year, track and disc numbers
- **Release type** (album, soundtrack, compilation, live, EP...)
- **Compilation flag** and album artist "Various Artists" for multi-artist albums
- MusicBrainz IDs, sort names, label, catalogue number. These help Plex match
  albums and artists reliably.
- Cover art, added only to files and folders that don't have any.

It **never touches** anything else in the file (ratings, lyrics, ReplayGain,
comments...). It doesn't rename or move files, and it keeps your genres unless
you ask otherwise (soundtracks get the genre "Soundtrack" by default).

### Soundtracks and compilations

How soundtracks are grouped is up to you (Settings → Soundtracks):

| Setting | *Pulp Fiction* (many artists) | *Inception* (Hans Zimmer score) |
|---|---|---|
| Follow MusicBrainz (default) | Various Artists | Hans Zimmer |
| All under "Various Artists" | Various Artists | Various Artists |
| All under "Soundtrack" | Soundtrack | Soundtrack |

Whichever you choose, every soundtrack is tagged with release type
`soundtrack`. Plex uses that tag to sort albums into sections such as
Soundtracks, Compilations and Live on the artist page. Multi-artist compilations get album artist *Various Artists* and
the compilation flag, so Plex shows them as one album instead of splitting it
across a dozen artists.

## Plex / Plexamp setup

Plex only reads your tags if you tell it to:

1. In Plex, open your music library → **Edit Library → Advanced**.
2. Tick **Prefer local metadata**.
3. After a big TagFixer run, open the library's **⋯** menu and choose **Refresh
   All Metadata** so Plex re-reads every file. A normal scan only picks up
   files whose tags changed.

Optional: in TagFixer's Settings, enter your Plex server address and
[token](https://support.plex.tv/articles/204059436). TagFixer will then tell
Plex to rescan each folder it changes. If TagFixer runs on a different computer
from Plex, fill in the path translation too (e.g. `/Volumes/Music` →
`/data/music`).

## Running on a NAS or server without a screen

```
python -m tagfixer --cli /path/to/music            # look everything up, print a report
python -m tagfixer --cli /path/to/music --apply    # ...and write the confident matches
python -m tagfixer --undo                          # undo the last batch
```

You can also run the web app on the NAS and open it from another computer:
`python -m tagfixer --host 0.0.0.0 --no-browser`, then go to
`http://<nas-address>:8765`. Only do this on a home network you trust: anyone
who can reach that port can change your tags.

## Good to know

- **Back up first.** There's an undo, but a backup is a good idea before
  rewriting thousands of files with any tool.
- Matching uses existing tags, folder names (`Artist/Album (Year)` or
  `Artist - Album`), file names, track counts and track lengths. Files with
  no tags *and* meaningless names (`track01.mp3` in a folder called `New
  Folder`) can't be identified. Those show up as *Not found*, and you can
  paste a MusicBrainz link for them.
- Settings and undo history are stored in `~/.local/share/tagfixer`, and the
  lookup cache in `~/.cache/tagfixer`.

## Running the tests

```
python -m unittest discover -s tests
```

(Needs `ffmpeg` installed to generate sample audio files.)
