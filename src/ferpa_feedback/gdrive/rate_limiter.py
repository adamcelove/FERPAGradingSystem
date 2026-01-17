"""Rate limiter for Google Drive API calls.

This module provides a thread-safe rate limiter using a fixed window algorithm
to stay within Google's API quota limits.

Example:
    from ferpa_feedback.gdrive.rate_limiter import RateLimiter

    # Create limiter: 900 requests per 100 seconds
    limiter = RateLimiter(max_requests=900, window_seconds=100)

    # Before each API call
    limiter.acquire()
    service.files().list(...).execute()
"""

import threading
import time
from typing import Optional


class RateLimiter:
    """Thread-safe rate limiter using fixed window algorithm.

    This limiter allows a maximum number of requests within a time window.
    If the limit is exceeded, acquire() will block until the window resets.

    The fixed window algorithm divides time into fixed windows (e.g., 100 seconds)
    and counts requests within each window. When the limit is reached, requests
    are blocked until the next window begins.

    Default configuration: 900 requests per 100 seconds, which is safely under
    Google Drive API's limit of 1000 requests per 100 seconds.

    Attributes:
        max_requests: Maximum number of requests allowed per window.
        window_seconds: Length of each time window in seconds.

    Example:
        limiter = RateLimiter()  # Uses default 900/100sec

        for file in files:
            limiter.acquire()  # Blocks if rate exceeded
            result = service.files().get(fileId=file.id).execute()
    """

    # Default values based on Google Drive API quota
    DEFAULT_MAX_REQUESTS = 900  # Under Google's 1000 limit
    DEFAULT_WINDOW_SECONDS = 100  # Google's quota window

    def __init__(
        self,
        max_requests: Optional[int] = None,
        window_seconds: Optional[float] = None,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            max_requests: Maximum requests per window (default: 900).
            window_seconds: Window duration in seconds (default: 100).
        """
        self._max_requests = max_requests or self.DEFAULT_MAX_REQUESTS
        self._window_seconds = window_seconds or self.DEFAULT_WINDOW_SECONDS

        # Current window state
        self._window_start: float = time.time()
        self._request_count: int = 0

        # Thread safety
        self._lock = threading.Lock()

    @property
    def max_requests(self) -> int:
        """Maximum requests allowed per window."""
        return self._max_requests

    @property
    def window_seconds(self) -> float:
        """Window duration in seconds."""
        return self._window_seconds

    def acquire(self) -> None:
        """Acquire permission to make an API call.

        This method blocks if the rate limit has been exceeded for the current
        window. It will wait until the next window begins before returning.

        Thread-safe: multiple threads can call acquire() concurrently.

        Example:
            limiter.acquire()  # May block if rate exceeded
            result = api.call()  # Safe to make the call
        """
        with self._lock:
            current_time = time.time()

            # Check if we've moved to a new window
            elapsed = current_time - self._window_start
            if elapsed >= self._window_seconds:
                # Reset to new window
                self._window_start = current_time
                self._request_count = 0

            # Check if we're at the limit
            if self._request_count >= self._max_requests:
                # Calculate time until next window
                time_remaining = self._window_seconds - elapsed
                if time_remaining > 0:
                    # Release lock while sleeping to allow other operations
                    self._lock.release()
                    try:
                        time.sleep(time_remaining)
                    finally:
                        self._lock.acquire()

                    # Reset window after sleep
                    self._window_start = time.time()
                    self._request_count = 0

            # Increment count and allow request
            self._request_count += 1

    def get_status(self) -> dict[str, object]:
        """Get current rate limiter status.

        Returns:
            Dictionary with current window state:
            - request_count: Requests made in current window
            - max_requests: Maximum allowed per window
            - window_seconds: Window duration
            - seconds_remaining: Time until window resets
            - requests_remaining: Requests available in current window
        """
        with self._lock:
            current_time = time.time()
            elapsed = current_time - self._window_start

            # Check if we've moved to a new window
            if elapsed >= self._window_seconds:
                seconds_remaining = self._window_seconds
                requests_remaining = self._max_requests
                current_count = 0
            else:
                seconds_remaining = self._window_seconds - elapsed
                current_count = self._request_count
                requests_remaining = max(0, self._max_requests - current_count)

            return {
                "request_count": current_count,
                "max_requests": self._max_requests,
                "window_seconds": self._window_seconds,
                "seconds_remaining": round(seconds_remaining, 2),
                "requests_remaining": requests_remaining,
            }

    def reset(self) -> None:
        """Reset the rate limiter to start a new window.

        This can be useful for testing or when starting a new batch operation.
        """
        with self._lock:
            self._window_start = time.time()
            self._request_count = 0
