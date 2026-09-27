"""Time bucketing for cache/ETag stability.

Every timestamp the pipeline embeds in responses is anchored to a 5-minute
bucket. Without this, `observed_at = now` changes every request, the SDUI
ETag changes every request, and mobile 304 Not Modified would never hit —
silently wasting battery on pull-to-refresh. 5 minutes matches the
`max-age=300` cache policy; the demo never looks stale either.
"""

from __future__ import annotations

from datetime import UTC, datetime

BUCKET_SECONDS = 300


def bucketed_now() -> datetime:
    """UTC now floored to the current 5-minute bucket."""
    now = datetime.now(UTC)
    epoch = int(now.timestamp())
    bucket = epoch - (epoch % BUCKET_SECONDS)
    return datetime.fromtimestamp(bucket, tz=UTC)
