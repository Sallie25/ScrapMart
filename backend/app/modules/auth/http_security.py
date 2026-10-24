"""Bound credential-body parsing and prevent caching auth responses."""
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings

if TYPE_CHECKING:
    from app.modules.auth.session_service import SessionCredentials

REFRESH_COOKIE = "__Secure-scrapmart_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def require_origin_csrf(request: Request, settings: Settings) -> None:
    origins = request.headers.getlist("origin")
    if len(origins) != 1 or origins[0] not in settings.auth_allowed_origins:
        raise HTTPException(403, detail={"code": "origin_rejected", "message": "Request origin is not permitted", "fields": []},
                            headers={"Cache-Control": "no-store"})
    if request.headers.getlist("x-scrapmart-csrf") != ["1"]:
        raise HTTPException(403, detail={"code": "csrf_rejected", "message": "Required request header is missing or invalid", "fields": []},
                            headers={"Cache-Control": "no-store"})


def set_refresh_cookie(response: Response, credentials: "SessionCredentials") -> None:
    remaining = max(0, math.floor((credentials.expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(REFRESH_COOKIE, credentials.refresh_token, max_age=remaining,
                        expires=credentials.expires_at, path=REFRESH_COOKIE_PATH,
                        secure=True, httponly=True, samesite="lax")


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH,
                           secure=True, httponly=True, samesite="lax")


class AuthRequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/auth/"):
            await self.app(scope, receive, send)
            return

        response_started = False
        operations = {"/api/v1/auth/buyer/signup": "Registration", "/api/v1/auth/buyer/login": "Login",
                      "/api/v1/auth/refresh": "Refresh", "/api/v1/auth/logout": "Logout",
                      "/api/v1/auth/me": "Profile request", "/api/v1/auth/logout-all": "Logout"}
        operation = operations.get(scope["path"], "Registration")

        async def no_store(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def dispatch(source: Receive) -> None:
            try:
                await self.app(scope, source, no_store)
            except Exception:
                if response_started:
                    raise
                # Never include exception text, request bodies, headers or locals.
                response = JSONResponse(status_code=500, content={"detail": {
                    "code": "internal_error", "message": f"{operation} could not be completed", "fields": [],
                }})
                await response(scope, source, no_store)

        if scope["path"] in operations and scope["method"] == "POST":
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > 16384:
                    response = JSONResponse(status_code=413, content={"detail": {
                        "code": "request_too_large", "message": f"{operation} request is too large", "fields": [],
                    }})
                    await response(scope, receive, no_store)
                    return
                if not message.get("more_body", False):
                    break
            delivered = False

            async def buffered_receive() -> Message:
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await dispatch(buffered_receive)
        else:
            await dispatch(receive)


class AuthNoStoreMiddleware:
    """Outermost layer, also covering CORS preflights and generated errors."""
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/auth/"):
            await self.app(scope, receive, send)
            return

        async def no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        await self.app(scope, receive, no_store)
