"""Match album groups to MusicBrainz releases and work out the new tags."""

import difflib
import re
import unicodedata

from .musicbrainz import (
    VARIOUS_ARTISTS_ID, credit_ids, credit_name, credit_sort_name,
)

DEFAULT_SETTINGS = {
    # How soundtracks should be grouped in Plex:
    #   "auto"       - follow MusicBrainz: multi-artist soundtracks become
    #                  "Various Artists", a film score keeps its composer
    #   "various"    - every soundtrack goes under "Various Artists"
    #   "soundtrack" - every soundtrack goes under an artist named "Soundtrack"
    "soundtrack_artist": "auto",
    "soundtrack_genre": True,        # set genre to "Soundtrack" on soundtracks
    "use_original_date": True,       # year of first release, not of the reissue
    "write_genres": False,           # replace genres with MusicBrainz genres
    "embed_cover": True,             # embed front cover in files that have none
    "save_cover_file": True,         # write cover.jpg into the album folder if missing
    "auto_select": 0.85,             # confidence needed to be ticked automatically
    # Optional: ask Plex to rescan changed folders after applying
    "plex_url": "",
    "plex_token": "",
    "plex_path_from": "",
    "plex_path_to": "",
}

GOOD, REVIEW = "good", "review"

# Fields that describe a specific release. When we switch a file to a new
# release, old values of these are removed if the new release has none, so a
# stale catalog number from a different pressing can't linger.
RELEASE_SPECIFIC = [
    "label", "catalognumber", "barcode", "media", "releasestatus",
    "releasecountry", "isrc", "mb_recordingid", "mb_releasetrackid",
    "mb_albumid", "mb_releasegroupid", "mb_artistid", "mb_albumartistid",
    "artistsort", "albumartistsort", "originaldate", "totaldiscs", "totaltracks",
]

SOUNDTRACK_WORDS = re.compile(
    r"\b(soundtrack|o\.?s\.?t\.?|original (motion picture|score|cast)|music from (the )?(motion picture|film|series)|film score)\b",
    re.I,
)

# ---------------------------------------------------------------------------
# String comparison
# ---------------------------------------------------------------------------
_BRACKETS = re.compile(r"[\(\[][^\)\]]*[\)\]]")


def normalize(text, strip_brackets=True):
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("&", " and ")
    if strip_brackets:
        stripped = _BRACKETS.sub(" ", text)
        if stripped.strip():
            text = stripped
    text = re.sub(r"\b(feat|ft|featuring)\b.*$", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"^the ", "", text.strip())
    return re.sub(r"\s+", " ", text).strip()


def similarity(a, b):
    """0..1 fuzzy similarity of two titles/names."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    overlap = len(ta & tb) / max(len(ta), len(tb))
    # One title fully containing the other ("Album" vs "Album Deluxe Edition")
    contained = 0.9 if (na in nb or nb in na) and min(len(na), len(nb)) >= 4 else 0
    return max(ratio, overlap, contained)


# ---------------------------------------------------------------------------
# Candidate scoring
# ---------------------------------------------------------------------------
def score_search_result(rel, hints):
    """Quick score from a search result, before fetching full track lists."""
    album_s = similarity(hints["album"], rel.get("title")) if hints["album"] else 0.5
    rel_artist = credit_name(rel.get("artist-credit"))
    is_va = VARIOUS_ARTISTS_ID in credit_ids(rel.get("artist-credit"))
    if hints["various"]:
        artist_s = 1.0 if is_va else 0.4
    elif hints["artist"]:
        artist_s = similarity(hints["artist"], rel_artist)
    else:
        artist_s = 0.5
    n, count = hints["track_count"], rel.get("track-count") or 0
    if count == n:
        tracks_s = 1.0
    elif count > n:  # some tracks missing from the folder
        tracks_s = max(0.0, 1 - (count - n) / max(count, 1) * 1.5)
    else:
        tracks_s = max(0.0, 1 - (n - count) / max(n, 1) * 3)
    year_s = 0.5
    date = rel.get("date") or (rel.get("release-group") or {}).get("first-release-date") or ""
    if hints["year"] and date:
        diff = abs(int(hints["year"]) - int(date[:4])) if date[:4].isdigit() else 99
        year_s = 1.0 if diff == 0 else 0.6 if diff <= 1 else 0.3
    official = 1.0 if rel.get("status") in (None, "Official") else 0.6
    return (0.40 * album_s + 0.25 * artist_s + 0.25 * tracks_s + 0.10 * year_s) * (0.9 + 0.1 * official)


def release_tracks(release):
    out = []
    for medium in release.get("media") or []:
        for t in medium.get("tracks") or []:
            out.append({
                "disc": medium.get("position") or 1,
                "disc_total": medium.get("track-count") or len(medium.get("tracks") or []),
                "format": medium.get("format"),
                "position": t.get("position"),
                "title": t.get("title") or (t.get("recording") or {}).get("title"),
                "length": (t.get("length") or (t.get("recording") or {}).get("length") or 0) / 1000.0,
                "track": t,
            })
    return out


def _duration_score(file_len, track_len):
    if not file_len or not track_len:
        return None
    diff = abs(file_len - track_len)
    if diff <= 3:
        return 1.0
    return max(0.0, 1 - (diff - 3) / 15)


def pair_score(tf, mt, disc_count):
    title = similarity(tf.title_hint, mt["title"])
    dur = _duration_score(tf.duration, mt["length"])
    score = title if dur is None else 0.55 * title + 0.45 * dur
    if tf.track_hint and tf.track_hint == mt["position"] and (disc_count == 1 or tf.disc_hint == mt["disc"]):
        score += 0.15
    return min(score, 1.0)


def assign_tracks(files, release):
    """Pair each file with a track on the release.

    Returns (mapping {file index: track}, mean pair quality).
    """
    tracks = release_tracks(release)
    disc_count = len(release.get("media") or []) or 1
    pairs = []
    for i, tf in enumerate(files):
        for j, mt in enumerate(tracks):
            pairs.append((pair_score(tf, mt, disc_count), i, j))
    pairs.sort(key=lambda p: -p[0])
    used_f, used_t, mapping, scores = set(), set(), {}, {}
    for s, i, j in pairs:
        if s < 0.45:
            break
        if i in used_f or j in used_t:
            continue
        used_f.add(i)
        used_t.add(j)
        mapping[i] = tracks[j]
        scores[i] = s
    quality = sum(scores.values()) / len(files) if files else 0
    return mapping, scores, quality


def evaluate(release, group, hints):
    """Full score (0..1) for a fetched release, plus the track mapping."""
    # Full releases don't carry "track-count" at the top level.
    count = sum(len(m.get("tracks") or []) for m in release.get("media") or [])
    pre = score_search_result(dict(release, **{"track-count": count}), hints)
    mapping, scores, quality = assign_tracks(group.files, release)
    total = 0.4 * pre + 0.6 * quality
    if len(mapping) < len(group.files):
        total *= 0.5 + 0.5 * len(mapping) / len(group.files)
    return total, mapping, scores


# ---------------------------------------------------------------------------
# Building new tag values
# ---------------------------------------------------------------------------
def release_types(release):
    rg = release.get("release-group") or {}
    types = []
    if rg.get("primary-type"):
        types.append(rg["primary-type"].lower())
    types += [s.lower() for s in rg.get("secondary-types") or []]
    return types


def describe_release(release, track_count=None):
    rg = release.get("release-group") or {}
    media = release.get("media") or []
    formats = sorted({m.get("format") or "?" for m in media})
    count = track_count or release.get("track-count") or sum(
        len(m.get("tracks") or []) for m in media)
    labels = release.get("label-info") or []
    return {
        "id": release["id"],
        "title": release.get("title"),
        "artist": credit_name(release.get("artist-credit")),
        "date": release.get("date") or "",
        "original_date": rg.get("first-release-date") or "",
        "country": release.get("country") or "",
        "format": (f"{len(media)}×{formats[0]}" if len(media) > 1 and len(formats) == 1
                   else ", ".join(formats)) if media else "",
        "tracks": count,
        "label": ((labels[0].get("label") or {}).get("name") if labels else "") or "",
        "types": release_types(release),
        "url": f"https://musicbrainz.org/release/{release['id']}",
    }


def album_level_tags(release, settings):
    """Tags shared by every track on the release."""
    rg = release.get("release-group") or {}
    secondary = [s.lower() for s in rg.get("secondary-types") or []]
    credit = release.get("artist-credit")
    album_artist = credit_name(credit)
    album_artist_sort = credit_sort_name(credit)
    album_artist_ids = credit_ids(credit)
    is_va = VARIOUS_ARTISTS_ID in album_artist_ids or album_artist.lower() == "various artists"
    is_soundtrack = "soundtrack" in secondary

    if is_soundtrack:
        mode = settings.get("soundtrack_artist", "auto")
        if mode == "various" and not is_va:
            album_artist = album_artist_sort = "Various Artists"
            album_artist_ids = [VARIOUS_ARTISTS_ID]
            is_va = True
        elif mode == "soundtrack":
            album_artist = album_artist_sort = "Soundtrack"
            album_artist_ids = []

    original = rg.get("first-release-date") or ""
    date = release.get("date") or ""
    if settings.get("use_original_date") and original:
        date = original
    labels = release.get("label-info") or []
    label = next(((li.get("label") or {}).get("name") for li in labels if li.get("label")), None)
    catno = next((li.get("catalog-number") for li in labels if li.get("catalog-number")), None)

    tags = {
        "album": release.get("title"),
        "albumartist": album_artist,
        "albumartistsort": album_artist_sort,
        "mb_albumartistid": album_artist_ids or None,
        "date": date or None,
        "originaldate": original or None,
        "releasetype": release_types(release) or None,
        "compilation": "1" if (is_va or (is_soundtrack and settings.get("soundtrack_artist") == "soundtrack")) else None,
        "label": label,
        "catalognumber": catno,
        "barcode": release.get("barcode") or None,
        "releasestatus": (release.get("status") or "").lower() or None,
        "releasecountry": release.get("country") or None,
        "mb_albumid": release["id"],
        "mb_releasegroupid": rg.get("id"),
        "totaldiscs": str(len(release.get("media") or [])) if release.get("media") else None,
    }
    if is_soundtrack and settings.get("soundtrack_genre"):
        tags["genre"] = ["Soundtrack"]
    elif settings.get("write_genres"):
        genres = sorted(release.get("genres") or rg.get("genres") or [],
                        key=lambda g: -(g.get("count") or 0))
        if genres:
            tags["genre"] = [genres[0]["name"].title()]
    return tags, {"various": is_va, "soundtrack": is_soundtrack,
                  "compilation": "compilation" in secondary}


def track_level_tags(mt):
    t = mt["track"]
    rec = t.get("recording") or {}
    credit = t.get("artist-credit") or rec.get("artist-credit")
    isrcs = rec.get("isrcs") or []
    return {
        "title": mt["title"],
        "artist": credit_name(credit),
        "artistsort": credit_sort_name(credit),
        "mb_artistid": credit_ids(credit) or None,
        "tracknumber": str(mt["position"]),
        "totaltracks": str(mt["disc_total"]),
        "discnumber": str(mt["disc"]),
        "media": mt["format"],
        "isrc": isrcs[0] if isrcs else None,
        "mb_recordingid": rec.get("id"),
        "mb_releasetrackid": t.get("id"),
    }


def diff_tags(current, proposed):
    """Only the fields that actually change."""
    changes = {}
    for field, new in proposed.items():
        old = current.get(field)
        if _same(old, new):
            continue
        if field == "compilation" and new is None and old in (None, "0"):
            continue
        if new is None and field not in RELEASE_SPECIFIC and field != "compilation":
            continue  # don't blank a field just because MusicBrainz lacks it
        changes[field] = new
    return changes


def _same(old, new):
    if isinstance(old, list) or isinstance(new, list):
        return [str(x) for x in (old or [])] == [str(x) for x in (new or [])]
    if field_empty(old) and field_empty(new):
        return True
    if field_empty(old) or field_empty(new):
        return False
    return str(old).strip() == str(new).strip() or (
        str(old).isdigit() and str(new).isdigit() and int(old) == int(new))


def field_empty(v):
    return v is None or (isinstance(v, str) and not v.strip())


# ---------------------------------------------------------------------------
# The main entry points
# ---------------------------------------------------------------------------
def plan_from_release(group, release, settings, score=None, mapping=None, scores=None):
    """Turn a chosen release into per-file changes."""
    if mapping is None:
        mapping, scores, _ = assign_tracks(group.files, release)
    album_tags, flags = album_level_tags(release, settings)
    files = []
    for i, tf in enumerate(group.files):
        entry = {"path": tf.path, "rel": tf.rel, "current": _display_tags(tf.tags),
                 "duration": round(tf.duration), "has_cover": tf.has_cover}
        mt = mapping.get(i)
        if mt is None:
            entry.update(changes={}, matched=None,
                         warning="No matching track on this release - file will be left alone")
        else:
            proposed = dict(album_tags)
            proposed.update(track_level_tags(mt))
            entry["changes"] = diff_tags(tf.tags, proposed)
            entry["matched"] = {"disc": mt["disc"], "position": mt["position"],
                                "title": mt["title"], "length": round(mt["length"]),
                                "quality": round((scores or {}).get(i, 0), 2)}
        files.append(entry)
    return {"files": files, "flags": flags}


def _display_tags(tags):
    keys = ("title", "artist", "album", "albumartist", "date", "tracknumber",
            "discnumber", "genre", "compilation", "releasetype")
    return {k: tags[k] for k in keys if k in tags}


def match_album(mb, group, settings, max_fetch=3, release_id=None):
    """Find the best MusicBrainz release for an album group.

    Returns a dict with status, confidence, the chosen release, alternative
    candidates and the per-file plan.
    """
    hints = group.hints()
    candidates = []
    best = None  # (score, release, mapping, scores)

    def consider(release):
        nonlocal best
        score, mapping, scores = evaluate(release, group, hints)
        if best is None or score > best[0]:
            best = (score, release, mapping, scores)
        return score

    forced = release_id or hints.get("mb_albumid")
    if forced:
        release = mb.get_release(forced)
        if release:
            consider(release)
            candidates.append(dict(describe_release(release), score=round(best[0], 2)))

    if not release_id and (best is None or best[0] < 0.9):
        results = _search(mb, hints)
        ranked = sorted(results, key=lambda r: -score_search_result(r, hints))
        seen = {c["id"] for c in candidates}
        fetched = 0
        for r in ranked:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            desc = describe_release(r)
            desc["score"] = round(score_search_result(r, hints), 2)
            if fetched < max_fetch and desc["score"] >= 0.45:
                release = mb.get_release(r["id"])
                fetched += 1
                if release:
                    desc["score"] = round(consider(release), 2)
                    if best[0] >= 0.95:
                        candidates.append(desc)
                        break
            candidates.append(desc)

    candidates.sort(key=lambda c: -c["score"])
    candidates = candidates[:12]

    if best is None or best[0] < 0.5:
        local = local_fix(group, settings)
        if local:
            return dict(local, candidates=candidates)
        return {"status": "nomatch", "confidence": round(best[0], 2) if best else 0,
                "release": None, "candidates": candidates, "files": _untouched(group),
                "flags": {}, "message": "No convincing match found online. Pick a candidate or paste a MusicBrainz link."}

    score, release, mapping, scores = best
    plan = plan_from_release(group, release, settings, score, mapping, scores)
    status = GOOD if score >= settings.get("auto_select", 0.85) else REVIEW
    return {"status": status, "confidence": round(score, 2),
            "release": describe_release(release), "candidates": candidates,
            "files": plan["files"], "flags": plan["flags"], "message": None}


def _search(mb, hints):
    results = []
    if hints["album"]:
        artist = None if hints["various"] else hints["artist"]
        results = mb.search_releases(hints["album"], artist, hints["track_count"])
        if hints["various"]:
            results += mb.search_releases(hints["album"], "Various Artists", hints["track_count"])
        if not results and artist:
            results = mb.search_releases(hints["album"], None, hints["track_count"])
    return results


def _untouched(group):
    return [{"path": tf.path, "rel": tf.rel, "current": _display_tags(tf.tags),
             "duration": round(tf.duration), "has_cover": tf.has_cover,
             "changes": {}, "matched": None} for tf in group.files]


def local_fix(group, settings):
    """No online match: still fix compilation/soundtrack grouping using what
    is already in the files."""
    hints = group.hints()
    album = hints["album"] or ""
    is_soundtrack = bool(SOUNDTRACK_WORDS.search(album) or SOUNDTRACK_WORDS.search(group.folder))
    various = group.looks_various
    if not (various or is_soundtrack):
        return None

    mode = settings.get("soundtrack_artist", "auto")
    proposed = {}
    if is_soundtrack and mode == "soundtrack":
        proposed.update(albumartist="Soundtrack", albumartistsort="Soundtrack", compilation="1")
    elif various or (is_soundtrack and mode == "various"):
        proposed.update(albumartist="Various Artists", albumartistsort="Various Artists",
                        compilation="1", mb_albumartistid=[VARIOUS_ARTISTS_ID])
    types = ["album"] + (["soundtrack"] if is_soundtrack else []) + (["compilation"] if various and not is_soundtrack else [])
    proposed["releasetype"] = types
    if is_soundtrack and settings.get("soundtrack_genre"):
        proposed["genre"] = ["Soundtrack"]
    if hints["album"]:
        proposed["album"] = hints["album"]  # makes every track agree on the album name

    files = []
    for tf in group.files:
        files.append({"path": tf.path, "rel": tf.rel, "current": _display_tags(tf.tags),
                      "duration": round(tf.duration), "has_cover": tf.has_cover,
                      "changes": diff_tags(tf.tags, proposed), "matched": None})
    if not any(f["changes"] for f in files):
        return None
    what = "soundtrack" if is_soundtrack else "various-artists compilation"
    return {"status": "local", "confidence": None, "release": None, "files": files,
            "flags": {"various": "albumartist" in proposed and proposed["albumartist"] == "Various Artists",
                      "soundtrack": is_soundtrack, "compilation": various},
            "message": f"Not found online, but this looks like a {what}. "
                       "Only the album artist / compilation / type tags will be fixed."}
