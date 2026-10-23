"""Bound credential-body parsing and prevent caching auth responses."""
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class AuthRequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/auth/"):
            await self.app(scope, receive, send)
            return

        response_started = False
        operation = "Login" if scope["path"] == "/api/v1/auth/buyer/login" else "Registration"

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

        if scope["path"] in {"/api/v1/auth/buyer/signup", "/api/v1/auth/buyer/login"} and scope["method"] == "POST":
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
