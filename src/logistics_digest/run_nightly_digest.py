"""Runnable example entry point for a logistics operations team."""
from __future__ import annotations

import json
from pathlib import Path

from .overnight_digest import InfraiClient, OvernightDigestRequest, deliver_digest


def main() -> None:
    source = Path("shipments.json")
    request = OvernightDigestRequest.model_validate_json(source.read_text())
    print(json.dumps(deliver_digest(request, InfraiClient()), indent=2))


if __name__ == "__main__":
    main()
