"""Phase 1 API 종단 테스트 — fixture seed → 재계산 → 조회/라벨/백업 전체 흐름."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app


class ApiFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        cls.settings = Settings(db_path=str(Path(cls._tmp.name) / "test.db"))
        cls.app = create_app(cls.settings)
        cls._client = TestClient(cls.app)
        cls.client = cls._client.__enter__()
        cls.client.post("/api/admin/seed")

    @classmethod
    def tearDownClass(cls):
        cls._client.__exit__(None, None, None)
        cls.app.state.engine.dispose()  # Windows: 파일 핸들을 놓아야 임시 디렉터리 정리 가능
        cls._tmp.cleanup()

    # ── 기본 ──────────────────────────────────────────────────

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_meta(self):
        meta = self.client.get("/api/meta").json()
        self.assertEqual(meta["algorithm_version"], "v0.1-phase0")
        self.assertEqual(meta["analyzer"], "mock-v1")
        self.assertEqual(meta["ad_filter_levels"]["basic"], 0.7)
        self.assertFalse(meta["auth_required"])

    def test_seed_counts(self):
        stats = self.client.get("/api/admin/stats").json()
        self.assertEqual(stats["restaurants"], 5)
        self.assertEqual(stats["reviews"], 175)
        self.assertEqual(stats["analyzed"], 175)
        self.assertEqual(stats["unanalyzed"], 0)
        self.assertIn("naver_blog", stats["reviews_by_source"])

    # ── 재계산 잡 ────────────────────────────────────────────

    def test_01_recalculate_job(self):
        created = self.client.post("/api/admin/recalculate").json()
        self.assertIn("job_id", created)
        job = self.client.get(f"/api/admin/jobs/{created['job_id']}").json()
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["progress"]["total"], 5)

    def test_job_404(self):
        self.assertEqual(self.client.get("/api/admin/jobs/99999").status_code, 404)

    # ── 목록/상세 ────────────────────────────────────────────

    def test_list_ranking_order(self):
        result = self.client.get("/api/restaurants").json()
        ids = [item["id"] for item in result["items"]]
        # Phase 0 시뮬레이션과 동일 순서 (D > B > E > C > A)
        self.assertEqual(ids, ["rest-d", "rest-b", "rest-e", "rest-c", "rest-a"])
        top = result["items"][0]
        for key in ("overall_a", "overall_b", "n_eff", "evidence_strength",
                    "evidence_label", "local_badge", "manipulation_score"):
            self.assertIn(key, top)

    def test_list_filters(self):
        local_only = self.client.get("/api/restaurants", params={"local_only": True}).json()
        # Phase 0 결과: 로컬배지는 B/D/E (E는 local_evidence 2.8로 배지 통과)
        self.assertEqual({i["id"] for i in local_only["items"]}, {"rest-b", "rest-d", "rest-e"})

        query = self.client.get("/api/restaurants", params={"q": "면옥"}).json()
        self.assertEqual([i["id"] for i in query["items"]], ["rest-b"])

        high = self.client.get("/api/restaurants", params={"min_overall": 70}).json()
        self.assertEqual({i["id"] for i in high["items"]}, {"rest-d", "rest-b"})

    def test_detail(self):
        detail = self.client.get("/api/restaurants/rest-b").json()
        self.assertEqual(detail["name"], "을지면옥")
        self.assertTrue(60 <= detail["scores"]["overall_a"] <= 90)
        explanation = detail["detail"]["explanation"]
        self.assertEqual(len(explanation), 7)  # 가산 6항목 + manipulation
        self.assertIn("label", explanation[0])
        self.assertTrue(detail["detail"]["signals"]["local_badge"])
        self.assertGreaterEqual(len(detail["detail"]["platforms"]), 2)
        self.assertTrue(0 < detail["detail"]["signals"]["evidence_strength"] <= 1)

    def test_detail_not_found(self):
        self.assertEqual(self.client.get("/api/restaurants/nope").status_code, 404)

    # ── 리뷰 조회 / 광고 필터 ─────────────────────────────────

    def test_reviews_ad_filter(self):
        off = self.client.get("/api/restaurants/rest-a/reviews", params={"ad_filter": "off"}).json()
        self.assertEqual(off["total"], 60)

        basic = self.client.get("/api/restaurants/rest-a/reviews", params={"ad_filter": "basic"}).json()
        self.assertLess(basic["returned"], 60)  # 광고 가능성 ≥0.7 제외
        self.assertEqual(basic["threshold"], 0.7)
        for item in basic["items"]:
            self.assertLess(item["analysis"]["ad_probability"], 0.7)

        strict = self.client.get("/api/restaurants/rest-a/reviews", params={"ad_filter": "strict"}).json()
        self.assertLessEqual(strict["returned"], basic["returned"])

    def test_reviews_not_found(self):
        self.assertEqual(
            self.client.get("/api/restaurants/nope/reviews").status_code, 404
        )

    # ── 수동 라벨 → 재계산 반영 ───────────────────────────────

    def _overall_a(self, restaurant_id: str) -> float:
        detail = self.client.get(f"/api/restaurants/{restaurant_id}").json()
        return detail["scores"]["overall_a"]

    def test_manual_label_overrides_llm(self):
        before = self._overall_a("rest-a")
        ad_reviews = [
            item for item in self.client.get(
                "/api/restaurants/rest-a/reviews", params={"ad_filter": "off", "limit": 500}
            ).json()["items"]
            if item["analysis"]["ad_probability"] >= 0.7
        ]
        self.assertGreaterEqual(len(ad_reviews), 30)
        for item in ad_reviews[:10]:  # 광고 10개를 '일반 리뷰'로 수동 판정
            response = self.client.post(f"/api/reviews/{item['id']}/label",
                                        json={"ad_label": "normal"})
            self.assertEqual(response.status_code, 200)

        stats = self.client.get("/api/admin/stats").json()
        self.assertEqual(stats["ad_labels"], {"normal": 10})

        self.client.post("/api/admin/recalculate")
        after = self._overall_a("rest-a")
        # 사람의 판정이 LLM보다 우선 → 광고로 감점됐던 리뷰 10개가 복원되어 상승
        self.assertGreater(after, before)

    def test_label_validation_and_clear(self):
        invalid = self.client.post("/api/reviews/rest-a-001/label", json={"ad_label": "sure"})
        self.assertEqual(invalid.status_code, 422)

        missing = self.client.post("/api/reviews/zzz/label", json={"ad_label": "ad"})
        self.assertEqual(missing.status_code, 404)

        cleared = self.client.post("/api/reviews/rest-a-001/label", json={})
        self.assertEqual(cleared.status_code, 200)
        self.assertTrue(cleared.json()["cleared"])

    # ── 백업 ─────────────────────────────────────────────────

    def test_backup_export(self):
        self.client.post("/api/admin/recalculate")  # 이력 2배치 이상 보장 (자족적)
        export = self.client.get("/api/backup/export").json()
        for key in ("restaurants", "reviews", "review_analysis", "manual_labels",
                    "restaurant_scores", "jobs"):
            self.assertIn(key, export)
        self.assertEqual(len(export["restaurants"]), 5)
        self.assertEqual(len(export["reviews"]), 175)
        # 점수 이력이 배치별로 보존된다
        self.assertGreaterEqual(len(export["restaurant_scores"]), 10)


class FreshDbListTest(unittest.TestCase):
    """재계산 전에는 목록이 비어 있어야 한다 (스코어링 완료 후 노출 원칙)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        cls.app = create_app(Settings(db_path=str(Path(cls._tmp.name) / "fresh.db")))
        cls._client = TestClient(cls.app)
        cls.client = cls._client.__enter__()
        cls.client.post("/api/admin/seed")

    @classmethod
    def tearDownClass(cls):
        cls._client.__exit__(None, None, None)
        cls.app.state.engine.dispose()
        cls._tmp.cleanup()

    def test_list_empty_before_recalculate(self):
        result = self.client.get("/api/restaurants").json()
        self.assertEqual(result["count"], 0)
        detail = self.client.get("/api/restaurants/rest-b").json()
        self.assertIsNone(detail["scores"])


class AuthFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        settings = Settings(
            db_path=str(Path(cls._tmp.name) / "auth.db"), auth_token="secret-token"
        )
        cls.app = create_app(settings)
        cls._client = TestClient(cls.app)
        cls.client = cls._client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client.__exit__(None, None, None)
        cls.app.state.engine.dispose()
        cls._tmp.cleanup()

    def test_token_required(self):
        self.assertEqual(self.client.get("/api/meta").status_code, 401)
        ok = self.client.get("/api/meta", headers={"Authorization": "Bearer secret-token"})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["auth_required"])


if __name__ == "__main__":
    unittest.main()
