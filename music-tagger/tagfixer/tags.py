"""Read and write tags in a format-neutral way.

Every supported file type (MP3, FLAC, Ogg Vorbis, Opus, M4A/AAC/ALAC, AIFF, WAV)
is exposed through the same small set of field names. The on-disk tag names
follow MusicBrainz Picard's conventions, which is what Plex and Plexamp read
when "Prefer local metadata" is turned on.

Field values are plain strings, except ``releasetype``, ``genre`` and the
MusicBrainz artist IDs, which are lists of strings. ``None`` means "remove this tag".
"""

import base64
import os

import mutagen
from mutagen.aiff import AIFF
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC, ID3, PictureType, TALB, TCMP, TCON, TDOR, TDRC, TIT2, TMED, TPE1,
    TPE2, TPOS, TPUB, TRCK, TSO2, TSOP, TSRC, TXXX, UFID,
)
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".m4b", ".mp4",
    ".aac", ".alac", ".aif", ".aiff", ".wav",
}

# Every field this app knows how to read and write.
FIELDS = [
    "title", "artist", "artistsort", "album", "albumartist", "albumartistsort",
    "date", "originaldate", "tracknumber", "totaltracks", "discnumber",
    "totaldiscs", "compilation", "releasetype", "genre", "label",
    "catalognumber", "barcode", "isrc", "media", "releasestatus",
    "releasecountry", "mb_recordingid", "mb_releasetrackid", "mb_albumid",
    "mb_releasegroupid", "mb_artistid", "mb_albumartistid",
]
LIST_FIELDS = {"releasetype", "genre", "mb_artistid", "mb_albumartistid"}

# ---------------------------------------------------------------------------
# Vorbis comments (FLAC, Ogg Vorbis, Opus)
# ---------------------------------------------------------------------------
VORBIS_KEYS = {
    "title": "TITLE", "artist": "ARTIST", "artistsort": "ARTISTSORT",
    "album": "ALBUM", "albumartist": "ALBUMARTIST",
    "albumartistsort": "ALBUMARTISTSORT", "date": "DATE",
    "originaldate": "ORIGINALDATE", "tracknumber": "TRACKNUMBER",
    "totaltracks": "TRACKTOTAL", "discnumber": "DISCNUMBER",
    "totaldiscs": "DISCTOTAL", "compilation": "COMPILATION",
    "releasetype": "RELEASETYPE", "genre": "GENRE", "label": "LABEL",
    "catalognumber": "CATALOGNUMBER", "barcode": "BARCODE", "isrc": "ISRC",
    "media": "MEDIA", "releasestatus": "RELEASESTATUS",
    "releasecountry": "RELEASECOUNTRY",
    "mb_recordingid": "MUSICBRAINZ_TRACKID",
    "mb_releasetrackid": "MUSICBRAINZ_RELEASETRACKID",
    "mb_albumid": "MUSICBRAINZ_ALBUMID",
    "mb_releasegroupid": "MUSICBRAINZ_RELEASEGROUPID",
    "mb_artistid": "MUSICBRAINZ_ARTISTID",
    "mb_albumartistid": "MUSICBRAINZ_ALBUMARTISTID",
}
# Older/alternative spellings that should be read, and removed on write so a
# stale value can't contradict the new one.
VORBIS_ALIASES = {
    "totaltracks": ["TOTALTRACKS"],
    "totaldiscs": ["TOTALDISCS"],
    "albumartist": ["ALBUM ARTIST"],
    "releasetype": ["MUSICBRAINZ_ALBUMTYPE"],
}

# ---------------------------------------------------------------------------
# ID3 (MP3, AIFF, WAV)
# ---------------------------------------------------------------------------
ID3_TEXT = {
    "title": TIT2, "artist": TPE1, "album": TALB, "albumartist": TPE2,
    "artistsort": TSOP, "albumartistsort": TSO2, "date": TDRC,
    "originaldate": TDOR, "compilation": TCMP, "genre": TCON, "label": TPUB,
    "isrc": TSRC, "media": TMED,
}
ID3_TXXX = {
    "releasetype": "MusicBrainz Album Type",
    "releasestatus": "MusicBrainz Album Status",
    "releasecountry": "MusicBrainz Album Release Country",
    "catalognumber": "CATALOGNUMBER",
    "barcode": "BARCODE",
    "mb_releasetrackid": "MusicBrainz Release Track Id",
    "mb_albumid": "MusicBrainz Album Id",
    "mb_releasegroupid": "MusicBrainz Release Group Id",
    "mb_artistid": "MusicBrainz Artist Id",
    "mb_albumartistid": "MusicBrainz Album Artist Id",
}
# Extra copies written alongside the Picard names. Some players (and some Plex
# versions) look for a plain RELEASETYPE tag instead.
ID3_TXXX_EXTRA = {"releasetype": "RELEASETYPE"}
UFID_OWNER = "http://musicbrainz.org"

# ---------------------------------------------------------------------------
# MP4 (M4A, ALAC)
# ---------------------------------------------------------------------------
MP4_TEXT = {
    "title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb",
    "albumartist": "aART", "date": "\xa9day", "genre": "\xa9gen",
    "artistsort": "soar", "albumartistsort": "soaa",
}
_FF = "----:com.apple.iTunes:"
MP4_FREEFORM = {
    "originaldate": _FF + "ORIGINALDATE",
    "label": _FF + "LABEL",
    "catalognumber": _FF + "CATALOGNUMBER",
    "barcode": _FF + "BARCODE",
    "isrc": _FF + "ISRC",
    "media": _FF + "MEDIA",
    "releasetype": _FF + "MusicBrainz Album Type",
    "releasestatus": _FF + "MusicBrainz Album Status",
    "releasecountry": _FF + "MusicBrainz Album Release Country",
    "mb_recordingid": _FF + "MusicBrainz Track Id",
    "mb_releasetrackid": _FF + "MusicBrainz Release Track Id",
    "mb_albumid": _FF + "MusicBrainz Album Id",
    "mb_releasegroupid": _FF + "MusicBrainz Release Group Id",
    "mb_artistid": _FF + "MusicBrainz Artist Id",
    "mb_albumartistid": _FF + "MusicBrainz Album Artist Id",
}
MP4_FREEFORM_EXTRA = {"releasetype": _FF + "RELEASETYPE"}


class UnsupportedFile(Exception):
    pass


def is_audio_file(path):
    return os.path.splitext(path)[1].lower() in AUDIO_EXTENSIONS


def _open(path):
    audio = mutagen.File(path)
    if audio is None:
        raise UnsupportedFile(path)
    return audio


def _kind(audio):
    if isinstance(audio, (MP3, AIFF, WAVE)):
        return "id3"
    if isinstance(audio, (FLAC, OggVorbis, OggOpus)):
        return "vorbis"
    if isinstance(audio, MP4):
        return "mp4"
    raise UnsupportedFile(type(audio).__name__)


def _split_pair(value):
    """'3/12' -> ('3', '12'); '3' -> ('3', None)."""
    if value is None:
        return None, None
    value = str(value).strip()
    if "/" in value:
        a, b = value.split("/", 1)
        return (a.strip() or None), (b.strip() or None)
    return (value or None), None


def _clean(values):
    out = [str(v).strip() for v in values if v is not None and str(v).strip()]
    return out


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def read_file(path):
    """Return {'tags': {...}, 'duration': seconds, 'has_cover': bool}."""
    audio = _open(path)
    kind = _kind(audio)
    reader = {"id3": _read_id3, "vorbis": _read_vorbis, "mp4": _read_mp4}[kind]
    tags = reader(audio)
    duration = float(getattr(audio.info, "length", 0) or 0)
    return {"tags": tags, "duration": duration, "has_cover": _has_cover(audio, kind)}


def _store(tags, field, values):
    values = _clean(values)
    if not values:
        return
    tags[field] = values if field in LIST_FIELDS else values[0]


def _read_vorbis(audio):
    tags = {}
    comments = audio.tags or {}
    for field, key in VORBIS_KEYS.items():
        values = comments.get(key) or []
        if not values:
            for alias in VORBIS_ALIASES.get(field, []):
                values = comments.get(alias) or []
                if values:
                    break
        _store(tags, field, values)
    # "3/12" style track numbers
    for num, total in (("tracknumber", "totaltracks"), ("discnumber", "totaldiscs")):
        if num in tags and "/" in tags[num]:
            n, t = _split_pair(tags[num])
            tags[num] = n
            if t and total not in tags:
                tags[total] = t
            if not n:
                del tags[num]
    return tags


def _read_id3(audio):
    tags = {}
    id3 = audio.tags
    if id3 is None:
        return tags
    for field, frame_cls in ID3_TEXT.items():
        frame = id3.get(frame_cls.__name__)
        if frame is not None:
            _store(tags, field, [str(t) for t in frame.text])
    for field, desc in ID3_TXXX.items():
        frame = id3.get("TXXX:" + desc)
        if frame is None and field in ID3_TXXX_EXTRA:
            frame = id3.get("TXXX:" + ID3_TXXX_EXTRA[field])
        if frame is not None:
            _store(tags, field, [str(t) for t in frame.text])
    ufid = id3.get("UFID:" + UFID_OWNER)
    if ufid is not None and ufid.data:
        tags["mb_recordingid"] = ufid.data.decode("ascii", "ignore")
    trck = id3.get("TRCK")
    if trck is not None:
        n, t = _split_pair(trck.text[0] if trck.text else None)
        if n:
            tags["tracknumber"] = n
        if t:
            tags["totaltracks"] = t
    tpos = id3.get("TPOS")
    if tpos is not None:
        n, t = _split_pair(tpos.text[0] if tpos.text else None)
        if n:
            tags["discnumber"] = n
        if t:
            tags["totaldiscs"] = t
    return tags


def _read_mp4(audio):
    tags = {}
    mp4 = audio.tags or {}
    for field, key in MP4_TEXT.items():
        if key in mp4:
            _store(tags, field, mp4[key])
    for field, key in MP4_FREEFORM.items():
        values = mp4.get(key) or mp4.get(MP4_FREEFORM_EXTRA.get(field, ""), [])
        if values:
            _store(tags, field, [bytes(v).decode("utf-8", "ignore") for v in values])
    if "trkn" in mp4 and mp4["trkn"]:
        n, t = mp4["trkn"][0]
        if n:
            tags["tracknumber"] = str(n)
        if t:
            tags["totaltracks"] = str(t)
    if "disk" in mp4 and mp4["disk"]:
        n, t = mp4["disk"][0]
        if n:
            tags["discnumber"] = str(n)
        if t:
            tags["totaldiscs"] = str(t)
    if "cpil" in mp4:
        tags["compilation"] = "1" if mp4["cpil"] else "0"
    return tags


def _has_cover(audio, kind):
    if kind == "vorbis":
        if isinstance(audio, FLAC):
            return bool(audio.pictures)
        return bool((audio.tags or {}).get("METADATA_BLOCK_PICTURE"))
    if kind == "id3":
        return bool(audio.tags and audio.tags.getall("APIC"))
    if kind == "mp4":
        return bool((audio.tags or {}).get("covr"))
    return False


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def write_file(path, changes, cover=None, remove_cover=False):
    """Apply ``changes`` ({field: value-or-None}) to the file at ``path``.

    Only the fields present in ``changes`` are touched; everything else in the
    file (lyrics, ratings, replaygain, ...) is left alone. ``cover`` is JPEG or
    PNG bytes to embed as the front cover.
    """
    audio = _open(path)
    kind = _kind(audio)
    if audio.tags is None:
        audio.add_tags()
    writer = {"id3": _write_id3, "vorbis": _write_vorbis, "mp4": _write_mp4}[kind]
    writer(audio, changes)
    if remove_cover:
        _remove_cover(audio, kind)
    if cover:
        _remove_cover(audio, kind)
        _add_cover(audio, kind, cover)
    if kind == "id3":
        audio.save(v2_version=4) if isinstance(audio, MP3) else audio.save()
    else:
        audio.save()


def _as_list(field, value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return _clean(value)
    return _clean([value])


def _write_vorbis(audio, changes):
    comments = audio.tags
    for field, value in changes.items():
        key = VORBIS_KEYS[field]
        for old in [key] + VORBIS_ALIASES.get(field, []):
            if old in comments:
                del comments[old]
        values = _as_list(field, value)
        if values:
            comments[key] = values


def _write_id3(audio, changes):
    id3 = audio.tags
    changes = dict(changes)

    def merged(num_field, total_field, frame_name):
        if num_field not in changes and total_field not in changes:
            return
        old = id3.get(frame_name)
        old_n, old_t = _split_pair(old.text[0] if old is not None and old.text else None)
        n = changes.pop(num_field, old_n) if num_field in changes else old_n
        t = changes.pop(total_field, old_t) if total_field in changes else old_t
        id3.delall(frame_name)
        if n:
            text = f"{n}/{t}" if t else str(n)
            frame_cls = TRCK if frame_name == "TRCK" else TPOS
            id3.add(frame_cls(encoding=3, text=[text]))

    merged("tracknumber", "totaltracks", "TRCK")
    merged("discnumber", "totaldiscs", "TPOS")

    for field, value in changes.items():
        values = _as_list(field, value)
        if field in ID3_TEXT:
            frame_cls = ID3_TEXT[field]
            id3.delall(frame_cls.__name__)
            if values:
                id3.add(frame_cls(encoding=3, text=values))
        elif field in ID3_TXXX:
            descs = [ID3_TXXX[field]]
            if field in ID3_TXXX_EXTRA:
                descs.append(ID3_TXXX_EXTRA[field])
            for desc in descs:
                id3.delall("TXXX:" + desc)
                if values:
                    id3.add(TXXX(encoding=3, desc=desc, text=values))
        elif field == "mb_recordingid":
            id3.delall("UFID:" + UFID_OWNER)
            if values:
                id3.add(UFID(owner=UFID_OWNER, data=values[0].encode("ascii")))


def _write_mp4(audio, changes):
    mp4 = audio.tags
    changes = dict(changes)

    def merged(num_field, total_field, key):
        if num_field not in changes and total_field not in changes:
            return
        old_n, old_t = (mp4[key][0] if key in mp4 and mp4[key] else (0, 0))
        n = changes.pop(num_field) if num_field in changes else old_n
        t = changes.pop(total_field) if total_field in changes else old_t
        n, t = _to_int(n), _to_int(t)
        if key in mp4:
            del mp4[key]
        if n:
            mp4[key] = [(n, t)]

    merged("tracknumber", "totaltracks", "trkn")
    merged("discnumber", "totaldiscs", "disk")

    for field, value in changes.items():
        values = _as_list(field, value)
        if field == "compilation":
            if "cpil" in mp4:
                del mp4["cpil"]
            if values:
                mp4["cpil"] = values[0] == "1"
        elif field in MP4_TEXT:
            key = MP4_TEXT[field]
            if key in mp4:
                del mp4[key]
            if values:
                mp4[key] = values
        elif field in MP4_FREEFORM:
            keys = [MP4_FREEFORM[field]]
            if field in MP4_FREEFORM_EXTRA:
                keys.append(MP4_FREEFORM_EXTRA[field])
            for key in keys:
                if key in mp4:
                    del mp4[key]
                if values:
                    mp4[key] = [MP4FreeForm(v.encode("utf-8")) for v in values]


def _to_int(value):
    try:
        return int(str(value).split("/")[0])
    except (TypeError, ValueError):
        return 0


def _image_mime(data):
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def _remove_cover(audio, kind):
    if kind == "vorbis":
        if isinstance(audio, FLAC):
            audio.clear_pictures()
        elif "METADATA_BLOCK_PICTURE" in audio.tags:
            del audio.tags["METADATA_BLOCK_PICTURE"]
    elif kind == "id3":
        audio.tags.delall("APIC")
    elif kind == "mp4":
        if "covr" in audio.tags:
            del audio.tags["covr"]


def _add_cover(audio, kind, data):
    mime = _image_mime(data)
    if kind == "vorbis":
        pic = Picture()
        pic.type = PictureType.COVER_FRONT
        pic.mime = mime
        pic.desc = "Cover"
        pic.data = data
        if isinstance(audio, FLAC):
            audio.add_picture(pic)
        else:
            audio.tags["METADATA_BLOCK_PICTURE"] = [
                base64.b64encode(pic.write()).decode("ascii")
            ]
    elif kind == "id3":
        audio.tags.add(APIC(encoding=3, mime=mime, type=PictureType.COVER_FRONT,
                            desc="Cover", data=data))
    elif kind == "mp4":
        fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
        audio.tags["covr"] = [MP4Cover(data, imageformat=fmt)]
