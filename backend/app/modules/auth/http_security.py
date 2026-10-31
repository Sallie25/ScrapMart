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


def marketplace_path(path):
    return any(path == prefix or path.startswith(prefix + '/') for prefix in
               ('/api/v1/vendor/listings', '/api/v1/listings', '/api/v1/categories'))


class AuthRequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not (scope["path"].startswith("/api/v1/auth/") or marketplace_path(scope["path"])):
            await self.app(scope, receive, send)
            return

        marketplace = marketplace_path(scope["path"])
        response_started = False
        operations = {"/api/v1/auth/vendor/identity-document": "Document submission",
                      "/api/v1/auth/phone/send-code": "Phone verification", "/api/v1/auth/phone/verify-code": "Phone verification", "/api/v1/auth/vendor/onboarding": "Onboarding", "/api/v1/auth/vendor/logout-all": "Logout", "/api/v1/auth/vendor/me": "Profile request",
                      "/api/v1/auth/capabilities": "Account request", "/api/v1/auth/vendor/login": "Login", "/api/v1/auth/vendor/signup": "Registration",
                      "/api/v1/auth/vendor/enroll": "Enrollment", "/api/v1/auth/buyer/signup": "Registration", "/api/v1/auth/buyer/login": "Login",
                      "/api/v1/auth/refresh": "Refresh", "/api/v1/auth/logout": "Logout",
                      "/api/v1/auth/me": "Profile request", "/api/v1/auth/logout-all": "Logout"}
        review_path = scope["path"] == "/api/v1/auth/verification/cases" or scope["path"].startswith("/api/v1/auth/verification/cases/")
        submission_path = scope["path"] == "/api/v1/auth/vendor/verification/submit"
        operation = "Listing request" if marketplace else "Verification review" if review_path or submission_path else operations.get(scope["path"], "Registration")

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

        if (marketplace or scope["path"] in operations or review_path or submission_path) and scope["method"] in {"POST", "PATCH", "DELETE"}:
            # Bound uploaded bytes before parsing or copying them into services.
            limit = 3 * 1024 * 1024 if scope["path"] == "/api/v1/auth/vendor/identity-document" or (marketplace and scope["path"].endswith("/photos") and scope["method"] == "POST") else 16384
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > limit:
                    response = JSONResponse(status_code=413, content={"detail": {
                        "code": "request_too_large", "message": f"{operation} request is too large", "fields": [],
                    }})
                    await response(scope, receive, no_store)
                    return
                body.extend(chunk)
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
        if scope["type"] != "http" or not (scope["path"].startswith("/api/v1/auth/") or marketplace_path(scope["path"])):
            await self.app(scope, receive, send)
            return

        async def no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"]
                message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        await self.app(scope, receive, no_store)
