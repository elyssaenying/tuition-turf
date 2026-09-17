"""OneMap authentication-only preflight for the private competitor pipeline.

This deliberately does not reuse the older combined S001/S007 preflight: it
makes at most one authentication request and never makes a search or routing
request. Authentication material exists only inside ``_authenticate`` while
the request is in flight and is discarded before this module returns.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .geocode import OneMapUnavailable, _authenticate


def run_auth_preflight(repo_root: Path) -> dict[str, Any]:
    """Attempt exactly one authentication request where credentials exist.

    The returned object contains only safe status/count fields and an optional
    HTTP status code. It never includes credentials, a token, request body or
    response body, and it writes no files.
    """
    try:
        _authenticate(repo_root)
    except OneMapUnavailable as error:
        result: dict[str, Any] = {
            "status": f"blocked_{error.category}",
            "authentication_requests": 0 if error.category == "missing_credentials" else 1,
            "search_requests": 0,
            "routing_requests": 0,
        }
        if error.http_status is not None:
            result["http_status"] = error.http_status
        return result
    return {
        "status": "pass",
        "authentication_requests": 1,
        "search_requests": 0,
        "routing_requests": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one OneMap authentication request only; no search or routing requests."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = run_auth_preflight(args.repo_root.resolve())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
