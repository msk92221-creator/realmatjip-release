"""DB 엔진/세션/초기화. 개인용이므로 마이그레이션 도구 대신 create_all +
스키마 버전 스탬프/경량 마이그레이션으로 관리한다 (진화가 커지면 Alembic 도입)."""
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

SCHEMA_VERSION = "4"  # v4: restaurants.provider_metadata 추가 (Google Places 연동)


def make_engine(database_url: str) -> Engine:
    return create_engine(database_url, connect_args={"check_same_thread": False})


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def init_db(engine: Engine) -> None:
    _migrate_analysis_cache_pk(engine)
    _migrate_manual_labels_two_axis(engine)
    _migrate_restaurant_provider_metadata(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app_settings(key, value) VALUES('schema_version', :v) "
                "ON CONFLICT(key) DO NOTHING"
            ),
            {"v": SCHEMA_VERSION},
        )
        conn.execute(
            text("UPDATE app_settings SET value = :v WHERE key = 'schema_version'"),
            {"v": SCHEMA_VERSION},
        )


def _migrate_analysis_cache_pk(engine: Engine) -> None:
    """v1 캐시 테이블(text_hash 단일 PK)을 v2 복합키 스키마로 교체."""
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(analysis_cache)")).fetchall()
        if not rows:
            return
        pk_columns = [row[1] for row in rows if row[5]]
        if pk_columns != ["text_hash"]:
            return
        conn.execute(text("DROP TABLE analysis_cache"))


def _migrate_manual_labels_two_axis(engine: Engine) -> None:
    """v2 단일 label 컬럼 → v3 2축(ad_label + manipulation_label) 분리.

    기존 라벨은 재라벨링 대상이므로 drop-recreate."""
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(manual_labels)")).fetchall()
        if not rows:
            return
        columns = [row[1] for row in rows]
        if "ad_label" in columns:
            return  # 이미 v3
        conn.execute(text("DROP TABLE manual_labels"))


def _migrate_restaurant_provider_metadata(engine: Engine) -> None:
    """v3 restaurants → v4: provider_metadata(JSON, nullable) 컬럼 추가.

    create_all은 기존 테이블에 컬럼을 붙이지 않으므로, v4 이전에 만들어진 DB는
    RestaurantORM 조회가 전부 'no such column'으로 실패한다. 값이 nullable이라
    기존 행은 그대로 두고 ADD COLUMN만 수행한다."""
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(restaurants)")).fetchall()
        if not rows:
            return  # 테이블 자체가 없으면 create_all이 최신 스키마로 생성
        columns = [row[1] for row in rows]
        if "provider_metadata" in columns:
            return  # 이미 v4
        conn.execute(text("ALTER TABLE restaurants ADD COLUMN provider_metadata JSON"))
