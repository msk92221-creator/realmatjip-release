"""SQLAlchemy ORM 모델 — DESIGN.md §3 스키마의 Phase 1 구현.

레이어 원칙: RAW(reviews.raw_payload) → NORMALIZED(reviews) → ENRICHED(review_analysis)
→ AGGREGATED(restaurant_scores). 원본은 수정하지 않고 이력을 쌓는다.
"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class RestaurantORM(Base):
    __tablename__ = "restaurants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String, default="")
    address: Mapped[str] = mapped_column(String, default="")
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    # Phase 3B: provider 데이터 보존 (google_place_id, google_rating 등)
    provider_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ReviewORM(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        Index("ix_reviews_restaurant", "restaurant_id"),
        Index("ix_reviews_text_hash", "text_hash"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    restaurant_id: Mapped[str] = mapped_column(ForeignKey("restaurants.id"))
    source: Mapped[str] = mapped_column(String)
    source_review_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewer_review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)  # 1~5, 없으면 None
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String)  # 정규화 텍스트 sha256 (exact dedup + 캐시 키)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # RAW 레이어 보존
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime)
    duplicate_of: Mapped[str | None] = mapped_column(String, nullable=True)  # near-dup 대표 리뷰


class ReviewAnalysisORM(Base):
    __tablename__ = "review_analysis"

    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"), primary_key=True)
    analyzer: Mapped[str] = mapped_column(String)             # mock-v1 | rules_v1 | glm-*
    prompt_version: Mapped[str] = mapped_column(String)
    analysis_version: Mapped[str] = mapped_column(String, default="1")
    ad_probability: Mapped[float] = mapped_column(Float)
    ad_confidence: Mapped[float] = mapped_column(Float)
    authenticity: Mapped[float] = mapped_column(Float)
    specificity: Mapped[float] = mapped_column(Float)
    local_probability: Mapped[float] = mapped_column(Float)
    sentiment: Mapped[dict] = mapped_column(JSON)
    visit_context: Mapped[dict] = mapped_column(JSON)
    ad_signals: Mapped[list] = mapped_column(JSON)            # [{code, quote}]
    authentic_signals: Mapped[list] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text, default="")
    pseudo_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    flags: Mapped[dict] = mapped_column(JSON)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ManualLabelORM(Base):
    """사람의 수동 판단 — 2축 분리 (Phase 3A.1).

    ad_label: 광고 ground truth (ad | likely_ad | ambiguous | normal | null)
      → effective_ad_probability 계산에만 사용

    manipulation_label: 조작 ground truth (suspicious | ambiguous | normal | null)
      → manipulation evaluation/calibration에만 사용, ad_probability에 영향 없음

    광고 판단과 조작 판단은 독립적으로 관리한다.
    """
    __tablename__ = "manual_labels"

    review_id: Mapped[str] = mapped_column(ForeignKey("reviews.id"), primary_key=True)
    ad_label: Mapped[str | None] = mapped_column(String, nullable=True)
    manipulation_label: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str] = mapped_column(String, default="")
    evidence: Mapped[str] = mapped_column(String, default="")
    dataset: Mapped[str] = mapped_column(String, default="")  # natural | challenge | ""
    labeled_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RestaurantScoreORM(Base):
    """식당 점수 — batch_id별 이력 보존, 알고리즘 버전과 함께 저장 (스펙 §36)."""
    __tablename__ = "restaurant_scores"
    __table_args__ = (
        Index("ix_scores_version_overall", "algorithm_version", "overall_a"),
        Index("ix_scores_batch", "batch_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[str] = mapped_column(ForeignKey("restaurants.id"))
    algorithm_version: Mapped[str] = mapped_column(String)
    batch_id: Mapped[str] = mapped_column(String)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    overall_a: Mapped[float | None] = mapped_column(Float, nullable=True)
    overall_b: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_adjusted: Mapped[float] = mapped_column(Float)
    local: Mapped[float] = mapped_column(Float)
    trust: Mapped[float] = mapped_column(Float)
    ad_free: Mapped[float] = mapped_column(Float)
    food: Mapped[float | None] = mapped_column(Float, nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    repeat: Mapped[float] = mapped_column(Float)
    consistency: Mapped[float] = mapped_column(Float)
    longevity: Mapped[float] = mapped_column(Float)
    manipulation_score: Mapped[float] = mapped_column(Float)
    n_raw: Mapped[int] = mapped_column(Integer)
    n_eff: Mapped[float] = mapped_column(Float)
    local_evidence: Mapped[float] = mapped_column(Float)
    evidence_strength: Mapped[float] = mapped_column(Float)
    local_badge: Mapped[bool] = mapped_column(Boolean)
    dup_count: Mapped[int] = mapped_column(Integer)
    terms_a: Mapped[list] = mapped_column(JSON)   # [(항목, 신호값, 기여점수)] — explanation 렌더링용
    terms_b: Mapped[list] = mapped_column(JSON)
    platforms: Mapped[list] = mapped_column(JSON)  # [{source, n_reviews, sum_w, shrunk_rating}]


class AnalysisCacheORM(Base):
    """LLM 분석 캐시 — (text_hash, analyzer, prompt_version, analysis_version) 조합은
    재분석하지 않는다 (스펙 §6). 프롬프트/모델이 바뀌면 새 키로 재분석된다."""
    __tablename__ = "analysis_cache"
    __table_args__ = (
        PrimaryKeyConstraint("text_hash", "analyzer", "prompt_version", "analysis_version"),
    )

    text_hash: Mapped[str] = mapped_column(String)
    analyzer: Mapped[str] = mapped_column(String)
    prompt_version: Mapped[str] = mapped_column(String)
    analysis_version: Mapped[str] = mapped_column(String, default="1")
    result: Mapped[dict] = mapped_column(JSON)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class JobORM(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String)      # recalculate | seed | ...
    status: Mapped[str] = mapped_column(String)    # queued | running | done | failed
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AppSettingORM(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)
