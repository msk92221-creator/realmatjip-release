"""Phase 3B.1 Smoke Test — Google Places 실제 호출 1회 검증 (스펙 §4).

사용법:
    set GOOGLE_PLACES_API_KEY=...   (노출 금지 — 스크립트는 키를 절대 출력하지 않는다)
    python realdata/smoke_test_google.py [검색어]

검증 항목 (스펙 §4 Smoke Test):
    1. Text Search 1회 → 후보 식당 파싱
    2. 상위 1곳 Place Details + 리뷰 샘플 파싱
    3. HTTP status / Google error code 상세 보고 (실패 시)
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.providers.google_places.client import GooglePlacesClient, GooglePlacesError
from app.providers.google_places.mapper import parse_google_place, parse_google_review


def mask_key(key: str) -> str:
    """키 마스킹 — 앞 4자리만. 로그/출력에 전체 키가 절대 나가지 않게 한다."""
    return f"{key[:4]}***({len(key)}자)" if key else "(없음)"


def main() -> int:
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
    query = sys.argv[1] if len(sys.argv) > 1 else "강남역 떡볶이"

    print(f"[smoke] query={query!r}")
    print(f"[smoke] GOOGLE_PLACES_API_KEY={mask_key(api_key)}")
    if not api_key:
        print("[FAIL] GOOGLE_PLACES_API_KEY 환경변수가 비어 있습니다.")
        return 2

    client = GooglePlacesClient(api_key=api_key)
    try:
        # 1) Text Search
        print("\n=== 1) Text Search ===")
        response = client.search_text(query, max_results=3)
        places = response.get("places", [])
        print(f"HTTP 200 — {len(places)}곳 반환")
        if not places:
            print("[FAIL] 검색 결과 0곳 — 쿼리 또는 과금 계정 상태 확인 필요")
            return 1

        for i, p in enumerate(places, 1):
            rest = parse_google_place(p)
            reviews = p.get("reviews", [])
            print(f"  [{i}] {rest.name} | place_id={rest.provider_place_id} | "
                  f"rating={rest.rating} | reviews_in_search={len(reviews)}")

        # 2) Place Details (상위 1곳)
        print("\n=== 2) Place Details (상위 1곳) ===")
        top_id = parse_google_place(places[0]).provider_place_id
        detail = client.get_place_detail(top_id)
        rest = parse_google_place(detail)
        reviews = [parse_google_review(r, top_id) for r in detail.get("reviews", [])]
        print(f"  name={rest.name} | address={rest.formatted_address}")
        print(f"  rating={rest.rating} | user_rating_count={rest.user_rating_count}")
        print(f"  review_count={len(reviews)} (Places API는 식당당 최대 5개만 준다 — 스펙 §6)")
        for r in reviews:
            text_head = (r.text or "")[:60].replace("\n", " ")
            date = r.published_at.strftime("%Y-%m-%d") if r.published_at else "?"
            print(f"    - rating={r.rating} date={date} text={text_head!r}")

        # 3) 판정
        print("\n=== 3) SMOKE RESULT ===")
        checks = [
            ("Text Search 반환", len(places) >= 1),
            ("Place Details 파싱", rest.name != ""),
            ("리뷰 ≥ 1개", len(reviews) >= 1),
        ]
        passed = all(ok for _, ok in checks)
        for name, ok in checks:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        print(f"\n[{'PASS' if passed else 'FAIL'}] Smoke Test {'통과' if passed else '실패'}")
        return 0 if passed else 1

    except GooglePlacesError as e:
        print(f"\n[FAIL] GooglePlacesError: {e}")
        print(f"  status_code={e.status_code!r}")
        return 1
    except Exception:
        print("\n[FAIL] 예상치 못한 오류:")
        traceback.print_exc()
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
