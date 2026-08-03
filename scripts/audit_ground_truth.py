"""
Ground Truth Audit — Phase 7
==============================
Audits all model specs in the registry for citation coverage.
Reports which models have expired, low-confidence, or missing citations.

Usage:
    python scripts/audit_ground_truth.py
    python scripts/audit_ground_truth.py --provider nvidia_nim
    python scripts/audit_ground_truth.py --min-confidence 0.8
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gateway.model_registry import (
    AutoModelRegistry,
    ModelSpec,
    ModelStatus,
    SourceCitation,
    get_registry,
)


# ============================================================
# Audit Logic
# ============================================================


def audit_model(
    spec: ModelSpec,
    max_age_days: int = 90,
    min_confidence: float = 0.7,
) -> dict:
    """Audit a single model's citation coverage.

    Returns:
        dict with audit results including issues found.
    """
    issues: list[str] = []
    warnings: list[str] = []
    now = datetime.now(UTC)
    max_age = timedelta(days=max_age_days)

    # Check verification confidence
    if spec.verification_confidence < min_confidence:
        issues.append(
            f"Low confidence: {spec.verification_confidence:.2f} < {min_confidence}"
        )

    # Check citation count
    if not spec.citations:
        issues.append("No citations attached")
    else:
        for field_name, citation in spec.citations.items():
            # Check citation age
            if citation.accessed_at and (now - citation.accessed_at) > max_age:
                days_old = (now - citation.accessed_at).days
                warnings.append(
                    f"Citation '{field_name}' is {days_old} days old "
                    f"(max: {max_age_days})"
                )

            # Check citation confidence
            if citation.confidence < min_confidence:
                issues.append(
                    f"Citation '{field_name}' has low confidence: "
                    f"{citation.confidence:.2f}"
                )

            # Check URL validity
            if not citation.url:
                warnings.append(f"Citation '{field_name}' has no URL")

    # Check model status
    if spec.status == ModelStatus.DEPRECATED:
        warnings.append("Model is DEPRECATED")
    elif spec.status == ModelStatus.DISABLED:
        warnings.append("Model is DISABLED")

    # Check last verified date
    if spec.last_verified:
        days_since_verified = (now - spec.last_verified).days
        if days_since_verified > max_age_days:
            warnings.append(
                f"Last verified {days_since_verified} days ago "
                f"(threshold: {max_age_days})"
            )

    return {
        "model_id": spec.model_id,
        "provider": spec.provider,
        "tier": spec.tier.value,
        "status": spec.status.value,
        "confidence": spec.verification_confidence,
        "citation_count": len(spec.citations),
        "issues": issues,
        "warnings": warnings,
        "passed": len(issues) == 0,
    }


def audit_registry(
    registry: AutoModelRegistry,
    provider_filter: str | None = None,
    max_age_days: int = 90,
    min_confidence: float = 0.7,
) -> dict:
    """Audit all models in the registry.

    Returns:
        dict with summary and per-model results.
    """
    models = registry.list_all()
    if provider_filter:
        models = [m for m in models if m.provider == provider_filter]

    results = []
    for spec in models:
        result = audit_model(spec, max_age_days, min_confidence)
        results.append(result)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    total_issues = sum(len(r["issues"]) for r in results)
    total_warnings = sum(len(r["warnings"]) for r in results)

    return {
        "audit_timestamp": datetime.now(UTC).isoformat(),
        "registry_stats": registry.get_stats(),
        "filter": {"provider": provider_filter, "max_age_days": max_age_days, "min_confidence": min_confidence},
        "summary": {
            "total_models": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{(passed / total * 100):.1f}%" if total else "N/A",
            "total_issues": total_issues,
            "total_warnings": total_warnings,
        },
        "results": results,
    }


def print_audit_report(audit: dict) -> None:
    """Print a human-readable audit report."""
    summary = audit["summary"]

    print("\n" + "=" * 70)
    print("📋 GROUND TRUTH AUDIT REPORT")
    print("=" * 70)
    print(f"  Timestamp:      {audit['audit_timestamp']}")
    print(f"  Provider Filter: {audit['filter']['provider'] or 'ALL'}")
    print(f"  Min Confidence:  {audit['filter']['min_confidence']}")
    print(f"  Max Age (days):  {audit['filter']['max_age_days']}")
    print()
    print(f"  Total Models:    {summary['total_models']}")
    print(f"  ✅ Passed:       {summary['passed']}")
    print(f"  ❌ Failed:       {summary['failed']}")
    print(f"  Pass Rate:       {summary['pass_rate']}")
    print(f"  Issues:          {summary['total_issues']}")
    print(f"  Warnings:        {summary['total_warnings']}")
    print("=" * 70)

    # Show failed models
    failed = [r for r in audit["results"] if not r["passed"]]
    if failed:
        print("\n❌ FAILED MODELS:")
        print("-" * 60)
        for r in failed:
            print(f"\n  {r['model_id']} ({r['provider']}, {r['tier']})")
            print(f"    Confidence: {r['confidence']:.2f}")
            print(f"    Citations:  {r['citation_count']}")
            for issue in r["issues"]:
                print(f"    ⚠️  {issue}")
            for warning in r["warnings"]:
                print(f"    ℹ️  {warning}")

    # Show models with warnings only
    warned = [r for r in audit["results"] if r["passed"] and r["warnings"]]
    if warned:
        print(f"\n⚠️  MODELS WITH WARNINGS ({len(warned)}):")
        print("-" * 60)
        for r in warned[:10]:  # Limit to 10
            print(f"  {r['model_id']}: {'; '.join(r['warnings'][:2])}")

    print()


# ============================================================
# CLI
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="Audit ground truth citations in model registry")
    parser.add_argument("--provider", type=str, default=None, help="Filter by provider name")
    parser.add_argument("--max-age", type=int, default=90, help="Max citation age in days (default: 90)")
    parser.add_argument("--min-confidence", type=float, default=0.7, help="Min confidence threshold (default: 0.7)")
    parser.add_argument("--output", type=str, default=None, help="Save JSON report to file")
    parser.add_argument("--fail-on-issues", action="store_true", help="Exit with code 1 if any issues found")

    args = parser.parse_args()

    # Get registry (may be empty if not initialized)
    registry = get_registry()

    audit = audit_registry(
        registry=registry,
        provider_filter=args.provider,
        max_age_days=args.max_age,
        min_confidence=args.min_confidence,
    )

    print_audit_report(audit)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(audit, f, indent=2, default=str)
        print(f"📁 Report saved to: {output_path}")

    if args.fail_on_issues and audit["summary"]["total_issues"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
