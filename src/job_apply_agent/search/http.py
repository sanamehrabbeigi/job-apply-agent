"""Polite async HTTP for job sources: timeouts, retries with backoff, and a delay per host.

Uses urllib from the standard library in a worker thread, like the rest of the project.
``fetch`` is injectable so tests never touch the network.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


class HttpError(RuntimeError):
    def __init__(self, status: int | None, url: str, message: str = ""):
        self.status = status
        self.url = url
        super().__init__(message or f"{url} returned HTTP {status}")


class RateLimited(HttpError):
    """The site asked us to slow down (HTTP 429, or LinkedIn's 999)."""


@dataclass
class Response:
    status: int
    text: str

    def json(self) -> Any:
        return json.loads(self.text)


FetchFn = Callable[[str, str, dict[str, str], bytes | None, float], Response]


def urllib_fetch(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float) -> Response:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return Response(response.status, response.read().decode(charset, errors="replace"))
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - the body is only informative
            text = ""
        return Response(exc.code, text)


class Http:
    def __init__(
        self,
        fetch: FetchFn = urllib_fetch,
        *,
        retries: int = 2,
        backoff: float = 1.0,
        timeout: float = 25.0,
        host_delays: dict[str, tuple[float, float]] | None = None,
        default_delay: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetch = fetch
        self.retries = retries
        self.backoff = backoff
        self.timeout = timeout
        self._delays = host_delays or {}
        self._default_delay = default_delay
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def _wait_turn(self, host: str) -> None:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            low, high = self._delays.get(host, (self._default_delay, self._default_delay))
            last = self._last.get(host)
            if last is not None:
                wait = last + random.uniform(low, high) - self._clock()
                if wait > 0:
                    await self._sleep(wait)
            self._last[host] = self._clock()

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: Any = None,
        retry_429: bool = True,
        retries: int | None = None,
    ) -> Response:
        """``retries=0`` for quota-counted APIs: every attempt would be billed, so never retry them."""
        attempts = self.retries if retries is None else retries
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        all_headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9", **(headers or {})}
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            all_headers.setdefault("Content-Type", "application/json")
            all_headers.setdefault("Accept", "application/json")
        host = urllib.parse.urlsplit(url).hostname or ""
        for attempt in range(attempts + 1):
            await self._wait_turn(host)
            try:
                response = await asyncio.to_thread(self._fetch, method, url, all_headers, body, self.timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt == attempts:
                    raise HttpError(None, url, f"Couldn't reach {url}: {exc}") from exc
                await self._sleep(self.backoff * 2**attempt)
                continue
            if response.status == 999 or (response.status == 429 and (not retry_429 or attempt == attempts)):
                raise RateLimited(response.status, url)
            if response.status == 429 or response.status >= 500:
                if attempt == attempts:
                    raise HttpError(response.status, url)
                await self._sleep(self.backoff * 2**attempt)
                continue
            if response.status >= 400:
                raise HttpError(response.status, url)
            return response
        raise HttpError(None, url)  # unreachable

    async def get_json(self, url: str, *, params=None, headers=None, retry_429: bool = True,
                       retries: int | None = None) -> Any:
        response = await self.request("GET", url, params=params, headers=headers, retry_429=retry_429,
                                      retries=retries)
        return _decode(response, url)

    async def post_json(self, url: str, body: Any, *, headers=None, retry_429: bool = True,
                        retries: int | None = None) -> Any:
        response = await self.request("POST", url, headers=headers, json_body=body, retry_429=retry_429,
                                      retries=retries)
        return _decode(response, url)

    async def get_text(self, url: str, *, params=None, headers=None, retry_429: bool = True,
                       retries: int | None = None) -> str:
        return (await self.request("GET", url, params=params, headers=headers, retry_429=retry_429,
                                   retries=retries)).text


def _decode(response: Response, url: str) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise HttpError(response.status, url, f"{url} did not return valid JSON") from exc
