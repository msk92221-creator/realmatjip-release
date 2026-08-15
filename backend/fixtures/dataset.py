"""Synthetic dataset 빌더 — 5개 식당 / 175개 리뷰 (시드 고정, 재현 가능).

식당 구성 (스펙 §38):
  A 더피자랩     60개: 별점 높음 + 광고성 리뷰 다수(블로그 카탈로그형) + 최근 2개월 폭증
  B 을지면옥     34개: 3플랫폼 분산 + 재방문/로컬 리뷰 다수 + 단점 일부 → 이상적인 찐맛집
  C 더블유성수    40개: SNS 바이럴로 최근 1개월 폭증 + near-duplicate 10개
  D 충무노포국밥  16개: 6년에 걸친 노포 리뷰, 장기 꾸준함
  E 그릴하우스청담 25개: 플랫폼별 평가 크게 갈림 (google 4.6~5.0 vs naver 2.8~4.0)

의도된 중복은 C의 viral_dup 10개뿐이다. 나머지 패턴은 placeholder 조합을 모두 달리
뽑아(동일 텍스트 재추출 금지) fixture 자체가 우발적 중복을 만들지 않게 한다.
"""
import random
from datetime import datetime, timedelta

from app.models import Restaurant, Review

from .mock_analyzer import mock_analyze
from .templates import POOLS, TEMPLATES

REFERENCE_DATE = datetime(2026, 8, 15, 12, 0)

# 핵심 invariant (결정 #2) — 고정 기대 순위를 강제하지 않는다:
#   1. A(광고 다수)는 단순 별점 순위 대비 크게 하락해야 한다
#   2. B(로컬 찐맛집)와 D(노포)는 상위권이어야 한다
#   3. E는 플랫폼 불일치로 B/D보다 낮아야 한다
#   4. C(바이럴)는 manipulation risk가 높아야 하나 바이럴이라는 이유만으로 과잉 처벌하지 않는다
#   5. A와 C의 상대 순위는 신호 결과에 맡긴다

RESTAURANTS: list[Restaurant] = [
    Restaurant("rest-a", "더피자랩", "피자·파스타", 37.4852, 127.0186, "서울 서초구 서초대로"),
    Restaurant("rest-b", "을지면옥", "평양냉면", 37.5668, 126.9913, "서울 중구 을지로"),
    Restaurant("rest-c", "더블유성수", "브런치 카페", 37.5444, 127.0560, "서울 성동구 성수동"),
    Restaurant("rest-d", "충무노포국밥", "돼지국밥", 37.5605, 127.0150, "서울 중구 신당동"),
    Restaurant("rest-e", "그릴하우스청담", "스테이크", 37.5271, 127.0440, "서울 강남구 청담동"),
]

EXPECTED_COUNTS = {"rest-a": 60, "rest-b": 34, "rest-c": 40, "rest-d": 16, "rest-e": 25}


def distinct_texts(pattern: str, count: int, rng: random.Random) -> list[str]:
    """템플릿 × placeholder 조합을 펼쳐 서로 다른 텍스트 count개를 샘플."""
    pool: set[str] = set()
    for template in TEMPLATES[pattern]:
        variants = [template]
        for key, values in POOLS.items():
            placeholder = "{" + key + "}"
            if placeholder in template:
                variants = [v.replace(placeholder, value) for v in variants for value in values]
        pool.update(variants)
    assert len(pool) >= count, f"{pattern}: pool {len(pool)} < {count}"
    return rng.sample(sorted(pool), count)


def build_dataset(seed: int = 42) -> tuple[list[Restaurant], list[Review]]:
    rng = random.Random(seed)
    reviews: list[Review] = []
    seq: dict[str, int] = {}

    def add(
        rid: str,
        source: str,
        pattern: str,
        days: int,
        rating_range: tuple[float, float],
        reviewer_range: tuple[int, int],
        text: str,
    ) -> None:
        seq[rid] = seq.get(rid, 0) + 1
        review = Review(
            id=f"{rid}-{seq[rid]:03d}",
            restaurant_id=rid,
            source=source,
            rating=round(rng.uniform(*rating_range), 1),
            text=text,
            reviewed_at=REFERENCE_DATE - timedelta(days=days),
            reviewer_review_count=rng.randint(*reviewer_range),
        )
        review.analysis = mock_analyze(pattern, text, rng)
        reviews.append(review)

    # ── A: 광고성 많음 + 최근 폭발 ─────────────────────────────
    blog_texts = distinct_texts("ad_blog", 30, rng)
    for text in blog_texts:
        add("rest-a", "naver_blog", "ad_blog", rng.randint(3, 60), (4.8, 5.0), (3, 40), text)
    map_texts = distinct_texts("ad_map", 15, rng)
    for text in map_texts:
        add("rest-a", "kakao_map", "ad_map", rng.randint(5, 60), (4.7, 5.0), (1, 8), text)
    normal_texts = distinct_texts("general_positive", 15, rng)
    for text in normal_texts:
        add("rest-a", "naver_map", "general_positive", rng.randint(90, 360), (3.4, 4.4), (10, 120), text)

    # ── B: 3플랫폼 분산 + 로컬/재방문 ──────────────────────────
    b_patterns = ["genuine_local"] * 14 + ["genuine_positive"] * 15 + ["casual_short"] * 5
    b_sources = ["google_places"] * 12 + ["naver_map"] * 12 + ["kakao_map"] * 10
    rng.shuffle(b_patterns)
    rng.shuffle(b_sources)
    b_queues = {
        "genuine_local": distinct_texts("genuine_local", 14, rng),
        "genuine_positive": distinct_texts("genuine_positive", 15, rng),
        "casual_short": distinct_texts("casual_short", 5, rng),
    }
    for source, pattern in zip(b_sources, b_patterns):
        if pattern == "casual_short":
            days, rating, reviewer = rng.randint(10, 300), (4.0, 5.0), (2, 30)
        elif pattern == "genuine_local":
            days, rating, reviewer = rng.randint(20, 540), (4.1, 5.0), (15, 200)
        else:
            days, rating, reviewer = rng.randint(30, 600), (4.1, 5.0), (15, 200)
        add("rest-b", source, pattern, days, rating, reviewer, b_queues[pattern].pop())

    # ── C: 바이럴 폭증 + near-duplicate ────────────────────────
    base_texts = distinct_texts("tourist_casual", 10, rng)
    for text in base_texts:
        add("rest-c", "naver_map", "tourist_casual", rng.randint(120, 240), (3.5, 4.5), (5, 80), text)
    viral_sources = ["naver_map"] * 10 + ["kakao_map"] * 7 + ["manual_import"] * 3
    rng.shuffle(viral_sources)
    viral_texts = distinct_texts("viral_tourist", 20, rng)
    for source, text in zip(viral_sources, viral_texts):
        add("rest-c", source, "viral_tourist", rng.randint(3, 30), (4.5, 5.0), (3, 50), text)
    for i, text in enumerate(TEMPLATES["viral_dup"]):
        add("rest-c", "naver_map", "viral_dup", 3 + i * 2, (4.6, 5.0), (1, 5), text)

    # ── D: 오래된 노포, 장기 꾸준함 ────────────────────────────
    add("rest-d", "naver_map", "genuine_local", rng.randint(100, 130), (4.3, 4.8), (20, 150),
        distinct_texts("genuine_local", 2, rng).pop())
    add("rest-d", "google_places", "genuine_local", rng.randint(130, 160), (4.3, 4.8), (20, 150),
        distinct_texts("genuine_local", 2, rng).pop())
    d_patterns = ["genuine_local"] * 8 + ["nopo_old"] * 6
    d_sources = ["naver_map"] * 7 + ["google_places"] * 7
    rng.shuffle(d_patterns)
    rng.shuffle(d_sources)
    d_queues = {
        "genuine_local": distinct_texts("genuine_local", 8, rng),
        "nopo_old": distinct_texts("nopo_old", 6, rng),
    }
    for source, pattern in zip(d_sources, d_patterns):
        add("rest-d", source, pattern, rng.randint(550, 2100), (4.0, 5.0), (10, 180),
            d_queues[pattern].pop())

    # ── E: 플랫폼별 평가 갈림 ──────────────────────────────────
    e_texts = distinct_texts("enthusiastic_short", 20, rng)
    for text in e_texts:
        add("rest-e", "google_places", "enthusiastic_short", rng.randint(10, 180), (4.6, 5.0), (8, 150), text)
    crit_texts = distinct_texts("critical_specific", 5, rng)
    for text in crit_texts:
        add("rest-e", "naver_map", "critical_specific", rng.randint(30, 240), (2.8, 4.0), (20, 150), text)

    assert len(reviews) == sum(EXPECTED_COUNTS.values()) == 175
    for rid, expected in EXPECTED_COUNTS.items():
        actual = sum(1 for r in reviews if r.restaurant_id == rid)
        assert actual == expected, f"{rid}: {actual} != {expected}"
    return RESTAURANTS, reviews
