"""Phase 3A API 테스트 — import preview/commit, analyze preview/pending, calibration."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

IMPORT_JSON = """
{"restaurants": [
  {"name": "테스트식당", "category": "한식", "reviews": [
    {"source": "naver_map", "rating": 4.0, "text": "회사가 근처라 자주 가는 곳"},
    {"source": "naver_map", "rating": 5.0, "text": "협찬 받고 다녀왔어요 맛 최고 서비스 최고"},
    {"source": "", "text": "플랫폼 누락"}
  ]}
]}
"""


class Phase3ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["REALMATJIP_ANALYZER"] = "mock"  # 실 LLM 없이 파이프라인 검증
        cls._tmp = TemporaryDirectory()
        cls.app = create_app(Settings(db_path=str(Path(cls._tmp.name) / "p3a.db")))
        cls._client = TestClient(cls.app)
        cls.client = cls._client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client.__exit__(None, None, None)
        cls.app.state.engine.dispose()
        cls._tmp.cleanup()
        os.environ.pop("REALMATJIP_ANALYZER", None)

    def test_01_import_preview_dry_run(self):
        result = self.client.post("/api/admin/import/preview",
                                  json={"format": "json", "content": IMPORT_JSON}).json()
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["valid"], 2)
        self.assertEqual(result["invalid"], 1)
        self.assertEqual(result["estimated_new_reviews"], 2)
        self.assertEqual(result["new_restaurants"], 1)
        self.assertEqual(result["errors"][0]["field"], "source")
        # preview는 DB를 바꾸지 않는다
        stats = self.client.get("/api/admin/stats").json()
        self.assertEqual(stats["reviews"], 0)

    def test_02_import_commit(self):
        result = self.client.post("/api/admin/import/commit",
                                  json={"format": "json", "content": IMPORT_JSON}).json()
        self.assertEqual(result["inserted_restaurants"], 1)
        self.assertEqual(result["inserted_reviews"], 2)
        self.assertEqual(result["invalid"], 1)

        stats = self.client.get("/api/admin/stats").json()
        self.assertEqual(stats["restaurants"], 1)
        self.assertEqual(stats["reviews"], 2)
        self.assertEqual(stats["unanalyzed"], 2)

        # 재커밋 → 전부 중복
        again = self.client.post("/api/admin/import/commit",
                                 json={"format": "json", "content": IMPORT_JSON}).json()
        self.assertEqual(again["inserted_reviews"], 0)
        self.assertEqual(again["skipped_duplicates"], 2)

    def test_03_analyze_preview_then_job(self):
        preview = self.client.post("/api/admin/analyze/preview").json()
        self.assertEqual(preview["to_analyze"], 2)
        self.assertTrue(preview["within_limits"])
        self.assertGreater(preview["estimated_cost"], 0)
        self.assertEqual(preview["analyzer"], "mock-rules-v1")

        started = self.client.post("/api/admin/analyze-pending").json()
        self.assertIn("job_id", started)
        job = self.client.get(f"/api/admin/jobs/{started['job_id']}").json()
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["progress"]["completed"], 2)
        self.assertEqual(job["progress"]["failed"], 0)

        stats = self.client.get("/api/admin/stats").json()
        self.assertEqual(stats["analyzed"], 2)
        self.assertEqual(stats["unanalyzed"], 0)

    def test_04_csv_import_and_commit(self):
        csv_content = ("restaurant_name,source,rating,text\n"
                       "테스트식당,kakao_map,4.0,CSV로 넣은 리뷰 본문\n")
        preview = self.client.post("/api/admin/import/preview",
                                   json={"format": "csv", "content": csv_content}).json()
        self.assertEqual(preview["estimated_new_reviews"], 1)
        self.assertEqual(preview["matched_restaurants"], 1)
        commit = self.client.post("/api/admin/import/commit",
                                  json={"format": "csv", "content": csv_content}).json()
        self.assertEqual(commit["inserted_reviews"], 1)

    def test_05_calibration_after_labels(self):
        export = self.client.get("/api/backup/export").json()
        by_text = {r["text"]: r["id"] for r in export["reviews"]}
        self.assertEqual(len(by_text), 3)  # JSON 2 + CSV 1

        ad_review = by_text["협찬 받고 다녀왔어요 맛 최고 서비스 최고"]
        normal_reviews = [rid for text, rid in by_text.items() if rid != ad_review]
        self.client.post(f"/api/reviews/{ad_review}/label", json={"ad_label": "ad"})
        for rid in normal_reviews:
            self.client.post(f"/api/reviews/{rid}/label", json={"ad_label": "normal"})

        report = self.client.get("/api/admin/calibration").json()
        self.assertEqual(report["n_total_labeled"], 3)
        ad_all = report["ad_axis"]["all"]
        self.assertIn("precision", ad_all)
        self.assertIn("natural", report["ad_axis"])
        self.assertIn("challenge", report["ad_axis"])
        self.assertIn("ad_at_0_5", report)
        self.assertIn("FP = 일반 리뷰", report["note"])

    def test_06_import_bad_format_rejected(self):
        response = self.client.post("/api/admin/import/preview",
                                    json={"format": "xml", "content": "<x/>"})
        self.assertEqual(response.status_code, 400)

    def test_07_analyze_job_cached_on_second_run(self):
        # CSV 리뷰 1건(test_04) 신규 분석 후 재실행 → 신규 없음
        first = self.client.post("/api/admin/analyze-pending").json()
        job1 = self.client.get(f"/api/admin/jobs/{first['job_id']}").json()
        self.assertEqual(job1["status"], "done")
        self.assertEqual(job1["progress"]["completed"], 1)

        second = self.client.post("/api/admin/analyze-pending").json()
        job2 = self.client.get(f"/api/admin/jobs/{second['job_id']}").json()
        self.assertEqual(job2["status"], "done")
        self.assertEqual(job2["progress"]["cached"] + job2["progress"]["completed"], 0)


if __name__ == "__main__":
    unittest.main()
