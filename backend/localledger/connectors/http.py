"""Outbound network policy for bank connectors.

The backend may talk to a provider only over HTTPS and only to hosts the connector
declared up front. A URL that comes back from a provider (for example a SimpleFIN access
URL) is checked against the same list before it is ever requested.
"""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from localledger.connectors.base import ConnectorError


class OutboundPolicy:
    def __init__(self, allowed_hosts: tuple[str, ...] = (),
                 allowed_suffixes: tuple[str, ...] = ()) -> None:
        self._hosts = {h.lower() for h in allowed_hosts}
        self._suffixes = tuple(s.lower() for s in allowed_suffixes)

    def check(self, url: str) -> str:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https":
            raise ConnectorError("insecure_url", "Refusing a non-HTTPS provider address.")
        allowed = host in self._hosts or any(
            host == s or host.endswith("." + s) for s in self._suffixes)
        if not allowed:
            raise ConnectorError("host_not_allowed",
                                 "The provider returned an address outside its approved hosts.")
        return url


def new_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    # trust_env=False: ignore proxy variables so credentials cannot be routed elsewhere.
    # Redirects are not followed, so an approved host cannot bounce a request off-list.
    return httpx.Client(timeout=30.0, transport=transport, trust_env=False,
                        follow_redirects=False)


def request(client: httpx.Client, method: str, url: str, **kwargs: object) -> httpx.Response:
    try:
        return client.request(method, url, **kwargs)  # type: ignore[arg-type]
    except httpx.TimeoutException as exc:
        raise ConnectorError("timeout", "The provider did not respond in time.") from exc
    except httpx.HTTPError as exc:
        raise ConnectorError("unreachable",
                             "Could not reach the provider. Check your connection.") from exc
