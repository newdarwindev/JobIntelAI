class FetchNotImplemented(RuntimeError):
    pass


class HttpAcquirer:
    """Future httpx adapter; disabled until SSRF, redirects and size bounds are tested."""

    def fetch(self, url: str) -> str:
        raise FetchNotImplemented(
            "HTTP acquisition is not implemented; use the manual snapshot endpoint"
        )
