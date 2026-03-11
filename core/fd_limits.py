from __future__ import annotations

"""File-descriptor utilities (limits + lightweight runtime metrics)."""

import logging
import os
from pathlib import Path

logger = logging.getLogger("animaworks.fd")

try:
    import resource
except Exception:  # pragma: no cover - platform dependent
    resource = None  # type: ignore[assignment]


def _env_int(name: str, default: int) -> int:
    """Read int env var with safe fallback."""
    # Keep parsing lenient so startup never fails due to malformed env vars.
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r (expected int), using %d", name, raw, default)
        return default


def _normalize_limit(value: int | None) -> int | None:
    """Normalize RLIMIT values to plain ints/None."""
    # Treat RLIMIT_INFINITY and negative sentinel values as "unlimited / unknown".
    if value is None:
        return None
    if resource is not None and value == resource.RLIM_INFINITY:
        return None
    if value < 0:
        return None
    return int(value)


def get_nofile_limits() -> tuple[int | None, int | None]:
    """Return (soft, hard) NOFILE limits; None where unavailable/unlimited."""
    if resource is None:
        return (None, None)
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except Exception:
        return (None, None)
    return (_normalize_limit(soft), _normalize_limit(hard))


def raise_nofile_soft_limit(*, min_soft: int | None = None) -> tuple[int | None, int | None, int | None]:
    """Raise soft RLIMIT_NOFILE up to *min_soft* when possible.

    Returns: (old_soft, new_soft, hard)
    """
    if resource is None:
        return (None, None, None)

    target = min_soft if min_soft is not None else _env_int("ANIMAWORKS_NOFILE_SOFT", 8192)

    try:
        raw_soft, raw_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except Exception:
        return (None, None, None)

    old_soft = _normalize_limit(raw_soft)
    hard = _normalize_limit(raw_hard)

    # Unlimited soft (None) means no bump needed.
    if old_soft is None:
        # Already unlimited; no cap exists to raise.
        return (None, None, hard)

    desired_soft = max(old_soft, max(64, target))
    if hard is not None:
        desired_soft = min(desired_soft, hard)

    if desired_soft <= old_soft:
        return (old_soft, old_soft, hard)

    try:
        # Keep hard limit unchanged.
        resource.setrlimit(resource.RLIMIT_NOFILE, (desired_soft, raw_hard))
    except Exception as exc:
        logger.warning(
            "Failed to raise RLIMIT_NOFILE soft limit from %s to %s: %s",
            old_soft,
            desired_soft,
            exc,
        )
        return (old_soft, old_soft, hard)

    return (old_soft, desired_soft, hard)


def count_open_fds() -> int | None:
    """Return current process open FD count (best effort)."""
    # Use platform-specific proc handles when available; some systems expose /proc/self/fd only.
    for candidate in (Path("/proc/self/fd"), Path("/dev/fd")):
        try:
            if not candidate.exists():
                continue
            # Only numeric entries correspond to file descriptors.
            return sum(1 for name in os.listdir(candidate) if name.isdigit())
        except Exception:
            continue
    return None


def fd_usage_ratio(open_fds: int | None, soft_limit: int | None) -> float | None:
    """Return open_fds / soft_limit if both are known."""
    if open_fds is None or soft_limit is None or soft_limit <= 0:
        return None
    return open_fds / float(soft_limit)


def fd_headroom(open_fds: int | None, soft_limit: int | None) -> int | None:
    """Return remaining file descriptors until soft limit."""
    if open_fds is None or soft_limit is None:
        return None
    return soft_limit - open_fds
