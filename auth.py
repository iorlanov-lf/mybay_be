import hashlib
import hmac
import os
import time

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret")
API_BYPASS_KEY = os.getenv("API_BYPASS_KEY", "")
TOKEN_TTL_SECONDS = 3600

router = APIRouter()


class TurnstileVerifyRequest(BaseModel):
    token: str


class TurnstileVerifyResponse(BaseModel):
    session_token: str


def _create_session_token() -> str:
    exp = int(time.time()) + TOKEN_TTL_SECONDS
    payload = str(exp)
    sig = hmac.new(JWT_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def _verify_session_token(token: str) -> bool:
    try:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        exp_str, sig = parts
        exp = int(exp_str)
        if time.time() > exp:
            return False
        expected_sig = hmac.new(JWT_SECRET_KEY.encode(), exp_str.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except Exception:
        return False


async def verify_session(request: Request) -> None:
    if not TURNSTILE_SECRET_KEY:
        return

    if API_BYPASS_KEY:
        api_key = request.headers.get("X-Api-Key", "")
        if hmac.compare_digest(api_key, API_BYPASS_KEY):
            return

    session_token = request.headers.get("X-Session-Token", "")
    if not session_token or not _verify_session_token(session_token):
        raise HTTPException(status_code=401, detail="Invalid or missing session token")


@router.post("/auth/verify", response_model=TurnstileVerifyResponse)
async def verify_turnstile(body: TurnstileVerifyRequest) -> TurnstileVerifyResponse:
    if not TURNSTILE_SECRET_KEY:
        return TurnstileVerifyResponse(session_token=_create_session_token())

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": TURNSTILE_SECRET_KEY, "response": body.token},
        )
        result = resp.json()

    if not result.get("success"):
        raise HTTPException(status_code=403, detail="Turnstile verification failed")

    return TurnstileVerifyResponse(session_token=_create_session_token())
