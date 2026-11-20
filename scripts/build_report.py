#!/usr/bin/env python3
"""Build verified figures, the final report, and the repository README."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("XDG_CACHE_HOME", str(PROJECT_ROOT / ".cache"))
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".cache" / "matplotlib"))

from kuairand_analysis.config import AnalysisConfig  # noqa: E402
from kuairand_analysis.db import connect  # noqa: E402
from kuairand_analysis.reporting import ReportComposer  # noqa: E402
from kuairand_analysis.visualization import VisualizationBuilder  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config.yaml"),
        help="Path to config.yaml.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = AnalysisConfig.from_yaml(args.config)
    connection = connect(config)
    try:
        for existing in config.figures_dir.glob("*.png"):
            existing.unlink()
        figures = VisualizationBuilder(connection, config).build_all()
        report, readme = ReportComposer(connection, config).compose()
        (config.project_root / "reports" / "final_report.md").write_text(
            report, encoding="utf-8"
        )
        (config.project_root / "README.md").write_text(readme, encoding="utf-8")
        print(f"Wrote {len(figures)} figures, final_report.md, and README.md.")
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
