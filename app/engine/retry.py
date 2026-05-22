import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

http_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception_type(
        (
            httpx.TransportError,
            httpx.TimeoutException,
            ConnectionError,
            OSError,
        )
    ),
    reraise=True,
)
