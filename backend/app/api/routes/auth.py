"""Proxy-assisted logout handoff for phase-1 SSO."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse

from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
settings = get_settings()


@router.get("/logout-url")
def get_logout_url(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing upstream identity token")

    id_token = authorization.removeprefix("Bearer ").strip()
    if not id_token:
        raise HTTPException(status_code=401, detail="Missing upstream identity token")

    logout_params = {
        "client_id": settings.planner_oauth_client_id,
        "post_logout_redirect_uri": f"{settings.planner_public_base_url}/oauth2/sign_in",
        "id_token_hint": id_token,
    }
    logout_url = f"{settings.planner_auth_logout_url}?{urlencode(logout_params)}"

    return {"proxy_sign_out_url": f"/oauth2/sign_out?rd={quote(logout_url, safe='')}"}


@router.get("/logout-redirect", include_in_schema=False)
def logout_redirect(authorization: str | None = Header(default=None)):
    payload = get_logout_url(authorization)
    return RedirectResponse(url=payload["proxy_sign_out_url"], status_code=302)
