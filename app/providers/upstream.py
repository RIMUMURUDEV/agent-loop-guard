from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import urljoin, urlparse

import httpx

from app.core.security import filtered_upstream_headers
from app.providers.base import ProviderResult, ProviderStream


def validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Upstream base URL must be an absolute http(s) URL.")
    return base_url.rstrip("/") + "/"


def _target(base_url: str, endpoint: str) -> str:
    return urljoin(validate_base_url(base_url), endpoint.lstrip("/"))


def _response_headers(headers: httpx.Headers) -> dict[str, str]:
    hop_by_hop = {
        "connection",
        "content-length",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
    return {key: value for key, value in headers.items() if key.lower() not in hop_by_hop}


class UpstreamProvider:
    def __init__(self, *, base_url: str, api_key: str | None, protocol: str):
        self.base_url = validate_base_url(base_url)
        self.api_key = api_key
        self.protocol = protocol

    def _headers(self, incoming: dict[str, str]) -> dict[str, str]:
        headers = filtered_upstream_headers(incoming)
        if self.api_key:
            if self.protocol == "anthropic":
                headers["x-api-key"] = self.api_key
                headers.setdefault("anthropic-version", "2023-06-01")
            else:
                headers["authorization"] = f"Bearer {self.api_key}"
        return headers

    async def request(self, endpoint: str, raw_body: bytes, incoming_headers: dict[str, str]) -> ProviderResult:
        async with httpx.AsyncClient(timeout=None) as client:
            response = await client.request(
                "POST" if raw_body else "GET",
                _target(self.base_url, endpoint),
                content=raw_body if raw_body else None,
                headers=self._headers(incoming_headers),
            )
        json_body = None
        try:
            json_body = response.json()
        except ValueError:
            pass
        return ProviderResult(
            response.status_code,
            _response_headers(response.headers),
            response.content,
            json_body,
            response.headers.get("content-type"),
        )

    async def stream(
        self, endpoint: str, raw_body: bytes, incoming_headers: dict[str, str]
    ) -> ProviderStream:
        client = httpx.AsyncClient(timeout=None)
        request = client.build_request(
            "POST",
            _target(self.base_url, endpoint),
            content=raw_body,
            headers=self._headers(incoming_headers),
        )
        response = await client.send(request, stream=True)

        async def iterator() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return ProviderStream(
            response.status_code,
            _response_headers(response.headers),
            iterator(),
            response.headers.get("content-type") or "text/event-stream",
        )

