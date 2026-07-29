"""
Clerk session-token verification, applied as a single Starlette
middleware rather than a per-route Depends so every route in main.py is
covered without touching each handler.

Verifies the RS256 JWT Clerk issues on sign-in against Clerk's public
JWKS (fetched over HTTPS, cached in-process). No secret key is needed to
verify a token — CLERK_SECRET_KEY is unused here, reserved for any future
server-to-server Clerk Backend API calls.
"""

import os

import jwt
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

CLERK_JWKS_URL = os.environ["CLERK_JWKS_URL"]

# PyJWKClient caches keys by kid and refetches the JWKS only on a cache
# miss (e.g. Clerk rotates its signing key), so this is safe to construct
# once at import time rather than re-fetching per request.
_jwks_client = PyJWKClient(CLERK_JWKS_URL)

# Paths that must work with no session — health checks and CORS preflight.
_EXEMPT_PATHS = {"/health"}


def _verify(token: str) -> dict:
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={"require": ["exp", "iat"]},
    )
    return claims


class ClerkAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)

        token = auth_header.removeprefix("Bearer ")
        try:
            claims = _verify(token)
        except jwt.PyJWTError:
            return JSONResponse({"detail": "Invalid or expired session"}, status_code=401)

        request.state.user_id = claims["sub"]
        return await call_next(request)
