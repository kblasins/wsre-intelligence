"""Circuit breakers — one per data source, backed by Redis when available.

Shared Redis state means the breaker trips consistently across all
processes (API server + scheduler workers). A breaker in OPEN state
blocks calls from both the nightly scheduler and any manual re-runs.

Falls back to in-memory state when Redis is unavailable (e.g. during tests).

Tuning:
  - fail_max=5: a transient blip (1-2 failures) doesn't trip; sustained
    outages do
  - reset_timeout=300: 5-minute cool-down before the breaker goes HALF-OPEN
    and tries one probe request
  - exclude=[ValueError]: ValueError means the page was fetched fine but
    parsing failed — that's a schema-drift issue, not a connectivity issue,
    so it shouldn't trip the network breaker
"""

from __future__ import annotations

import pybreaker
import redis
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis | None:
    global _redis
    if _redis is not None:
        return _redis
    try:
        r = redis.from_url(str(settings.redis_url), decode_responses=True, socket_connect_timeout=2)
        r.ping()
        _redis = r
        return _redis
    except Exception:
        log.warning("circuit_breaker_redis_unavailable", hint="using in-memory state")
        return None


def _make_breaker(
    name: str, fail_max: int = 5, reset_timeout: int = 300
) -> pybreaker.CircuitBreaker:
    r = _get_redis()
    state_storage: pybreaker.CircuitBreakerStorage
    if r is not None:
        state_storage = pybreaker.CircuitRedisStorage(
            pybreaker.STATE_CLOSED,
            r,
            namespace=f"cb:{name}",
        )
    else:
        state_storage = pybreaker.CircuitMemoryStorage(pybreaker.STATE_CLOSED)

    return pybreaker.CircuitBreaker(
        fail_max=fail_max,
        reset_timeout=reset_timeout,
        exclude=[ValueError],  # parsing errors ≠ connectivity errors
        state_storage=state_storage,
        name=name,
        listeners=[_SentryListener()],
    )


class _SentryListener(pybreaker.CircuitBreakerListener):
    """Log state changes; emit Sentry event when DSN is configured."""

    def state_change(
        self,
        cb: pybreaker.CircuitBreaker,
        old_state: pybreaker.CircuitBreakerState,
        new_state: pybreaker.CircuitBreakerState,
    ) -> None:
        log.warning(
            "circuit_breaker_state_change",
            breaker=cb.name,
            old=old_state.name,
            new=new_state.name,
        )
        # Sentry is optional — only active when SENTRY_DSN is set
        try:
            import sentry_sdk

            if sentry_sdk.is_initialized():
                sentry_sdk.capture_message(
                    f"Circuit breaker [{cb.name}]: {old_state.name} → {new_state.name}",
                    level="warning",
                )
        except ImportError:
            pass


# One breaker per source — REGA failure doesn't block Aqar
BREAKERS: dict[str, pybreaker.CircuitBreaker] = {
    "rega": _make_breaker("rega"),
    "tadawul": _make_breaker("tadawul", fail_max=3),  # yfinance is usually reliable
    "aqar": _make_breaker("aqar"),
    "modon": _make_breaker("modon", fail_max=10),  # slow site, high tolerance
    "news": _make_breaker("news"),
    "anthropic": _make_breaker("anthropic", fail_max=5, reset_timeout=60),
    "etimad": _make_breaker("etimad"),
}
