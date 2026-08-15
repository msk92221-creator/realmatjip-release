"""Phase 3B.1 Real E2E — 검색 20곳 → Import 10곳 → LLM 분석 → 점수 비교 (스펙 §5~§8).

사용법: 백엔드 서버 기동 후 (REALMATJIP_DB=e2e3b1.db)
    python realdata/e2e_phase3b1.py

키/시크릿은 서버가 환경변수로만 다루므로 이 스크립트에는 키가 없다.
"""
import json
import sqlite3
import sys
import time
from collections import OrderedDict

import httpx

BASE = "http://127.0.0.1:8000"
DB_PATH = "e2e3b1.db"
REPORT_PATH = "realdata/e2e_phase3b1_report.json"

QUERIES = [
    "강남역 떡볶이",
    "홍대입구역 김치찌개",
    "성수동 브런치 카페",
    "을지로 곱창",
    "종로3가 설렁탕",
]

IMPORT_TARGET = 10
SEARCH_LIMIT_PER_QUERY = 6


def section(title: str):
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def wait_job(client: httpx.Client, job_id: int, timeout_s: float = 900) -> dict:
    """JobORM 상태가 done/failed 될 때까지 폴링."""
    started = time.time()
    while time.time() - started < timeout_s:
        r = client.get(f"{BASE}/api/admin/jobs/{job_id}")
        r.raise_for_status()
        job = r.json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(3)
    raise TimeoutError(f"job {job_id} timeout")


def step_search(client: httpx.Client) -> list[dict]:
    """§5: 다양한 쿼리로 검색 → 20곳 이상 unique 수집 + 품질 통계."""
    section("§5 SEARCH — 20곳 수집")
    unique: OrderedDict[str, dict] = OrderedDict()
    per_query = []
    for q in QUERIES:
        r = client.get(f"{BASE}/api/providers/google/search",
                       params={"q": q, "limit": SEARCH_LIMIT_PER_QUERY})
        r.raise_for_status()
        data = r.json()
        new = 0
        for p in data["results"]:
            if p["place_id"] not in unique:
                p["_query"] = q
                unique[p["place_id"]] = p
                new += 1
        per_query.append({"query": q, "returned": data["count"], "new_unique": new})
        print(f"  [{q}] returned={data['count']} new_unique={new}")

    places = list(unique.values())
    # 필드 완성도
    fields = ["name", "formatted_address", "primary_type", "rating",
              "user_rating_count", "google_maps_url", "lat", "lng"]
    completeness = {}
    for f in fields:
        ok = sum(1 for p in places if p.get(f) not in (None, "", 0))
        completeness[f] = f"{ok}/{len(places)}"
    has_reviews_meta = sum(1 for p in places if (p.get("user_rating_count") or 0) > 0)

    print(f"\n  TOTAL_UNIQUE = {len(places)}")
    print(f"  필드 완성도: {completeness}")
    print(f"  user_rating_count>0: {has_reviews_meta}/{len(places)}")

    assert len(places) >= 20, f"20곳 미달: {len(places)}"
    return places


def pick_import_targets(places: list[dict]) -> list[dict]:
    """쿼리별로 골고루 10곳 선택 (리뷰 있는 곳 우선)."""
    by_query: OrderedDict[str, list[dict]] = OrderedDict()
    for p in places:
        by_query.setdefault(p["_query"], []).append(p)
    picked = []
    # 리뷰 수 많은 순으로 정렬 후 라운드로빈
    for lst in by_query.values():
        lst.sort(key=lambda p: -(p.get("user_rating_count") or 0))
    while len(picked) < IMPORT_TARGET:
        for lst in by_query.values():
            if lst and len(picked) < IMPORT_TARGET:
                picked.append(lst.pop(0))
    return picked


def step_import(client: httpx.Client, targets: list[dict]) -> list[dict]:
    """§6: preview → commit × 10곳 + 1곳 재커밋(중복 방지 확인)."""
    section(f"§6 IMPORT — {len(targets)}곳 preview→commit")
    imported = []
    for i, p in enumerate(targets, 1):
        # preview
        r = client.post(f"{BASE}/api/providers/google/import/preview",
                        json={"place_id": p["place_id"]})
        r.raise_for_status()
        pv = r.json()
        assert pv["match"]["match_type"] == "no_match", \
            f"빈 DB인데 match={pv['match']['match_type']} (no_match여야 신규 생성)"
        # commit
        r = client.post(f"{BASE}/api/providers/google/import/commit",
                        json={"place_id": p["place_id"]})
        r.raise_for_status()
        cm = r.json()
        imported.append({"place_id": p["place_id"], "name": cm["restaurant_name"],
                         "restaurant_id": cm["restaurant_id"],
                         "inserted_reviews": cm["inserted_reviews"],
                         "google_rating": cm["google_rating"]})
        print(f"  [{i:2d}] {cm['restaurant_name']} | action={cm['action']} "
              f"| reviews={cm['inserted_reviews']} "
              f"(google {cm['google_rating']}★/{cm['google_rating_count']}개)")

    # 중복 방지: 첫 곳 재커밋 → 신규 0, 스킵 발생해야 함
    section("§6b 중복 방지 — 같은 place 재커밋")
    r = client.post(f"{BASE}/api/providers/google/import/commit",
                    json={"place_id": targets[0]["place_id"]})
    r.raise_for_status()
    recommit = r.json()
    print(f"  재커밋: action={recommit['action']} "
          f"inserted={recommit['inserted_reviews']} "
          f"skipped_duplicates={recommit['skipped_duplicates']}")
    assert recommit["inserted_reviews"] == 0, "중복 리뷰 삽입 발생!"
    return imported


def step_analyze(client: httpx.Client) -> dict:
    """§7: analyze-pending → LLM 분석 (glm-4.5-flash, 비용 상한 자동 적용)."""
    section("§7 LLM ANALYZE — analyze-pending")
    r = client.post(f"{BASE}/api/admin/analyze-pending")
    r.raise_for_status()
    job_id = r.json()["job_id"]
    print(f"  job_id={job_id} 시작... (폴링)")
    job = wait_job(client, job_id)
    print(f"  status={job['status']}")
    progress = job.get("progress") or {}
    for k in ("total", "completed", "cached", "failed", "tokens_input",
              "tokens_output", "cost_usd"):
        print(f"  {k} = {progress.get(k)}")
    assert job["status"] == "done", f"analyze job failed: {job}"
    assert progress.get("failed", 0) == 0, f"분석 실패 {progress['failed']}건"
    return progress


def step_recalculate_and_compare(client: httpx.Client) -> dict:
    """§8: recalculate → naive(단순 평균) vs trust(overall_a) 랭킹 비교."""
    section("§8 SCORE — recalculate + naive vs trust")
    r = client.post(f"{BASE}/api/admin/recalculate")
    r.raise_for_status()
    job_id = r.json()["job_id"]
    job = wait_job(client, job_id)
    assert job["status"] == "done", f"recalculate failed: {job}"
    print(f"  recalculate done (batch {job.get('result', {}).get('batch_id', '?')[:8]})")

    # trust 랭킹 (API)
    r = client.get(f"{BASE}/api/restaurants", params={"sort": "overall_a", "limit": 100})
    r.raise_for_status()
    trust = r.json()["items"]

    # naive 랭킹 (DB 단순 평균 — 비교 기준)
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT r.name, AVG(v.rating), COUNT(*), r.id "
        "FROM reviews v JOIN restaurants r ON r.id = v.restaurant_id "
        "GROUP BY r.id ORDER BY AVG(v.rating) DESC"
    ).fetchall()
    conn.close()
    naive = [{"name": n, "avg": round(a, 2), "n": c, "id": i} for n, a, c, i in rows]

    trust_names = [t["name"] for t in trust]
    naive_names = [n["name"] for n in naive]
    print(f"\n  {'trust순위':<6} {'식당':<24} {'overall_a':>9} {'n_eff':>6} | "
          f"{'naive순위':>4} {'naive_avg':>8} {'n':>3}")
    naive_rank = {n["name"]: rank for rank, n in enumerate(naive_names, 1)}
    for rank, t in enumerate(trust, 1):
        n = next(x for x in naive if x["name"] == t["name"])
        print(f"  {rank:<6} {t['name'][:22]:<24} {t['overall_a']:>9.2f} "
              f"{t['n_eff']:>6.1f} | {naive_rank[t['name']]:>4} "
              f"{n['avg']:>8.2f} {n['n']:>3}")

    moved = [(t["name"], naive_rank[t["name"]], rank)
             for rank, t in enumerate(trust, 1) if naive_rank[t["name"]] != rank]
    print(f"\n  순위 변동 {len(moved)}곳: "
          + ", ".join(f"{m[0]}({m[1]}→{m[2]})" for m in moved[:8]))
    return {"trust": trust, "naive": naive}


def main() -> int:
    t0 = time.time()
    report: dict = {"phase": "3B.1", "started_at": time.strftime("%Y-%m-%d %H:%M:%S")}

    with httpx.Client(timeout=60) as client:
        places = step_search(client)
        targets = pick_import_targets(places)
        imported = step_import(client, targets)
        progress = step_analyze(client)
        ranking = step_recalculate_and_compare(client)

        report["search_unique"] = len(places)
        report["imported"] = imported
        report["analyze"] = progress
        report["ranking"] = ranking

    report["elapsed_s"] = round(time.time() - t0, 1)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] {report['elapsed_s']}s — report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
