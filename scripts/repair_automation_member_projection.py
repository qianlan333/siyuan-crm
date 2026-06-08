from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wecom_ability_service import create_app
from wecom_ability_service.domains.automation_conversion.projection_repair_service import (
    repair_automation_member_projection,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run/apply automation_member projection repair for one user/program.")
    parser.add_argument("--program-id", type=int, required=True)
    parser.add_argument("--external-userid", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--operator-id", default="projection_repair")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    dry_run = not bool(args.apply) or bool(args.dry_run)
    app = create_app()
    with app.app_context():
        result = repair_automation_member_projection(
            external_userid=args.external_userid,
            program_id=int(args.program_id),
            dry_run=dry_run,
            apply=bool(args.apply),
            operator_id=args.operator_id,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
