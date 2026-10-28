"""Start the local web server (bound to 127.0.0.1 only) and open the GUI."""
from __future__ import annotations

import socket
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn

from .app import create_app, new_token


def run_server(root: Optional[Path] = None, port: int = 0, open_browser: bool = True) -> None:
    token = new_token()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError as exc:
        raise SystemExit(f"Cannot listen on 127.0.0.1:{port}: {exc}")
    actual_port = sock.getsockname()[1]
    app = create_app(token, actual_port, root)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    url = f"http://127.0.0.1:{actual_port}/?token={token}"

    print("\n📦  Archivist is running. Everything stays on this computer.", flush=True)
    print(f"    Open: {url}", flush=True)
    print("    Press Ctrl+C to stop.\n", flush=True)

    if open_browser:
        def opener() -> None:
            for _ in range(100):
                if server.started:
                    webbrowser.open(url)
                    return
                time.sleep(0.1)
        threading.Thread(target=opener, daemon=True).start()

    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    print("👋  Archivist stopped.")
