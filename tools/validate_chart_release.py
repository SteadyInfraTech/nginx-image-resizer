#!/usr/bin/env python3
"""Validate Helm chart release metadata without third-party dependencies."""

import argparse
import re
import sys
from pathlib import Path

SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def read_scalar(contents: str, key: str) -> str:
    matches = re.findall(
        rf"(?m)^{re.escape(key)}:\s*['\"]?([^\s'\"#]+)", contents
    )
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one {key!r} scalar in Chart.yaml; found {len(matches)}"
        )
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chart",
        type=Path,
        default=Path("charts/nginx-image-resizer/Chart.yaml"),
        help="path to Helm Chart.yaml",
    )
    parser.add_argument(
        "--expected-app-version",
        help="require appVersion to match this release version (without leading v)",
    )
    args = parser.parse_args()

    try:
        contents = args.chart.read_text(encoding="utf-8")
        chart_version = read_scalar(contents, "version")
        app_version = read_scalar(contents, "appVersion")
        if not SEMVER.fullmatch(chart_version):
            raise ValueError(f"chart version is not valid SemVer: {chart_version!r}")
        if not SEMVER.fullmatch(app_version):
            raise ValueError(f"appVersion is not valid SemVer: {app_version!r}")
        if args.expected_app_version and app_version != args.expected_app_version:
            raise ValueError(
                f"chart appVersion {app_version!r} does not match release "
                f"version {args.expected_app_version!r}"
            )
    except (OSError, ValueError) as error:
        print(f"release metadata validation failed: {error}", file=sys.stderr)
        return 1

    print(f"chart version {chart_version}; appVersion {app_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
