"""Background jobs shared by the web interface: scan, match, apply, undo."""

import json
import os
import threading
import traceback
from collections import Counter

from . import library, matcher, plex, writer
from .musicbrainz import MusicBrainz, MusicBrainzError, parse_mbid


class App:
    def __init__(self, mb=None, data_dir=None):
        self.mb = mb or MusicBrainz()
        self.data_dir = data_dir or writer.default_data_dir()
        self.settings = dict(matcher.DEFAULT_SETTINGS)
        self.settings.update(self._load_settings())
        self.lock = threading.RLock()
        self.thread = None
        self.cancel = threading.Event()
        self.version = 0
        self._reset()

    def _reset(self):
        self.root = None
        self.groups = {}       # id -> AlbumGroup
        self.results = {}      # id -> match result dict
        self.unreadable = []
        self.phase = "idle"    # idle | scanning | matching | applying | done
        self.progress = {"done": 0, "total": 0, "current": ""}
        self.messages = []

    # ---- settings ------------------------------------------------------------
    def _settings_path(self):
        return os.path.join(self.data_dir, "settings.json")

    def _load_settings(self):
        try:
            with open(self._settings_path(), encoding="utf-8") as f:
                data = json.load(f)
            return {k: v for k, v in data.items() if k in matcher.DEFAULT_SETTINGS}
        except (OSError, ValueError):
            return {}

    def update_settings(self, new):
        with self.lock:
            for k, v in new.items():
                if k in matcher.DEFAULT_SETTINGS:
                    self.settings[k] = v
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=1)
            return dict(self.settings)

    # ---- helpers ---------------------------------------------------------------
    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def _bump(self, result=None):
        self.version += 1
        if result is not None:
            result["version"] = self.version

    def _log(self, text):
        with self.lock:
            self.messages.append(text)
            self.messages = self.messages[-200:]
            self._bump()

    def _start(self, target, *args):
        if self.busy():
            raise RuntimeError("Something is already running - wait for it or press Stop.")
        self.cancel.clear()
        self.thread = threading.Thread(target=self._guard, args=(target,) + args, daemon=True)
        self.thread.start()

    def _guard(self, target, *args):
        try:
            target(*args)
        except Exception as e:
            traceback.print_exc()
            self._log(f"Error: {e}")
        finally:
            with self.lock:
                if self.phase != "idle":
                    self.phase = "done"
                self.progress["current"] = ""
                self._bump()

    def stop(self):
        self.cancel.set()

    # ---- scan + match ----------------------------------------------------------
    def start_scan(self, root):
        root = os.path.abspath(os.path.expanduser(root or ""))
        if not os.path.isdir(root):
            raise ValueError(f"Folder not found: {root}")
        with self.lock:
            if self.busy():
                raise RuntimeError("Something is already running.")
            self._reset()
            self.root = root
            self.phase = "scanning"
            self._bump()
        self._start(self._scan_and_match, root)

    def _scan_and_match(self, root):
        def progress(done, total, path):
            with self.lock:
                self.progress = {"done": done, "total": total, "current": os.path.relpath(path, root)}
                if done % 25 == 0 or done == total:
                    self._bump()
            if self.cancel.is_set():
                raise KeyboardInterrupt

        try:
            groups, bad = library.scan(root, progress)
        except KeyboardInterrupt:
            self._log("Scan stopped.")
            return
        with self.lock:
            self.groups = {g.id: g for g in groups}
            self.unreadable = [{"rel": b.rel, "error": b.error} for b in bad]
            for g in groups:
                r = {"status": "pending", "confidence": None, "release": None,
                     "candidates": [], "files": [], "flags": {}, "message": None,
                     "selected": False, "applied": False}
                self._bump(r)
                self.results[g.id] = r
            self.phase = "matching"
            self.progress = {"done": 0, "total": len(groups), "current": ""}
            self._bump()
        self._log(f"Found {sum(len(g.files) for g in groups)} tracks in {len(groups)} albums."
                  + (f" {len(bad)} files could not be read." if bad else ""))
        self._match_all([g.id for g in groups])

    def _match_all(self, ids):
        failures = 0
        for n, gid in enumerate(ids):
            if failures >= 3:
                self._log("Can't reach MusicBrainz - check your internet connection, then press "
                          "'Look up remaining'.")
                break
            if self.cancel.is_set():
                self._log("Stopped. Albums not yet looked up are marked 'pending' - press Look up again to continue.")
                break
            group = self.groups[gid]
            with self.lock:
                self.progress = {"done": n, "total": len(ids), "current": group.rel}
                self.results[gid]["status"] = "matching"
                self._bump(self.results[gid])
            self._match_one(gid)
            failures = failures + 1 if self.results[gid]["status"] == "error" else 0
            with self.lock:
                self.progress["done"] = n + 1
                self._bump()

    def _match_one(self, gid, release_id=None):
        group = self.groups[gid]
        try:
            res = matcher.match_album(self.mb, group, self.settings, release_id=release_id)
        except MusicBrainzError as e:
            res = {"status": "error", "confidence": None, "release": None, "candidates": [],
                   "files": [], "flags": {}, "message": f"MusicBrainz problem: {e}"}
        with self.lock:
            res["selected"] = res["status"] == matcher.GOOD and _has_changes(res)
            res["applied"] = False
            if release_id:
                res["selected"] = _has_changes(res)
                if res["status"] in (matcher.GOOD, matcher.REVIEW):
                    res["status"] = "chosen"
            if not _has_changes(res) and res["status"] in (matcher.GOOD, matcher.REVIEW, "chosen"):
                res["status"] = "ok"
                res["message"] = "Tags already correct - nothing to change."
            self.results[gid] = res
            self._bump(res)

    def retry_pending(self):
        with self.lock:
            ids = [gid for gid, r in self.results.items() if r["status"] in ("pending", "error")]
            if not ids:
                return 0
            self.phase = "matching"
            self._bump()
        self._start(self._match_all, ids)
        return len(ids)

    def choose_release(self, gid, text):
        mbid = parse_mbid(text)
        if not mbid:
            raise ValueError("That doesn't look like a MusicBrainz release link or ID.")
        if gid not in self.groups:
            raise KeyError(gid)
        if self.busy():
            raise RuntimeError("Wait for the current lookup to finish (or press Stop) first.")
        self._match_one(gid, release_id=mbid)
        return self.results[gid]

    def set_selected(self, ids, value):
        with self.lock:
            for gid in ids:
                r = self.results.get(gid)
                if r and not r["applied"] and _has_changes(r):
                    r["selected"] = bool(value)
                    self._bump(r)

    # ---- apply ---------------------------------------------------------------
    def start_apply(self):
        with self.lock:
            ids = [gid for gid, r in self.results.items() if r["selected"] and not r["applied"]]
            if not ids:
                raise ValueError("Nothing selected.")
            self.phase = "applying"
            self.progress = {"done": 0, "total": len(ids), "current": ""}
            self._bump()
        self._start(self._apply, ids)
        return len(ids)

    def _apply(self, ids):
        undo = writer.UndoLog(self.data_dir)
        undo.start()
        folders = Counter(self.groups[g].folder for g in self.groups)
        total_files, changed_folders, all_errors = 0, [], []
        for n, gid in enumerate(ids):
            if self.cancel.is_set():
                self._log("Stopped part-way. Everything written so far can be undone.")
                break
            group, res = self.groups[gid], self.results[gid]
            with self.lock:
                self.progress = {"done": n, "total": len(ids), "current": group.rel}
                self._bump()
            release_id = (res.get("release") or {}).get("id")
            written, errors = writer.apply_album(
                res, release_id, self.settings, self.mb, undo,
                single_album_folder=folders[group.folder] == 1)
            total_files += written
            all_errors += errors
            if written:
                changed_folders.append(group.folder)
            # Re-read the files so a second look shows the new state.
            for tf in group.files:
                tf.load()
            with self.lock:
                res["applied"] = not errors
                res["selected"] = bool(errors)
                if errors:
                    res["message"] = "Some files failed: " + "; ".join(errors[:3])
                else:
                    for f in res["files"]:
                        f["current"] = matcher._display_tags(
                            next(t.tags for t in group.files if t.path == f["path"]))
                self._bump(res)
        self._log(f"Updated {total_files} files." + (f" {len(all_errors)} errors." if all_errors else ""))
        for e in all_errors[:20]:
            self._log("  " + e)
        if changed_folders and self.settings.get("plex_url") and self.settings.get("plex_token"):
            try:
                msg = plex.refresh_folders(self.settings, changed_folders)
                if msg:
                    self._log(msg)
            except Exception as e:
                self._log(f"Plex refresh failed: {e}")

    def undo(self):
        if self.busy():
            raise RuntimeError("Wait for the current job to finish first.")
        restored, errors, path = writer.undo_last(self.data_dir)
        if path is None:
            self._log("Nothing to undo.")
            return 0
        self._log(f"Undo: restored {restored} files." + (f" {len(errors)} errors." if errors else ""))
        for e in errors[:20]:
            self._log("  " + e)
        with self.lock:
            # The on-screen plan is stale now: re-read the files and look the
            # affected albums up again (fast - lookups are cached).
            ids = [gid for gid, r in self.results.items() if r["applied"]]
            for gid in ids:
                for tf in self.groups[gid].files:
                    tf.load()
                self.results[gid].update(status="pending", applied=False, selected=False)
                self._bump(self.results[gid])
            if ids:
                self.phase = "matching"
        if ids:
            self._start(self._match_all, ids)
        return restored

    # ---- views for the UI ------------------------------------------------------
    def state(self, since=0):
        with self.lock:
            albums = [self._album_row(gid) for gid, r in self.results.items()
                      if r.get("version", 0) > since]
            counts = Counter(r["status"] for r in self.results.values())
            return {
                "version": self.version, "phase": self.phase, "busy": self.busy(),
                "root": self.root, "progress": dict(self.progress),
                "messages": self.messages[-30:], "counts": counts,
                "selected": sum(1 for r in self.results.values() if r["selected"]),
                "applied": sum(1 for r in self.results.values() if r["applied"]),
                "unreadable": self.unreadable[:200], "albums": albums,
                "full": since == 0,
            }

    def _album_row(self, gid):
        g, r = self.groups[gid], self.results[gid]
        return {
            "id": gid, "folder": g.rel, "current": g.summary(), "status": r["status"],
            "confidence": r["confidence"], "release": r["release"], "flags": r.get("flags") or {},
            "selected": r["selected"], "applied": r["applied"], "message": r.get("message"),
            "tracks": len(g.files),
            "changed": sum(1 for f in r.get("files") or [] if f.get("changes")),
            "new": _album_preview(r),
        }

    def album_detail(self, gid):
        with self.lock:
            r = self.results[gid]
            return dict(self._album_row(gid), files=r.get("files") or [],
                        candidates=r.get("candidates") or [])


def _has_changes(res):
    return any(f.get("changes") for f in res.get("files") or [])


def _album_preview(res):
    """Album-level values after the change, for the summary table."""
    for f in res.get("files") or []:
        ch = f.get("changes") or {}
        cur = f.get("current") or {}
        if f.get("matched") or ch:
            pick = lambda k: ch[k] if k in ch else cur.get(k)
            return {"albumartist": pick("albumartist") or cur.get("artist"),
                    "album": pick("album"), "date": (pick("date") or "")[:4],
                    "releasetype": pick("releasetype")}
    return None
