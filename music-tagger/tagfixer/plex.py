"""Ask a Plex Media Server to rescan folders after their tags have changed.

Needs the server address (e.g. http://192.168.1.10:32400) and a Plex token
(see https://support.plex.tv/articles/204059436). If TagFixer runs on a
different machine than Plex, the music folder paths will differ; set
``plex_path_from`` / ``plex_path_to`` to translate them (for example
``/Volumes/Music`` -> ``/data/music``).
"""

import json
import urllib.parse
import urllib.request


def _get(base, path, token, params=None):
    query = dict(params or {}, **{"X-Plex-Token": token})
    url = base.rstrip("/") + path + "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read()
    return json.loads(body) if body.strip() else {}


def map_path(path, settings):
    src, dst = settings.get("plex_path_from"), settings.get("plex_path_to")
    if src and dst and path.startswith(src):
        path = dst + path[len(src):]
        if "\\" not in dst:
            path = path.replace("\\", "/")
    return path


def music_sections(base, token):
    data = _get(base, "/library/sections", token)
    out = []
    for d in data.get("MediaContainer", {}).get("Directory", []):
        if d.get("type") == "artist":
            out.append({"key": d["key"], "title": d.get("title"),
                        "paths": [loc["path"] for loc in d.get("Location", [])]})
    return out


def refresh_folders(settings, folders):
    """Trigger a scan of each changed folder. Returns a short status message."""
    base, token = settings.get("plex_url"), settings.get("plex_token")
    if not base or not token:
        return None
    sections = music_sections(base, token)
    if not sections:
        return "Plex: no music libraries found"
    unmatched = False
    scanned = 0
    for folder in sorted(set(folders)):
        plex_path = map_path(folder, settings)
        section = next((s for s in sections for p in s["paths"]
                        if plex_path == p or plex_path.startswith(p.rstrip("/\\") + "/")
                        or plex_path.startswith(p.rstrip("/\\") + "\\")), None)
        if section is None:
            unmatched = True
            continue
        _get(base, f"/library/sections/{section['key']}/refresh", token, {"path": plex_path})
        scanned += 1
    if unmatched:
        # Paths didn't line up; fall back to scanning every music library.
        for s in sections:
            _get(base, f"/library/sections/{s['key']}/refresh", token)
        return f"Plex: scanned {scanned} folder(s) and refreshed all music libraries"
    return f"Plex: asked to rescan {scanned} folder(s)"
