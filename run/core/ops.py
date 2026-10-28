"""Registry of every operation exposed by the web GUI and the terminal menu."""
from __future__ import annotations

from . import burnin, crop, metadata, rename, restructure
from .common import Operation

OPERATIONS: list = [
    *rename.OPERATIONS,
    *burnin.OPERATIONS,
    *crop.OPERATIONS,
    *metadata.OPERATIONS,
    *restructure.OPERATIONS,
]
BY_ID: dict = {op.id: op for op in OPERATIONS}


def get(op_id: str) -> Operation:
    try:
        return BY_ID[op_id]
    except KeyError:
        raise KeyError(f"Unknown operation: {op_id}") from None
