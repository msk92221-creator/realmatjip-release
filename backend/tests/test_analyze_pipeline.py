"""분석 파이프라인 테스트 — 캐시, 비용 상한, 부분 실패 허용."""
import os
import tempfile
import unittest
from datetime import datetime

from app.analysis.analyzer import AnalyzerTransportError
from app.analysis.schema import parse_llm_analysis
from app.db.database import init_db, make_engine, make_session_factory
from app.db.mappers import restaurant_to_row, review_to_row
from app.db.models import AnalysisCacheORM, JobORM, ReviewAnalysisORM, ReviewORM
from app.models import Restaurant, Review
from app.pipeline.analyze import estimate_analysis, execute_analyze_job
from app.pipeline.limits import AnalyzeLimits, estimate_cost

GOOD_OUTPUT = {
    "ad_probability": 0.1, "ad_confidence": 0.9, "authenticity": 0.9,
    "specificity": 0.85, "local_probability": 0.75,
    "sentiment": {"food": 0.8}, "visit_context": {"repeat_visit": True, "menu_specificity": 0.8},
    "signals": {"ad_signals": [], "authentic_signals": []},
    "pseudo_rating": None, "summary": "정상", "flags": {},
}


class CountingAnalyzer:
    """호출 수를 세는 가짜 분석기 — 특정 리뷰에서 전송 오류를 낼 수 있다."""
    name = "fake-v1"
    prompt_version = "review-analysis-v1"

    def __init__(self, fail_ids=()):
        self.calls = []
        self.fail_ids = set(fail_ids)
        self.tokens_input = 0
        self.tokens_output = 0

    def analyze(self, review):
        self.calls.append(review.id)
        if review.id in self.fail_ids:
            raise AnalyzerTransportError("simulated timeout")
        self.tokens_input += 500
        self.tokens_output += 100
        return parse_llm_analysis(dict(GOOD_OUTPUT), analyzer=self.name)


class AnalyzePipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        url = "sqlite:///" + os.path.join(self.tmp.name, "analyze.db").replace("\\", "/")
        self.engine = make_engine(url)
        init_db(self.engine)
        self.sf = make_session_factory(self.engine)
        with self.sf() as session:
            session.merge(restaurant_to_row(Restaurant("a", "A식당", "한식", 1.0, 2.0)))
            for i in range(4):
                review = Review(
                    id=f"a-r{i}", restaurant_id="a", source="naver_map", rating=4.0,
                    text=f"회사가 근처라 자주 가는 곳 {i}번째 방문", reviewed_at=datetime(2026, 8, 1),
                )
                session.merge(review_to_row(review))
            session.commit()

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _create_job(self) -> int:
        with self.sf() as session:
            job = JobORM(kind="analyze-pending", status="queued", progress={})
            session.add(job)
            session.commit()
            return job.id

    def _job(self, job_id):
        with self.sf() as session:
            job = session.get(JobORM, job_id)
            return job.status, dict(job.progress or {}), job.error

    def test_estimate_counts(self):
        analyzer = CountingAnalyzer()
        limits = AnalyzeLimits()
        with self.sf() as session:
            estimate = estimate_analysis(session, analyzer.name, analyzer.prompt_version, limits)
        self.assertEqual(estimate["to_analyze"], 4)
        self.assertEqual(estimate["cached_hits"], 0)
        self.assertTrue(estimate["within_limits"])
        self.assertGreater(estimate["estimated_tokens_input"], 0)

    def test_full_run_then_cache_hit(self):
        job_id = self._create_job()
        analyzer = CountingAnalyzer()
        execute_analyze_job(self.sf, job_id, analyzer, AnalyzeLimits())

        status, progress, error = self._job(job_id)
        self.assertEqual(status, "done", error)
        self.assertEqual(progress["completed"], 4)
        self.assertEqual(progress["cached"], 0)
        self.assertEqual(progress["failed"], 0)
        self.assertEqual(progress["tokens_input"], 2000)
        self.assertEqual(len(analyzer.calls), 4)

        with self.sf() as session:
            self.assertEqual(session.query(ReviewAnalysisORM).count(), 4)
            self.assertEqual(session.query(AnalysisCacheORM).count(), 4)

        # 캐시 히트 시나리오: 같은 텍스트+source+rating이 다른 식당으로 재임포트
        # (llm_input_hash는 source+rating+text를 포함하므로 전부 동일해야 캐시 히트)
        with self.sf() as session:
            session.merge(restaurant_to_row(Restaurant("b", "B식당", "한식", 1.0, 2.0)))
            for i in range(4):
                review = Review(
                    id=f"b-r{i}", restaurant_id="b", source="naver_map", rating=4.0,
                    text=f"회사가 근처라 자주 가는 곳 {i}번째 방문", reviewed_at=datetime(2026, 8, 2),
                )
                session.merge(review_to_row(review))
            session.commit()

        job2 = self._create_job()
        analyzer2 = CountingAnalyzer()
        execute_analyze_job(self.sf, job2, analyzer2, AnalyzeLimits())
        status2, progress2, _ = self._job(job2)
        self.assertEqual(status2, "done")
        self.assertEqual(progress2["cached"], 4)
        self.assertEqual(progress2["completed"], 0)
        self.assertEqual(analyzer2.calls, [])  # 재분석 없음 (스펙 §6)
        with self.sf() as session:
            self.assertEqual(session.query(ReviewAnalysisORM).count(), 8)

    def test_partial_failure_continues(self):
        job_id = self._create_job()
        analyzer = CountingAnalyzer(fail_ids={"a-r1", "a-r2"})
        execute_analyze_job(self.sf, job_id, analyzer, AnalyzeLimits(max_estimated_cost_per_job=99))

        status, progress, error = self._job(job_id)
        self.assertEqual(status, "done")  # 개별 실패가 job을 죽이지 않는다 (스펙 §4)
        self.assertEqual(progress["completed"], 2)
        self.assertEqual(progress["failed"], 2)
        self.assertEqual(progress["failed_ids"], ["a-r1", "a-r2"])
        with self.sf() as session:
            self.assertEqual(session.query(ReviewAnalysisORM).count(), 2)

    def test_cost_cap_fails_fast(self):
        job_id = self._create_job()
        tiny_limits = AnalyzeLimits(max_estimated_cost_per_job=0.0001)
        execute_analyze_job(self.sf, job_id, CountingAnalyzer(), tiny_limits)
        status, _, error = self._job(job_id)
        self.assertEqual(status, "failed")
        self.assertIn("상한 초과", error)

    def test_review_cap_truncates(self):
        job_id = self._create_job()
        analyzer = CountingAnalyzer()
        execute_analyze_job(self.sf, job_id, analyzer,
                            AnalyzeLimits(max_reviews_per_job=2, max_estimated_cost_per_job=99,
                                          max_estimated_tokens_per_job=10_000_000))
        status, progress, _ = self._job(job_id)
        self.assertEqual(status, "done")
        self.assertTrue(progress["truncated"])
        self.assertEqual(progress["completed"], 2)
        self.assertEqual(len(analyzer.calls), 2)

    def test_estimate_cost_formula(self):
        limits = AnalyzeLimits(price_input_per_1k=1.0, price_output_per_1k=2.0)
        self.assertAlmostEqual(estimate_cost(limits, 1000, 500), 1.0 + 1.0)


if __name__ == "__main__":
    unittest.main()
