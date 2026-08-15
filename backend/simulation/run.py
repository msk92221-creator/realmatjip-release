"""Phase 0 시뮬레이션 — A/B 알고리즘 랭킹 비교, 기여도 분해, invariant 검증,
c_rating/duplicate threshold 민감도 분석.

실행: python -m simulation.run  → REPORT.md 생성 + 콘솔 출력
"""
from dataclasses import replace
from pathlib import Path

from app.config import (
    C_RATING_CANDIDATES,
    DUPLICATE_THRESHOLD_CANDIDATES,
    ScoringConfig,
)
from app.scoring.duplicates import near_duplicate_clusters
from app.scoring.engine import (
    RestaurantResult,
    naive_ranking,
    rank_by,
    score_dataset,
)
from fixtures.dataset import EXPECTED_COUNTS, REFERENCE_DATE, build_dataset

NAME = {"rest-a": "A 더피자랩", "rest-b": "B 을지면옥", "rest-c": "C 더블유성수",
        "rest-d": "D 충무노포국밥", "rest-e": "E 그릴하우스청담"}


def stars(r01: float) -> float:
    return r01 * 4 + 1


def row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def result_by_id(results: list[RestaurantResult]) -> dict[str, RestaurantResult]:
    return {r.restaurant.id: r for r in results}


def section_ranking(results, naive) -> list[str]:
    ranked_a = rank_by(results, "A")
    ranked_b = rank_by(results, "B")
    lines = [
        "## 1. 순위 비교 — 단순 별점 vs 알고리즘 A/B",
        "",
        row(["순위", "단순 별점 평균", "Overall A", "Overall B"]),
        row(["---"] * 4),
    ]
    for i in range(len(results)):
        naive_rest, naive_mean, naive_n = naive[i]
        ra, rb = ranked_a[i], ranked_b[i]
        lines.append(row([
            str(i + 1),
            f"{NAME[naive_rest.id]} {stars(naive_mean):.2f}★ ({naive_n}개)",
            f"{NAME[ra.restaurant.id]} {ra.score('A'):.1f}",
            f"{NAME[rb.restaurant.id]} {rb.score('B'):.1f}",
        ]))
    lines.append("")
    return lines


def section_rating_shift(results, naive) -> list[str]:
    by_id = result_by_id(results)
    naive_map = {rest.id: mean for rest, mean, _ in naive}
    lines = [
        "## 2. 광고 감점 전후 평점 변화 (Review Weight 효과)",
        "",
        row(["식당", "리뷰수", "중복", "n_eff", "단순평점", "보정평점", "Δ(별점)", "p_eff≥0.7 비율"]),
        row(["---"] * 8),
    ]
    for rid in ["rest-b", "rest-d", "rest-e", "rest-a", "rest-c"]:
        res = by_id[rid]
        naive_stars = stars(naive_map[rid])
        adj_stars = stars(res.sub.rating_adjusted)
        lines.append(row([
            NAME[rid], str(res.sub.n_raw), str(res.dup_count), f"{res.sub.n_eff:.1f}",
            f"{naive_stars:.2f}★", f"{adj_stars:.2f}★", f"{adj_stars - naive_stars:+.2f}",
            f"{res.sub.ad_share_07:.0%}",
        ]))
    lines.append("")
    return lines


def section_subscores(results) -> list[str]:
    by_id = result_by_id(results)
    cfg = ScoringConfig()
    lines = [
        "## 3. 하위 점수 (모두 0~100 환산, 베이지안 수축 적용)",
        "",
        row(["식당", "보정평점", "광고청정도", "신뢰도", "로컬", "음식", "가성비", "재방문비율",
             "근거강도", "로컬근거(Σw)", "로컬배지"]),
        row(["---"] * 11),
    ]
    for rid in ["rest-b", "rest-d", "rest-e", "rest-a", "rest-c"]:
        res = by_id[rid]
        s = res.sub
        fmt = lambda v: f"{v * 100:.0f}" if v is not None else "-"
        lines.append(row([
            NAME[rid],
            fmt(s.rating_adjusted), fmt(s.ad_free), fmt(s.trust), fmt(s.local),
            fmt(s.food), fmt(s.value), f"{s.repeat:.0%}",
            f"{s.evidence_strength:.2f}({cfg.evidence_label(s.evidence_strength)})",
            f"{s.local_evidence:.1f}", "O" if res.local_badge else "X",
        ]))
    lines += [
        "",
        "> 근거강도 evidence_strength = n_eff/(n_eff+8) — Overall 미반영, UI/설명 전용 (결정 #1).",
        "",
    ]
    return lines


def section_signals(results) -> list[str]:
    by_id = result_by_id(results)
    lines = [
        "## 4. 식당 레벨 신호",
        "",
        row(["식당", "플랫폼 수(게이트 통과)", "consistency(할인 후)", "longevity",
             "manipulation", "burst01", "dup01", "최대월/중앙월"]),
        row(["---"] * 8),
    ]
    for rid in ["rest-b", "rest-d", "rest-e", "rest-a", "rest-c"]:
        res = by_id[rid]
        m = res.manipulation
        lines.append(row([
            NAME[rid], str(len(res.platforms)),
            f"{res.consistency:.2f}", f"{res.longevity:.2f}", f"{m.score:.2f}",
            f"{m.burst01:.2f}", f"{m.dup01:.2f}", f"{m.peak_month_count}/{m.median_month_count:.0f}",
        ]))
    lines.append("")
    return lines


def section_contribution(results) -> list[str]:
    by_id = result_by_id(results)
    lines = ["## 5. 점수 기여도 분해 (각 항목이 몇 점을 더했는지)", ""]
    for rid in ["rest-b", "rest-d", "rest-e", "rest-a", "rest-c"]:
        res = by_id[rid]
        lines.append(f"### {NAME[rid]} — A={res.overall_a.score:.1f} / B={res.overall_b.score:.1f}")
        lines.append("")
        lines.append(row(["항목", "신호값", "A안 기여", "B안 기여"]))
        lines.append(row(["---"] * 4))
        terms_b = {name: pts for name, _, pts in res.overall_b.terms}
        for name, value, points_a in res.overall_a.terms:
            lines.append(row([name, f"{value:.3f}", f"{points_a:+.1f}", f"{terms_b[name]:+.1f}"]))
        lines.append("")
    return lines


def section_invariants(results, naive) -> list[str]:
    """결정 #2의 핵심 invariant를 자동 검증한다 (고정 기대 순위 아님)."""
    by_id = result_by_id(results)
    ranked = rank_by(results, "A")
    rank_of = {r.restaurant.id: i for i, r in enumerate(ranked)}
    naive_map = {rest.id: mean for rest, mean, _ in naive}
    naive_order = [rest.id for rest, _, _ in naive]

    a_drop = stars(by_id["rest-a"].sub.rating_adjusted) - stars(naive_map["rest-a"])
    top2 = {r.restaurant.id for r in ranked[:2]}
    checks = [
        ("A(광고 다수)는 단순 별점 대비 크게 하락",
         naive_order[0] == "rest-a" and rank_of["rest-a"] >= 3 and a_drop <= -0.10),
        ("B(로컬)·D(노포) 상위권", top2 == {"rest-b", "rest-d"}),
        ("E는 플랫폼 불일치로 B/D보다 아래",
         rank_of["rest-e"] > rank_of["rest-b"] and rank_of["rest-e"] > rank_of["rest-d"]),
        ("C manipulation risk가 진성 식당(B/D/E)보다 높음",
         by_id["rest-c"].manipulation.score > max(
             by_id["rest-b"].manipulation.score,
             by_id["rest-d"].manipulation.score,
             by_id["rest-e"].manipulation.score,
         )),
        ("C는 바이럴이라는 이유만으로 과잉 처벌되지 않음 (보정평점이 단순평점과 유지)",
         stars(by_id["rest-c"].sub.rating_adjusted) >= stars(naive_map["rest-c"]) - 0.15),
    ]
    lines = ["## 6. 핵심 invariant 검증 (결정 #2)", "", row(["invariant", "결과"]), row(["---"] * 2)]
    for desc, ok in checks:
        lines.append(row([desc, "**PASS**" if ok else "**FAIL**"]))
    lines += [
        "",
        f"- A/C 상대 순위(현재: {'C > A' if rank_of['rest-c'] < rank_of['rest-a'] else 'A > C'})는 "
        "신호 결과를 따르며 판단 대상이 아니다.",
        f"- A 하락 폭: 단순 {stars(naive_map['rest-a']):.2f}★ → 보정 "
        f"{stars(by_id['rest-a'].sub.rating_adjusted):.2f}★ ({a_drop:+.2f}★), "
        f"순위 1위 → {rank_of['rest-a'] + 1}위",
        "",
    ]
    return lines


def section_c_rating_sensitivity(restaurants, reviews) -> list[str]:
    """결정 #3: 기본 10 유지, 후보 4값에 대한 순위/점수 민감도."""
    lines = [
        "## 7. c_rating 민감도 (결정 #3: 기본값 10, 실데이터로 확정)",
        "",
        row(["c_rating", "순위", "B", "D", "E", "C", "A", "B−D 격차"]),
        row(["---"] * 8),
    ]
    for c_rating in C_RATING_CANDIDATES:
        cfg = replace(ScoringConfig(), c_rating=c_rating)
        results = score_dataset(restaurants, reviews, cfg, REFERENCE_DATE)
        by_id = result_by_id(results)
        order = " > ".join(NAME[r.restaurant.id] for r in rank_by(results, "A"))
        gap = by_id["rest-b"].overall_a.score - by_id["rest-d"].overall_a.score
        lines.append(row([
            str(c_rating), order,
            f"{by_id['rest-b'].overall_a.score:.1f}", f"{by_id['rest-d'].overall_a.score:.1f}",
            f"{by_id['rest-e'].overall_a.score:.1f}", f"{by_id['rest-c'].overall_a.score:.1f}",
            f"{by_id['rest-a'].overall_a.score:.1f}", f"{gap:+.1f}",
        ]))
    lines.append("")
    return lines


def section_dup_threshold_sensitivity(restaurants, reviews) -> list[str]:
    """결정 #4: duplicate threshold 후보 6값에 대한 식당별 중복 탐지 수."""
    lines = [
        "## 8. duplicate threshold 민감도 (결정 #4: 기본값 0.89)",
        "",
        row(["threshold"] + [NAME[rid] for rid in ["rest-a", "rest-b", "rest-c", "rest-d", "rest-e"]]),
        row(["---"] * 6),
    ]
    cfg = ScoringConfig()
    for threshold in DUPLICATE_THRESHOLD_CANDIDATES:
        probe = replace(cfg, duplicate_threshold=threshold)
        counts = []
        for rid in ["rest-a", "rest-b", "rest-c", "rest-d", "rest-e"]:
            own = [r for r in reviews if r.restaurant_id == rid]
            clusters = near_duplicate_clusters(own, probe)
            counts.append(str(sum(len(c) - 1 for c in clusters)))
        marker = " ← 기본" if threshold == cfg.duplicate_threshold else ""
        lines.append(row([f"{threshold:.2f}{marker}"] + counts))
    lines += [
        "",
        "> threshold가 낮아지면 정상 리뷰의 단어 변형까지 중복으로 오탐(FP), "
        "높아지면 1~2글자 편집 복붙 스팸을 놓친다(FN). 0.89는 두 집단의 실측 분리 간극 중앙.",
        "",
    ]
    return lines


def section_prior_sensitivity(restaurants, reviews) -> list[str]:
    """D5: ad_prior가 설정값임을 시연 — prior 변경이 순위/점수에 주는 영향."""
    lines = [
        "## 9. ad_prior 민감도 (D5: 관측 prior로 교체 가능)",
        "",
        row(["ad_prior", "순위", "A 더피자랩 Overall A", "B 을지면옥 Overall A"]),
        row(["---"] * 4),
    ]
    for prior in (0.20, 0.30, 0.50):
        cfg = replace(ScoringConfig(), ad_prior=prior)
        results = score_dataset(restaurants, reviews, cfg, REFERENCE_DATE)
        by_id = result_by_id(results)
        order = " > ".join(NAME[r.restaurant.id] for r in rank_by(results, "A"))
        lines.append(row([
            str(prior), order,
            f"{by_id['rest-a'].overall_a.score:.1f}", f"{by_id['rest-b'].overall_a.score:.1f}",
        ]))
    lines += [
        "",
        "→ ad_prior는 confidence가 낮은 LLM 판단의 수축 목적지. 라벨 데이터가 쌓이면 observed prior로 교체.",
        "",
    ]
    return lines


def build_report() -> str:
    restaurants, reviews = build_dataset()
    cfg = ScoringConfig()
    results = score_dataset(restaurants, reviews, cfg, REFERENCE_DATE)
    naive = naive_ranking(restaurants, reviews)

    lines = [
        "# Phase 0 시뮬레이션 보고서",
        "",
        f"- 알고리즘 버전: {cfg.algorithm_version} / 기준일: {REFERENCE_DATE:%Y-%m-%d}"
        f" / 리뷰 {len(reviews)}개",
        "",
    ]
    lines += section_ranking(results, naive)
    lines += section_rating_shift(results, naive)
    lines += section_subscores(results)
    lines += section_signals(results)
    lines += section_contribution(results)
    lines += section_invariants(results, naive)
    lines += section_c_rating_sensitivity(restaurants, reviews)
    lines += section_dup_threshold_sensitivity(restaurants, reviews)
    lines += section_prior_sensitivity(restaurants, reviews)
    return "\n".join(lines)


def main() -> None:
    report = build_report()
    print(report)
    out = Path(__file__).resolve().parent / "REPORT.md"
    out.write_text(report, encoding="utf-8")
    print(f"\n→ 저장: {out}")


if __name__ == "__main__":
    main()
