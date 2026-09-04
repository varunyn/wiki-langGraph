"""Optional Langfuse v4 tracing shared by pipeline and LLM entry points."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from wiki_langgraph.config import Settings

logger = logging.getLogger(__name__)


def langfuse_configured(settings: Settings) -> bool:
    """Return whether this process has enough configuration to export traces."""

    return bool(
        settings.langfuse_tracing_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    )


@lru_cache(maxsize=8)
def _langfuse_client(
    public_key: str,
    secret_key: str,
    base_url: str | None,
    environment: str | None,
    release: str | None,
    service_name: str,
):  # noqa: ANN201
    """Create one SDK client per effective Langfuse configuration."""
    os.environ["OTEL_SERVICE_NAME"] = service_name
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            environment=environment,
            release=release,
        )
    except Exception as exc:  # pragma: no cover - depends on optional runtime setup
        logger.warning("Langfuse tracing disabled: could not initialize client: %s", exc)
        return None


def langfuse_client(settings: Settings):  # noqa: ANN201
    """Create or retrieve the Langfuse client without making the SDK mandatory at import time."""
    if not langfuse_configured(settings):
        return None
    assert settings.langfuse_public_key is not None
    assert settings.langfuse_secret_key is not None
    return _langfuse_client(
        settings.langfuse_public_key,
        settings.langfuse_secret_key,
        settings.langfuse_base_url,
        settings.langfuse_tracing_environment,
        settings.langfuse_tracing_release,
        settings.langfuse_service_name,
    )


def langfuse_callback(settings: Settings):  # noqa: ANN201
    """Return a LangChain callback connected to this Settings instance, if enabled."""

    client = langfuse_client(settings)
    if client is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler(public_key=settings.langfuse_public_key)
    except Exception as exc:  # pragma: no cover - depends on optional runtime setup
        logger.warning("Langfuse LangChain tracing disabled: %s", exc)
        return None


def invoke_with_optional_callback(runnable: object, messages: object, settings: Settings) -> object:
    """Invoke a LangChain runnable while remaining compatible with small test doubles."""

    callback = langfuse_callback(settings)
    invoke = getattr(runnable, "invoke")
    if callback is None:
        return invoke(messages)
    try:
        return invoke(messages, config={"callbacks": [callback]})
    except TypeError as exc:
        if "unexpected keyword argument 'config'" not in str(exc):
            raise
        return invoke(messages)


@contextmanager
def trace_operation(
    settings: Settings,
    *,
    name: str,
    input_data: object | None = None,
    root: bool = False,
    observation_type: str = "span",
) -> Iterator[object | None]:
    """Create a v4 root/child observation and safely degrade when tracing is unavailable."""

    client = langfuse_client(settings)
    if client is None:
        yield None
        return

    try:
        from langfuse import propagate_attributes
    except Exception as exc:  # pragma: no cover - depends on optional runtime setup
        logger.warning("Langfuse tracing disabled for %s: %s", name, exc)
        yield None
        return

    try:
        observation_context = client.start_as_current_observation(
            as_type=observation_type,
            name=name,
        )
        span = observation_context.__enter__()
        propagation_context = propagate_attributes(
            trace_name=name if root else None,
            environment=settings.langfuse_tracing_environment,
        )
        propagation_context.__enter__()
    except Exception as exc:  # pragma: no cover - exporter setup failures
        logger.warning("Langfuse tracing operation unavailable for %s: %s", name, exc)
        yield None
        return

    try:
        if input_data is not None:
            span.update(input=input_data)
        try:
            yield span
        except Exception as exc:
            span.update(level="ERROR", status_message=str(exc))
            raise
    finally:
        propagation_context.__exit__(None, None, None)
        observation_context.__exit__(None, None, None)


def finish_trace(span: object | None, *, output: object | None = None) -> None:
    """Attach a bounded operation result to a span when one was created."""

    if span is not None and output is not None:
        try:
            span.update(output=output)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - exporter failure is best effort
            logger.debug("Unable to update Langfuse span output", exc_info=True)


def flush_langfuse(settings: Settings) -> None:
    """Flush pending observations for short-lived CLI processes."""
    client = langfuse_client(settings)
    if client is None:
        return
    try:
        client.flush()
    except Exception:  # pragma: no cover - exporter failure is best effort
        logger.warning("Unable to flush Langfuse observations", exc_info=True)
