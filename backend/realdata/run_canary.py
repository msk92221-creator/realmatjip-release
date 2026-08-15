"""Phase 3A.2 Canary 실행 — 실 LLM 15개 + 원본 응답 저장 + 상세 평가.

실행: python realdata/run_canary.py [--model MODEL] [--run-id ID]
ZAI_API_KEY 잔액이 있어야 동작한다.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.analysis.analyzer import ZaiReviewAnalyzer, AnalyzerConfigError
from app.analysis.schema import AnalysisParseError, parse_llm_analysis, analysis_to_cache_dict
from app.analysis.verification import verify_analysis
from app.analysis.input_hash import llm_input_hash
from app.models import Review

CANARY_PATH = Path(__file__).parent / "canary_set.json"


def run_canary(model: str, run_id: str):
    canary = json.loads(CANARY_PATH.read_text(encoding="utf-8"))

    api_key = os.environ.get("ZAI_API_KEY", "")
    if not api_key:
        print("오류: ZAI_API_KEY가 설정되지 않았습니다")
        return

    analyzer = ZaiReviewAnalyzer(
        api_key=api_key, model=model, retry_delays=(2.0, 5.0),
    )

    results = []
    runs_log = []

    try:
        pass  # flash는 /models에 미등록이지만 직접 호출 가능 — 위에서 httpx로 확인함
        print(f"모델: {analyzer.model} (prompt v{analyzer.prompt_version})")
        print(f"Canary: {len(canary['reviews'])}개\n")
    except AnalyzerConfigError as e:
        print(f"설정 오류: {e}")
        return

    for item in canary["reviews"]:
        review = Review(
            id=item["id"], restaurant_id="canary", source=item["source"],
            rating=item["rating"], text=item["text"],
            reviewed_at=datetime(2026, 8, 15),
        )
        input_hash = llm_input_hash(review)

        start = time.time()
        attempts = 1
        raw_response = ""
        validation_errors = []
        analysis = None

        try:
            # 직접 호출해서 raw response를 캡처
            base_messages = analyzer._build_messages()
            messages = base_messages + [{"role": "user", "content": analyzer._user_payload(review)}]
            content, usage = analyzer._chat(messages, 0)
            analyzer.tokens_input += usage[0]
            analyzer.tokens_output += usage[1]
            analyzer.calls += 1
            raw_response = content

            try:
                analysis = parse_llm_analysis(content, analyzer=analyzer.name)
                analysis = verify_analysis(analysis, review.text)
            except AnalysisParseError as e:
                # repair retry
                attempts = 2
                validation_errors.append(str(e))
                repair_messages = base_messages + [
                    {"role": "user", "content": analyzer._user_payload(review)},
                    {"role": "assistant", "content": str(content)[:1500]},
                    {"role": "user", "content":
                        f"이전 응답이 schema validation에 실패했다 ({e}). "
                        "다음 schema에 맞는 JSON만 다시 반환하라."},
                ]
                content2, usage2 = analyzer._chat(repair_messages, 1)
                analyzer.tokens_input += usage2[0]
                analyzer.tokens_output += usage2[1]
                analyzer.calls += 1
                raw_response = content2
                try:
                    analysis = parse_llm_analysis(content2, analyzer=analyzer.name)
                    analysis = verify_analysis(analysis, review.text)
                except AnalysisParseError as e2:
                    attempts = 3
                    validation_errors.append(str(e2))
                    from app.analysis.schema import needs_manual_fallback
                    analysis = needs_manual_fallback(analyzer.name, str(e2))

        except AnalyzerConfigError as e:
            print(f"\n설정 오류로 중단: {e}")
            break
        except Exception as e:
            attempts = 3
            validation_errors.append(f"{type(e).__name__}: {e}")
            from app.analysis.schema import needs_manual_fallback
            analysis = needs_manual_fallback(analyzer.name, str(e))

        elapsed_ms = round((time.time() - start) * 1000)

        # 로그 저장
        run_log = {
            "run_id": run_id,
            "review_id": item["id"],
            "model": analyzer.model,
            "prompt_version": analyzer.prompt_version,
            "input_hash": input_hash,
            "raw_response": raw_response[:5000],
            "validated_result": analysis_to_cache_dict(analysis) if analysis else None,
            "validation_errors": validation_errors,
            "latency_ms": elapsed_ms,
            "input_tokens": analyzer.tokens_input,
            "output_tokens": analyzer.tokens_output,
            "attempts": attempts,
        }
        runs_log.append(run_log)

        # 결과
        if analysis:
            pred = "ad" if analysis.ad_probability >= 0.7 else (
                "likely" if analysis.ad_probability >= 0.5 else "normal")
            expected_pos = item["expected_ad"] in ("ad", "likely_ad")
            pred_pos = pred in ("ad", "likely")
            match = "✓" if expected_pos == pred_pos else "✗"
            if item["expected_ad"] == "ambiguous":
                match = "~"  # ambiguous는 FP/FN에서 제외

            print(f"  {item['id']:12s} [{item['category'][:12]:12s}] "
                  f"exp={item['expected_ad']:10s} "
                  f"p={analysis.ad_probability:.2f} c={analysis.ad_confidence:.2f} "
                  f"loc={analysis.local_probability:.2f} "
                  f"sig={len(analysis.ad_signals)}+{len(analysis.authentic_signals)} "
                  f"{match} {elapsed_ms}ms")

            results.append({
                "id": item["id"], "category": item["category"],
                "expected": item["expected_ad"],
                "ad_probability": analysis.ad_probability,
                "ad_confidence": analysis.ad_confidence,
                "local_probability": analysis.local_probability,
                "authenticity": analysis.authenticity,
                "specificity": analysis.specificity,
                "ad_signals": [{"code": s.code, "quote": s.quote[:50]} for s in analysis.ad_signals],
                "authentic_signals": [{"code": s.code, "quote": s.quote[:50]} for s in analysis.authentic_signals],
                "signals_dropped": analysis.flags.get("signals_dropped", 0),
                "needs_manual": analysis.flags.get("needs_manual_review", False),
                "attempts": attempts,
                "latency_ms": elapsed_ms,
                "match": match,
            })
        else:
            print(f"  {item['id']:12s} [{item['category'][:12]:12s}] FAILED")

    # 저장
    output = {
        "run_id": run_id,
        "model": analyzer.model,
        "prompt_version": analyzer.prompt_version,
        "timestamp": datetime.utcnow().isoformat(),
        "tokens_input": analyzer.tokens_input,
        "tokens_output": analyzer.tokens_output,
        "calls": analyzer.calls,
        "results": results,
        "runs_log": runs_log,
    }
    out_path = Path(__file__).parent / f"canary_results_{run_id}.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n토큰: in={analyzer.tokens_input} out={analyzer.tokens_output} calls={analyzer.calls}")
    print(f"결과 저장: {out_path}")

    # 요약 출력 (§7)
    print_summary(results, analyzer)


def print_summary(results, analyzer):
    print(f"\n{'='*60}")
    print(f"CANARY SUMMARY")
    print(f"{'='*60}")

    # API 안정성
    total = len(results)
    first_pass = sum(1 for r in results if r["attempts"] == 1)
    repair = sum(1 for r in results if r["attempts"] == 2)
    fallback = sum(1 for r in results if r["attempts"] >= 3)
    print(f"\n## API 안정성")
    print(f"  total={total} first_pass={first_pass} repair={repair} fallback={fallback}")

    # Structured output
    print(f"\n## Structured output")
    print(f"  first-pass: {first_pass}/{total} ({first_pass/total*100:.0f}%)" if total else "  no results")
    print(f"  repair:     {repair}/{total}" if total else "")
    print(f"  failure:    {fallback}/{total}" if total else "")

    # Evidence
    total_signals = sum(len(r["ad_signals"]) + len(r["authentic_signals"]) for r in results)
    dropped = sum(r["signals_dropped"] for r in results)
    print(f"\n## Evidence")
    print(f"  signals={total_signals} dropped(hallucinated)={dropped}")

    # Ad probability 분포
    print(f"\n## Ad Probability")
    for group in ("normal", "likely_ad", "ambiguous"):
        probs = [r["ad_probability"] for r in results if r["expected"] == group]
        if probs:
            print(f"  {group:12s}: {[f'{p:.2f}' for p in sorted(probs)]}")

    # Local probability
    print(f"\n## Local Probability")
    local_repeats = [r for r in results if "로컬" in r["category"] or "재방문" in r["category"]]
    for r in local_repeats:
        print(f"  {r['id']}: {r['local_probability']:.2f}")
    non_local = [r for r in results if "로컬" not in r["category"] and "재방문" not in r["category"]]
    high_local_no_evidence = [r for r in non_local if r["local_probability"] > 0.5]
    if high_local_no_evidence:
        print(f"  근거 없이 local>0.5: {len(high_local_no_evidence)}개")
        for r in high_local_no_evidence:
            print(f"    {r['id']}: {r['local_probability']:.2f}")

    # Performance
    latencies = sorted(r["latency_ms"] for r in results)
    median = latencies[len(latencies)//2] if latencies else 0
    p95 = latencies[int(len(latencies)*0.95)] if len(latencies) > 1 else latencies[-1] if latencies else 0
    print(f"\n## Performance")
    print(f"  latency median={median}ms p95={p95}ms")
    print(f"  tokens in={analyzer.tokens_input} out={analyzer.tokens_output}")

    # FP 사례
    print(f"\n## FP 사례 (normal → 높은 ad_probability)")
    fps = [r for r in results if r["expected"] == "normal" and r["ad_probability"] >= 0.5]
    if fps:
        for fp in fps:
            print(f"  {fp['id']}: p={fp['ad_probability']:.2f}")
            print(f"    signals: {[s['code'] for s in fp['ad_signals']]}")
    else:
        print(f"  없음")

    # FN 사례
    print(f"\n## FN 사례 (likely_ad → 낮은 ad_probability)")
    fns = [r for r in results if r["expected"] == "likely_ad" and r["ad_probability"] < 0.5]
    if fns:
        for fn in fns:
            print(f"  {fn['id']}: p={fn['ad_probability']:.2f}")
            print(f"    signals: {[s['code'] for s in fn['ad_signals']]}")
    else:
        print(f"  없음")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.environ.get("ZAI_MODEL", "glm-4.5-air"))
    parser.add_argument("--run-id", default=f"canary-{datetime.utcnow().strftime('%Y%m%d-%H%M')}")
    args = parser.parse_args()
    run_canary(args.model, args.run_id)
