"""HTTP utilitaires — User-Agent, retries, throttle."""

from __future__ import annotations

import random
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_UA = (
    "Mozilla/5.0 (compatible; AccordDataStudio/1.0; "
    "+https://local.dev/hotels; research-for-partner-app)"
)


def fetch(
    url: str,
    *,
    timeout: float = 25.0,
    retries: int = 2,
    pause_s: float = 0.35,
    binary: bool = False,
) -> tuple[int, Any]:
    """
    GET url → (status_code, body).

    body = bytes si binary else str (utf-8 replace).
    status 404/410 renvoyés sans exception.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        if pause_s > 0:
            time.sleep(pause_s + random.uniform(0, 0.15))
        req = Request(
            url,
            headers={
                "User-Agent": DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,image/*,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
            },
        )
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                code = getattr(resp, "status", 200) or 200
                if binary:
                    return int(code), data
                return int(code), data.decode("utf-8", errors="replace")
        except HTTPError as exc:
            if exc.code in {404, 410, 403}:
                body = exc.read() if hasattr(exc, "read") else b""
                if binary:
                    return int(exc.code), body
                return int(exc.code), body.decode("utf-8", errors="replace")
            last_exc = exc
        except (URLError, TimeoutError, OSError) as exc:
            last_exc = exc
        time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"fetch failed {url}: {last_exc}")
