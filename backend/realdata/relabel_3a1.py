"""59개 리뷰 재라벨링 (Phase 3A.1 기준) — 광고와 조작을 분리하고
카탈로그형/홍보성 문체만으로 ad_likely가 된 리뷰를 재검토한다.

새 기준:
- ad: 협찬/제공받음/체험단/원고료 명시 → 해당 없음 (원문에 명시적 disclosure 없음)
- likely_ad: 직접 disclosure 없지만 복합 정황으로 광고 가능성 매우 높음 → 카탈로그형 블로그
- ambiguous: 광고처럼 보이지만 근거 불충분 → 바이럴/유사문구
- normal: 광고 판단 근거 없음 → 대부분의 일반 리뷰
"""
import json
import urllib.request

def post(path, body):
    req = urllib.request.Request(
        f"http://127.0.0.1:8000{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req).read())

def get(path):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:8000{path}").read())

# ── 재라벨링 기준표 ──────────────────────────────────────────
# 각 리뷰 텍스트의 특징적 키워드로 판별

RELABEL_RULES = [
    # naver_blog 카탈로그형 (주소+영업시간+주차+전항목칭찬+강추)
    # → 직접 disclosure는 없지만 복합 정황으로 광고 가능성 매우 높음 → likely_ad
    {"pattern": "맛집 찾아서 다녀왔습니다", "ad_label": "likely_ad",
     "manipulation_label": None,
     "reason": "블로그 카탈로그형: 주소/영업시간/주차 정보 체계적 나열 + 전 항목 칭찬 + 강추 CTA. 복합 정황으로 광고 가능성 높음",
     "dataset": "challenge"},
    {"pattern": "맛집으로 유명한 곳에 다녀왔습니다", "ad_label": "likely_ad",
     "manipulation_label": None,
     "reason": "블로그 카탈로그형: 찾아가는 길 + USP + 연예인 언급 + 강추",
     "dataset": "challenge"},
    {"pattern": "수제돈까스 다녀왔어요", "ad_label": "likely_ad",
     "manipulation_label": None,
     "reason": "블로그 카탈로그형: 위치/주차/영업시간/예약방법 + 인스타감성 + 데이트 강추",
     "dataset": "challenge"},
    {"pattern": "스테이크 하우스를 찾아서", "ad_label": "likely_ad",
     "manipulation_label": None,
     "reason": "블로그 카탈로그형: 1++한우 + 발렛 + 예약안내 + 코스가격 + 전 항목 만점",
     "dataset": "challenge"},

    # 바이럴/유사문구 (성수동 카페 3개) — 조작은 의심되지만 광고 ground truth는 없음
    {"pattern": "성수동 새로 생긴 카페", "ad_label": "ambiguous",
     "manipulation_label": "suspicious",
     "reason": "유사 문구가 서로 다른 리뷰어명으로 3개 반복 — 조작 의심. 광고 여부는 근거 불충분",
     "dataset": "challenge"},

    # 바이럴 관광객 (SNS/유튜브 보고 온 리뷰들) — 바이럴 자체는 광고가 아님
    {"pattern": "유튜브 보고 왔어요", "ad_label": "normal",
     "manipulation_label": None,
     "reason": "SNS 바이럴 반응형이지만 광고 근거 없음 — 정상 관광객 리뷰",
     "dataset": "natural"},
    {"pattern": "인스타에서 보고 왔는데", "ad_label": "normal",
     "manipulation_label": None,
     "reason": "SNS 보고 방문 — 광고 근거 없음",
     "dataset": "natural"},
    {"pattern": "SNS에서 제일 핫한", "ad_label": "normal",
     "manipulation_label": None,
     "reason": "SNS 바이럴 반응 — 광고 근거 없음",
     "dataset": "natural"},
    {"pattern": "릴스 보고 바로 왔어요", "ad_label": "normal",
     "manipulation_label": None,
     "reason": "SNS 보고 방문 — 광고 근거 없음",
     "dataset": "natural"},
]

# 나머지는 전부 normal + natural (기본값)
DEFAULT_LABEL = {
    "ad_label": "normal",
    "manipulation_label": None,
    "reason": "",
    "dataset": "natural",
}


def classify_review(text: str) -> dict:
    for rule in RELABEL_RULES:
        if rule["pattern"] in text:
            return rule
    return DEFAULT_LABEL


def main():
    restaurants = get("/api/restaurants?limit=100")
    total_relabeled = 0
    changes = {"to_likely_ad": 0, "to_ambiguous": 0, "to_normal": 0, "manip_suspicious": 0}

    for rest in restaurants["items"]:
        reviews = get(f"/api/restaurants/{rest['id']}/reviews?ad_filter=off&limit=500")
        for item in reviews["items"]:
            result = classify_review(item["text"])
            post(f"/api/reviews/{item['id']}/label", result)
            total_relabeled += 1
            if result["ad_label"] == "likely_ad":
                changes["to_likely_ad"] += 1
            elif result["ad_label"] == "ambiguous":
                changes["to_ambiguous"] += 1
            else:
                changes["to_normal"] += 1
            if result.get("manipulation_label") == "suspicious":
                changes["manip_suspicious"] += 1

    print(f"총 재라벨링: {total_relabeled}개")
    print(f"변경 내역: {changes}")

    # 통계 확인
    stats = get("/api/admin/stats")
    print(f"\nad_labels: {stats['ad_labels']}")
    print(f"manipulation_labels: {stats['manipulation_labels']}")

    # Calibration
    cal = get("/api/admin/calibration")
    ad = cal["ad_axis"]["all"]
    print(f"\n=== AD Calibration (all, threshold {cal['ad_threshold']}) ===")
    for k in ("n_scored", "precision", "recall", "f1", "false_positive_rate", "false_negative_rate"):
        print(f"  {k}: {ad[k]}")
    print(f"\n=== Natural ===")
    nat = cal["ad_axis"]["natural"]
    print(f"  n={nat['n_scored']} P={nat['precision']} R={nat['recall']} FP율={nat['false_positive_rate']}")
    print(f"\n=== Challenge ===")
    ch = cal["ad_axis"]["challenge"]
    print(f"  n={ch['n_scored']} P={ch['precision']} R={ch['recall']} FN율={ch['false_negative_rate']}")


if __name__ == "__main__":
    main()
