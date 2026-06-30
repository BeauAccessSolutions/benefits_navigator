#!/usr/bin/env python
"""
Run All Testing Agents

Executes all AI-powered testing agents and generates a combined report.
"""

import os
import sys
import json
from datetime import datetime

# Add project root to path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from tests.agents.explorer_agent import ExplorerAgent
from tests.agents.user_journey_agent import UserJourneyAgent
from tests.agents.chaos_agent import ChaosAgent


def run_all_agents(
    headless: bool = True,
    report_dir: str = "tests/agents/reports",
) -> dict:
    """
    Run all testing agents and generate reports.

    Returns a summary of all agent runs.
    """
    os.makedirs(report_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results = {
        "timestamp": timestamp,
        "agents": [],
        "total_pages_visited": set(),
        "total_errors": 0,
        "vulnerabilities": [],
    }

    agents = [
        (
            "Explorer (Anonymous)",
            ExplorerAgent(headless=headless, authenticated=False, max_pages=30),
        ),
        (
            "Explorer (Authenticated)",
            ExplorerAgent(headless=headless, authenticated=True, max_pages=50),
        ),
        ("User Journey", UserJourneyAgent(headless=headless)),
        ("Chaos", ChaosAgent(headless=headless)),
    ]

    for name, agent in agents:
        print(f'\n{"="*60}')
        print(f"Running: {name}")
        print("=" * 60)

        try:
            session = agent.run()

            # Save individual report
            report_path = f"{report_dir}/{agent.name}_{timestamp}.json"
            session.save_report(report_path)

            agent_result = {
                "name": name,
                "agent_type": agent.name,
                "pages_visited": len(session.pages_visited),
                "actions": len(session.results),
                "success_rate": session.success_rate,
                "errors": len(session.errors_found),
                "report_path": report_path,
            }

            results["agents"].append(agent_result)
            results["total_pages_visited"].update(session.pages_visited)
            results["total_errors"] += len(session.errors_found)

            # Check for vulnerabilities (from chaos agent)
            if hasattr(session, "details") and session.details.get("vulnerabilities"):
                results["vulnerabilities"].extend(session.details["vulnerabilities"])

            print(f'  Pages: {agent_result["pages_visited"]}')
            print(f'  Actions: {agent_result["actions"]}')
            print(f'  Success Rate: {agent_result["success_rate"]:.1%}')
            print(f'  Errors: {agent_result["errors"]}')

        except Exception as e:
            print(f"  ERROR: {e}")
            results["agents"].append(
                {
                    "name": name,
                    "agent_type": agent.name,
                    "error": str(e),
                }
            )

    # Convert set to list for JSON
    results["total_pages_visited"] = list(results["total_pages_visited"])

    # Save combined report
    combined_path = f"{report_dir}/combined_{timestamp}.json"
    with open(combined_path, "w") as f:
        json.dump(results, f, indent=2)

    return results


def print_summary(results: dict):
    """Print a summary of the agent run."""
    print("\n" + "=" * 60)
    print("AGENT TESTING SUMMARY")
    print("=" * 60)

    print(f'\nTimestamp: {results["timestamp"]}')
    print(f'Total Pages Visited: {len(results["total_pages_visited"])}')
    print(f'Total Errors Found: {results["total_errors"]}')

    print("\nAgent Results:")
    for agent in results["agents"]:
        if "error" in agent:
            print(f'  {agent["name"]}: FAILED - {agent["error"]}')
        else:
            status = (
                "✓"
                if agent["success_rate"] > 0.95
                else "!" if agent["success_rate"] > 0.8 else "✗"
            )
            print(
                f'  {status} {agent["name"]}: {agent["success_rate"]:.1%} success ({agent["actions"]} actions)'
            )

    if results["vulnerabilities"]:
        print(
            f'\n⚠️  POTENTIAL VULNERABILITIES FOUND: {len(results["vulnerabilities"])}'
        )
        for vuln in results["vulnerabilities"][:5]:
            print(
                f'    - {vuln["type"]}: {vuln.get("url", vuln.get("payload", ""))[:50]}'
            )
    else:
        print("\n✓ No vulnerabilities detected")

    print("\nReports saved to: tests/agents/reports/")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run all AI testing agents")
    parser.add_argument(
        "--headed", action="store_true", help="Run browsers in headed mode"
    )
    parser.add_argument(
        "--report-dir", default="tests/agents/reports", help="Report output directory"
    )
    args = parser.parse_args()

    results = run_all_agents(
        headless=not args.headed,
        report_dir=args.report_dir,
    )

    print_summary(results)

    # Exit with error code if there were failures
    if results["total_errors"] > 0 or results["vulnerabilities"]:
        sys.exit(1)
