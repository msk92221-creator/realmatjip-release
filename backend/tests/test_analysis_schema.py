"""LLM 출력 스키마 검증 + 근거(quote) 검증 테스트."""
import unittest

from app.analysis import ReviewAnalysis
from app.analysis.schema import (
    AnalysisParseError,
    analysis_from_cache_dict,
    analysis_to_cache_dict,
    needs_manual_fallback,
    parse_llm_analysis,
)
from app.analysis.verification import verify_analysis

VALID = {
    "ad_probability": 0.85, "ad_confidence": 0.8, "authenticity": 0.2,
    "specificity": 0.5, "local_probability": 0.3,
    "sentiment": {"food": 0.9, "service": None},
    "visit_context": {"repeat_visit": False, "menu_specificity": 0.4, "negative_points_present": False},
    "signals": {
        "ad_signals": [{"code": "catalog_listing", "quote": "영업시간 11:00~21:00"}],
        "authentic_signals": [{"code": "local_context", "quote": "없는 문장"}],
    },
    "pseudo_rating": 4.8, "summary": "요약", "flags": {"insufficient_text": False},
}


class ParseTest(unittest.TestCase):
    def test_valid_dict(self):
        analysis = parse_llm_analysis(VALID, analyzer="t")
        self.assertEqual(analysis.ad_probability, 0.85)
        self.assertEqual(analysis.sentiment["service"], None)
        self.assertEqual(analysis.ad_signals[0].code, "catalog_listing")

    def test_string_with_code_fence(self):
        import json
        fenced = "```json\n" + json.dumps(VALID) + "\n```"
        analysis = parse_llm_analysis(fenced, analyzer="t")
        self.assertEqual(analysis.ad_probability, 0.85)

    def test_clamping(self):
        data = dict(VALID, ad_probability=1.7, authenticity=-0.3)
        analysis = parse_llm_analysis(data, analyzer="t")
        self.assertEqual(analysis.ad_probability, 1.0)
        self.assertEqual(analysis.authenticity, 0.0)

    def test_missing_required_raises(self):
        bad = dict(VALID)
        del bad["ad_probability"]
        with self.assertRaises(AnalysisParseError):
            parse_llm_analysis(bad, analyzer="t")

    def test_unknown_signal_code_dropped(self):
        data = dict(VALID)
        data["signals"] = {"ad_signals": [{"code": "made_up_code", "quote": "영업시간"}], "authentic_signals": []}
        analysis = parse_llm_analysis(data, analyzer="t")
        self.assertEqual(analysis.ad_signals, [])

    def test_pseudo_rating_clamp(self):
        analysis = parse_llm_analysis(dict(VALID, pseudo_rating=99), analyzer="t")
        self.assertEqual(analysis.pseudo_rating, 5.0)

    def test_needs_manual_fallback(self):
        analysis = needs_manual_fallback("zai:test", "JSON 파싱 실패")
        self.assertEqual(analysis.ad_probability, 0.5)
        self.assertEqual(analysis.ad_confidence, 0.0)
        self.assertTrue(analysis.flags["needs_manual_review"])

    def test_cache_roundtrip(self):
        analysis = parse_llm_analysis(VALID, analyzer="t")
        restored = analysis_from_cache_dict(analysis_to_cache_dict(analysis))
        self.assertEqual(restored.ad_probability, analysis.ad_probability)
        self.assertEqual(restored.ad_signals[0].quote, analysis.ad_signals[0].quote)
        self.assertEqual(restored.flags, analysis.flags)


class VerificationTest(unittest.TestCase):
    TEXT = "위치는 강남역 3번 출구에서 도보 5분이고 영업시간 11:00~21:00입니다. 회사가 근처라 자주 가요."

    def _analysis(self, **overrides) -> ReviewAnalysis:
        base = dict(VALID)
        base.update(overrides)
        return parse_llm_analysis(base, analyzer="t")

    def test_existing_quote_kept(self):
        analysis = self._analysis()
        result = verify_analysis(analysis, self.TEXT)
        self.assertEqual(len(result.ad_signals), 1)  # catalog_listing quote 존재

    def test_missing_quote_dropped_and_confidence_reduced(self):
        analysis = self._analysis(ad_confidence=1.0)
        result = verify_analysis(analysis, self.TEXT)
        # authentic_signals의 quote("없는 문장")는 원문에 없음 → 제거
        self.assertEqual(result.authentic_signals, [])
        self.assertLess(result.ad_confidence, 1.0)
        self.assertEqual(result.flags.get("signals_dropped"), 1)

    def test_local_without_evidence_clamped(self):
        analysis = self._analysis(local_probability=0.95)
        analysis.authentic_signals = []  # local 근거 없음
        result = verify_analysis(analysis, self.TEXT)
        # 0.95 → 0.5 + 0.45*0.3 = 0.635
        self.assertAlmostEqual(result.local_probability, 0.635, places=3)

    def test_low_local_unchanged_without_evidence(self):
        analysis = self._analysis(local_probability=0.3)
        analysis.authentic_signals = []
        result = verify_analysis(analysis, self.TEXT)
        self.assertEqual(result.local_probability, 0.3)  # 이미 중립 이하


if __name__ == "__main__":
    unittest.main()
