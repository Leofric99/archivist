"""Terminal menu built on the same operations as the web GUI (run with --cli)."""
from __future__ import annotations

import os
from pathlib import Path

from .core import ops
from .core.common import (Cancelled, Context, OperationError, Operation, Reporter, iter_media, kind_of, to_path)

MAX_LISTED = 40
GROUP_TITLES = {"photos": "Photographs", "videos": "Videos", "metadata": "Metadata", "folder": "Folders"}
SYMBOLS = {"ok": "✅", "warn": "⚠️ ", "error": "❌", "info": "  "}


def ask(prompt: str) -> str:
    return input(f" {prompt}: ").strip()


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    answer = ask(f"{prompt} ({'Y/n' if default else 'y/N'})").lower()
    return default if not answer else answer.startswith("y")


def _visible(param, values: dict) -> bool:
    return not param.show_if or all(bool(values.get(k)) == bool(v) for k, v in param.show_if.items())


def prompt_params(op: Operation) -> dict:
    values = {p.name: p.get_default() for p in op.params}
    for p in op.params:
        if not _visible(p, values):
            continue
        if p.help:
            print(f"   ({p.help})")
        if p.kind == "bool":
            values[p.name] = ask_yes_no(p.label, bool(p.get_default()))
        elif p.kind == "choice":
            choices, default = p.get_choices(), str(p.get_default() or "")
            by_lower = {v.lower(): v for v, _ in choices}
            short = len(choices) <= 12
            hint = ", ".join(f"{v} = {label}" for v, label in choices) if short else "type a name, ? to list"
            while True:
                answer = ask(f"{p.label} [{hint}] (default: {default})") or default
                if answer == "?":
                    print("   " + ", ".join(v for v, _ in choices))
                elif answer.lower() in by_lower:
                    values[p.name] = by_lower[answer.lower()]
                    break
                else:
                    print("   Not a valid choice.")
        else:
            while True:
                answer = ask(p.label + ("" if p.required else " (optional)"))
                if answer or not p.required:
                    values[p.name] = answer
                    break
    return values


def collect_files(op: Operation) -> tuple:
    """Return (context, files) for an operation, prompting for paths."""
    if op.scope == "folder":
        folder = to_path(ask("Folder to process"))
        if not folder.is_dir():
            raise OperationError(f"Not a folder: {folder}")
        return Context(root=folder), []
    raw = ask("Path to a file or folder (separate several with ;)")
    subdirs = None
    files = []
    for part in filter(None, (s.strip() for s in raw.split(";"))):
        path = to_path(part)
        if path.is_dir():
            if subdirs is None:
                subdirs = ask_yes_no("Include sub-folders", False)
            files.extend(iter_media(path, subdirs=subdirs))
        elif path.is_file():
            files.append(path)
        else:
            print(f"   Not found: {path}")
    files = list(dict.fromkeys(f for f in files if kind_of(f) in op.accepts))
    if not files:
        raise OperationError("No supported files found.")
    root = Path(os.path.commonpath([str(f.parent) for f in files]))
    return Context(root=root), files


def show_plan(ctx: Context, plan) -> None:
    print()
    for item in plan.items[:MAX_LISTED]:
        mark = {"ok": "→", "skip": "·", "error": "✗"}[item.status]
        target = f" -> {ctx.rel(Path(item.target))}" if item.target else ""
        note = f"  [{item.note}]" if item.note else ""
        print(f"  {mark} {ctx.rel(Path(item.source))}{target}{note}")
    if len(plan.items) > MAX_LISTED:
        print(f"  ... and {len(plan.items) - MAX_LISTED} more")
    for message in plan.warnings:
        print(f"⚠️  {message}")
    for message in plan.errors:
        print(f"❌ {message}")
    if plan.summary:
        print(f"\n{plan.summary}")


def run_operation(op: Operation) -> None:
    print("\n" + "═" * 50)
    print(op.label.center(50))
    print("═" * 50)
    print(op.description)
    try:
        ctx, files = collect_files(op)
        params = prompt_params(op)
        if op.captions:
            captions = {}
            hint = "leave blank to skip" if op.captions == "required" else "leave blank to use the common text"
            for f in files:
                text = ask(f"Caption for {f.name} ({hint})")
                if text:
                    captions[ctx.rel(f)] = text
            params["captions"] = captions
        answers: dict = {}
        while True:
            plan = op.plan(ctx, files, params, answers)
            if not plan.questions:
                break
            for q in plan.questions:
                print(f"\n{q['prompt']}\n  {q['detail']}")
                answers[q["id"]] = ask_yes_no("Group together", False)
    except OperationError as exc:
        print(f"❌ {exc}")
        return
    show_plan(ctx, plan)
    if not plan.ready:
        print("Nothing to do.")
        return
    if plan.confirmation:
        if ask(f"{plan.confirmation['message']} ({plan.confirmation['expected']})") != plan.confirmation["expected"]:
            print("Aborted.")
            return
    elif not ask_yes_no("Proceed", False):
        print("Aborted.")
        return
    rep = Reporter(on_log=lambda msg, level: print(f"{SYMBOLS.get(level, '  ')} {msg}"))
    try:
        op.apply(ctx, plan, rep)
    except Cancelled:
        print("Cancelled.")
    print(f"\nDone: {rep.n_ok} succeeded, {rep.n_skipped} skipped, {rep.n_failed} failed.")


def main() -> None:
    menu = []
    for group, title in GROUP_TITLES.items():
        menu.append((title, [op for op in ops.OPERATIONS if op.group == group]))
    while True:
        print("\n" + "═" * 50)
        print("📦  Welcome to the Archivist Utility!  📦".center(50))
        print("═" * 50)
        numbered, n = {}, 0
        for title, group_ops in menu:
            print(f" {title}")
            for op in group_ops:
                n += 1
                numbered[str(n)] = op
                print(f"   {n:>2}. {op.label}")
        print(f"   {'q':>2}. Exit")
        choice = ask("Select an option").lower()
        if choice in ("q", "quit", "exit"):
            print("👋  Exiting the Archivist Utility. Goodbye!")
            return
        if choice in numbered:
            run_operation(numbered[choice])
        else:
            print("❌  Invalid selection.")
