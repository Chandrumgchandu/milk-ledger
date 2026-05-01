from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter
from zoneinfo import ZoneInfo
import uuid


IST = ZoneInfo("Asia/Kolkata")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ist_now_iso() -> str:
    return datetime.now(IST).isoformat()


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


@contextmanager
def timed_operation(logger, operation: str, **fields):
    start = perf_counter()
    logger.info(
        "event=%s stage=start utc=%s ist=%s %s",
        operation,
        utc_now_iso(),
        ist_now_iso(),
        _format_fields(fields),
    )
    try:
        yield
    except Exception:
        elapsed_ms = int((perf_counter() - start) * 1000)
        logger.exception(
            "event=%s stage=error elapsed_ms=%s utc=%s ist=%s %s",
            operation,
            elapsed_ms,
            utc_now_iso(),
            ist_now_iso(),
            _format_fields(fields),
        )
        raise
    elapsed_ms = int((perf_counter() - start) * 1000)
    logger.info(
        "event=%s stage=success elapsed_ms=%s utc=%s ist=%s %s",
        operation,
        elapsed_ms,
        utc_now_iso(),
        ist_now_iso(),
        _format_fields(fields),
    )


def _format_fields(fields: dict) -> str:
    parts = []
    for key, value in fields.items():
        if value is None or value == "":
            continue
        safe = str(value).replace(" ", "_")
        parts.append(f"{key}={safe}")
    return " ".join(parts)
