"""베이지안 수축(shrinkage). 리뷰 수가 적은 식당의 과대평가 방지."""


def shrunk_mean(values: list[float], weights: list[float], prior: float, c: float) -> float:
    """(Σ w·v + C·prior) / (Σw + C). 가중치 합이 0이면 prior, 커질수록 가중평균에 수렴."""
    total_w = sum(weights)
    weighted = sum(v * w for v, w in zip(values, weights))
    return (weighted + c * prior) / (total_w + c)
