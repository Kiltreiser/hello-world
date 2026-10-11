"""Find audio files and group them into albums."""

import os
import re
from collections import Counter

from . import tags as tagio

DISC_DIR_RE = re.compile(r"^(cd|disc|disk|side)[\s._-]*\d+\b", re.I)
FILENAME_RE = re.compile(
    r"^\s*(?:(?P<disc>\d)[-.](?P<track2>\d{2})|(?P<track>\d{1,3}))(?:[\s._-]+|$)(?P<rest>.*)$"
)
YEAR_RE = re.compile(r"[\(\[]\s*((?:19|20)\d{2})\s*[\)\]]")
JUNK_RE = re.compile(r"[\(\[][^\)\]]*(flac|mp3|320|v0|kbps|24bit|16bit|web|cd|vinyl|lossless|aac|khz)[^\)\]]*[\)\]]", re.I)


class TrackFile:
    def __init__(self, path, root):
        self.path = path
        self.rel = os.path.relpath(path, root)
        self.tags = {}
        self.duration = 0.0
        self.has_cover = False
        self.error = None

    def load(self):
        try:
            info = tagio.read_file(self.path)
            self.tags = info["tags"]
            self.duration = info["duration"]
            self.has_cover = info["has_cover"]
        except Exception as e:  # unreadable or corrupt file
            self.error = f"{type(e).__name__}: {e}"
        return self

    # Guesses based on the file name, used when tags are missing.
    def filename_guess(self):
        stem = os.path.splitext(os.path.basename(self.path))[0]
        m = FILENAME_RE.match(stem)
        disc, track, title = None, None, stem
        if m:
            if m.group("disc"):
                disc, track = int(m.group("disc")), int(m.group("track2"))
            else:
                track = int(m.group("track"))
            title = m.group("rest").strip() or stem
        return disc, track, title.replace("_", " ").strip()

    @property
    def title_hint(self):
        return self.tags.get("title") or self.filename_guess()[2]

    @property
    def track_hint(self):
        n = _int(self.tags.get("tracknumber"))
        return n if n else self.filename_guess()[1]

    @property
    def disc_hint(self):
        n = _int(self.tags.get("discnumber"))
        return n if n else (self.filename_guess()[0] or 1)


class AlbumGroup:
    def __init__(self, group_id, folder, files, root):
        self.id = group_id
        self.root = root
        self.folder = folder
        self.rel = os.path.relpath(folder, root) if folder != root else os.path.basename(root)
        self.files = sorted(files, key=lambda f: (f.disc_hint, f.track_hint or 999, f.rel))

    # ---- hints used to search MusicBrainz --------------------------------
    def _common(self, field, min_share=0.5):
        values = [f.tags.get(field) for f in self.files if f.tags.get(field)]
        if not values:
            return None
        value, count = Counter(values).most_common(1)[0]
        return value if count >= min_share * len(self.files) else None

    @property
    def track_artists(self):
        return {(f.tags.get("artist") or "").strip().lower()
                for f in self.files if f.tags.get("artist")}

    @property
    def looks_various(self):
        """Many different track artists and no single dominant one."""
        artists = [f.tags.get("artist", "").strip().lower() for f in self.files if f.tags.get("artist")]
        if len(artists) < 3:
            return False
        top = Counter(artists).most_common(1)[0][1]
        return len(set(artists)) >= 3 and top < 0.5 * len(artists)

    def folder_guess(self):
        """Parse 'Artist - Album (Year)' style folder names."""
        name = os.path.basename(self.folder)
        year = None
        m = YEAR_RE.search(name)
        if m:
            year = m.group(1)
        name = JUNK_RE.sub("", YEAR_RE.sub("", name)).strip(" -_.")
        artist = None
        if " - " in name:
            artist, name = [p.strip() for p in name.split(" - ", 1)]
        else:
            parent_dir = os.path.dirname(self.folder)
            parent = os.path.basename(parent_dir)
            # Artist/Album layout - but never use the scanned folder itself
            if parent and not DISC_DIR_RE.match(parent) and _is_inside(parent_dir, self.root):
                artist = parent
        return artist, name, year

    def hints(self):
        f_artist, f_album, f_year = self.folder_guess()
        album = self._common("album", 0.3) or f_album
        artist = self._common("albumartist", 0.3)
        if not artist and not self.looks_various:
            artist = self._common("artist", 0.5)
        if not artist and not self.looks_various:
            artist = f_artist
        date = self._common("date", 0.3) or self._common("originaldate", 0.3) or f_year
        year = date[:4] if date else None
        discs = {f.disc_hint for f in self.files}
        return {
            "album": album,
            "artist": artist,
            "year": year,
            "track_count": len(self.files),
            "disc_count": max(discs) if discs else 1,
            "various": self.looks_various or (artist or "").lower() in ("various artists", "various", "va"),
            "mb_albumid": self._common("mb_albumid", 0.8),
        }

    def summary(self):
        """What the album looks like now, from the tags only."""
        artist = self._common("albumartist", 0.5)
        if not artist:
            n = len(self.track_artists)
            artist = self._common("artist", 0.5) or (f"Mixed ({n} artists)" if n > 1 else None)
        date = self._common("date", 0.3) or ""
        return {"album": self._common("album", 0.3), "artist": artist,
                "year": date[:4] or None, "tracks": len(self.files)}


def _is_inside(path, root):
    path, root = os.path.abspath(path), os.path.abspath(root)
    return path != root and path.startswith(root.rstrip(os.sep) + os.sep)


def _int(value):
    try:
        return int(str(value).split("/")[0])
    except (TypeError, ValueError):
        return None


def find_audio_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if not name.startswith(".") and tagio.is_audio_file(name):
                yield os.path.join(dirpath, name)


def scan(root, progress=None):
    """Read every audio file under ``root`` and group them into albums.

    Returns (albums, unreadable_files).
    """
    root = os.path.abspath(os.path.expanduser(root))
    paths = list(find_audio_files(root))
    by_folder = {}
    bad = []
    for i, path in enumerate(paths):
        tf = TrackFile(path, root).load()
        if progress:
            progress(i + 1, len(paths), path)
        if tf.error:
            bad.append(tf)
            continue
        folder = os.path.dirname(path)
        # Album/CD1, Album/CD2 -> one album
        if DISC_DIR_RE.match(os.path.basename(folder)) and folder != root:
            folder = os.path.dirname(folder)
        by_folder.setdefault(folder, []).append(tf)

    albums = []
    for folder in sorted(by_folder):
        for files in _split_folder(by_folder[folder]):
            albums.append(AlbumGroup(str(len(albums) + 1), folder, files, root))
    return albums, bad


def _split_folder(files):
    """A folder normally holds one album. If it clearly holds several
    (e.g. a 'Singles' or 'Misc' folder), split it by album tag."""
    counts = Counter(f.tags.get("album", "").strip().lower() for f in files)
    real = [a for a, c in counts.items() if a and c >= 3]
    if len(real) < 2:
        return [files]
    groups = {}
    for f in files:
        key = f.tags.get("album", "").strip().lower()
        groups.setdefault(key, []).append(f)
    return list(groups.values())
