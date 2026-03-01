"""HTTP tools module."""

from __future__ import annotations

from fastapi import FastAPI

from anyide.models import HttpRequestRequest, HttpRequestResponse
from anyide.modules.base import ToolModule
from anyide.modules.http.tools import HttpTools


_REQUEST_DESC = """Make an HTTP request to an external URL.

Supported methods: GET, POST, PUT, PATCH, DELETE, HEAD

Use {{secret:KEY}} syntax in headers or body values to inject secrets
without exposing them in the request parameters or audit logs.

Security protections:
- Private/reserved IP addresses are blocked (SSRF protection)
- Cloud metadata endpoints (169.254.169.254, etc.) are blocked
- Domain allowlist/blocklist enforced from configuration
- Response body is truncated at the configured size limit

Required: url
Optional: method (default: GET), headers, body, json_body, timeout (max 120s), follow_redirects"""


class HttpModule(ToolModule):
    MODULE_NAME = "http"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "HTTP Tools"

    @property
    def description(self) -> str:
        return "HTTP client with SSRF protection for AnyIDE"

    def __init__(self, context):
        super().__init__(context)
        self.http_tools = HttpTools(context.config.http)
        self.context.register_dispatch_target("http", self.http_tools)

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/http/request",
            operation_id="http_request",
            summary="Make HTTP Request",
            description=_REQUEST_DESC,
            response_model=HttpRequestResponse,
            tags=["http"],
        )
        async def http_request_root(request: HttpRequestRequest) -> HttpRequestResponse:
            resolved = self.context.resolve_request_secrets(request)
            return await self.context.execute_tool(
                "http",
                "request",
                request.model_dump(),
                lambda: self.http_tools.request(resolved),
            )

        @sub_app.post(
            "/request",
            operation_id="http_request",
            summary="Make HTTP Request",
            description=_REQUEST_DESC,
            response_model=HttpRequestResponse,
            tags=["http"],
        )
        async def http_request_sub(request: HttpRequestRequest) -> HttpRequestResponse:
            resolved = self.context.resolve_request_secrets(request)
            return await self.context.execute_tool(
                "http",
                "request",
                request.model_dump(),
                lambda: self.http_tools.request(resolved),
            )
