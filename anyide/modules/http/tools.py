"""HTTP client tool with SSRF protection and domain filtering."""

import ipaddress
import re
import time
from typing import Optional
from urllib.parse import urlparse

import httpx

from anyide.config import HttpConfig
from anyide.models import HttpRequestRequest, HttpRequestResponse
from anyide.logging_config import get_logger

logger = get_logger(__name__)

# Private / reserved IP networks (RFC 1918, loopback, link-local, etc.)
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("100.64.0.0/10"),   # Shared address space
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / metadata
    ipaddress.ip_network("192.0.0.0/24"),    # IANA reserved
    ipaddress.ip_network("192.0.2.0/24"),    # TEST-NET-1
    ipaddress.ip_network("198.18.0.0/15"),   # Benchmark testing
    ipaddress.ip_network("198.51.100.0/24"), # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("240.0.0.0/4"),     # Reserved
    ipaddress.ip_network("255.255.255.255/32"),
]

# Cloud metadata endpoints (block even if IP checking is disabled)
_METADATA_HOSTNAMES = {
    "169.254.169.254",         # AWS / GCP / Azure IMDS
    "metadata.google.internal",  # GCP metadata
    "169.254.170.2",           # AWS ECS task metadata
}

# Allowed HTTP methods
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


class SSRFError(ValueError):
    """Raised when a request is blocked due to SSRF protection."""
    pass


class DomainBlockedError(ValueError):
    """Raised when a request is blocked by domain policy."""
    pass


def _is_private_ip(host: str) -> bool:
    """Check whether *host* resolves to a private / loopback / reserved address.

    NOTE: This is a best-effort check on the literal host string.  We do NOT
    perform an actual DNS lookup here because that would be slow and could
    suffer from TOCTOU issues.  If *host* is a hostname (not a raw IP) and
    looks like a public domain, we allow it through — the network layer will
    refuse unroutable addresses anyway.
    """
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        # Not a raw IP address — hostname, we can't check without DNS lookup
        return False


def _check_ssrf(url: str, http_config: HttpConfig) -> None:
    """Validate a URL against SSRF protection rules.

    Raises:
        SSRFError: If the request should be blocked
        DomainBlockedError: If the domain is on the blocklist
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    scheme = parsed.scheme.lower()

    if scheme not in ("http", "https"):
        raise SSRFError(f"Unsupported scheme '{scheme}'. Only http and https are allowed.")

    # Block metadata endpoints by hostname
    if http_config.block_metadata_endpoints and host in _METADATA_HOSTNAMES:
        raise SSRFError(
            f"Requests to '{host}' are blocked. Cloud metadata endpoints are not allowed."
        )

    # Block private IPs
    if http_config.block_private_ips and _is_private_ip(host):
        raise SSRFError(
            f"Requests to private/reserved IP address '{host}' are blocked (SSRF protection)."
        )

    # Domain allowlist (if configured, only listed domains are permitted)
    if http_config.allow_domains:
        allowed = False
        for pattern in http_config.allow_domains:
            if _domain_matches(host, pattern):
                allowed = True
                break
        if not allowed:
            raise DomainBlockedError(
                f"Domain '{host}' is not in the allowlist. "
                f"Allowed domains: {', '.join(http_config.allow_domains)}"
            )

    # Domain blocklist
    for pattern in http_config.block_domains:
        if _domain_matches(host, pattern):
            raise DomainBlockedError(
                f"Domain '{host}' is blocked by policy."
            )


def _domain_matches(host: str, pattern: str) -> bool:
    """Check whether *host* matches a domain *pattern*.

    Supports:
    - Exact match: "example.com"
    - Wildcard subdomain: "*.example.com"
    """
    pattern = pattern.lower().lstrip("*.")
    host = host.lower()
    return host == pattern or host.endswith("." + pattern)


class HttpTools:
    """HTTP client tool implementations."""

    def __init__(self, http_config: HttpConfig):
        """Initialize HTTP tools.

        Args:
            http_config: HTTP configuration with domain allow/block lists and SSRF settings
        """
        self.http_config = http_config

    async def request(self, req: HttpRequestRequest) -> HttpRequestResponse:
        """Make an HTTP request.

        Args:
            req: HTTP request parameters

        Returns:
            HTTP response

        Raises:
            SSRFError: If the request targets a private/reserved address
            DomainBlockedError: If the domain is blocked by policy
            ValueError: If the method is not allowed or params are invalid
        """
        method = req.method.upper()
        if method not in _ALLOWED_METHODS:
            raise ValueError(
                f"HTTP method '{method}' is not allowed. "
                f"Allowed methods: {', '.join(sorted(_ALLOWED_METHODS))}"
            )

        # Enforce timeout limits
        timeout = min(req.timeout, self.http_config.max_timeout)

        # SSRF + domain check
        _check_ssrf(req.url, self.http_config)

        # Validate mutually exclusive body options
        if req.body is not None and req.json_body is not None:
            raise ValueError("Provide either 'body' or 'json_body', not both.")

        headers = dict(req.headers or {})

        logger.info(
            "http_request_start",
            method=method,
            url=req.url,
            timeout=timeout,
        )

        start = time.time()
        try:
            async with httpx.AsyncClient(
                follow_redirects=req.follow_redirects,
                timeout=timeout,
            ) as client:
                if req.json_body is not None:
                    response = await client.request(
                        method, req.url, headers=headers, json=req.json_body
                    )
                elif req.body is not None:
                    response = await client.request(
                        method, req.url, headers=headers, content=req.body.encode()
                    )
                else:
                    response = await client.request(method, req.url, headers=headers)

            duration_ms = int((time.time() - start) * 1000)

            # Enforce max response size
            max_bytes = self.http_config.max_response_size_kb * 1024
            body = response.text
            if len(response.content) > max_bytes:
                body = (
                    response.text[:max_bytes]
                    + f"\n\n[TRUNCATED — response exceeded {self.http_config.max_response_size_kb} KB limit]"
                )

            resp_headers = dict(response.headers)
            content_type = response.headers.get("content-type")

            logger.info(
                "http_request_complete",
                method=method,
                url=str(response.url),
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

            return HttpRequestResponse(
                status_code=response.status_code,
                headers=resp_headers,
                body=body,
                url=str(response.url),
                duration_ms=duration_ms,
                content_type=content_type,
            )

        except (SSRFError, DomainBlockedError, ValueError):
            raise
        except httpx.TimeoutException as exc:
            duration_ms = int((time.time() - start) * 1000)
            raise TimeoutError(
                f"HTTP request timed out after {timeout}s: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            duration_ms = int((time.time() - start) * 1000)
            raise ConnectionError(
                f"HTTP request failed: {exc}"
            ) from exc
