from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


def readiness(repo_root: Path) -> dict[str, object]:
    config = json.loads(
        (repo_root / "config/accessibility/national_routing_plan.json").read_text(encoding="utf-8")
    )
    national_approved = (
        config.get("execution_status") == "approved_for_national_execution"
        and config.get("national_execution_authorised") is True
    )
    bounded_only = (
        config.get("execution_status") == "approved_for_bounded_readiness"
        and config.get("bounded_sample_authorised") is True
        and not config.get("national_execution_authorised")
    )
    return {
        "status": "ready_for_national_execution" if national_approved else ("bounded_sample_only" if bounded_only else "blocked_not_approved"),
        "authentication_requests": 0,
        "routing_requests": 0,
        "network_requests": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely gate national OneMap route execution")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = readiness(args.repo_root.resolve())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ready_for_national_execution" else 2


if __name__ == "__main__":
    raise SystemExit(main())
