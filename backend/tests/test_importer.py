"""Import 파서/서비스 테스트 — JSON(nested/flat)/CSV, 검증, 중복, raw 보존."""
import unittest

from app.db.database import init_db, make_engine, make_session_factory
from app.db.models import ReviewORM
from app.importer.parser import parse_payload
from app.importer.service import commit_import, preview_import

JSON_NESTED = """
{
  "restaurants": [
    {"name": "을지면옥", "category": "냉면", "lat": 37.56, "lng": 126.99,
     "reviews": [
       {"source": "naver_map", "rating": 4.0, "text": "회사가 근처라 자주 가는 곳"},
       {"source": "kakao_map", "text": "맛있어요"}
     ]},
    {"name": "충무국밥", "reviews": [
       {"source": "naver_map", "text": "국물이 진해요", "reviewed_at": "2026-07-01"}
     ]}
  ]
}
"""


class ParserTest(unittest.TestCase):
    def test_json_nested(self):
        parsed, errors = parse_payload("json", JSON_NESTED)
        self.assertEqual(errors, [])
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0].restaurant_name, "을지면옥")
        self.assertEqual(parsed[0].rating, 4.0)
        self.assertEqual(parsed[2].reviewed_at.year, 2026)
        self.assertEqual(parsed[2].reviewed_at.month, 7)

    def test_json_flat_reviews(self):
        content = """{"reviews": [
          {"restaurant": {"name": "을지면옥", "category": "냉면"},
           "source": "naver_map", "text": "괜찮음"},
          {"restaurant_name": "충무국밥", "source": "kakao_map", "text": "좋음"}
        ]}"""
        parsed, errors = parse_payload("json", content)
        self.assertEqual(errors, [])
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].category, "냉면")

    def test_validation_errors(self):
        content = """{"reviews": [
          {"restaurant_name": "A식당", "source": "naver_map", "text": ""},
          {"restaurant_name": "A식당", "source": "", "text": "텍스트"},
          {"restaurant_name": "A식당", "source": "naver_map", "text": "정상", "rating": 9.9}
        ]}"""
        parsed, errors = parse_payload("json", content)
        self.assertEqual(parsed, [])
        self.assertEqual(len(errors), 3)
        fields = {e.field for e in errors}
        self.assertEqual(fields, {"text", "source", "rating"})

    def test_csv(self):
        csv_content = (
            "restaurant_name,category,source,rating,text,reviewed_at\n"
            "을지면옥,냉면,naver_map,4.5,맛있는 냉면,2026-08-01\n"
            "충무국밥,,kakao_map,,국밥 맛집\n"
        )
        parsed, errors = parse_payload("csv", csv_content)
        self.assertEqual(errors, [])
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].rating, 4.5)
        self.assertIsNone(parsed[1].rating)

    def test_csv_bad_header(self):
        parsed, errors = parse_payload("csv", "a,b\n1,2\n")
        self.assertEqual(parsed, [])
        self.assertIn("restaurant_name", errors[0].reason)

    def test_unknown_format(self):
        _, errors = parse_payload("xml", "<x/>")
        self.assertIn("지원하지 않는", errors[0].reason)

    def test_invalid_json_file(self):
        _, errors = parse_payload("json", "{not json")
        self.assertIn("JSON 파싱 실패", errors[0].reason)


class ImportServiceTest(unittest.TestCase):
    def setUp(self):
        import tempfile, os
        self.tmp = tempfile.TemporaryDirectory()
        url = "sqlite:///" + os.path.join(self.tmp.name, "import.db").replace("\\", "/")
        self.engine = make_engine(url)
        init_db(self.engine)
        self.session_factory = make_session_factory(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def test_preview_then_commit_with_dup_detection(self):
        with self.session_factory() as session:
            first = preview_import(session, "json", JSON_NESTED)
            self.assertEqual(first.valid, 3)
            self.assertEqual(first.invalid, 0)
            self.assertEqual(first.estimated_new_reviews, 3)
            self.assertEqual(first.new_restaurants, 2)

            commit = commit_import(session, "json", JSON_NESTED)
            self.assertEqual(commit.inserted_restaurants, 2)
            self.assertEqual(commit.inserted_reviews, 3)

            # 동일 파일 재임포트 → 전부 중복
            second = preview_import(session, "json", JSON_NESTED)
            self.assertEqual(second.exact_duplicates, 3)
            self.assertEqual(second.estimated_new_reviews, 0)
            self.assertEqual(second.matched_restaurants, 2)
            self.assertEqual(second.new_restaurants, 0)

            # 같은 식당에 새 리뷰 하나만 추가
            extra = '{"restaurants": [{"name": "을지면옥", "reviews": [' \
                    '{"source": "naver_map", "text": "새로운 리뷰 본문"}]}]}'
            third = preview_import(session, "json", extra)
            self.assertEqual(third.exact_duplicates, 0)
            self.assertEqual(third.estimated_new_reviews, 1)
            self.assertEqual(third.new_restaurants, 0)
            self.assertEqual(third.matched_restaurants, 1)

    def test_raw_payload_preserved(self):
        with self.session_factory() as session:
            commit_import(session, "json", JSON_NESTED)
            rows = session.query(ReviewORM).all()
            self.assertEqual(len(rows), 3)
            for row in rows:
                self.assertIsNotNone(row.raw_payload)
                self.assertIn("_import", row.raw_payload)
                self.assertEqual(row.raw_payload["_import"]["format"], "json")
            # 원본 행 필드 보존 확인
            first = next(r for r in rows if "회사가 근처" in r.text)
            self.assertEqual(first.raw_payload["source"], "naver_map")


if __name__ == "__main__":
    unittest.main()
