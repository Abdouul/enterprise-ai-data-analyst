from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostTracker:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usd_per_1k_prompt_tokens: float = 0.0
    usd_per_1k_completion_tokens: float = 0.0

    def add_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens

    @property
    def estimated_cost_usd(self) -> float:
        prompt_cost = self.prompt_tokens / 1_000 * self.usd_per_1k_prompt_tokens
        completion_cost = self.completion_tokens / 1_000 * self.usd_per_1k_completion_tokens
        return round(prompt_cost + completion_cost, 6)
