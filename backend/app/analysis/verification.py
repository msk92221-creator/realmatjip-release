"""근거(Evidence) 검증 — signal의 quote가 원문에 실제 존재하는지 확인한다 (스펙 §5).

- 존재하지 않는 quote → signal 제거 + ad_confidence 감소
- 로컬 근거 quote가 모두 무효면 local_probability를 중립(0.5)쪽으로 clamp
"""
from ..scoring.duplicates import normalize_text

from .models import ReviewAnalysis


def _quote_in_text(quote: str, normalized_text: str) -> bool:
    normalized_quote = normalize_text(quote)
    if len(normalized_quote) < 2:
        return False
    if normalized_quote in normalized_text:
        return True
    # LLM이 인용을 미묘하게 다듬은 경우: 토큰 포함률로 판정
    quote_chars = set(normalized_quote)
    if not quote_chars:
        return False
    contained = sum(1 for c in quote_chars if c in normalized_text)
    return contained / len(quote_chars) >= 0.9


def verify_analysis(analysis: ReviewAnalysis, review_text: str) -> ReviewAnalysis:
    normalized = normalize_text(review_text)

    kept_ad = [s for s in analysis.ad_signals if _quote_in_text(s.quote, normalized)]
    kept_auth = [s for s in analysis.authentic_signals if _quote_in_text(s.quote, normalized)]
    dropped = (len(analysis.ad_signals) - len(kept_ad)) + (len(analysis.authentic_signals) - len(kept_auth))

    flags = dict(analysis.flags)
    if dropped:
        flags["signals_dropped"] = dropped
        analysis.ad_confidence = round(analysis.ad_confidence * 0.8, 4)

    # 로컬 근거 quote가 하나도 없는데 로컬 가능성이 높게 나왔다면 중립으로 clamp
    has_local_evidence = any(s.code == "local_context" for s in kept_auth)
    if not has_local_evidence and analysis.local_probability > 0.5:
        analysis.local_probability = round(0.5 + (analysis.local_probability - 0.5) * 0.3, 4)

    analysis.ad_signals = kept_ad
    analysis.authentic_signals = kept_auth
    analysis.flags = flags
    return analysis
