"""Phase 3A.4 — Golden Set 59 Full Baseline 평가 스크립트.

모든 평가 조건 고정:
  model=glm-4.5-flash, thinking=disabled, temperature=0,
  response_format=json_object, max_tokens=2048,
  prompt=review-analysis-v1, golden_set=golden-v1, scoring=v0.1-phase0

Usage:
  python realdata/run_golden_baseline.py --mode fresh    # 59개 fresh (캐시 우회)
  python realdata/run_golden_baseline.py --mode cache    # 캐시 히트 확인
  python realdata/run_golden_baseline.py --mode source-bias  # counterfactual
  python realdata/run_golden_baseline.py --mode rating-bias  # counterfactual
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.analysis.schema import (
    AnalysisParseError, load_system_prompt, load_examples,
    parse_llm_analysis, analysis_to_cache_dict,
)
from app.analysis.verification import verify_analysis
from app.analysis.input_hash import llm_input_hash
from app.models import Review

GOLDEN_SET_VERSION = "golden-v1"
SCORING_VERSION = "v0.1-phase0"
AD_PRIOR = 0.30  # ScoringConfig 기본값

BASE_URL = "https://api.z.ai/api/paas/v4"
MODEL = "glm-4.5-flash"
INFERENCE_CONFIG = "v2-thinking-off-json-2048"
PROMPT_VERSION = "review-analysis-v1"


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def load_golden():
    """source-of-truth에서 59개 리뷰 + 라벨 로드."""
    import_data = json.loads(
        (Path(__file__).parent / "import_phase3a.json").read_text(encoding="utf-8"))
    golden_labels = json.loads(
        (Path(__file__).parent / "golden_set_labels.json").read_text(encoding="utf-8"))

    defaults = golden_labels["_default"]
    rules = golden_labels["labels"]

    reviews = []
    for rest in import_data["restaurants"]:
        for rv in rest["reviews"]:
            # 라벨 매칭
            label = dict(defaults)
            for rule in rules:
                if rule["text_prefix"] in rv["text"]:
                    label = rule
                    break

            review = Review(
                id=f"gold-{len(reviews):03d}",
                restaurant_id=rest["name"],
                source=rv["source"],
                rating=rv.get("rating"),
                text=rv["text"],
                reviewed_at=datetime(2026, 8, 15),
            )
            reviews.append({
                "review": review,
                "ad_label": label["ad_label"],
                "manipulation_label": label.get("manipulation_label"),
                "dataset": label.get("dataset", "natural"),
                "reason": label.get("reason", ""),
                "restaurant": rest["name"],
            })
    return reviews


def call_llm(api_key, review, client, system_messages):
    """단일 LLM 호출 — raw response와 메타데이터 반환."""
    payload = {"source": review.source, "rating": review.rating, "text": review.text}
    messages = system_messages + [
        {"role": "user", "content": "리뷰를 분석해 JSON만 반환:\n" + json.dumps(payload, ensure_ascii=False)}
    ]

    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 2048,
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
    }

    start = time.time()
    response = client.post(f"{BASE_URL}/chat/completions", json=body)
    elapsed = round((time.time() - start) * 1000)

    if response.status_code != 200:
        return {
            "http_error": response.status_code,
            "raw_response": response.text[:300],
            "latency_ms": elapsed,
            "attempts": 3,
            "analysis": None,
        }

    data = response.json()
    choice = data["choices"][0]
    content = choice["message"]["content"]
    usage = data.get("usage", {})

    # 파싱 + 검증
    attempts = 1
    validation_errors = []
    analysis = None
    try:
        analysis = parse_llm_analysis(content, analyzer=f"zai:{MODEL}:{INFERENCE_CONFIG}")
        analysis = verify_analysis(analysis, review.text)
    except AnalysisParseError as e:
        attempts = 2
        validation_errors.append(str(e))
        # repair retry
        repair_messages = messages + [
            {"role": "assistant", "content": content[:1500]},
            {"role": "user", "content": f"이전 응답이 schema validation에 실패했다 ({e}). 다음 schema에 맞는 JSON만 다시 반환하라."},
        ]
        body["messages"] = repair_messages
        response2 = client.post(f"{BASE_URL}/chat/completions", json=body)
        if response2.status_code == 200:
            data2 = response2.json()
            content2 = data2["choices"][0]["message"]["content"]
            usage = data2.get("usage", usage)
            try:
                analysis = parse_llm_analysis(content2, analyzer=f"zai:{MODEL}:{INFERENCE_CONFIG}")
                analysis = verify_analysis(analysis, review.text)
                content = content2
            except AnalysisParseError as e2:
                attempts = 3
                validation_errors.append(str(e2))

    return {
        "finish_reason": choice.get("finish_reason"),
        "raw_response": content[:5000],
        "latency_ms": elapsed,
        "attempts": attempts,
        "validation_errors": validation_errors,
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "analysis": analysis,
    }


def compute_p_eff(ad_probability, ad_confidence, ad_prior=AD_PRIOR):
    """Phase 0 scoring과 동일한 p_eff 공식."""
    return ad_confidence * ad_probability + (1 - ad_confidence) * ad_prior


def run_fresh_baseline():
    """59개 전체를 fresh로 호출하고 전체 결과를 저장."""
    api_key = os.environ.get("ZAI_API_KEY", "")
    if not api_key:
        print("오류: ZAI_API_KEY 없음")
        return

    golden = load_golden()
    print(f"Golden Set: {len(golden)}개 (v{GOLDEN_SET_VERSION})")
    print(f"Model: {MODEL} | Config: {INFERENCE_CONFIG}")
    print(f"Prompt: {PROMPT_VERSION} | Scoring: {SCORING_VERSION}\n")

    system_prompt = load_system_prompt()
    examples = load_examples()
    system_messages = [{"role": "system", "content": system_prompt}]
    for ex in examples:
        system_messages.append({"role": "user", "content": "리뷰를 분석해 JSON만 반환:\n" + json.dumps(ex["review"], ensure_ascii=False)})
        system_messages.append({"role": "assistant", "content": json.dumps(ex["output"], ensure_ascii=False)})

    client = httpx.Client(
        timeout=httpx.Timeout(120.0),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )

    results = []
    total_tokens_in = 0
    total_tokens_out = 0
    latencies = []
    first_pass = 0
    repair = 0
    fallback = 0

    for i, entry in enumerate(golden):
        review = entry["review"]
        result = call_llm(api_key, review, client, system_messages)

        analysis = result.get("analysis")
        if analysis is None:
            from app.analysis.schema import needs_manual_fallback
            analysis = needs_manual_fallback(f"zai:{MODEL}", "; ".join(result.get("validation_errors", [])))
            fallback += 1
        elif result["attempts"] == 1:
            first_pass += 1
        else:
            repair += 1

        p_eff = compute_p_eff(analysis.ad_probability, analysis.ad_confidence)

        row = {
            "review_id": review.id,
            "restaurant": entry["restaurant"],
            "short_text": review.text[:60],
            "source": review.source,
            "rating": review.rating,
            "ground_truth_ad": entry["ad_label"],
            "ground_truth_manipulation": entry["manipulation_label"],
            "dataset": entry["dataset"],
            "label_reason": entry["reason"],
            "ad_probability": analysis.ad_probability,
            "ad_confidence": analysis.ad_confidence,
            "p_eff": round(p_eff, 4),
            "authenticity": analysis.authenticity,
            "specificity": analysis.specificity,
            "local_probability": analysis.local_probability,
            "ad_signals": [{"code": s.code, "quote": s.quote} for s in analysis.ad_signals],
            "authentic_signals": [{"code": s.code, "quote": s.quote} for s in analysis.authentic_signals],
            "signals_dropped": analysis.flags.get("signals_dropped", 0),
            "needs_manual": analysis.flags.get("needs_manual_review", False),
            "attempts": result["attempts"],
            "validation_errors": result.get("validation_errors", []),
            "input_tokens": result.get("input_tokens", 0),
            "output_tokens": result.get("output_tokens", 0),
            "latency_ms": result["latency_ms"],
            "finish_reason": result.get("finish_reason"),
            "raw_response": result.get("raw_response", ""),
        }
        results.append(row)

        total_tokens_in += row["input_tokens"]
        total_tokens_out += row["output_tokens"]
        latencies.append(row["latency_ms"])

        match = "?"
        gt = entry["ad_label"]
        if gt != "ambiguous":
            expected_pos = gt in ("ad", "likely_ad")
            actual_pos = analysis.ad_probability >= 0.7
            match = "✓" if expected_pos == actual_pos else "✗"
        else:
            match = "~"

        print(f"  {i+1:3d}/{len(golden)} {review.id:10s} [{review.source:14s}] "
              f"gt={gt:10s} p={analysis.ad_probability:.2f} pe={p_eff:.2f} "
              f"c={analysis.ad_confidence:.2f} loc={analysis.local_probability:.2f} "
              f"{match} {row['latency_ms']:6d}ms")

    client.close()

    latencies.sort()
    summary = {
        "run_id": f"golden-baseline-{utcnow().strftime('%Y%m%d-%H%M')}",
        "golden_set_version": GOLDEN_SET_VERSION,
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "inference_config_version": INFERENCE_CONFIG,
        "scoring_algorithm_version": SCORING_VERSION,
        "ad_prior": AD_PRIOR,
        "timestamp": utcnow().isoformat(),
        "total_reviews": len(results),
        "structured_output": {
            "first_pass": first_pass,
            "repair_success": repair,
            "fallback": fallback,
            "first_pass_rate": round(first_pass / len(results), 4),
        },
        "tokens": {
            "total_input": total_tokens_in,
            "total_output": total_tokens_out,
            "input_per_review": round(total_tokens_in / len(results)),
            "output_per_review": round(total_tokens_out / len(results)),
        },
        "latency": {
            "median_ms": latencies[len(latencies) // 2],
            "p95_ms": latencies[int(len(latencies) * 0.95)],
            "max_ms": latencies[-1],
        },
    }

    output = {"summary": summary, "results": results}
    out_path = Path(__file__).parent / "golden_baseline_results.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"  run_id: {summary['run_id']}")
    print(f"  first_pass: {first_pass}/{len(results)} ({first_pass/len(results)*100:.0f}%)")
    print(f"  repair: {repair} / fallback: {fallback}")
    print(f"  tokens: {total_tokens_in:,} in + {total_tokens_out:,} out")
    print(f"  latency: median={summary['latency']['median_ms']}ms p95={summary['latency']['p95_ms']}ms")
    print(f"  저장: {out_path}")

    # 분석 출력
    analyze_results(results)


def analyze_results(results):
    """결과 분석 — threshold별, FP/FN, 분포 등."""
    print(f"\n{'='*70}")
    print(f"ANALYSIS")
    print(f"{'='*70}")

    # Ground truth 분포
    gt_counts = {}
    for r in results:
        gt_counts[r["ground_truth_ad"]] = gt_counts.get(r["ground_truth_ad"], 0) + 1
    print(f"\nGround Truth: {gt_counts}")

    # Threshold별 metric (관찰 전용)
    print(f"\n--- Threshold별 Metric (관찰 전용, 변경 금지) ---")
    for threshold in [0.2, 0.4, 0.5, 0.7]:
        tp = fp = tn = fn = 0
        for r in results:
            gt = r["ground_truth_ad"]
            if gt == "ambiguous":
                continue
            predicted = r["ad_probability"] >= threshold
            actual = gt in ("ad", "likely_ad")
            if predicted and actual: tp += 1
            elif predicted and not actual: fp += 1
            elif not predicted and actual: fn += 1
            else: tn += 1

        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
        fpr = fp / (fp + tn) if fp + tn else None

        print(f"  threshold={threshold}: TP={tp} FP={fp} TN={tn} FN={fn} "
              f"P={precision:.3f} R={recall:.3f} F1={f1:.3f} FP율={fpr:.3f}" if precision else
              f"  threshold={threshold}: TP={tp} FP={fp} TN={tn} FN={fn} P=N/A R=N/A")

    # p_eff 기준도 동일하게
    print(f"\n--- p_eff 기준 (threshold=0.7) ---")
    for threshold in [0.4, 0.5, 0.7]:
        tp = fp = tn = fn = 0
        for r in results:
            gt = r["ground_truth_ad"]
            if gt == "ambiguous":
                continue
            predicted = r["p_eff"] >= threshold
            actual = gt in ("ad", "likely_ad")
            if predicted and actual: tp += 1
            elif predicted and not actual: fp += 1
            elif not predicted and actual: fn += 1
            else: tn += 1
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        print(f"  p_eff>={threshold}: TP={tp} FP={fp} TN={tn} FN={fn} P={precision:.3f} R={recall:.3f}" if precision else
              f"  p_eff>={threshold}: TP={tp} FP={fp} TN={tn} FN={fn}")

    # Normal 51개 FP 분포
    print(f"\n--- Normal 51개 ad_probability 분포 ---")
    normals = [r for r in results if r["ground_truth_ad"] == "normal"]
    bins = {"<0.2": 0, "0.2-0.4": 0, "0.4-0.7": 0, ">=0.7": 0}
    for r in normals:
        p = r["ad_probability"]
        if p < 0.2: bins["<0.2"] += 1
        elif p < 0.4: bins["0.2-0.4"] += 1
        elif p < 0.7: bins["0.4-0.7"] += 1
        else: bins[">=0.7"] += 1
    print(f"  {bins}")

    # FP 상세 (normal + p >= 0.7)
    high_fp = [r for r in normals if r["ad_probability"] >= 0.7]
    print(f"\n--- HIGH FP (normal + ad_p >= 0.7): {len(high_fp)}개 ---")
    for r in high_fp:
        hc = " ★HIGH-CONF" if r["ad_confidence"] >= 0.8 else ""
        print(f"  {r['review_id']} [{r['source']}] p={r['ad_probability']:.2f} c={r['ad_confidence']:.2f}{hc}")
        print(f"    text: {r['short_text']}...")
        print(f"    signals: {[s['code'] for s in r['ad_signals']]}")

    # likely_ad 4개 상세
    print(f"\n--- likely_ad 4개 상세 ---")
    likely_ads = [r for r in results if r["ground_truth_ad"] == "likely_ad"]
    for r in likely_ads:
        fn_flag = " ⚠️FN(p<0.4)" if r["ad_probability"] < 0.4 else ""
        print(f"  {r['review_id']} [{r['source']}] p={r['ad_probability']:.2f} pe={r['p_eff']:.2f} "
              f"c={r['ad_confidence']:.2f}{fn_flag}")
        print(f"    text: {r['short_text']}...")
        print(f"    reason: {r['label_reason']}")
        print(f"    ad_signals: {[(s['code'], s['quote'][:30]) for s in r['ad_signals']]}")

    # ambiguous 4개
    print(f"\n--- ambiguous 4개 ---")
    ambiguous = [r for r in results if r["ground_truth_ad"] == "ambiguous"]
    for r in ambiguous:
        extreme = ""
        if r["ad_probability"] >= 0.9: extreme = " ★EXTREME HIGH"
        elif r["ad_probability"] <= 0.1: extreme = " ★EXTREME LOW"
        print(f"  {r['review_id']} p={r['ad_probability']:.2f} pe={r['p_eff']:.2f} "
              f"c={r['ad_confidence']:.2f}{extreme}")

    # Local probability 검증
    print(f"\n--- Local Probability >= 0.7 검증 ---")
    local_evidence_keywords = ["동네", "회사가 근처", "집이 근처", "몇 년째", "단골",
                               "재방문", "번째 방문", "직장인", "자주", "매주"]
    unsupported = 0
    for r in results:
        if r["local_probability"] >= 0.7:
            has_evidence = any(kw in r["short_text"] for kw in local_evidence_keywords)
            local_signal = any(s["code"] == "local_context" for s in r["authentic_signals"])
            if not has_evidence and not local_signal:
                unsupported += 1
                print(f"  ⚠️ {r['review_id']} loc={r['local_probability']:.2f} — 근거 없음")
            else:
                print(f"  ✓ {r['review_id']} loc={r['local_probability']:.2f} — 근거 있음")
    print(f"  unsupported high local: {unsupported}")

    # Confidence 유효성
    print(f"\n--- Confidence 유효성 ---")
    for label in ("normal", "likely_ad"):
        group = [r for r in results if r["ground_truth_ad"] == label]
        if not group:
            continue
        high_conf = [r for r in group if r["ad_confidence"] >= 0.8]
        low_conf = [r for r in group if r["ad_confidence"] < 0.8]
        # correct = binary prediction matches ground truth
        correct_high = sum(1 for r in high_conf if (r["ad_probability"] >= 0.5) == (label in ("ad", "likely_ad")))
        wrong_high = len(high_conf) - correct_high
        print(f"  {label}: high_conf={len(high_conf)} (correct={correct_high}, wrong={wrong_high}) "
              f"low_conf={len(low_conf)}")


def run_source_bias():
    """Source bias counterfactual — normal 리뷰 8개 × 3 source variants."""
    api_key = os.environ.get("ZAI_API_KEY", "")
    golden = load_golden()
    normals = [e for e in golden if e["ad_label"] == "normal"][:8]

    system_messages = [{"role": "system", "content": load_system_prompt()}]
    for ex in load_examples():
        system_messages.append({"role": "user", "content": "리뷰를 분석해 JSON만 반환:\n" + json.dumps(ex["review"], ensure_ascii=False)})
        system_messages.append({"role": "assistant", "content": json.dumps(ex["output"], ensure_ascii=False)})

    client = httpx.Client(timeout=120.0, headers={"Authorization": f"Bearer {api_key}"})

    print(f"\n=== Source Bias Counterfactual (8개 × 3 source) ===\n")
    variants = ["manual_import", "naver_map", "naver_blog"]
    results = []

    for entry in normals:
        original = entry["review"]
        row = {"original_source": original.source, "text": original.text[:50]}
        for variant_source in variants:
            modified = Review(
                id=original.id, restaurant_id=original.restaurant_id,
                source=variant_source, rating=original.rating,
                text=original.text, reviewed_at=original.reviewed_at,
            )
            result = call_llm(api_key, modified, client, system_messages)
            analysis = result.get("analysis")
            row[variant_source] = {
                "ad_probability": analysis.ad_probability if analysis else None,
                "ad_confidence": analysis.ad_confidence if analysis else None,
                "attempts": result.get("attempts"),
            }
        probs = [row[v]["ad_probability"] for v in variants if row[v]["ad_probability"] is not None]
        delta = max(probs) - min(probs) if len(probs) == 3 else None
        row["delta_source"] = round(delta, 3) if delta is not None else None
        results.append(row)

        flag = " ⚠️BIAS" if delta and delta >= 0.20 else ""
        print(f"  [{original.source:14s}] manual={row['manual_import']['ad_probability']:.2f} "
              f"map={row['naver_map']['ad_probability']:.2f} "
              f"blog={row['naver_blog']['ad_probability']:.2f} "
              f"Δ={delta:.3f}{flag}" if delta is not None else "  오류")

    client.close()
    out = Path(__file__).parent / "source_bias_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")

    biased = [r for r in results if r.get("delta_source") and r["delta_source"] >= 0.20]
    print(f"delta >= 0.20 사례: {len(biased)}개")


def run_rating_bias():
    """Rating bias counterfactual — 동일 text/source에 rating만 변경."""
    api_key = os.environ.get("ZAI_API_KEY", "")
    golden = load_golden()
    normals = [e for e in golden if e["ad_label"] == "normal"][:8]

    system_messages = [{"role": "system", "content": load_system_prompt()}]
    for ex in load_examples():
        system_messages.append({"role": "user", "content": "리뷰를 분석해 JSON만 반환:\n" + json.dumps(ex["review"], ensure_ascii=False)})
        system_messages.append({"role": "assistant", "content": json.dumps(ex["output"], ensure_ascii=False)})

    client = httpx.Client(timeout=120.0, headers={"Authorization": f"Bearer {api_key}"})

    print(f"\n=== Rating Bias Counterfactual (8개 × rating 3/5) ===\n")
    results = []

    for entry in normals:
        original = entry["review"]
        row = {"text": original.text[:50], "source": original.source}

        for rating_val in [3.0, 5.0]:
            modified = Review(
                id=original.id, restaurant_id=original.restaurant_id,
                source=original.source, rating=rating_val,
                text=original.text, reviewed_at=original.reviewed_at,
            )
            result = call_llm(api_key, modified, client, system_messages)
            analysis = result.get("analysis")
            row[f"rating_{int(rating_val)}"] = {
                "ad_probability": analysis.ad_probability if analysis else None,
                "ad_confidence": analysis.ad_confidence if analysis else None,
            }

        delta = abs(row["rating_3"]["ad_probability"] - row["rating_5"]["ad_probability"]) \
            if row["rating_3"]["ad_probability"] is not None and row["rating_5"]["ad_probability"] is not None else None
        row["delta_rating"] = round(delta, 3) if delta is not None else None
        results.append(row)

        flag = " ⚠️BIAS" if delta and delta >= 0.20 else ""
        print(f"  r3={row['rating_3']['ad_probability']:.2f} r5={row['rating_5']['ad_probability']:.2f} "
              f"Δ={delta:.3f}{flag}" if delta is not None else "  오류")

    client.close()
    out = Path(__file__).parent / "rating_bias_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {out}")

    biased = [r for r in results if r.get("delta_rating") and r["delta_rating"] >= 0.20]
    print(f"delta >= 0.20 사례: {len(biased)}개")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fresh", "source-bias", "rating-bias"], default="fresh")
    args = parser.parse_args()

    if args.mode == "fresh":
        run_fresh_baseline()
    elif args.mode == "source-bias":
        run_source_bias()
    elif args.mode == "rating-bias":
        run_rating_bias()
