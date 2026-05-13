"""Exponential-backoff retry decorator for transient GAM API errors."""

from __future__ import annotations

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from gampan.core.errors import GamApiRetryableError

retry_transient = retry(
    retry=retry_if_exception_type(GamApiRetryableError),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    stop=stop_after_attempt(4),
    reraise=True,
)
