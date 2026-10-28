"""Archivist entry point: starts the local web GUI (or the terminal menu with --cli)."""
from __future__ import annotations

import argparse

from .core.common import OperationError, to_path


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m run",
        description="Archivist: organise photo and video archives. Runs a local web GUI; nothing leaves this computer.",
    )
    parser.add_argument("folder", nargs="?", help="Folder to open in the GUI (can also be chosen in the browser).")
    parser.add_argument("--port", type=int, default=0, help="Port to listen on (default: any free port).")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")
    parser.add_argument("--cli", action="store_true", help="Use the terminal menu instead of the web GUI.")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.cli:
        from . import cli
        try:
            cli.main()
        except (KeyboardInterrupt, EOFError):
            print("\n👋  Exiting the Archivist Utility. Goodbye!")
        return
    root = None
    if args.folder:
        try:
            root = to_path(args.folder)
        except OperationError as exc:
            raise SystemExit(str(exc))
        if not root.is_dir():
            raise SystemExit(f"Not a folder: {root}")
    from .web.server import run_server
    run_server(root, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
