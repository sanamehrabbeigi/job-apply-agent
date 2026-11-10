"""All job sources. Each module exposes ``async fetch(ctx) -> SourceResult``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ..base import Source
from . import adzuna, ashby, greenhouse, jsearch, lever, linkedin, workday

SOURCES: dict[str, Source] = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "workday": workday.fetch,
    "jsearch": jsearch.fetch,
    "adzuna": adzuna.fetch,
    "linkedin": linkedin.fetch,
}

# For the Settings "Test" button: list a company's board without saving anything.
BOARD_LISTERS: dict[str, Callable[[Any, dict[str, Any]], Awaitable[list]]] = {
    "greenhouse": greenhouse.list_board,
    "lever": lever.list_board,
    "ashby": ashby.list_board,
    "workday": workday.list_first_page,
}
