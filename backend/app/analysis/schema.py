"""LLM 출력을 ReviewAnalysis 스키마로 검증한다.

실패는 예외(AnalysisParseError)로 알린다 — 호출자(retry 로직)가 판단한다.
모든 수치는 0~1로 clamp하고, 알 수 없는 sentiment 키/signal 코드는 버린다.
"""
import json
import re
from pathlib import Path

from .models import ReviewAnalysis, Signal

AD_SIGNAL_CODES = {
    "explicit_sponsorship", "catalog_listing", "all_positive_no_drawback",
    "marketing_usp_repeat", "template_style", "cta_outlink", "photo_promo",
}
AUTHENTIC_SIGNAL_CODES = {
    "repeat_visit", "specific_menu_eval", "negative_point", "wait_time",
    "price_detail", "local_context", "visit_timing", "long_term_patron",
}
SENTIMENT_KEYS = ("food", "service", "price", "atmosphere", "accessibility")

PROMPT_VERSION = "review-analysis-v1"
ANALYSIS_SCHEMA_VERSION = "1"
PROMPTS_DIR = Path(__file__).parent / "prompts"


class AnalysisParseError(Exception):
    pass


def load_system_prompt() -> str:
    return (PROMPTS_DIR / "review_analysis_v1.txt").read_text(encoding="utf-8")


def load_examples() -> list[dict]:
    data = json.loads((PROMPTS_DIR / "examples_v1.json").read_text(encoding="utf-8"))
    return data["examples"]


def _clamp01(value) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError) as exc:
        raise AnalysisParseError(f"not numeric: {value!r}") from exc


def _extract_json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise AnalysisParseError("no JSON object in output")
    candidate = text[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise AnalysisParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AnalysisParseError("output is not a JSON object")
    return parsed


def _parse_signals(raw_signals, allowed: set[str]) -> list[Signal]:
    if not isinstance(raw_signals, list):
        return []
    signals = []
    for item in raw_signals:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        quote = item.get("quote")
        if code in allowed and isinstance(quote, str) and quote.strip():
            signals.append(Signal(code=code, quote=quote.strip()))
    return signals


def parse_llm_analysis(raw, analyzer: str) -> ReviewAnalysis:
    """LLM 원출력(str 또는 dict) → 검증된 ReviewAnalysis. 스키마 위반 시 AnalysisParseError."""
    data = _extract_json_object(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise AnalysisParseError("output is not a dict")

    required = ("ad_probability", "ad_confidence", "authenticity", "specificity", "local_probability")
    for key in required:
        if key not in data:
            raise AnalysisParseError(f"missing required field: {key}")

    sentiment_raw = data.get("sentiment") or {}
    if not isinstance(sentiment_raw, dict):
        raise AnalysisParseError("sentiment must be an object")
    sentiment = {}
    for key in SENTIMENT_KEYS:
        value = sentiment_raw.get(key)
        sentiment[key] = None if value is None else _clamp01(value)

    context_raw = data.get("visit_context") or {}
    if not isinstance(context_raw, dict):
        raise AnalysisParseError("visit_context must be an object")

    def _bool(key):
        value = context_raw.get(key)
        return value if isinstance(value, bool) else None

    signals_raw = data.get("signals") or {}
    ad_list = signals_raw.get("ad_signals", []) if isinstance(signals_raw, dict) else []
    auth_list = signals_raw.get("authentic_signals", []) if isinstance(signals_raw, dict) else []

    pseudo = data.get("pseudo_rating")
    if pseudo is not None:
        try:
            pseudo = min(max(float(pseudo), 1.0), 5.0)
        except (TypeError, ValueError) as exc:
            raise AnalysisParseError("pseudo_rating not numeric") from exc

    flags_raw = data.get("flags") or {}
    insufficient = bool(flags_raw.get("insufficient_text", False)) if isinstance(flags_raw, dict) else False

    return ReviewAnalysis(
        analyzer=analyzer,
        prompt_version=PROMPT_VERSION,
        ad_probability=_clamp01(data["ad_probability"]),
        ad_confidence=_clamp01(data["ad_confidence"]),
        authenticity=_clamp01(data["authenticity"]),
        specificity=_clamp01(data["specificity"]),
        local_probability=_clamp01(data["local_probability"]),
        sentiment=sentiment,
        visit_context={
            "repeat_visit": _bool("repeat_visit"),
            "wait_time_mentioned": _bool("wait_time_mentioned"),
            "menu_specificity": _clamp01(context_raw.get("menu_specificity", 0.0)),
            "negative_points_present": _bool("negative_points_present"),
        },
        ad_signals=_parse_signals(ad_list, AD_SIGNAL_CODES),
        authentic_signals=_parse_signals(auth_list, AUTHENTIC_SIGNAL_CODES),
        pseudo_rating=pseudo,
        summary=str(data.get("summary") or "")[:300],
        flags={"insufficient_text": insufficient},
    )


def needs_manual_fallback(analyzer: str, reason: str) -> ReviewAnalysis:
    """재시도까지 실패한 리뷰의 최후 폴백 — 확률은 중립, 수동 검토 대상 표시.
    이 리뷰 하나 때문에 job이 실패하지 않게 한다 (스펙 §4)."""
    return ReviewAnalysis(
        analyzer=analyzer,
        prompt_version=PROMPT_VERSION,
        ad_probability=0.5,
        ad_confidence=0.0,
        authenticity=0.5,
        specificity=0.5,
        local_probability=0.5,
        sentiment={k: None for k in SENTIMENT_KEYS},
        visit_context={
            "repeat_visit": None, "wait_time_mentioned": None,
            "menu_specificity": 0.5, "negative_points_present": None,
        },
        ad_signals=[],
        authentic_signals=[],
        summary=f"분석 실패({reason}) — 수동 검토 필요",
        flags={"insufficient_text": False, "needs_manual_review": True},
    )


def analysis_to_cache_dict(analysis: ReviewAnalysis) -> dict:
    return {
        "analyzer": analysis.analyzer,
        "prompt_version": analysis.prompt_version,
        "ad_probability": analysis.ad_probability,
        "ad_confidence": analysis.ad_confidence,
        "authenticity": analysis.authenticity,
        "specificity": analysis.specificity,
        "local_probability": analysis.local_probability,
        "sentiment": analysis.sentiment,
        "visit_context": analysis.visit_context,
        "ad_signals": [{"code": s.code, "quote": s.quote} for s in analysis.ad_signals],
        "authentic_signals": [{"code": s.code, "quote": s.quote} for s in analysis.authentic_signals],
        "pseudo_rating": analysis.pseudo_rating,
        "summary": analysis.summary,
        "flags": analysis.flags,
    }


def analysis_from_cache_dict(data: dict) -> ReviewAnalysis:
    return ReviewAnalysis(
        analyzer=data["analyzer"],
        prompt_version=data["prompt_version"],
        ad_probability=data["ad_probability"],
        ad_confidence=data["ad_confidence"],
        authenticity=data["authenticity"],
        specificity=data["specificity"],
        local_probability=data["local_probability"],
        sentiment=data.get("sentiment") or {k: None for k in SENTIMENT_KEYS},
        visit_context=data.get("visit_context") or {},
        ad_signals=[Signal(code=s["code"], quote=s["quote"]) for s in data.get("ad_signals", [])],
        authentic_signals=[Signal(code=s["code"], quote=s["quote"]) for s in data.get("authentic_signals", [])],
        pseudo_rating=data.get("pseudo_rating"),
        summary=data.get("summary", ""),
        flags=data.get("flags") or {},
    )
