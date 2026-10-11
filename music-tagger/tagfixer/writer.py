"""Write planned changes to disk, keeping an undo log."""

import glob
import json
import os
import time

from . import tags as tagio

COVER_FILES = ("cover", "folder", "front", "album", "albumart")


def default_data_dir():
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "tagfixer")


class UndoLog:
    """One file per batch, one JSON line per change, holding the old value of
    every field changed. Lines are appended, so big batches stay fast and a
    crash mid-batch is still undoable."""

    def __init__(self, data_dir=None):
        self.dir = os.path.join(data_dir or default_data_dir(), "undo")
        self.path = None

    def start(self):
        os.makedirs(self.dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(self.dir, f"{stamp}.jsonl")
        n = 1
        while os.path.exists(self.path):
            n += 1
            self.path = os.path.join(self.dir, f"{stamp}-{n}.jsonl")
        open(self.path, "w").close()

    def record(self, entry):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()

    def batches(self):
        # Empty batches (nothing was written) are skipped.
        return sorted(p for p in glob.glob(os.path.join(self.dir, "*.jsonl"))
                      if os.path.getsize(p) > 0)


def apply_album(album, release_id, settings, mb=None, undo=None, single_album_folder=True):
    """Write the planned changes for one album. Returns (files_written, errors)."""
    files = [f for f in album["files"] if f.get("changes")]
    cover = None
    want_cover = release_id and mb is not None and (
        settings.get("embed_cover") and any(not f.get("has_cover") for f in files)
        or settings.get("save_cover_file") and single_album_folder
    )
    if want_cover:
        cover = mb.get_cover(release_id)

    written, errors = 0, []
    for f in files:
        try:
            before_tags = tagio.read_file(f["path"])
            before = {k: before_tags["tags"].get(k) for k in f["changes"]}
            add_cover = bool(cover and settings.get("embed_cover") and not before_tags["has_cover"])
            tagio.write_file(f["path"], f["changes"], cover=cover if add_cover else None)
            if undo:
                undo.record({"path": f["path"], "before": before, "cover_added": add_cover})
            f["has_cover"] = f.get("has_cover") or add_cover
            written += 1
        except Exception as e:
            errors.append(f"{f['rel']}: {type(e).__name__}: {e}")

    if cover and settings.get("save_cover_file") and single_album_folder and album["files"]:
        folder = os.path.dirname(album["files"][0]["path"])
        if not _folder_has_cover(folder):
            target = os.path.join(folder, "cover.png" if cover[:4] == b"\x89PNG" else "cover.jpg")
            try:
                with open(target, "wb") as fh:
                    fh.write(cover)
                if undo:
                    undo.record({"created_file": target})
            except OSError as e:
                errors.append(f"cover image: {e}")
    return written, errors


def _folder_has_cover(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return True
    for name in names:
        stem, ext = os.path.splitext(name.lower())
        if ext in (".jpg", ".jpeg", ".png") and stem in COVER_FILES:
            return True
    return False


def undo_last(data_dir=None):
    """Restore the most recent batch. Returns (files_restored, errors, batch_path)."""
    log = UndoLog(data_dir)
    batches = log.batches()
    if not batches:
        return 0, [], None
    path = batches[-1]
    entries = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                entries.append(json.loads(line))
            except ValueError:
                pass  # half-written last line after a crash
    restored, errors = 0, []
    for e in reversed(entries):
        try:
            if "created_file" in e:
                if os.path.exists(e["created_file"]):
                    os.remove(e["created_file"])
                continue
            tagio.write_file(e["path"], e["before"], remove_cover=e.get("cover_added", False))
            restored += 1
        except Exception as ex:
            errors.append(f"{e.get('path') or e.get('created_file')}: {ex}")
    os.replace(path, path[:-6] + ".undone")
    return restored, errors, path
