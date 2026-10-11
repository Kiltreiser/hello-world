import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import HAVE_FFMPEG, VA, FakeMB, credit, make_audio, release  # noqa: E402

from tagfixer import library, matcher, writer  # noqa: E402
from tagfixer import tags as tagio  # noqa: E402
from tagfixer.app import App  # noqa: E402
from tagfixer.musicbrainz import VARIOUS_ARTISTS_ID, parse_mbid  # noqa: E402

FORMATS = [".mp3", ".flac", ".m4a", ".ogg", ".opus"]
RID_OST = "11111111-1111-1111-1111-111111111111"
RID_OST_ALT = "22222222-2222-2222-2222-222222222222"
RID_BAND = "33333333-3333-3333-3333-333333333333"
RID_SCORE = "44444444-4444-4444-4444-444444444444"

PULP = [("Misirlou", 5, [credit("Dick Dale", "a1")]),
        ("Jungle Boogie", 7, [credit("Kool & The Gang", "a2")]),
        ("Son of a Preacher Man", 9, [credit("Dusty Springfield", "a3")])]
BAND = [("Opening", 4, None), ("Middle", 6, None), ("Closing", 8, None)]
BAND_CREDIT = [credit("The Band", "b1", "Band, The")]
SCORE = [("Main Theme", 5, None), ("Chase", 6, None)]
SCORE_CREDIT = [credit("Hans Zimmer", "z1", "Zimmer, Hans")]


def fake_mb():
    band = [(t, s, BAND_CREDIT) for t, s, _ in BAND]
    score = [(t, s, SCORE_CREDIT) for t, s, _ in SCORE]
    return FakeMB([
        release(RID_OST, "Pulp Fiction", VA, PULP, secondary=["Soundtrack"],
                date="1994-09-27"),
        # Same album, wrong track count (bonus track edition)
        release(RID_OST_ALT, "Pulp Fiction", VA,
                PULP + [("Bonus", 30, [credit("X", "x")])], secondary=["Soundtrack"],
                date="2002-01-01", first_date="1994-09-27"),
        release(RID_BAND, "Great Album", BAND_CREDIT, band, date="2011-05-01",
                first_date="1975-03-01"),
        release(RID_SCORE, "Big Movie", SCORE_CREDIT, score, secondary=["Soundtrack"]),
    ])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is needed to create test audio files")
class TagRoundTrip(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_all_formats(self):
        values = {
            "title": "Song", "artist": "Artist", "album": "Album", "albumartist": "Various Artists",
            "date": "1994", "tracknumber": "3", "totaltracks": "12", "discnumber": "1",
            "totaldiscs": "2", "compilation": "1", "releasetype": ["album", "soundtrack"],
            "genre": ["Soundtrack"], "mb_albumid": RID_OST, "mb_recordingid": "rec-1",
            "mb_albumartistid": [VARIOUS_ARTISTS_ID], "label": "Label", "catalognumber": "C1",
        }
        for ext in FORMATS:
            with self.subTest(ext=ext):
                path = make_audio(os.path.join(self.dir, "a" + ext), 2, values)
                info = tagio.read_file(path)
                for k, v in values.items():
                    self.assertEqual(info["tags"].get(k), v, f"{ext} {k}")
                self.assertAlmostEqual(info["duration"], 2, delta=0.3)
                # removing fields and adding a cover
                tagio.write_file(path, {"compilation": None, "genre": None, "totaltracks": None},
                                 cover=b"\xff\xd8\xff\xe0jpeg")
                info = tagio.read_file(path)
                self.assertNotIn("compilation", info["tags"])
                self.assertNotIn("genre", info["tags"])
                self.assertNotIn("totaltracks", info["tags"])
                self.assertEqual(info["tags"]["tracknumber"], "3")
                self.assertTrue(info["has_cover"])
                tagio.write_file(path, {}, remove_cover=True)
                self.assertFalse(tagio.read_file(path)["has_cover"])

    def test_untouched_fields_survive(self):
        from mutagen.flac import FLAC
        path = make_audio(os.path.join(self.dir, "a.flac"), 1, {"title": "x"})
        f = FLAC(path)
        f["REPLAYGAIN_TRACK_GAIN"] = "-3.2 dB"
        f.save()
        tagio.write_file(path, {"title": "y"})
        self.assertEqual(FLAC(path)["REPLAYGAIN_TRACK_GAIN"], ["-3.2 dB"])


class Matching(unittest.TestCase):
    def test_similarity(self):
        self.assertEqual(matcher.similarity("The Beatles", "Beatles"), 1.0)
        self.assertGreater(matcher.similarity("Pulp Fiction (Remastered)", "Pulp Fiction"), 0.95)
        self.assertLess(matcher.similarity("Abbey Road", "Let It Be"), 0.5)

    def test_parse_mbid(self):
        self.assertEqual(parse_mbid(f"https://musicbrainz.org/release/{RID_OST}/discids"), RID_OST)
        self.assertIsNone(parse_mbid("hello"))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is needed to create test audio files")
class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.data = tempfile.mkdtemp()
        # A soundtrack with messy tags: no album artist, artist per track.
        for i, (t, s, c) in enumerate(PULP, 1):
            make_audio(os.path.join(self.root, "Pulp Fiction", f"{i:02d} {t}.mp3"), s,
                       {"title": t.lower(), "artist": c[0]["name"], "album": "Pulp Fiction"})
        # A normal album with no tags at all - only folder + file names.
        for i, (t, s, _) in enumerate(BAND, 1):
            make_audio(os.path.join(self.root, "The Band", "Great Album (2011)", f"{i:02d} - {t}.flac"), s)
        # A compilation not on MusicBrainz at all
        for i, a in enumerate(["Alpha", "Beta", "Gamma", "Delta"], 1):
            make_audio(os.path.join(self.root, "My Mixtape", f"{i:02d}.m4a"), 3,
                       {"title": f"Song {i}", "artist": a, "albumartist": a, "album": "My Mixtape"})
        # Single-composer film score, split over CD folders
        for i, (t, s, _) in enumerate(SCORE, 1):
            make_audio(os.path.join(self.root, "Big Movie", "CD1", f"{i:02d} {t}.ogg"), s,
                       {"title": t, "artist": "Hans Zimmer", "album": "Big Movie"})

    def tearDown(self):
        shutil.rmtree(self.root)
        shutil.rmtree(self.data)

    def scan(self, settings=None):
        groups, bad = library.scan(self.root)
        self.assertEqual(bad, [])
        s = dict(matcher.DEFAULT_SETTINGS, **(settings or {}))
        mb = fake_mb()
        return {os.path.basename(g.folder): (g, matcher.match_album(mb, g, s)) for g in groups}, mb, s

    def test_grouping(self):
        groups, _ = library.scan(self.root)
        names = sorted(os.path.basename(g.folder) for g in groups)
        self.assertEqual(names, ["Big Movie", "Great Album (2011)", "My Mixtape", "Pulp Fiction"])
        band = next(g for g in groups if "Great" in g.folder)
        h = band.hints()
        self.assertEqual((h["artist"], h["album"], h["year"]), ("The Band", "Great Album", "2011"))
        self.assertEqual(band.files[1].title_hint, "Middle")

    def test_soundtrack_various_artists(self):
        res, _, _ = self.scan()
        _, r = res["Pulp Fiction"]
        self.assertEqual(r["status"], "good")
        self.assertEqual(r["release"]["id"], RID_OST)  # not the bonus-track edition
        ch = r["files"][1]["changes"]
        self.assertEqual(ch["albumartist"], "Various Artists")
        self.assertEqual(ch["compilation"], "1")
        self.assertEqual(ch["releasetype"], ["album", "soundtrack"])
        self.assertEqual(ch["genre"], ["Soundtrack"])
        self.assertEqual(ch["title"], "Jungle Boogie")
        self.assertEqual(ch["mb_albumartistid"], [VARIOUS_ARTISTS_ID])
        self.assertNotIn("artist", ch)  # already right

    def test_score_keeps_composer_or_uses_soundtrack(self):
        res, _, _ = self.scan()
        g, r = res["Big Movie"]
        self.assertEqual(len(g.files), 2)
        ch = r["files"][0]["changes"]
        self.assertEqual(ch["albumartist"], "Hans Zimmer")
        self.assertNotIn("compilation", ch)
        self.assertEqual(ch["releasetype"], ["album", "soundtrack"])

        res, _, _ = self.scan({"soundtrack_artist": "soundtrack"})
        ch = res["Big Movie"][1]["files"][0]["changes"]
        self.assertEqual(ch["albumartist"], "Soundtrack")
        self.assertEqual(ch["compilation"], "1")
        res, _, _ = self.scan({"soundtrack_artist": "various"})
        ch = res["Big Movie"][1]["files"][0]["changes"]
        self.assertEqual(ch["albumartist"], "Various Artists")

    def test_untagged_album_from_folder_names(self):
        res, _, _ = self.scan()
        _, r = res["Great Album (2011)"]
        self.assertEqual(r["status"], "good")
        ch = r["files"][2]["changes"]
        self.assertEqual((ch["title"], ch["artist"], ch["albumartist"]), ("Closing", "The Band", "The Band"))
        self.assertEqual(ch["date"], "1975-03-01")  # original year by default
        self.assertEqual(ch["artistsort"], "Band, The")
        self.assertNotIn("compilation", ch)

    def test_local_compilation_fix(self):
        res, _, _ = self.scan()
        _, r = res["My Mixtape"]
        self.assertEqual(r["status"], "local")
        ch = r["files"][0]["changes"]
        self.assertEqual(ch["albumartist"], "Various Artists")
        self.assertEqual(ch["compilation"], "1")
        self.assertEqual(ch["releasetype"], ["album", "compilation"])

    def test_apply_and_undo(self):
        app = App(mb=fake_mb(), data_dir=self.data)
        app.start_scan(self.root)
        app.thread.join()
        st = app.state()
        by_folder = {a["folder"]: a for a in st["albums"]}
        self.assertTrue(by_folder["Pulp Fiction"]["selected"])
        self.assertFalse(by_folder["My Mixtape"]["selected"])  # local fixes need a tick
        app.set_selected([by_folder["My Mixtape"]["id"]], True)

        pulp = os.path.join(self.root, "Pulp Fiction", "02 Jungle Boogie.mp3")
        before = tagio.read_file(pulp)["tags"]
        app.start_apply()
        app.thread.join()
        after = tagio.read_file(pulp)
        self.assertEqual(after["tags"]["albumartist"], "Various Artists")
        self.assertEqual(after["tags"]["compilation"], "1")
        self.assertTrue(after["has_cover"])
        self.assertTrue(os.path.exists(os.path.join(self.root, "Pulp Fiction", "cover.jpg")))
        mix = tagio.read_file(os.path.join(self.root, "My Mixtape", "01.m4a"))["tags"]
        self.assertEqual(mix["albumartist"], "Various Artists")
        self.assertEqual(mix["artist"], "Alpha")
        self.assertTrue(all(a["applied"] for a in app.state()["albums"] if a["selected"] is False and a["changed"]))

        app.undo()
        app.thread.join()
        restored = tagio.read_file(pulp)
        self.assertEqual(restored["tags"], before)
        self.assertFalse(restored["has_cover"])
        self.assertFalse(os.path.exists(os.path.join(self.root, "Pulp Fiction", "cover.jpg")))
        # after undo the albums were looked up again and are ready once more
        self.assertEqual({a["folder"]: a["status"] for a in app.state()["albums"]}["Pulp Fiction"], "good")

    def test_choose_release_and_rescan_is_noop(self):
        app = App(mb=fake_mb(), data_dir=self.data)
        app.start_scan(self.root)
        app.thread.join()
        gid = next(a["id"] for a in app.state()["albums"] if a["folder"] == "Pulp Fiction")
        res = app.choose_release(gid, f"https://musicbrainz.org/release/{RID_OST_ALT}")
        self.assertEqual(res["release"]["id"], RID_OST_ALT)
        self.assertEqual(res["status"], "chosen")
        app.choose_release(gid, RID_OST)
        app.start_apply()
        app.thread.join()
        # a second scan after applying finds nothing left to change
        app.start_scan(self.root)
        app.thread.join()
        st = {a["folder"]: a for a in app.state()["albums"]}
        self.assertEqual(st["Pulp Fiction"]["status"], "ok")
        self.assertEqual(st["Pulp Fiction"]["changed"], 0)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is needed to create test audio files")
class Server(unittest.TestCase):
    def test_http_api(self):
        from http.server import ThreadingHTTPServer
        from tagfixer.server import make_handler
        root, data = tempfile.mkdtemp(), tempfile.mkdtemp()
        try:
            for i, (t, s, c) in enumerate(PULP, 1):
                make_audio(os.path.join(root, "Pulp Fiction", f"{i:02d}.mp3"), s,
                           {"title": t, "artist": c[0]["name"], "album": "Pulp Fiction"})
            app = App(mb=fake_mb(), data_dir=data)
            srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"

            def call(path, body=None, headers=None):
                req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                             headers=dict({"X-TagFixer": "1", "Content-Type": "application/json"}, **(headers or {})))
                with urllib.request.urlopen(req) as r:
                    return json.loads(r.read())

            self.assertIn(b"TagFixer", urllib.request.urlopen(base + "/").read())
            call("/api/scan", {"path": root})
            app.thread.join()
            st = call("/api/state")
            self.assertEqual(st["counts"], {"good": 1})
            detail = call("/api/album?id=" + st["albums"][0]["id"])
            self.assertEqual(len(detail["files"]), 3)
            self.assertEqual(call("/api/state?since=" + str(st["version"]))["albums"], [])
            with self.assertRaises(urllib.error.HTTPError) as e:
                call("/api/apply", {}, {"X-TagFixer": "0"})
            self.assertEqual(e.exception.code, 403)
            with self.assertRaises(urllib.error.HTTPError) as e:
                call("/api/state", None, {"Host": "evil.example"})
            self.assertEqual(e.exception.code, 403)
            self.assertEqual(call("/api/apply", {})["count"], 1)
            app.thread.join()
            self.assertEqual(call("/api/state")["applied"], 1)
            srv.shutdown()
        finally:
            shutil.rmtree(root)
            shutil.rmtree(data)


class Plex(unittest.TestCase):
    def test_refresh_folders(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from tagfixer import plex
        hits = []

        class FakePlex(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                hits.append(self.path)
                body = b""
                if self.path.startswith("/library/sections?"):
                    body = json.dumps({"MediaContainer": {"Directory": [
                        {"key": "3", "type": "artist", "title": "Music", "Location": [{"path": "/data/music"}]},
                        {"key": "1", "type": "movie", "title": "Films", "Location": [{"path": "/data/films"}]},
                    ]}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakePlex)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        settings = {"plex_url": f"http://127.0.0.1:{srv.server_address[1]}", "plex_token": "tok",
                    "plex_path_from": "/Volumes/Music", "plex_path_to": "/data/music"}
        msg = plex.refresh_folders(settings, ["/Volumes/Music/Pulp Fiction"])
        srv.shutdown()
        self.assertEqual(msg, "Plex: asked to rescan 1 folder(s)")
        self.assertIn("/library/sections/3/refresh?path=%2Fdata%2Fmusic%2FPulp+Fiction&X-Plex-Token=tok", hits)


if __name__ == "__main__":
    unittest.main()
