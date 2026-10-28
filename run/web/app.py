"""FastAPI application: a local-only web GUI over the Archivist core."""
from __future__ import annotations

import asyncio
import hmac
import io
import json
import logging
import mimetypes
import secrets
import threading
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..core import metadata as metadata_core
from ..core.rename import rename_file
from ..core import fonts, ops
from ..core.common import Context, Item, OperationError, Plan, iter_media, kind_of, to_path
from .jobs import JobBusy, JobManager
from .thumbs import ThumbnailCache

log = logging.getLogger("archivist")
STATIC_DIR = Path(__file__).parent / "static"
COOKIE = "archivist_token"
PLAN_TTL_SECONDS = 30 * 60
MAX_FILES = 50_000
THUMB_SIZE = 320
PREVIEW_SIZE = 1600

CSP = ("default-src 'self'; img-src 'self' data: blob:; media-src 'self'; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


class RootBody(BaseModel):
    path: str


class PlanBody(BaseModel):
    paths: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    answers: dict[str, Any] = Field(default_factory=dict)


class PreviewBody(BaseModel):
    path: str
    params: dict[str, Any] = Field(default_factory=dict)
    caption: Optional[str] = None


class RenameBody(BaseModel):
    path: str
    name: str


class ApplyBody(BaseModel):
    plan_id: str
    confirm: Optional[str] = None


class AppState:
    def __init__(self, root: Optional[Path]) -> None:
        self.ctx: Optional[Context] = Context(root=root) if root else None
        self.plans: dict = {}
        self.jobs = JobManager()
        self.thumbs = ThumbnailCache()

    def require_ctx(self) -> Context:
        if not self.ctx:
            raise HTTPException(400, "Open a folder first.")
        return self.ctx

    def store_plan(self, plan: Plan, op_id: str, ctx: Context) -> str:
        now = time.time()
        for key in [k for k, v in self.plans.items() if now - v["time"] > PLAN_TTL_SECONDS]:
            del self.plans[key]
        plan_id = uuid.uuid4().hex
        self.plans[plan_id] = {"plan": plan, "op": op_id, "root": ctx.root, "time": now}
        return plan_id


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _visible(param, values: dict) -> bool:
    if not param.show_if:
        return True
    return all(bool(values.get(k)) == bool(v) if isinstance(v, bool) else values.get(k) == v
               for k, v in param.show_if.items())


def _merge_params(op, given: dict) -> dict:
    values = {p.name: p.get_default() for p in op.params}
    values.update(given)
    for p in op.params:
        if p.required and _visible(p, values) and not str(values.get(p.name) or "").strip():
            raise HTTPException(400, f"'{p.label}' is required.")
    for key in ("captions", "crops"):
        value = given.get(key)
        values[key] = value if isinstance(value, dict) else {}
    return values


def create_app(token: str, port: int, root: Optional[Path] = None) -> FastAPI:
    secret = token
    state = AppState(root)
    # Scanning installed fonts takes about a second; do it before the first form needs it.
    threading.Thread(target=fonts.available_fonts, daemon=True).start()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        state.thumbs.close()

    app = FastAPI(title="Archivist", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.archivist = state

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Rejecting unknown Host headers defeats DNS-rebinding attacks against this localhost server.
        if request.headers.get("host", "") not in allowed_hosts:
            return PlainTextResponse("Forbidden host", status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    def authenticate(request: Request) -> None:
        supplied = request.cookies.get(COOKIE, "")
        if not _same(supplied, secret):
            raise HTTPException(401, "Not authorised. Open the URL printed in the terminal.")
        if request.method not in ("GET", "HEAD") and request.headers.get("origin") not in allowed_origins:
            raise HTTPException(403, "Cross-origin request refused.")

    api = APIRouter(prefix="/api", dependencies=[Depends(authenticate)])

    def file_from(rel: str) -> Path:
        ctx = state.require_ctx()
        try:
            path = ctx.resolve_inside(rel)
        except OperationError as exc:
            raise HTTPException(400, str(exc))
        if not path.is_file():
            raise HTTPException(404, "File not found.")
        return path

    @api.get("/state")
    def get_state() -> dict:
        return {
            "root": str(state.ctx.root) if state.ctx else None,
            "home": str(Path.home()),
            "ops": [op.to_dict() for op in ops.OPERATIONS],
            "tools": {"ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe"))},
        }

    @api.get("/browse")
    def browse(path: str = "") -> dict:
        try:
            folder = to_path(path) if path.strip() else (state.ctx.root if state.ctx else Path.home())
        except OperationError as exc:
            raise HTTPException(400, str(exc))
        if not folder.is_dir():
            raise HTTPException(400, f"Not a folder: {folder}")
        try:
            names = sorted((p.name for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")),
                           key=str.lower)
        except OSError as exc:
            raise HTTPException(403, f"Cannot read folder: {exc.strerror}")
        parent = str(folder.parent) if folder.parent != folder else None
        return {"path": str(folder), "parent": parent, "folders": names}

    @api.post("/root")
    def set_root(body: RootBody) -> dict:
        try:
            folder = to_path(body.path)
        except OperationError as exc:
            raise HTTPException(400, str(exc))
        if not folder.is_dir():
            raise HTTPException(400, f"Not a folder: {folder}")
        state.ctx = Context(root=folder)
        state.plans.clear()
        return {"root": str(folder)}

    @api.get("/files")
    def list_files(subdirs: bool = True) -> dict:
        ctx = state.require_ctx()
        files, truncated = [], False
        for p in iter_media(ctx.root, subdirs=subdirs):
            if len(files) >= MAX_FILES:
                truncated = True
                break
            try:
                st = p.stat()
            except OSError:
                continue
            files.append({"path": ctx.rel(p), "name": p.name, "kind": kind_of(p),
                          "size": st.st_size, "mtime": st.st_mtime})
        return {"root": str(ctx.root), "files": files, "truncated": truncated}

    @api.post("/rename")
    def rename_one(body: RenameBody) -> dict:
        ctx = state.require_ctx()
        src = file_from(body.path)
        if (ctx.root / body.path).is_symlink():
            raise HTTPException(400, "Symbolic links cannot be renamed here.")
        if state.jobs.busy():
            raise HTTPException(409, "Another operation is still running.")
        try:
            target = rename_file(src, body.name)
        except OperationError as exc:
            raise HTTPException(400, str(exc))
        state.plans.clear()  # earlier plans refer to the old name
        return {"path": ctx.rel(target), "name": target.name}

    @api.get("/info")
    def info(path: str) -> dict:
        return metadata_core.read_info(file_from(path))

    @api.get("/thumb")
    def thumb(path: str, size: int = THUMB_SIZE) -> Response:
        data = state.thumbs.get(file_from(path), max(32, min(size, 640)))
        if not data:
            return Response(status_code=204)
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})

    @api.get("/preview")
    def preview(path: str) -> Response:
        data = state.thumbs.get(file_from(path), PREVIEW_SIZE, quality=88)
        if not data:
            return Response(status_code=204)
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})

    @api.get("/file")
    def raw_file(path: str) -> FileResponse:
        p = file_from(path)
        if kind_of(p) != "video":
            raise HTTPException(400, "Only videos can be streamed.")
        return FileResponse(p, media_type=mimetypes.guess_type(p.name)[0] or "application/octet-stream")

    def get_op(op_id: str):
        try:
            return ops.get(op_id)
        except KeyError:
            raise HTTPException(404, "Unknown operation.")

    @api.post("/ops/{op_id}/plan")
    def make_plan(op_id: str, body: PlanBody) -> dict:
        op = get_op(op_id)
        ctx = state.require_ctx()
        params = _merge_params(op, body.params)
        accepted, rejected = [], []
        if op.scope == "files":
            if not body.paths:
                raise HTTPException(400, "Select at least one file.")
            seen = set()
            for rel in body.paths:
                path = file_from(rel)
                if path in seen:
                    continue
                seen.add(path)
                (accepted if kind_of(path) in op.accepts else rejected).append(path)
        try:
            plan = op.plan(ctx, accepted, params, body.answers)
        except OperationError as exc:
            raise HTTPException(400, str(exc))
        except HTTPException:
            raise
        except Exception:
            log.exception("Planning %s failed", op_id)
            raise HTTPException(500, "Planning failed unexpectedly; see the terminal for details.")
        plan.items.extend(Item(str(p), None, "", "skip", "not supported by this action") for p in rejected)
        for item in plan.items:
            item.source = ctx.rel(Path(item.source)) if Path(item.source).is_absolute() else item.source
            if item.target and Path(item.target).is_absolute():
                item.target = ctx.rel(Path(item.target))
        result = plan.to_dict()
        result["plan_id"] = state.store_plan(plan, op_id, ctx)
        return result

    @api.post("/ops/{op_id}/preview")
    def make_preview(op_id: str, body: PreviewBody) -> Response:
        op = get_op(op_id)
        if not op.preview:
            raise HTTPException(400, "This action has no preview.")
        ctx = state.require_ctx()
        try:
            image = op.preview(ctx, file_from(body.path), dict(body.params), body.caption)
        except Exception as exc:
            raise HTTPException(400, f"Preview failed: {exc}")
        buf = io.BytesIO()
        image.convert("RGB").save(buf, "JPEG", quality=85)
        return Response(buf.getvalue(), media_type="image/jpeg")

    @api.post("/ops/{op_id}/apply")
    def apply_plan(op_id: str, body: ApplyBody) -> dict:
        op = get_op(op_id)
        ctx = state.require_ctx()
        entry = state.plans.get(body.plan_id)
        if not entry or entry["op"] != op_id or entry["root"] != ctx.root:
            raise HTTPException(400, "This plan is no longer valid. Preview it again.")
        plan: Plan = entry["plan"]
        if time.time() - entry["time"] > PLAN_TTL_SECONDS:
            raise HTTPException(400, "This plan has expired. Preview it again.")
        if not plan.ready:
            raise HTTPException(400, "The plan has errors or unanswered questions.")
        if plan.confirmation and body.confirm != plan.confirmation["expected"]:
            raise HTTPException(400, "The confirmation text does not match.")
        try:
            job = state.jobs.start(op, ctx, plan)
        except JobBusy as exc:
            raise HTTPException(409, str(exc))
        state.plans.pop(body.plan_id, None)
        return {"job_id": job.id}

    def get_job(job_id: str):
        job = state.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "Unknown job.")
        return job

    @api.get("/jobs/{job_id}")
    def job_status(job_id: str, since: int = 0) -> dict:
        return get_job(job_id).snapshot(since)

    @api.post("/jobs/{job_id}/cancel")
    def job_cancel(job_id: str) -> dict:
        get_job(job_id).cancel_event.set()
        return {"ok": True}

    @api.get("/jobs/{job_id}/events")
    async def job_events(job_id: str) -> StreamingResponse:
        job = get_job(job_id)

        async def stream():
            sent = 0
            while True:
                snap = job.snapshot(sent)
                sent = snap["next"]
                yield f"data: {json.dumps(snap)}\n\n"
                if snap["status"] != "running":
                    return
                await asyncio.sleep(0.4)

        return StreamingResponse(stream(), media_type="text/event-stream")

    app.include_router(api)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, token: Optional[str] = Query(None, alias="token")):
        # `token` here is the query-string value; the closure's real token is `secret`.
        if token is not None:
            if not _same(token, secret):
                return PlainTextResponse("Invalid token.", status_code=403)
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(COOKIE, secret, httponly=True, samesite="strict")
            return response
        if not _same(request.cookies.get(COOKIE, ""), secret):
            return PlainTextResponse(
                "Open the full URL that Archivist printed in your terminal (it contains a one-time token).",
                status_code=403)
        return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def new_token() -> str:
    return secrets.token_urlsafe(32)
