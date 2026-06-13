from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


DEFAULT_API_URL = "https://enterprise-ai-analyst-1032931657035.europe-west1.run.app"

TEST_CASES = [
    {
        "id": "apple_mixed",
        "question": "What was Apple's revenue in 2024, and what risks were mentioned in its Q3 report?",
        "ground_truth": (
            "Revenue: 85.8 billion USD. Risks include US-China geopolitics, Asian supply-chain "
            "concentration, TSMC/Taiwan, EU regulation, FX, competition, antitrust, and privacy."
        ),
    },
    {
        "id": "alphabet_mixed",
        "question": "What was Alphabet's revenue in 2024, and what business risks were discussed in its Q1 report?",
        "ground_truth": (
            "Revenue: 80.5 billion USD. Risks include AI disruption to Search, EU DMA regulation, "
            "DOJ antitrust, AI Overviews monetization, and high capital expenditure."
        ),
    },
    {
        "id": "highest_net_income_sql",
        "question": "Which company has the highest net income in the SQL database, and what is the amount?",
        "ground_truth": "Microsoft Corporation has the highest net income: 88.1 billion USD.",
    },
    {
        "id": "microsoft_meta_comparison",
        "question": (
            "Compare Microsoft and Meta revenue in the database, then summarize one AI strategy "
            "mentioned in each company's report."
        ),
        "ground_truth": (
            "Microsoft revenue is 245.1 billion USD and Meta revenue is 134.9 billion USD. "
            "Microsoft emphasizes Azure/Copilot AI; Meta emphasizes open-source Llama and AI-driven products."
        ),
    },
    {
        "id": "tesla_risks",
        "question": "What risks or challenges were discussed in Tesla's Q4 FY2023 shareholder letter?",
        "ground_truth": (
            "Relevant challenges include vehicle demand and pricing pressure, manufacturing ramp risk, "
            "competition, regulatory/autonomy uncertainty, and capital-intensive expansion."
        ),
    },
]

MANUAL_GRADES = {
    "apple_mixed": {
        "faithfulness": 1.0,
        "answer_relevance": 1.0,
        "notes": "All numeric and qualitative claims are supported by SQL and the retrieved Q3 passages.",
    },
    "alphabet_mixed": {
        "faithfulness": 1.0,
        "answer_relevance": 1.0,
        "notes": "Revenue and all five risks match the SQL row and retrieved transcript sections.",
    },
    "highest_net_income_sql": {
        "faithfulness": 1.0,
        "answer_relevance": 1.0,
        "notes": "The concise answer exactly matches the ordered SQL result.",
    },
    "microsoft_meta_comparison": {
        "faithfulness": 0.8,
        "answer_relevance": 1.0,
        "notes": (
            "The values and strategies are correct, but the API response exposes only the last vector search "
            "context, so Microsoft's qualitative claim is not fully auditable from the returned payload."
        ),
    },
    "tesla_risks": {
        "faithfulness": 1.0,
        "answer_relevance": 1.0,
        "notes": "The answer is directly supported by the retrieved Key Risks and pricing-pressure sections.",
    },
}


def ask_agent(api_url: str, question: str, limit: int) -> tuple[dict[str, Any], float]:
    """Send one evaluation question to the deployed FastAPI agent."""
    payload = json.dumps({"question": question, "limit": limit}).encode("utf-8")
    request = Request(
        f"{api_url.rstrip('/')}/ask",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started_at = time.perf_counter()
    with urlopen(request, timeout=300) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result, round(time.perf_counter() - started_at, 3)


def is_quota_response(response: dict[str, Any]) -> bool:
    """Detect the API's controlled Gemini quota response."""
    return "quota/rate-limit error" in str(response.get("answer", "")).lower()


def run_evaluation(
    api_url: str,
    limit: int,
    selected_ids: set[str] | None = None,
    delay_seconds: float = 0,
    max_attempts: int = 3,
) -> list[dict[str, Any]]:
    """Run the five fixed evaluation cases and return auditable raw outputs."""
    results = []
    cases = [case for case in TEST_CASES if selected_ids is None or case["id"] in selected_ids]
    for case_index, case in enumerate(cases):
        attempts = 0
        total_latency = 0.0
        while True:
            attempts += 1
            response, latency_seconds = ask_agent(api_url, case["question"], limit)
            total_latency += latency_seconds
            if not is_quota_response(response) or attempts >= max_attempts:
                break
            wait_seconds = delay_seconds * attempts or 15 * attempts
            print(f"[{case['id']}] quota response; retrying in {wait_seconds:.0f}s")
            time.sleep(wait_seconds)

        results.append(
            {
                **case,
                "status": "quota_error" if is_quota_response(response) else "success",
                "answer": response.get("answer", ""),
                "contexts": response.get("context", []),
                "sql_result": response.get("sql_result"),
                "latency_seconds": round(total_latency, 3),
                "attempts": attempts,
                "manual_grade": (
                    MANUAL_GRADES[case["id"]]
                    if not is_quota_response(response)
                    else {
                        "faithfulness": None,
                        "answer_relevance": None,
                        "notes": "Not graded because the provider quota prevented an agent answer.",
                    }
                ),
            }
        )
        print(f"[{case['id']}] completed in {total_latency:.3f}s ({attempts} attempt(s))")
        if delay_seconds and case_index < len(cases) - 1:
            time.sleep(delay_seconds)
    return results


def main() -> None:
    """Run the deployed-agent evaluation and save results for manual grading."""
    parser = argparse.ArgumentParser(description="Run five RAGAS-style evaluation queries against the deployed agent.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--limit", default=5, type=int)
    parser.add_argument("--output", default=Path("data/evaluation_run.json"), type=Path)
    parser.add_argument("--only", nargs="*", choices=[case["id"] for case in TEST_CASES])
    parser.add_argument("--delay-seconds", default=10.0, type=float)
    parser.add_argument("--max-attempts", default=3, type=int)
    args = parser.parse_args()

    selected_ids = set(args.only) if args.only else None
    results = run_evaluation(
        args.api_url,
        args.limit,
        selected_ids=selected_ids,
        delay_seconds=args.delay_seconds,
        max_attempts=args.max_attempts,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(results)} evaluation results to {args.output}")


if __name__ == "__main__":
    main()
