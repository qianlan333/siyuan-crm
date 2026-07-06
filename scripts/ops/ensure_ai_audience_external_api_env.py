from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_REQUIRED_PREFIXES = ("prod_verify_", "audience_")
PREFIX_KEY = "AICRM_AI_AUDIENCE_SPEC_ALLOWED_PREFIXES"


def ensure_allowed_prefixes(env_path: Path, required_prefixes: tuple[str, ...] = DEFAULT_REQUIRED_PREFIXES) -> bool:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated_lines: list[str] = []
    found = False
    changed = False

    for line in lines:
        if line.startswith(f"{PREFIX_KEY}="):
            found = True
            raw_value = line.split("=", 1)[1].strip().strip('"').strip("'")
            prefixes = [item.strip() for item in raw_value.split(",") if item.strip()]
            for prefix in required_prefixes:
                if prefix not in prefixes:
                    prefixes.append(prefix)
                    changed = True
            updated_lines.append(f"{PREFIX_KEY}={','.join(prefixes)}")
        else:
            updated_lines.append(line)

    if not found:
        updated_lines.append(f"{PREFIX_KEY}={','.join(required_prefixes)}")
        changed = True

    if changed:
        env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure AI Audience External API package key prefixes are configured.")
    parser.add_argument("env_path", type=Path)
    parser.add_argument("--required-prefix", action="append", default=[])
    args = parser.parse_args()
    required = tuple(args.required_prefix or DEFAULT_REQUIRED_PREFIXES)
    changed = ensure_allowed_prefixes(args.env_path, required)
    print(f"{PREFIX_KEY} {'updated' if changed else 'already_configured'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
