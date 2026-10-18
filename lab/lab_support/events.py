"""Small structured activity callback; no model reasoning or automatic logging."""

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import re

_sink = ContextVar("lab_event_sink", default=None)
_call = ContextVar("lab_event_call", default={})


def clean(value, key=""):
    if isinstance(value, str):
        value = value.replace(key, "[REDACTED]") if key else value
        value = re.sub(r"sk-or-[A-Za-z0-9_-]+", "[REDACTED]", value)
        return "".join(c for c in value if c in "\n\t" or ord(c) >= 32 and ord(c) != 127)
    if isinstance(value, dict):
        return {clean(str(k), key): clean(v, key) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v, key) for v in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return clean(str(value), key)


def emit_event(kind, **data):
    sink = _sink.get()
    if sink is not None:
        sink({"type": kind, **_call.get(), **data})


@contextmanager
def event_scope(sink):
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


@contextmanager
def tool_scope(**identity):
    token = _call.set(identity)
    try:
        yield
    finally:
        _call.reset(token)


def record_event(records, callback, identity, event, key=""):
    record = clean({**identity, **event}, key)
    records.append(record)
    if callback:
        # Observers cannot mutate retained evidence or stop completed tool work.
        try:
            callback(deepcopy(record))
        except Exception:
            records.append({**identity, "type": "observer_error",
                            "error": "Activity callback failed."})
