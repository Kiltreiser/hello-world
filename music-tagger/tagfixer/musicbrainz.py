"""Small MusicBrainz + Cover Art Archive client.

MusicBrainz asks clients to send at most one request per second and to
identify themselves, so every request goes through a shared rate limiter and
responses are cached on disk (re-scanning a library is then nearly instant).
"""

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

API = "https://musicbrainz.org/ws/2/"
COVER_API = "https://coverartarchive.org/release/"
USER_AGENT = f"TagFixer/{__version__} ( https://github.com/Kiltreiser/hello-world )"
VARIOUS_ARTISTS_ID = "89ad4ac3-39f7-470e-963a-56509c546377"
MBID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

RELEASE_INCLUDES = "recordings+artist-credits+release-groups+media+labels+isrcs+genres"


def default_cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "tagfixer")


class MusicBrainzError(Exception):
    pass


class MusicBrainz:
    def __init__(self, cache_dir=None, min_interval=1.05, timeout=30):
        self.cache_dir = cache_dir if cache_dir is not None else default_cache_dir()
        self.min_interval = min_interval
        self.timeout = timeout
        self._lock = threading.Lock()
        self._last = 0.0

    # -- low level -----------------------------------------------------------
    def _cache_path(self, url):
        if not self.cache_dir:
            return None
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, "mb", digest[:2], digest + ".json")

    def _fetch(self, url, binary=False):
        """Rate-limited GET with retries. Returns parsed JSON or bytes."""
        delay = 2
        for attempt in range(5):
            with self._lock:
                wait = self._last + self.min_interval - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*" if binary else "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = resp.read()
                return data if binary else json.loads(data.decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise MusicBrainzError(f"HTTP {e.code} for {url}") from e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < 1:  # no connection at all: don't keep hammering
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise MusicBrainzError(f"Network error: {e}") from e
        raise MusicBrainzError(f"Giving up on {url}")

    def get_json(self, path, params):
        url = API + path + "?" + urllib.parse.urlencode(dict(params, fmt="json"))
        cache = self._cache_path(url)
        if cache and os.path.exists(cache):
            try:
                with open(cache, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass
        data = self._fetch(url)
        if cache and data is not None:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            tmp = cache + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, cache)
        return data

    # -- API -----------------------------------------------------------------
    def search_releases(self, album=None, artist=None, track_count=None, query=None, limit=15):
        if query is None:
            parts = []
            if album:
                parts.append(f"release:({lucene_escape(album)})")
            if artist:
                parts.append(f"artist:({lucene_escape(artist)})")
            if not parts:
                return []
            query = " AND ".join(parts)
            if track_count:
                # Not required, but boosts releases with the right track count.
                query += f" tracks:{int(track_count)}^2"
        data = self.get_json("release/", {"query": query, "limit": limit})
        return (data or {}).get("releases", [])

    def get_release(self, mbid):
        return self.get_json(f"release/{mbid}", {"inc": RELEASE_INCLUDES})

    def get_cover(self, release_id, size=1200):
        """Front cover bytes, or None if the release has no artwork."""
        cache = None
        if self.cache_dir:
            cache = os.path.join(self.cache_dir, "covers", f"{release_id}-{size}.jpg")
            if os.path.exists(cache):
                with open(cache, "rb") as f:
                    return f.read() or None
        try:
            data = self._fetch(f"{COVER_API}{release_id}/front-{size}", binary=True)
        except MusicBrainzError:
            return None
        if cache:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "wb") as f:
                f.write(data or b"")
        return data or None


def lucene_escape(text):
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", text)


def parse_mbid(text):
    """Pull a release MBID out of a pasted URL or ID."""
    if not text:
        return None
    m = MBID_RE.search(text)
    return m.group(0).lower() if m else None


def credit_name(artist_credit):
    """Join an artist-credit list into a display string ("A feat. B")."""
    out = ""
    for c in artist_credit or []:
        out += c.get("name") or c.get("artist", {}).get("name", "")
        out += c.get("joinphrase", "")
    return out.strip()


def credit_sort_name(artist_credit):
    out = ""
    for c in artist_credit or []:
        out += c.get("artist", {}).get("sort-name") or c.get("name", "")
        out += c.get("joinphrase", "")
    return out.strip()


def credit_ids(artist_credit):
    return [c["artist"]["id"] for c in artist_credit or [] if c.get("artist", {}).get("id")]
