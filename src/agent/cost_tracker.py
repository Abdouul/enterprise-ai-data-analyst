from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Iterable


# Google Gemini Developer API standard paid-tier prices as of June 13, 2026,
# USD per 1M tokens. Environment overrides keep deployments adaptable.
# Environment variables can override these values when pricing changes.
GEMINI_PRICING = {
    "gemini-2.5-flash": (Decimal("0.30"), Decimal("2.50")),
    "gemini-2.5-flash-lite": (Decimal("0.10"), Decimal("0.40")),
}


@dataclass
class CostTracker:
    """Track exact reported tokens and calculate their configured USD cost."""

    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += int(prompt_tokens or 0)
        self.completion_tokens += int(completion_tokens or 0)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def rates_per_million(self) -> tuple[Decimal, Decimal]:
        default_input, default_output = GEMINI_PRICING.get(self.model, (Decimal("0"), Decimal("0")))
        input_rate = Decimal(os.getenv("FINOPS_INPUT_USD_PER_MILLION", str(default_input)))
        output_rate = Decimal(os.getenv("FINOPS_OUTPUT_USD_PER_MILLION", str(default_output)))
        return input_rate, output_rate

    @property
    def estimated_cost_usd(self) -> Decimal:
        input_rate, output_rate = self.rates_per_million
        cost = (
            Decimal(self.prompt_tokens) * input_rate
            + Decimal(self.completion_tokens) * output_rate
        ) / Decimal("1000000")
        return cost.quantize(Decimal("0.00000001"))

    def as_log_record(self, event: str) -> dict[str, object]:
        record = asdict(self)
        input_rate, output_rate = self.rates_per_million
        record.update(
            {
                "event": event,
                "total_tokens": self.total_tokens,
                "input_usd_per_million": str(input_rate),
                "output_usd_per_million": str(output_rate),
                "estimated_cost_usd": str(self.estimated_cost_usd),
            }
        )
        return record


def tracker_from_messages(messages: Iterable[object], model: str) -> CostTracker:
    """Aggregate token usage reported on all AI messages in one agent run."""
    tracker = CostTracker(model=model)
    for message in messages:
        usage = getattr(message, "usage_metadata", None) or {}
        prompt_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        completion_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
        tracker.add_usage(prompt_tokens, completion_tokens)
    return tracker


def log_cost(tracker: CostTracker, event: str = "agent_finops") -> None:
    """Write one structured FinOps record to stdout/Cloud Run logs."""
    print("[finops] " + json.dumps(tracker.as_log_record(event), sort_keys=True))
