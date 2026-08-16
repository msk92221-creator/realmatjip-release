"""Cloud Run용 SQLite 백업 동기화 — GCS 버킷에 DB를 내려받고/올린다.

- REALMATJIP_GCS_BUCKET이 설정된 경우에만 활성화 (로컬 실행은 영향 없음)
- 시작: 버킷의 DB를 내려받아 이어서 사용 (Cloud Run 파일시스템은 휘발성)
- 주기: mtime이 바뀌면 30초 주기로 업로드, 종료 시 최종 업로드
- 인증: Cloud Run 메타데이터 서버의 서비스 계정 토큰 (httpx만 사용 — 추가 의존성 없음)

개인용 단일 인스턴스 전제. 동시 다중 인스턴스가 쓰면 안 된다 (min스케일=1, 동시성=1 권장).
"""
import hashlib
import os
import threading
import time

import httpx

METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/"
    "service-accounts/default/token"
)
SYNC_INTERVAL_S = 30


def _bucket() -> str:
    return os.environ.get("REALMATJIP_GCS_BUCKET", "").strip()


def _db_path() -> str:
    from ..core.settings import get_settings
    return get_settings().db_path


def _access_token() -> str:
    resp = httpx.get(
        METADATA_TOKEN_URL,
        headers={"Metadata-Flavor": "Google"},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def pull_db_from_bucket() -> bool:
    """시작 시 버킷의 DB를 내려받는다. 없으면 False (신규 시작)."""
    bucket, db_path = _bucket(), _db_path()
    if not bucket:
        return False
    try:
        token = _access_token()
        resp = httpx.get(
            f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/realmatjip.db",
            params={"alt": "media"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        with open(db_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:  # 동기화 실패가 서버 기동을 막지 않게 한다
        print(f"[cloud_sync] pull 실패 (계속 진행): {e}")
        return False


def push_db_to_bucket() -> bool:
    bucket, db_path = _bucket(), _db_path()
    if not bucket or not os.path.exists(db_path):
        return False
    try:
        token = _access_token()
        with open(db_path, "rb") as f:
            resp = httpx.put(
                f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o",
                params={"uploadType": "media", "name": "realmatjip.db"},
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/octet-stream"},
                content=f.read(),
                timeout=60,
            )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[cloud_sync] push 실패 (다음 주기 재시도): {e}")
        return False


class _SyncWorker(threading.Thread):
    """mtime+해시 감시 → 변경 시 업로드. 데몬 스레드라 강제 종료 시 최대 30초 유실 가능."""

    def __init__(self):
        super().__init__(daemon=True, name="realmatjip-cloud-sync")
        self._stop = threading.Event()
        self._last_hash: str | None = None
        self._snapshot()

    def _snapshot(self):
        try:
            with open(_db_path(), "rb") as f:
                self._last_hash = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            self._last_hash = None

    def run(self):
        while not self._stop.wait(SYNC_INTERVAL_S):
            if not self._changed():
                continue
            if push_db_to_bucket():
                self._snapshot()
                print("[cloud_sync] DB 변경분 업로드 완료")

    def _changed(self) -> bool:
        try:
            with open(_db_path(), "rb") as f:
                return hashlib.sha256(f.read()).hexdigest() != self._last_hash
        except OSError:
            return False

    def final_push(self):
        self._stop.set()
        if self._changed():
            push_db_to_bucket()


def start_sync_worker() -> _SyncWorker | None:
    if not _bucket():
        return None
    worker = _SyncWorker()
    worker.start()
    return worker
