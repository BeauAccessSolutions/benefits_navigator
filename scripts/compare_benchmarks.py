#!/usr/bin/env python3
"""
Benchmark Comparison Script

Compares current benchmark results against a baseline and reports regressions.
This script is for manual/local use. CI workflows upload artifacts separately
since cross-workflow artifact download is not straightforward in GitHub Actions.

Usage:
    python scripts/compare_benchmarks.py --baseline baseline.json --current current.json --threshold 20

Exit codes:
    0 - No significant regressions
    1 - Significant regression detected
    2 - Missing files or parse error
"""

import argparse
import json
import sys
from pathlib import Path


def load_benchmark_results(filepath: Path) -> dict:
    """Load benchmark results from JSON file."""
    if not filepath.exists():
        return None

    try:
        with open(filepath, "r") as f:
            data = json.load(f)

        # Handle pytest-benchmark format
        if "benchmarks" in data:
            return {b["name"]: b for b in data["benchmarks"]}

        # Handle our simple format
        if "tests" in data:
            return data["tests"]

        return data
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing {filepath}: {e}")
        return None


def compare_results(baseline: dict, current: dict, threshold_percent: float) -> list:
    """
    Compare benchmark results and return list of regressions.

    Returns list of (test_name, baseline_time, current_time, percent_change)
    """
    regressions = []

    for test_name, current_data in current.items():
        if test_name not in baseline:
            print(f"New test: {test_name} (no baseline)")
            continue

        baseline_data = baseline[test_name]

        # Extract timing - handle both formats
        if isinstance(current_data, dict):
            current_time = current_data.get("mean", current_data.get("time", 0))
            baseline_time = baseline_data.get("mean", baseline_data.get("time", 0))
        else:
            current_time = current_data
            baseline_time = baseline_data

        if baseline_time == 0:
            continue

        percent_change = ((current_time - baseline_time) / baseline_time) * 100

        if percent_change > threshold_percent:
            regressions.append((test_name, baseline_time, current_time, percent_change))

    return regressions


def main():
    parser = argparse.ArgumentParser(description="Compare benchmark results")
    parser.add_argument(
        "--baseline", type=str, required=True, help="Baseline results JSON"
    )
    parser.add_argument(
        "--current", type=str, required=True, help="Current results JSON"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=20.0,
        help="Regression threshold percentage (default: 20)",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)

    print(f"Comparing benchmarks (threshold: {args.threshold}% regression)")
    print(f"  Baseline: {baseline_path}")
    print(f"  Current:  {current_path}")
    print()

    # Load results
    baseline = load_benchmark_results(baseline_path)
    current = load_benchmark_results(current_path)

    if baseline is None:
        print("No baseline found - skipping comparison (first run?)")
        sys.exit(0)

    if current is None:
        print("Error: Could not load current benchmark results")
        sys.exit(2)

    # Compare
    regressions = compare_results(baseline, current, args.threshold)

    if regressions:
        print(
            f"REGRESSION DETECTED: {len(regressions)} test(s) regressed by >{args.threshold}%"
        )
        print()
        for test_name, baseline_time, current_time, percent_change in regressions:
            print(f"  {test_name}:")
            print(f"    Baseline: {baseline_time:.4f}s")
            print(f"    Current:  {current_time:.4f}s")
            print(f"    Change:   +{percent_change:.1f}%")
            print()
        sys.exit(1)
    else:
        print("OK: No significant performance regressions detected")
        sys.exit(0)


if __name__ == "__main__":
    main()
