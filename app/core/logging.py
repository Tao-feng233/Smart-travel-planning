"""Structured logging and a per-request trace id.

Opt-in on purpose: `LOG_FORMAT=json` switches stdlib logging to one JSON object
per line with the trace id attached. The default stays human-readable, so local
runs and the regression suite are unaffected; containers set the variable.
"""

import json
import logging
import os
import sys
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar, Token

TRACE_HEADER = "X-Trace-Id"
TRACE_ID: ContextVar[str] = ContextVar("shitu_trace_id", default="-")

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def trace_id():
    return TRACE_ID.get()


@contextmanager
def bound(trace):
    token = TRACE_ID.set(trace)
    try:
        yield trace
    finally:
        TRACE_ID.reset(token)


def new_trace():
    return uuid.uuid4().hex[:16]


def _json_default(value):
    return repr(value)


# LogRecord attributes that must not be promoted into the JSON payload.
_STANDARD = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """One JSON object per line: greppable, ingestible, no multi-line stack noise."""

    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": trace_id(),
        }
        # Anything the caller passed via `extra=` survives as a first-class field.
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _STANDARD or key in payload:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=_json_default)


def json_output():
    return os.environ.get("LOG_FORMAT", "").strip().lower() == "json"


def configure(level=None):
    """Idempotent: safe to call from lifespan on every start or reload."""
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, "_shitu_owned", False):
            handler.setFormatter(
                JsonFormatter() if json_output() else logging.Formatter(
                    "%(asctime)s %(levelname)s %(name)s %(message)s"
                )
            )
            if level:
                handler.setLevel(_LEVELS.get(level.upper(), logging.INFO))
            return handler
    handler = logging.StreamHandler(sys.stdout)
    handler._shitu_owned = True
    handler.setFormatter(
        JsonFormatter() if json_output() else logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
    )
    handler.setLevel(
        _LEVELS.get((level or os.environ.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    )
    root.addHandler(handler)
    # Never raise the root level: libraries that already log more verbosely keep doing so.
    if root.level == logging.NOTSET or root.level > handler.level:
        root.setLevel(handler.level)
    return handler


def request_log(logger_name="shitu.access"):
    return logging.getLogger(logger_name)


def emit_access(path, method, status, started, extra=None):
    """Emit one access record. Cheap enough to leave on in every environment."""
    payload = {
        "method": method,
        "path": path,
        "status": status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if extra:
        payload.update(extra)
    request_log().info("request", extra=payload)
