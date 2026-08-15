"""단일 bearer token 인증 (개인용). 토큰 미설정 시 인증 비활성 — Tailscale/LAN 전제."""
from fastapi import HTTPException, Request


def require_auth(request: Request) -> None:
    token = request.app.state.settings.auth_token
    if not token:
        return
    provided = request.headers.get("Authorization", "")
    if provided != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")
