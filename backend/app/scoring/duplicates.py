"""Near-duplicate 리뷰 탐지 — 식당 내 char n-gram Jaccard (개인 규모에서 O(n²)로 충분, 임베딩 불필요).

유사 문구 반복(마케팅 템플릿)은 manipulation 신호로 사용되고,
클러스터 멤버는 가중치를 dup_member_factor만큼 감쇠시켜 동일 리뷰의 반복 영향력을 막는다.
"""
import re

from ..config import ScoringConfig
from ..models import Review

_NON_WORD = re.compile(r"[^가-힣a-z0-9]+")


def normalize_text(text: str) -> str:
    return _NON_WORD.sub("", text.lower())


def char_ngrams(text: str, n: int) -> set[str]:
    normalized = normalize_text(text)
    if len(normalized) < n:
        return {normalized} if normalized else set()
    return {normalized[i : i + n] for i in range(len(normalized) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def near_duplicate_clusters(reviews: list[Review], cfg: ScoringConfig) -> list[list[Review]]:
    """Jaccard ≥ threshold인 리뷰들을 클러스터로 묶는다 (2개 이상만 반환).

    정규화 후 duplicate_min_length 미만의 짧은 상용구("맛있어요"류)는 서로 비교하지 않는다 —
    짧은 문구의 유사성은 조작 증거로 쓸 수 없다.
    """
    eligible = [r for r in reviews if len(normalize_text(r.text)) >= cfg.duplicate_min_length]
    grams = [char_ngrams(r.text, cfg.dup_ngram_size) for r in eligible]
    parent = list(range(len(eligible)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(len(eligible)):
        for j in range(i + 1, len(eligible)):
            if jaccard(grams[i], grams[j]) >= cfg.duplicate_threshold:
                union(i, j)

    groups: dict[int, list[Review]] = {}
    for i, review in enumerate(eligible):
        groups.setdefault(find(i), []).append(review)
    return [g for g in groups.values() if len(g) >= 2]


def mark_duplicates(reviews: list[Review], cfg: ScoringConfig) -> dict[str, str]:
    """{멤버 리뷰 id: 대표 리뷰 id}. 대표는 클러스터 내 가장 오래된 리뷰.

    리뷰 객체의 duplicate_of 필드도 함께 채운다.
    """
    member_to_rep: dict[str, str] = {}
    for cluster in near_duplicate_clusters(reviews, cfg):
        rep = min(cluster, key=lambda r: r.reviewed_at)
        for review in cluster:
            if review.id == rep.id:
                continue
            member_to_rep[review.id] = rep.id
            review.duplicate_of = rep.id
    return member_to_rep
