"""Command line entry point.

    python -m tagfixer                      open the app in your browser
    python -m tagfixer --cli /music         look up everything, print a report
    python -m tagfixer --cli /music --apply ...and write the confident matches
    python -m tagfixer --undo               undo the last batch of changes
"""

import argparse
import sys

from . import __version__, matcher, writer


def run_cli(args):
    from .app import App

    app = App()
    if args.min_confidence is not None:
        app.settings["auto_select"] = args.min_confidence
    print(f"Scanning {args.cli} ...")
    app.start_scan(args.cli)
    last = None
    try:
        while app.busy():
            app.thread.join(0.5)
            p = app.progress
            line = f"  {app.phase}: {p['done']}/{p['total']}  {p['current'][:60]}"
            if line != last:
                sys.stdout.write("\r" + line.ljust(90))
                sys.stdout.flush()
                last = line
    except KeyboardInterrupt:
        app.stop()
        app.thread.join()
    print()

    state = app.state()
    for a in sorted(state["albums"], key=lambda a: a["folder"].lower()):
        rel = a["release"] or {}
        conf = f"{a['confidence']:.2f}" if a["confidence"] is not None else "  - "
        mark = "*" if a["selected"] else " "
        target = f"{rel.get('artist')} - {rel.get('title')}" if rel else (a["message"] or "")
        print(f" {mark} [{a['status']:>7}] {conf}  {a['folder']}  ->  {target}")
    for m in app.messages:
        print(m)
    counts = state["counts"]
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
    print(f"{state['selected']} albums would be changed (marked *).")

    if args.apply and state["selected"]:
        app.start_apply()
        app.thread.join()
        for m in app.messages[-20:]:
            print(m)
        print("Run `python -m tagfixer --undo` to reverse this batch.")
    elif state["selected"]:
        print("Nothing written yet. Add --apply to write these changes.")


def main(argv=None):
    p = argparse.ArgumentParser(prog="tagfixer", description="Fix music tags using MusicBrainz.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1",
                   help="use 0.0.0.0 to reach it from other machines (e.g. a NAS)")
    p.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    p.add_argument("--cli", metavar="FOLDER", help="run without the web interface")
    p.add_argument("--apply", action="store_true", help="with --cli: write the confident matches")
    p.add_argument("--min-confidence", type=float, default=None,
                   help=f"with --cli: confidence needed to apply (default {matcher.DEFAULT_SETTINGS['auto_select']})")
    p.add_argument("--undo", action="store_true", help="undo the most recent batch of changes")
    args = p.parse_args(argv)

    if args.undo:
        restored, errors, path = writer.undo_last()
        if path is None:
            print("Nothing to undo.")
        else:
            print(f"Restored {restored} files from {path}")
            for e in errors:
                print("  error:", e)
        return
    if args.cli:
        return run_cli(args)

    from .server import serve
    serve(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
