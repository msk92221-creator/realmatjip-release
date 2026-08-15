"""Golden Set 자동 집계 스크립트 — source-of-truth JSON 기반.

실행: python realdata/apply_golden_labels.py [--db PATH]
백엔드 실행 중이면 API로, 아니면 직접 DB에 적용한다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def apply_via_api(base_url: str):
    """실행 중인 백엔드 API를 통해 라벨 적용."""
    import urllib.request

    def post(path, body):
        req = urllib.request.Request(
            f"{base_url}{path}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(urllib.request.urlopen(req).read())

    def get(path):
        return json.loads(urllib.request.urlopen(f"{base_url}{path}").read())

    golden = json.loads(
        (Path(__file__).parent / "golden_set_labels.json").read_text(encoding="utf-8")
    )
    defaults = golden["_default"]
    rules = golden["labels"]

    # 전체 리뷰 조회
    restaurants = get(f"{base_url}/api/restaurants?limit=100")
    all_reviews = []
    for rest in restaurants["items"]:
        page = get(f"{base_url}/api/restaurants/{rest['id']}/reviews?ad_filter=off&limit=500")
        all_reviews.extend(page["items"])

    # 라벨 적용
    counts = {"ad": 0, "likely_ad": 0, "ambiguous": 0, "normal": 0}
    manip_counts = {"suspicious": 0, "ambiguous": 0, "normal": 0, "none": 0}
    dataset_counts = {"natural": 0, "challenge": 0}

    for review in all_reviews:
        matched = defaults
        for rule in rules:
            if rule["text_prefix"] in review["text"]:
                matched = rule
                break

        post(f"/api/reviews/{review['id']}/label", {
            "ad_label": matched["ad_label"],
            "manipulation_label": matched.get("manipulation_label"),
            "reason": matched.get("reason", ""),
            "dataset": matched.get("dataset", "natural"),
        })

        counts[matched["ad_label"]] += 1
        ml = matched.get("manipulation_label")
        manip_counts[ml if ml else "none"] += 1
        dataset_counts[matched.get("dataset", "natural")] += 1

    # 검증
    total = sum(counts.values())
    print(f"총 라벨링: {total}개 (원본 {len(all_reviews)}개)")
    print(f"\nAd Ground Truth:")
    for label, n in counts.items():
        print(f"  {label}: {n}")
    print(f"  합계: {total}")
    assert total == len(all_reviews), f"집계 불일치: {total} != {len(all_reviews)}"

    print(f"\nManipulation Ground Truth:")
    for label, n in manip_counts.items():
        print(f"  {label}: {n}")

    print(f"\nDataset 구성:")
    for ds, n in dataset_counts.items():
        print(f"  {ds}: {n}")

    # Calibration
    cal = get(f"{base_url}/api/admin/calibration")
    ad_all = cal["ad_axis"]["all"]
    ad_nat = cal["ad_axis"]["natural"]
    ad_ch = cal["ad_axis"]["challenge"]

    print(f"\n=== Calibration (threshold {cal['ad_threshold']}) ===")
    print(f"All:     n={ad_all['n_scored']} P={ad_all['precision']} R={ad_all['recall']} "
          f"F1={ad_all['f1']} FP율={ad_all['false_positive_rate']}")
    print(f"Natural: n={ad_nat['n_scored']} FP율={ad_nat['false_positive_rate']}")
    print(f"Challenge: n={ad_ch['n_scored']} P={ad_ch['precision']} R={ad_ch['recall']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    apply_via_api(args.url)
