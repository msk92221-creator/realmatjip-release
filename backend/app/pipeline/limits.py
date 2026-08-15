"""LLM 비용 보호 한계 (스펙 §6) — 모두 환경변수로 조정 가능."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalyzeLimits:
    max_reviews_per_job: int = 200
    max_estimated_tokens_per_job: int = 300_000
    max_estimated_cost_per_job: float = 2.0        # USD (추정)
    # USD/1K tokens — GLM air급 실제가 수준의 보수적 추정치 (ZAI_PRICE_*로 덮어쓰기 권장)
    price_input_per_1k: float = 0.0006
    price_output_per_1k: float = 0.0022


def limits_from_env(env: dict | None = None) -> AnalyzeLimits:
    env = env if env is not None else os.environ
    defaults = AnalyzeLimits()

    def get_int(key: str, default: int) -> int:
        try:
            return int(env.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_float(key: str, default: float) -> float:
        try:
            return float(env.get(key, default))
        except (TypeError, ValueError):
            return default

    return AnalyzeLimits(
        max_reviews_per_job=get_int("MAX_REVIEWS_PER_JOB", defaults.max_reviews_per_job),
        max_estimated_tokens_per_job=get_int("MAX_ESTIMATED_TOKENS_PER_JOB",
                                             defaults.max_estimated_tokens_per_job),
        max_estimated_cost_per_job=get_float("MAX_ESTIMATED_COST_PER_JOB",
                                             defaults.max_estimated_cost_per_job),
        price_input_per_1k=get_float("ZAI_PRICE_INPUT_PER_1K", defaults.price_input_per_1k),
        price_output_per_1k=get_float("ZAI_PRICE_OUTPUT_PER_1K", defaults.price_output_per_1k),
    )


def estimate_cost(limits: AnalyzeLimits, tokens_input: int, tokens_output: int) -> float:
    return round(
        tokens_input / 1000 * limits.price_input_per_1k
        + tokens_output / 1000 * limits.price_output_per_1k,
        4,
    )
