"""Exponential backoff retry wrapper for LLM chat() calls.

Usage:
    from app.llm.retry import llm_chat_with_retry

    # Retry on failure with backoff
    result = await llm_chat_with_retry(llm, messages, temperature=0.1)

The wrapper calls llm.chat() with raise_on_error=True so exceptions
propagate up and can be retried, rather than returning the fallback
"[LLM unavailable]" on the first attempt.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


async def llm_chat_with_retry(
    llm,
    messages: list[dict],
    max_retries: int = 5,
    base_delay: float = 1.0,
    **kwargs,
) -> str:
    """Call llm.chat() with exponential backoff.

    Args:
        llm: An LLMClient instance (must support raise_on_error kwarg).
        messages: The chat messages list.
        max_retries: Maximum number of retry attempts (default 5).
        base_delay: Initial delay in seconds (doubles each retry).
        **kwargs: Additional keyword arguments forwarded to llm.chat().

    Returns:
        The LLM response string.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exception: Exception | None = None
    kwargs["raise_on_error"] = True

    for attempt in range(max_retries):
        try:
            start = time.monotonic()
            result = await llm.chat(messages, **kwargs)
            elapsed = time.monotonic() - start
            logger.debug("LLM chat succeeded (attempt %d/%d) in %.2fs", attempt + 1, max_retries, elapsed)
            return result
        except Exception as e:
            last_exception = e
            elapsed = time.monotonic() - kwargs.pop("_start", start) if "_start" in kwargs else 0
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "LLM chat failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1,
                    max_retries,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "LLM chat failed after %d attempts: %s",
                    max_retries,
                    last_exception,
                )

    raise last_exception  # type: ignore[misc]
