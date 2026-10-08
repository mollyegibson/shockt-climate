from collections.abc import Mapping

import httpx
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)
from tenacity.wait import wait_base

from shockt import __version__

USER_AGENT = f"shockt-climate/{__version__}"
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 5
RETRY_WAIT: wait_base = wait_exponential_jitter(multiplier=2, max=60)


class SourceRequestError(Exception):
    """A request to a source failed after retries. The message never contains secrets."""


def redact(text: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in RETRYABLE_STATUS


def make_client(timeout_seconds: float) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(timeout_seconds, connect=30.0),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def _get(client: httpx.Client, url: str, params: Mapping[str, str]) -> httpx.Response:
    for attempt in Retrying(
        retry=retry_if_exception(_is_retryable),
        wait=RETRY_WAIT,
        stop=stop_after_attempt(MAX_ATTEMPTS),
        reraise=True,
    ):
        with attempt:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response
    raise AssertionError("unreachable: Retrying either returns or re-raises")


def get(
    client: httpx.Client,
    url: str,
    params: Mapping[str, str],
    secrets: tuple[str, ...] = (),
) -> httpx.Response:
    """GET with retries on transport errors, 429 and 5xx; errors are re-raised without secrets."""
    try:
        return _get(client, url, params)
    except httpx.HTTPError as exc:
        raise SourceRequestError(redact(f"{type(exc).__name__}: {exc}", secrets)) from None
