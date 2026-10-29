"""Run Archivist in a native WebView, with API requests dispatched in-process."""
from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from fastapi.testclient import TestClient

from .web.app import COOKIE, create_app, new_token
from .core.common import Context, kind_of

_ORIGIN = "http://127.0.0.1:0"


class DesktopBridge:
    """Dispatch API traffic through an in-process ASGI client; no network server is started."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self._token = new_token()
        self._app = create_app(self._token, 0, root)
        self._client = TestClient(self._app, base_url=_ORIGIN)
        self._client.__enter__()
        self._client.cookies.set(COOKIE, self._token)

    def request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        if method not in {"GET", "POST"} or not path.startswith("/api/"):
            raise ValueError("Invalid desktop API request.")
        headers = {"Origin": _ORIGIN}
        response = self._client.request(
            method, path, json=body, headers=headers,
        ) if body is not None else self._client.request(method, path, headers=headers)
        return {
            "status": response.status_code,
            "content_type": response.headers.get("content-type", "application/octet-stream"),
            "body": base64.b64encode(response.content).decode("ascii"),
        }

    def media_url(self, relative_path: str) -> str:
        state = self._app.state.archivist
        path = state.file_from(relative_path)
        if kind_of(path) != "video":
            raise HTTPException(400, "Only videos can be streamed.")
        return path.as_uri()

    def add_files(self, paths: list[str]) -> dict:
        if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            raise ValueError("Dropped file paths must be a list of strings.")
        state = self._app.state.archivist
        current = state.ctx
        ctx = current if current and current.tracked_files is not None else Context(
            root=Path.home(), tracked_files={})
        added = skipped = 0
        known = {path.resolve() for path in ctx.tracked_files.values()}
        for raw in paths[:5000]:
            try:
                path = Path(raw).expanduser()
                if path.is_symlink() or not path.is_file() or kind_of(path) != "image":
                    skipped += 1
                    continue
                path = path.resolve(strict=True)
            except (OSError, RuntimeError, TypeError, ValueError):
                skipped += 1
                continue
            if path in known:
                skipped += 1
                continue
            ctx.tracked_files[uuid.uuid4().hex] = path
            known.add(path)
            added += 1
        skipped += max(0, len(paths) - 5000)
        if added:
            state.ctx = ctx
            state.plans.clear()
        return {"added": added, "skipped": skipped}

    def _close(self) -> None:
        self._client.__exit__(None, None, None)


def _enable_windows_file_drop(window, bridge: DesktopBridge) -> None:
    """Route WebView2 file-drop paths from the document drop event into the desktop bridge."""
    if sys.platform != "win32":
        return

    from webview.dom import DOMEventHandler

    def on_drop(event):
        transfer = event.get("dataTransfer") if isinstance(event, dict) else None
        files = transfer.get("files", []) if isinstance(transfer, dict) else []
        paths = [
            item["pywebviewFullPath"]
            for item in files
            if isinstance(item, dict) and isinstance(item.get("pywebviewFullPath"), str)
        ]
        if not paths:
            window.evaluate_js(
                "window.archivistDropFailed('Archivist could not read the dropped file paths. Drop photos from File Explorer.')"
            )
            return
        result = bridge.add_files(paths)
        result["skipped"] += len(files) - len(paths)
        script = f"window.archivistFilesDropped({json.dumps(result)});"
        window.evaluate_js(script)

    def attach():
        window.evaluate_js("""
            document.addEventListener('dragover', event => {
                if (event.dataTransfer && Array.from(event.dataTransfer.types).includes('Files')) {
                    event.preventDefault();
                }
            });
        """)
        body = window.dom.get_element("body")
        if body is None:
            raise RuntimeError("The Archivist document is unavailable for drag-and-drop.")
        body.on("drop", DOMEventHandler(on_drop, prevent_default=True))

    window.events.loaded += attach


def _resource_path(relative: str) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / relative
    return Path(__file__).resolve().parent.parent / relative


def _desktop_html(static_dir: Path) -> str:
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    base_tag = '<base href="/static/">'
    if base_tag not in html or '<html lang="en">' not in html:
        raise RuntimeError("The desktop GUI HTML is missing its expected asset base or root element.")
    html = html.replace(base_tag, f'<base href="{static_dir.resolve().as_uri()}/">', 1)
    return html.replace('<html lang="en">', '<html lang="en" data-desktop="true">', 1)


def main() -> None:
    import webview

    bridge = DesktopBridge()
    try:
        static_dir = _resource_path("run/web/static")
        with tempfile.TemporaryDirectory(prefix="archivist-desktop-") as page_root:
            page_root_path = Path(page_root)
            local_static = page_root_path / "static"
            shutil.copytree(static_dir, local_static)
            page = page_root_path / "index.html"
            page.write_text(_desktop_html(local_static), encoding="utf-8")
            window = webview.create_window(
                "Archivist",
                url=page.as_uri(),
                js_api=bridge,
                width=1280,
                height=820,
                min_size=(900, 600),
            )
            _enable_windows_file_drop(window, bridge)
            webview.start()
    finally:
        bridge._close()


if __name__ == "__main__":
    main()
