"""서버 설정 — 환경변수 기반. LLM/수집 시크릿은 여기 외에 존재하지 않는다."""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    db_path: str = "realmatjip.db"          # SQLite 파일 경로
    auth_token: str | None = None           # None이면 인증 비활성(로컬/Tailscale 전제)

    def database_url(self) -> str:
        return "sqlite:///" + self.db_path


def get_settings() -> Settings:
    return Settings(
        db_path=os.environ.get("REALMATJIP_DB", "realmatjip.db"),
        auth_token=os.environ.get("REALMATJIP_AUTH_TOKEN") or None,
    )
