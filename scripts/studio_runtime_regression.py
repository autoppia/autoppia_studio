#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(label: str, cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> bool:
    print(f"\n== {label} ==")
    print(" ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(cwd), env=env or os.environ.copy())
    if completed.returncode != 0:
        print(f"{label} failed with exit code {completed.returncode}")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run focused Autoppia Studio runtime regression checks.")
    parser.add_argument("--skip-frontend", action="store_true", help="Do not run frontend tests/build.")
    parser.add_argument("--audit-matrix", action="store_true", help="Also call the connector benchmark audit matrix against the configured backend.")
    parser.add_argument("--browser-smoke", action="store_true", help="Run the headless Chrome UI smoke through Chrome DevTools Protocol.")
    args = parser.parse_args()

    checks: list[tuple[str, list[str], Path, dict[str, str] | None]] = [
        (
            "backend runtime/approval/artifact tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "backend/tests/test_sio_resume.py",
                "backend/tests/test_approvals.py",
                "backend/tests/test_session_artifacts.py",
                "backend/tests/test_connector_benchmarks.py",
                "backend/tests/test_evals.py",
                "-q",
            ],
            ROOT,
            None,
        )
    ]

    if not args.skip_frontend:
        frontend_env = os.environ.copy()
        frontend_env["CI"] = "true"
        checks.extend(
            [
                (
                    "frontend runtime/approval/artifact tests",
                    [
                        "npm",
                        "test",
                        "--",
                        "--watchAll=false",
                        "src/components/session/agent-response.test.tsx",
                        "src/pages/approvals.test.tsx",
                        "src/pages/artifacts.test.tsx",
                    ],
                    ROOT / "frontend",
                    frontend_env,
                ),
                ("frontend production build", ["npm", "run", "build"], ROOT / "frontend", frontend_env),
            ]
        )

    if args.audit_matrix:
        checks.append(
            (
                "connector audit matrix",
                [sys.executable, "scripts/connector_runtime_benchmark.py", "--audit-matrix"],
                ROOT,
                None,
            )
        )
    if args.browser_smoke:
        checks.append(
            (
                "browser UI smoke",
                ["node", "scripts/studio_browser_smoke.mjs"],
                ROOT,
                None,
            )
        )

    failures = 0
    for label, cmd, cwd, env in checks:
        if not run(label, cmd, cwd=cwd, env=env):
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
