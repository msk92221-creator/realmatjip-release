"""ZaiReviewAnalyzer 테스트 — httpx MockTransport로 실 API 형식을 시뮬레이션."""
import json
import unittest
from datetime import datetime

import httpx

from app.analysis.analyzer import (
    AnalyzerConfigError,
    AnalyzerTransportError,
    MockReviewAnalyzer,
    ZaiReviewAnalyzer,
    create_analyzer_from_env,
)
from app.models import Review

VALID_OUTPUT = json.dumps({
    "ad_probability": 0.15, "ad_confidence": 0.85, "authenticity": 0.9,
    "specificity": 0.8, "local_probability": 0.8,
    "sentiment": {"food": 0.85},
    "visit_context": {"repeat_visit": True, "menu_specificity": 0.8, "negative_points_present": True},
    "signals": {
        "ad_signals": [],
        "authentic_signals": [
            {"code": "local_context", "quote": "회사가 근처라 점심으로 자주 가는 곳"},
            {"code": "repeat_visit", "quote": "네 번째 방문"},
        ],
    },
    "pseudo_rating": None, "summary": "신뢰도 높은 로컬 재방문 후기",
    "flags": {"insufficient_text": False},
}, ensure_ascii=False)

REVIEW = Review(
    id="r-1", restaurant_id="x", source="naver_map", rating=4.0,
    text="회사가 근처라 점심으로 자주 가는 곳. 이번이 네 번째 방문인데 맛이 항상 일정해요.",
    reviewed_at=datetime(2026, 8, 1),
)


def make_analyzer(handler, **kwargs):
    return ZaiReviewAnalyzer(
        api_key="test-key", model="glm-test", base_url="http://test",
        transport=httpx.MockTransport(handler), retry_delays=(0, 0), **kwargs,
    )


def chat_response(content, pin=100, pout=200):
    return httpx.Response(200, json={
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": pin, "completion_tokens": pout},
    })


def models_response(ids):
    return httpx.Response(200, json={"data": [{"id": i} for i in ids]})


class ZaiAnalyzerTest(unittest.TestCase):
    def test_success_flow(self):
        def handler(request):
            if request.url.path.endswith("/models"):
                return models_response(["glm-test"])
            return chat_response(VALID_OUTPUT, pin=120, pout=80)

        analyzer = make_analyzer(handler)
        analyzer.validate_model()
        result = analyzer.analyze(REVIEW)

        self.assertEqual(result.analyzer, "zai:glm-test:v2-thinking-off-json-2048")
        self.assertAlmostEqual(result.ad_probability, 0.15)
        self.assertEqual(len(result.authentic_signals), 2)
        self.assertEqual(analyzer.tokens_input, 120)  # 1회 호출
        self.assertEqual(analyzer.calls, 1)

    def test_invalid_json_then_retry_success(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            if len(calls) == 1:
                return chat_response("죄송합니다. 생각 중입니다...", pin=50, pout=10)
            return chat_response(VALID_OUTPUT, pin=60, pout=70)

        analyzer = make_analyzer(handler)
        result = analyzer.analyze(REVIEW)
        self.assertEqual(analyzer.calls, 2)
        self.assertAlmostEqual(result.ad_probability, 0.15)

    def test_retry_also_fails_needs_manual(self):
        def handler(request):
            return chat_response("이해할 수 없습니다", pin=10, pout=5)

        analyzer = make_analyzer(handler)
        result = analyzer.analyze(REVIEW)
        self.assertTrue(result.flags["needs_manual_review"])
        self.assertEqual(result.ad_probability, 0.5)
        self.assertEqual(analyzer.calls, 2)

    def test_unsupported_model_fails_fast(self):
        def handler(request):
            if request.url.path.endswith("/models"):
                return models_response(["glm-a", "glm-b"])
            return httpx.Response(404, json={"error": {"message": "model not found: glm-test"}})

        analyzer = make_analyzer(handler)
        with self.assertRaises(AnalyzerConfigError) as ctx:
            analyzer.validate_model()
        self.assertIn("지원되지 않는 모델", str(ctx.exception))
        self.assertIn("glm-a", str(ctx.exception))

    def test_balance_error_is_fatal(self):
        def handler(request):
            return httpx.Response(429, json={"error": {"code": "1113",
                                       "message": "Insufficient balance or no resource package."}})

        analyzer = make_analyzer(handler)
        with self.assertRaises(AnalyzerConfigError) as ctx:
            analyzer.analyze(REVIEW)
        self.assertIn("잔액 부족", str(ctx.exception))

    def test_server_error_retries_then_transport_error(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(503, text="service unavailable")

        analyzer = make_analyzer(handler)
        with self.assertRaises(AnalyzerTransportError):
            analyzer.analyze(REVIEW)
        self.assertEqual(len(calls), 3)  # 1회 + 2회 재시도

    def test_usage_accumulated(self):
        def handler(request):
            return chat_response(VALID_OUTPUT, pin=1000, pout=200)

        analyzer = make_analyzer(handler)
        analyzer.analyze(REVIEW)
        analyzer.analyze(REVIEW)
        self.assertEqual(analyzer.tokens_input, 2000)
        self.assertEqual(analyzer.tokens_output, 400)
        self.assertEqual(analyzer.calls, 2)


class FactoryTest(unittest.TestCase):
    def test_env_selection(self):
        mock = create_analyzer_from_env({"REALMATJIP_ANALYZER": "mock"})
        self.assertIsInstance(mock, MockReviewAnalyzer)

        no_key = create_analyzer_from_env({})
        self.assertIsInstance(no_key, MockReviewAnalyzer)

        zai = create_analyzer_from_env({"ZAI_API_KEY": "k", "ZAI_MODEL": "glm-4.5-air"})
        self.assertIsInstance(zai, ZaiReviewAnalyzer)
        self.assertEqual(zai.model, "glm-4.5-air")
        self.assertIn("glm-4.5-air", zai.name)
        self.assertIn("v2-thinking-off", zai.name)

        custom = create_analyzer_from_env(
            {"ZAI_API_KEY": "k", "ZAI_MODEL": "glm-5-turbo", "ZAI_BASE_URL": "http://x/v1"})
        self.assertEqual(custom.model, "glm-5-turbo")
        self.assertEqual(custom.base_url, "http://x/v1")

    def test_missing_api_key_raises_for_zai(self):
        with self.assertRaises(AnalyzerConfigError):
            create_analyzer_from_env({"REALMATJIP_ANALYZER": "zai"})

    def test_mock_analyzer_analysis_shape(self):
        analyzer = MockReviewAnalyzer()
        result = analyzer.analyze(REVIEW)
        self.assertTrue(0.0 <= result.ad_probability <= 1.0)
        self.assertGreater(len(result.authentic_signals), 0)  # 로컬 키워드 감지


if __name__ == "__main__":
    unittest.main()
