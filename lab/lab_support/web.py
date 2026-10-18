"""Supplied bounded web-search connection; independent of SDK tool context."""

from contextlib import contextmanager
from contextvars import ContextVar

from ._provider import RunError


_service = ContextVar("lab_web_search", default=None)


@contextmanager
def use(service):
    token = _service.set(service)
    try:
        yield
    finally:
        _service.reset(token)


def search(query: str) -> dict:
    service = _service.get()
    if service is None:
        raise RunError("Web search needs the configured live connection; offline file tools do not.")
    return service.search(query)
