"""ReviewAnalyzer 구현체 — 특정 모델명을 파이프라인 코드에 박지 않는다 (스펙 §3).

    ReviewAnalyzer (Protocol)
     ├─ MockReviewAnalyzer   (테스트/개인용 규칙 기반 — fixture mock_analyzer는 별도 유지)
     └─ ZaiReviewAnalyzer    (ZAI_API_KEY/ZAI_MODEL/ZAI_BASE_URL 환경변수 기반)

모델은 환경변수로 지정하고, API가 지원하지 않는 모델이면 AnalyzerConfigError로
명확히 실패한다. 사용 가능 모델은 /models로 실시간 확인한다.
"""
import json
import os
import time
from typing import Protocol

import httpx

from ..models import Review

from . import ReviewAnalysis
from .schema import (
    ANALYSIS_SCHEMA_VERSION,
    PROMPT_VERSION,
    AnalysisParseError,
    load_examples,
    load_system_prompt,
    needs_manual_fallback,
    parse_llm_analysis,
)
from .verification import verify_analysis

DEFAULT_ZAI_BASE_URL = "https://api.z.ai/api/paas/v4"
DEFAULT_ZAI_MODEL = "glm-4.5-air"  # 리뷰 분석 = 경량 분류 작업 — 코드 모델과 구분 (스펙 §3)

# Phase 3A.3.1: inference 설정 버전 — 캐시 identity에 포함된다.
# v1: thinking 기본(=enabled), max_tokens=900 → GLM-4.5에서 대량 실패
# v2: thinking=disabled, response_format=json_object, max_tokens=2048
INFERENCE_CONFIG_VERSION = "v2-thinking-off-json-2048"


class AnalyzerConfigError(Exception):
    """설정/모델 오류 — job 전체를 즉시 중단해야 하는 경우."""


class AnalyzerTransportError(Exception):
    """일시적 전송 오류 — 리뷰 1건 실패로 기록하고 계속."""


class ReviewAnalyzer(Protocol):
    name: str

    def analyze(self, review: Review) -> ReviewAnalysis: ...


class MockReviewAnalyzer:
    """가벼운 규칙 기반 분석기 — LLM 없는 개발/테스트용. fixture mock_analyzer와 별개."""

    name = "mock-rules-v1"
    prompt_version = PROMPT_VERSION

    _AD_WORDS = ("협찬", "제공받", "체험단", "원고료", "소정의", "식사권", "라스트오더",
                 "영업시간", "주차 가능", "발렛", "예약은", "강추합니다", "완전 강추")
    _LOCAL_WORDS = ("회사가 근처", "집이 근처", "동네", "단골", "자주 가", "몇 년째", "네 번째", "학원")
    _REPEAT_WORDS = ("재방문", "다시 가", "번째 방문", "또 올")
    _NEGATIVE_WORDS = ("아쉬", "별로", "실망", "좁", "느리", "짜", "비싸")

    def analyze(self, review: Review) -> ReviewAnalysis:
        text = review.text
        ad_hits = [w for w in self._AD_WORDS if w in text]
        local_hits = [w for w in self._LOCAL_WORDS if w in text]
        repeat_hits = [w for w in self._REPEAT_WORDS if w in text]
        negative = any(w in text for w in self._NEGATIVE_WORDS)

        ad_probability = min(0.25 + 0.18 * len(ad_hits), 0.95) if ad_hits else 0.12
        specificity = min(0.2 + 0.05 * (len(text) // 30), 0.9)
        local_probability = min(0.4 + 0.25 * len(local_hits), 0.95) if local_hits else 0.3

        def signal(word, code):
            start = text.find(word)
            return {"code": code, "quote": text[max(0, start - 8):start + len(word) + 8]}

        return parse_llm_analysis({
            "ad_probability": round(ad_probability, 2),
            "ad_confidence": 0.6,
            "authenticity": round(max(0.3, 0.9 - 0.15 * len(ad_hits)), 2),
            "specificity": round(specificity, 2),
            "local_probability": round(local_probability, 2),
            "sentiment": {"food": 0.8, "service": None, "price": None,
                          "atmosphere": 0.7, "accessibility": None},
            "visit_context": {
                "repeat_visit": bool(repeat_hits) or None,
                "wait_time_mentioned": "기다" in text or "대기" in text,
                "menu_specificity": round(specificity, 2),
                "negative_points_present": negative or None,
            },
            "signals": {
                "ad_signals": [signal(w, "template_style") for w in ad_hits[:2]],
                "authentic_signals": (
                    [signal(w, "local_context") for w in local_hits[:1]]
                    + [signal(w, "repeat_visit") for w in repeat_hits[:1]]
                ),
            },
            "pseudo_rating": None if review.rating is not None else 4.0,
            "summary": f"규칙 기반 분석 — 광고성 키워드 {len(ad_hits)}개, 로컬 키워드 {len(local_hits)}개",
            "flags": {"insufficient_text": len(text.strip()) < 8},
        }, analyzer=self.name)


class ZaiReviewAnalyzer:
    """Z.ai OpenAI 호환 chat/completions 기반 분석기.

    - 모델/주소/키는 모두 환경변수(ZAI_MODEL/ZAI_BASE_URL/ZAI_API_KEY).
    - 지원되지 않는 모델 → job 개시 전 /models 확인 + 응답 오류 매핑으로 즉시 실패.
    - JSON 파라미티/스키마 위반 → 1회 재시도 → needs_manual_review 폴백.
    """

    def __init__(self, api_key: str, model: str, base_url: str = DEFAULT_ZAI_BASE_URL,
                 timeout: float = 60.0, verify_quotes: bool = True,
                 transport: httpx.BaseTransport | None = None,
                 retry_delays: tuple[float, float] = (1.0, 3.0)):
        if not api_key:
            raise AnalyzerConfigError("ZAI_API_KEY가 설정되지 않았습니다")
        self.retry_delays = retry_delays
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verify_quotes = verify_quotes
        self.name = f"zai:{model}:{INFERENCE_CONFIG_VERSION}"
        self.prompt_version = PROMPT_VERSION
        self.analysis_version = ANALYSIS_SCHEMA_VERSION
        self.tokens_input = 0
        self.tokens_output = 0
        self.calls = 0
        self._system = load_system_prompt()
        self._examples = load_examples()
        self._messages: list[dict] | None = None
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            transport=transport,
        )

    # ── 모델 가용성 (스펙 §3: 존재하지 않는 모델 가정 금지) ──

    def validate_model(self) -> None:
        # Phase 3A.3/3B.1 실측: glm-4.5-flash는 호출 가능하지만 /models에 미등록.
        # ZAI_SKIP_MODEL_CHECK=1이면 목록 검증만 건너뛴다 — 실제 호출 오류는 analyze에서 즉시 실패한다.
        if os.environ.get("ZAI_SKIP_MODEL_CHECK", "").strip().lower() in ("1", "true", "yes"):
            return
        try:
            response = self._client.get(f"{self.base_url}/models")
        except httpx.HTTPError as exc:
            raise AnalyzerTransportError(f"/models 조회 실패: {exc}") from exc
        if response.status_code != 200:
            raise AnalyzerConfigError(
                f"모델 목록 조회 실패 (HTTP {response.status_code}): {response.text[:200]}"
            )
        ids = [m.get("id") for m in response.json().get("data", [])]
        if self.model not in ids:
            raise AnalyzerConfigError(
                f"지원되지 않는 모델 '{self.model}'. 사용 가능: {', '.join(ids)}"
            )

    # ── 분석 ──

    def analyze(self, review: Review) -> ReviewAnalysis:
        base = self._build_messages()
        last_error = ""
        for attempt in range(2):
            # Phase 3A.1: 온도를 상향하지 않는다 — 동일한 deterministic 값으로 repair만 시도
            messages = base + [{"role": "user", "content": self._user_payload(review)}]
            content, usage = self._chat(messages, attempt)
            self.tokens_input += usage[0]
            self.tokens_output += usage[1]
            self.calls += 1
            try:
                analysis = parse_llm_analysis(content, analyzer=self.name)
                if self.verify_quotes:
                    analysis = verify_analysis(analysis, review.text)
                return analysis
            except AnalysisParseError as exc:
                last_error = str(exc)
                base = base + [
                    {"role": "assistant", "content": str(content)[:1500]},
                    {"role": "user", "content":
                        f"이전 응답이 schema validation에 실패했다 ({last_error}). "
                        "다음 schema에 맞는 JSON만 다시 반환하라."},
                ]
        return needs_manual_fallback(self.name, last_error)

    def _build_messages(self) -> list[dict]:
        if self._messages is None:
            messages = [{"role": "system", "content": self._system}]
            for example in self._examples:
                messages.append({
                    "role": "user",
                    "content": "리뷰를 분석해 JSON만 반환:\n" + json.dumps(example["review"], ensure_ascii=False),
                })
                messages.append({
                    "role": "assistant",
                    "content": json.dumps(example["output"], ensure_ascii=False),
                })
            self._messages = messages
        return list(self._messages)

    def _user_payload(self, review: Review) -> str:
        payload = {"source": review.source, "rating": review.rating, "text": review.text}
        return "리뷰를 분석해 JSON만 반환:\n" + json.dumps(payload, ensure_ascii=False)

    def _chat(self, messages: list[dict], attempt: int) -> tuple[str, tuple[int, int]]:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,  # Phase 3A.1: 재시도에도 온도 상향하지 않음
            "max_tokens": 2048,  # Phase 3A.3.1: thinking 토큰 포함 여유 확보
            # Phase 3A.3.1: GLM-4.5+는 thinking이 기본 enabled — 분류 작업에서는 명시적으로 disabled
            "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
        }
        delays = self.retry_delays
        last_exc: Exception | None = None
        for retry in range(3):
            try:
                response = self._client.post(f"{self.base_url}/chat/completions", json=body)
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(delays[min(retry, 1)])
                continue
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                return content, (int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))
            error_text = response.text[:300]
            if response.status_code in (400, 404) and _is_model_error(response, error_text):
                raise AnalyzerConfigError(
                    f"모델 '{self.model}' 오류 (HTTP {response.status_code}): {error_text}"
                )
            if response.status_code == 429 and _is_balance_error(error_text):
                # 계정 수준 문제(잔액 부족) — 재시도/계속 진행이 무의미하므로 즉시 실패
                raise AnalyzerConfigError(
                    f"API 잔액 부족(429): {error_text} — 충전 후 다시 실행하세요"
                )
            if response.status_code in (429, 500, 502, 503, 504) and retry < 2:
                time.sleep(delays[min(retry, 1)])
                continue
            raise AnalyzerTransportError(f"HTTP {response.status_code}: {error_text}")
        raise AnalyzerTransportError(f"전송 실패: {last_exc}")

    def close(self) -> None:
        self._client.close()


def _is_model_error(response: httpx.Response, error_text: str) -> bool:
    lowered = error_text.lower()
    return any(k in lowered for k in ("model", "模型", "not found", "invalid"))


def _is_balance_error(error_text: str) -> bool:
    lowered = error_text.lower()
    return "1113" in error_text or "insufficient balance" in lowered or "resource package" in lowered


def create_analyzer_from_env(env: dict | None = None) -> ReviewAnalyzer:
    """REALMATJIP_ANALYZER=mock|zai (기본: ZAI_API_KEY 있으면 zai, 없으면 mock)."""
    env = env if env is not None else os.environ
    choice = (env.get("REALMATJIP_ANALYZER") or "").strip().lower()
    api_key = env.get("ZAI_API_KEY", "")
    if choice == "mock" or (not choice and not api_key):
        return MockReviewAnalyzer()
    return ZaiReviewAnalyzer(
        api_key=api_key,
        model=env.get("ZAI_MODEL") or DEFAULT_ZAI_MODEL,
        base_url=env.get("ZAI_BASE_URL") or DEFAULT_ZAI_BASE_URL,
        timeout=float(env.get("ZAI_TIMEOUT", "60")),
    )
