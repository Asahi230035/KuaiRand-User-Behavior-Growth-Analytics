#!/usr/bin/env python3
"""Run the full KuaiRand analysis pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from kuairand_analysis.config import AnalysisConfig  # noqa: E402
from kuairand_analysis.pipeline import AnalysisPipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config.yaml"),
        help="Path to config.yaml.",
    )
    parser.add_argument(
        "--raw-dir",
        default=None,
        help="Override the configured raw CSV directory.",
    )
    parser.add_argument(
        "--skip-statistics",
        action="store_true",
        help="Run data/SQL stages without fitting return models.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config = AnalysisConfig.from_yaml(args.config, raw_dir_override=args.raw_dir)
    pipeline = AnalysisPipeline(config, run_statistics=not args.skip_statistics)
    result = pipeline.run()
    print(
        f"Completed {len(result['completed_stages'])} stages in "
        f"{result['elapsed_seconds']:.1f} seconds."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
