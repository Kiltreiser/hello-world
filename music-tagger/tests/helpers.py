"""Test helpers: make real (silent) audio files and a fake MusicBrainz."""

import copy
import os
import shutil
import subprocess
import tempfile

from tagfixer import tags as tagio
from tagfixer.musicbrainz import VARIOUS_ARTISTS_ID

HAVE_FFMPEG = shutil.which("ffmpeg") is not None
_TEMPLATES = {}
_TEMPLATE_DIR = tempfile.mkdtemp(prefix="tagfixer-test-")

CODECS = {
    ".mp3": ["-c:a", "libmp3lame", "-b:a", "32k"],
    ".flac": ["-c:a", "flac"],
    ".m4a": ["-c:a", "aac", "-b:a", "32k"],
    ".ogg": ["-c:a", "libvorbis", "-q:a", "0"],
    ".opus": ["-c:a", "libopus", "-b:a", "16k"],
}


def make_audio(path, seconds, tags=None):
    """Create a silent audio file of the given length and write ``tags``."""
    ext = os.path.splitext(path)[1]
    key = (ext, seconds)
    src = _TEMPLATES.get(key)
    if not src or not os.path.exists(src):
        src = os.path.join(_TEMPLATE_DIR, f"{seconds}{ext}")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "anullsrc=r=22050:cl=mono", "-t", str(seconds), *CODECS[ext],
                        "-map_metadata", "-1", src], check=True)
        _TEMPLATES[key] = src
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.copy(src, path)
    if tags:
        tagio.write_file(path, tags)
    return path


def _credit(name, mbid, sort=None, join=""):
    return {"name": name, "joinphrase": join,
            "artist": {"id": mbid, "name": name, "sort-name": sort or name}}


def release(rid, title, artist_credit, tracks, rg_id="rg-" + "0" * 33, primary="Album",
            secondary=(), date="2001-01-01", first_date=None, discs=None):
    """Build a MusicBrainz-shaped release. ``tracks`` = [(title, seconds, credit)]"""
    discs = discs or [tracks]
    media = []
    n = 0
    for d, disc_tracks in enumerate(discs, 1):
        mt = []
        for i, (t, secs, credit) in enumerate(disc_tracks, 1):
            n += 1
            mt.append({"id": f"{rid}-t{n}", "position": i, "number": str(i), "title": t,
                       "length": secs * 1000, "artist-credit": credit,
                       "recording": {"id": f"{rid}-r{n}", "title": t, "length": secs * 1000,
                                     "artist-credit": credit, "isrcs": []}})
        media.append({"position": d, "format": "CD", "track-count": len(mt), "tracks": mt})
    return {
        "id": rid, "title": title, "status": "Official", "date": date, "country": "US",
        "barcode": "123456789012", "artist-credit": artist_credit,
        "label-info": [{"catalog-number": "CAT-1", "label": {"name": "Test Records"}}],
        "release-group": {"id": rg_id, "primary-type": primary, "secondary-types": list(secondary),
                          "first-release-date": first_date or date},
        "media": media, "genres": [],
    }


class FakeMB:
    """Stands in for tagfixer.musicbrainz.MusicBrainz."""

    def __init__(self, releases):
        self.releases = {r["id"]: r for r in releases}
        self.searches = []

    def search_releases(self, album=None, artist=None, track_count=None, query=None, limit=15):
        self.searches.append((album, artist))
        from tagfixer.matcher import similarity
        out = []
        for r in self.releases.values():
            if album and similarity(album, r["title"]) < 0.6:
                continue
            res = copy.deepcopy(r)
            res["track-count"] = sum(len(m["tracks"]) for m in r["media"])
            for m in res["media"]:
                del m["tracks"]
            out.append(res)
        return out

    def get_release(self, mbid):
        return copy.deepcopy(self.releases.get(mbid))

    def get_cover(self, release_id, size=1200):
        return b"\xff\xd8\xff\xe0fakejpeg"


VA = [_credit("Various Artists", VARIOUS_ARTISTS_ID)]
credit = _credit
