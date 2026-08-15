"""Calibration (Phase 3A.1) — 2축 분리 + Natural/Challenge Set 구분.

축 1 (Ad): LLM ad_probability vs ad_label ground truth
축 2 (Manipulation): manipulation_risk vs manipulation_label ground truth

데이터셋:
- Natural Sample: 실제 수집 분포 (oversampling 없음) → FP율, prevalence
- Challenge Set: 광고/애매/바이럴 의도적 편중 → recall, 구분 능력

둘을 섞어 하나의 accuracy로 만들지 않는다.
"""
from datetime import datetime

from sqlalchemy import select

from ..db.models import ManualLabelORM, ReviewAnalysisORM, ReviewORM

AD_POSITIVE = ("ad", "likely_ad")


def _axis_metrics(labeled_data, threshold, positive_set, score_key):
    """한 축의 지표를 계산한다."""
    tp = fp = fn = tn = 0
    fp_cases, fn_cases = [], []

    for entry in labeled_data:
        label = entry["label"]
        if label == "ambiguous" or label is None:
            continue
        predicted = entry[score_key] >= threshold
        actual = label in positive_set

        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
            fp_cases.append({
                "review_id": entry["review_id"],
                "score": round(entry[score_key], 3),
                "text": entry["text_snippet"],
                "reason": entry.get("reason", ""),
            })
        elif not predicted and actual:
            fn += 1
            fn_cases.append({
                "review_id": entry["review_id"],
                "score": round(entry[score_key], 3),
                "text": entry["text_snippet"],
                "reason": entry.get("reason", ""),
            })
        else:
            tn += 1

    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None

    return {
        "n_scored": tp + fp + fn + tn,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else None,
        "false_negative_rate": round(fn / (fn + tp), 4) if fn + tp else None,
        "fp_examples": fp_cases[:20],
        "fn_examples": fn_cases[:20],
    }


def calibration_report(session, ad_threshold: float = 0.7,
                       manipulation_threshold: float = 0.3) -> dict:
    """전체 calibration 보고 — 축별 × 데이터셋별 분리."""
    labels = {
        row.review_id: row
        for row in session.execute(select(ManualLabelORM)).scalars()
    }
    analyses = {
        row.review_id: row
        for row in session.execute(select(ReviewAnalysisORM)).scalars()
    }
    reviews = {
        row.id: row
        for row in session.execute(select(ReviewORM)).scalars()
    }

    # 데이터셋별 분류
    natural = []
    challenge = []
    for review_id, label_row in labels.items():
        if review_id not in analyses:
            continue
        review = reviews.get(review_id)
        entry = {
            "review_id": review_id,
            "label": label_row.ad_label,
            "manipulation_label": label_row.manipulation_label,
            "reason": label_row.reason,
            "ad_probability": analyses[review_id].ad_probability,
            "text_snippet": (review.text[:80] + "…") if review else "",
            "dataset": label_row.dataset or "natural",
        }
        if entry["dataset"] == "challenge":
            challenge.append(entry)
        else:
            natural.append(entry)
        # natural에도 라벨이 있으면 natural에 포함 (dataset 필드가 빈 경우)

    # 모든 라벨링된 리뷰를 natural에도 포함 (dataset 구분이 없는 경우)
    all_labeled = natural + [e for e in challenge if e not in natural]

    report = {
        "ad_threshold": ad_threshold,
        "manipulation_threshold": manipulation_threshold,
        "n_total_labeled": len(labels),
        "calculated_at": datetime.utcnow().isoformat(),

        "ad_axis": {
            "all": _axis_metrics(all_labeled, ad_threshold, AD_POSITIVE, "ad_probability"),
            "natural": _axis_metrics(natural, ad_threshold, AD_POSITIVE, "ad_probability"),
            "challenge": _axis_metrics(challenge, ad_threshold, AD_POSITIVE, "ad_probability"),
        },

        "note": (
            "FP = 일반 리뷰(normal)를 광고로 오판. "
            "Natural Sample은 실제 분포의 FP율/prevalence 측정용. "
            "Challenge Set은 recall/구분 능력 측정용."
        ),
    }

    # 추가 threshold
    report["ad_at_0_5"] = _axis_metrics(all_labeled, 0.5, AD_POSITIVE, "ad_probability")
    return report
