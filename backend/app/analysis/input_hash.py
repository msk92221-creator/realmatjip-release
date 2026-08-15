"""LLM 입력 해시 — 캐시 키가 LLM의 실제 입력을 결정하는 모든 정보를 포함하는지 검증.

현재 LLM 입력은 source + rating + text 3개 필드이므로,
text_hash 단독 캐시는 금지된다 (Phase 3A.1 §10).
"""
import hashlib
import json

from ..models import Review
from ..scoring.duplicates import normalize_text


def llm_input_payload(review: Review) -> dict:
    """ZaiReviewAnalyzer._user_payload와 동일한 구조 — 단일 source of truth."""
    return {"source": review.source, "rating": review.rating, "text": review.text}


def llm_input_hash(review: Review) -> str:
    """LLM 실제 입력의 SHA256 — source/rating/text 전부 포함."""
    payload = llm_input_payload(review)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def text_only_hash(text: str) -> str:
    """기존 text_hash — 텍스트만 반영, LLM 입력이 text 하나뿐인 경우에만 안전."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def cache_key_is_safe(review: Review) -> bool:
    """LLM 입력에 text 외 다른 필드가 있는지 검증."""
    payload = llm_input_payload(review)
    non_text_fields = [k for k, v in payload.items() if k != "text" and v is not None]
    return len(non_text_fields) == 0  # text만 있으면 text_hash로 충분
