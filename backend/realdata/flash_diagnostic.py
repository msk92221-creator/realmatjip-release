"""Phase 3A.3.1 — Flash Configuration Diagnostic.

3개 리뷰(normal/likely_ad/local)로 glm-4.5-flash의 호출 설정 문제를 격리한다.
thinking=disabled + response_format=json_object + max_tokens=2048.

기존 실패가 thinking + output budget 문제였는지 확인하는 것이 목적.
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.analysis.schema import load_system_prompt, load_examples, parse_llm_analysis, AnalysisParseError
from app.models import Review

DIAGNOSTIC_REVIEWS = [
    {
        "id": "diag-normal",
        "source": "naver_map", "rating": 4,
        "text": "맛은 괜찮은데 테이블 간격이 좁아서 대화하기 조금 불편했어요. 국밥 양은 적당합니다.",
        "ground_truth": "normal",
        "category": "확실한 일반",
    },
    {
        "id": "diag-likely-ad",
        "source": "naver_blog", "rating": None,
        "text": "강남 최고의 스테이크 하우스를 찾아서 다녀왔습니다. 1++ 한우와 직화 그릴이 자랑입니다. 위치는 강남역 4번 출구 도보 5분, 발렛 파킹 가능합니다. 영업시간 점심 11:30~14:30, 저녁 17:30~22:00. 예약은 인스타 DM 또는 전화로 가능합니다. 2인 코스 15만원으로 특별한 날에 강력 추천드립니다. 맛 최고 서비스 최고 분위기 최고!",
        "ground_truth": "likely_ad",
        "category": "카탈로그형 광고",
    },
    {
        "id": "diag-local",
        "source": "naver_map", "rating": 5,
        "text": "동네에서 10년째 가는 단골집이에요. 엄마랑 자주 오는데 순대국이 여기가 최고예요. 주차장이 좁은 게 흠.",
        "ground_truth": "normal",
        "category": "로컬 재방문",
    },
]


def run_diagnostic(model: str, config_name: str):
    """3개 리뷰를 지정 설정으로 분석하고 상세 로그 반환."""
    api_key = os.environ.get("ZAI_API_KEY", "")
    if not api_key:
        print("오류: ZAI_API_KEY 없음")
        return None

    system_prompt = load_system_prompt()
    examples = load_examples()

    # 메시지 구성 (기존 analyzer와 동일한 구조)
    messages = [{"role": "system", "content": system_prompt}]
    for ex in examples:
        messages.append({"role": "user", "content": "리뷰를 분석해 JSON만 반환:\n" + json.dumps(ex["review"], ensure_ascii=False)})
        messages.append({"role": "assistant", "content": json.dumps(ex["output"], ensure_ascii=False)})

    client = httpx.Client(
        timeout=httpx.Timeout(120.0),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )

    results = []
    for review_data in DIAGNOSTIC_REVIEWS:
        review = Review(
            id=review_data["id"], restaurant_id="diag", source=review_data["source"],
            rating=review_data["rating"], text=review_data["text"],
            reviewed_at=datetime(2026, 8, 15),
        )
        payload = {"source": review.source, "rating": review.rating, "text": review.text}
        full_messages = messages + [
            {"role": "user", "content": "리뷰를 분석해 JSON만 반환:\n" + json.dumps(payload, ensure_ascii=False)}
        ]

        body = {
            "model": model,
            "messages": full_messages,
            "temperature": 0,
            "max_tokens": 2048,
            # 핵심 변경: thinking 비활성화
            "thinking": {"type": "disabled"},
            # 핵심 변경: JSON object 모드
            "response_format": {"type": "json_object"},
        }

        start = time.time()
        try:
            response = client.post(
                "https://api.z.ai/api/paas/v4/chat/completions",
                json=body,
            )
            elapsed_ms = round((time.time() - start) * 1000)

            if response.status_code != 200:
                results.append({
                    "id": review_data["id"], "ground_truth": review_data["ground_truth"],
                    "category": review_data["category"], "config": config_name,
                    "http_status": response.status_code,
                    "error": response.text[:200],
                    "latency_ms": elapsed_ms,
                })
                print(f"  {review_data['id']:16s} HTTP {response.status_code} — {response.text[:100]}")
                continue

            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason", "?")
            content = message.get("content", "")
            reasoning_content = message.get("reasoning_content", "")
            usage = data.get("usage", {})

            # Schema validation
            validation_result = "PASS"
            parsed = None
            try:
                parsed = parse_llm_analysis(content, analyzer=f"diag:{model}")
            except AnalysisParseError as e:
                validation_result = f"FAIL: {e}"

            result = {
                "id": review_data["id"],
                "ground_truth": review_data["ground_truth"],
                "category": review_data["category"],
                "config": config_name,
                "http_status": 200,
                "finish_reason": finish_reason,
                "content": content[:2000],
                "content_length": len(content),
                "reasoning_content": reasoning_content[:500] if reasoning_content else "",
                "reasoning_content_length": len(reasoning_content) if reasoning_content else 0,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "latency_ms": elapsed_ms,
                "schema_validation": validation_result,
                "parsed": {
                    "ad_probability": parsed.ad_probability,
                    "ad_confidence": parsed.ad_confidence,
                    "local_probability": parsed.local_probability,
                    "authenticity": parsed.authenticity,
                    "specificity": parsed.specificity,
                } if parsed else None,
            }
            results.append(result)

            status = "✓" if validation_result == "PASS" else "✗"
            print(f"  {review_data['id']:16s} {status} finish={finish_reason:8s} "
                  f"content={len(content):4d}ch reasoning={len(reasoning_content) if reasoning_content else 0:4d}ch "
                  f"tokens={usage.get('completion_tokens', 0):4d} "
                  f"latency={elapsed_ms:6d}ms")

        except Exception as e:
            elapsed_ms = round((time.time() - start) * 1000)
            results.append({
                "id": review_data["id"], "ground_truth": review_data["ground_truth"],
                "category": review_data["category"], "config": config_name,
                "error": f"{type(e).__name__}: {e}", "latency_ms": elapsed_ms,
            })
            print(f"  {review_data['id']:16s} 오류: {type(e).__name__}: {e}")

    client.close()
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="glm-4.5-flash")
    parser.add_argument("--config-name", default="thinking-disabled+json+2048")
    args = parser.parse_args()

    print(f"\n=== 진단: {args.model} / {args.config_name} ===")
    print(f"  thinking=disabled, response_format=json_object, max_tokens=2048, temperature=0\n")

    results = run_diagnostic(args.model, args.config_name)

    if results:
        success = sum(1 for r in results if r.get("schema_validation") == "PASS")
        print(f"\n결과: {success}/{len(results)} 성공")

        # 저장
        out = Path(__file__).parent / f"diag_{args.model.replace('.', '_')}_{args.config_name[:20]}.json"
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {out}")
