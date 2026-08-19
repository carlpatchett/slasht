from time import sleep


class TransientError(Exception):
    """A failure that may resolve if retried."""


def call_with_retries(operation, attempts=5, base_delay=0.5):
    """Run operation, retrying transient failures with backoff."""
    for attempt in range(attempts):
        try:
            return operation()
        except TransientError:
            if attempt == attempts - 1:
                raise
            delay = base_delay * (2**attempt)
            sleep(delay)
    return None
