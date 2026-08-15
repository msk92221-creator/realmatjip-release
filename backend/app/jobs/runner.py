"""잡 실행 기본 구조 — LLM 분석과 점수 계산은 분리한다(스펙: Scoring 재계산 시 GLM 재호출 없음).

recalculate: DB의 리뷰(+수동 라벨) → 도메인 변환 → score_dataset → 점수 이력 적재.
near-dup 판정 결과(duplicate_of)를 reviews 테이블에 다시 반영한다.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import ScoringConfig
from ..db.mappers import review_to_domain, score_to_row
from ..db.models import (
    JobORM,
    ManualLabelORM,
    RestaurantORM,
    RestaurantScoreORM,
    ReviewAnalysisORM,
    ReviewORM,
    utcnow,
)
from ..models import Restaurant
from ..scoring.engine import score_dataset


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_job(session_factory: sessionmaker[Session], kind: str) -> int:
    with session_factory() as session:
        job = JobORM(kind=kind, status="queued", progress={})
        session.add(job)
        session.commit()
        return job.id


def _set_job(session_factory: sessionmaker[Session], job_id: int, **fields) -> None:
    with session_factory() as session:
        job = session.get(JobORM, job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = utcnow()
        session.commit()


def load_domain_dataset(session: Session) -> tuple[list[Restaurant], list]:
    restaurants = [
        Restaurant(id=r.id, name=r.name, category=r.category, address=r.address, lat=r.lat, lng=r.lng)
        for r in session.execute(select(RestaurantORM)).scalars()
    ]
    analyses = {a.review_id: a for a in session.execute(select(ReviewAnalysisORM)).scalars()}
    ad_labels = {l.review_id: l.ad_label for l in session.execute(select(ManualLabelORM)).scalars()}
    reviews = [
        review_to_domain(r, analyses.get(r.id), ad_labels.get(r.id))
        for r in session.execute(select(ReviewORM)).scalars()
    ]
    return restaurants, reviews


def execute_recalculate(
    session_factory: sessionmaker[Session],
    job_id: int,
    cfg: ScoringConfig,
) -> str:
    """전체 식당 점수 재계산. GLM 호출 없음 — 이미 저장된 분석 결과만 사용."""
    _set_job(session_factory, job_id, status="running", progress={"done": 0, "total": 0})
    batch_id = uuid.uuid4().hex
    try:
        with session_factory() as session:
            restaurants, reviews = load_domain_dataset(session)
            results = score_dataset(restaurants, reviews, cfg, _now())

        total = len(results)
        for done, result in enumerate(results, start=1):
            with session_factory() as session:
                session.add(score_to_row(result, batch_id, cfg.algorithm_version))
                # near-dup 판정 결과 반영 (원문 수정 아님 — 정규화 판정 메타데이터)
                for review in reviews:
                    if review.restaurant_id == result.restaurant.id and review.duplicate_of:
                        row = session.get(ReviewORM, review.id)
                        if row is not None:
                            row.duplicate_of = review.duplicate_of
                session.commit()
            _set_job(session_factory, job_id,
                     progress={"done": done, "total": total},
                     status="running")
        _set_job(session_factory, job_id, status="done")
        return batch_id
    except Exception as exc:  # 잡 실패가 서버를 죽이지 않게
        _set_job(session_factory, job_id, status="failed", error=str(exc))
        raise
