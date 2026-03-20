"""
NaviBuild-Sentinel v2 — Main Pipeline

전체 파이프라인 실행:
  1. 로그 생성 (12 scenarios)
  2. DLT 파싱 → SQLite
  3. TF-IDF 이슈 분류
  4. FMEA RPN 심각도 산출
  5. 재발 분석
  6. A-SPICE 품질 게이트 판정
  7. OTA 롤아웃 시뮬레이션
  8. PM 대시보드 + 리포트 생성
  9. 12개 시나리오 Expected vs Actual 검증
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from log_generator import generate_all_scenarios
from log_parser import DLTLogParser
from issue_classifier import IssueClassifier
from severity_engine import FMEASeverityEngine
from recurrence_analyzer import RecurrenceAnalyzer
from release_gate import ASPICEQualityGate, OTARolloutSimulator
from report_generator import ReportGenerator


def run_pipeline(data_dir="data", output_dir="output"):
    """Execute the full NaviBuild-Sentinel v2 pipeline."""

    data_path = Path(data_dir)
    output_path = Path(output_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  NaviBuild-Sentinel v2 — Full Pipeline Execution")
    print("=" * 60)

    # ──────────────────────────────────────────
    # Phase 1: Generate synthetic logs
    # ──────────────────────────────────────────
    print("\n[Phase 1] Generating synthetic CAN/DLT logs...")
    manifest = generate_all_scenarios(output_dir=str(data_path))

    # ──────────────────────────────────────────
    # Phase 2: Parse logs into SQLite
    # ──────────────────────────────────────────
    print("\n[Phase 2] Parsing DLT logs...")
    parser = DLTLogParser(db_path=str(data_path / "events.db"))
    parser.clear_all()

    for sc in manifest:
        sc_id = sc["scenario_id"]
        log_file = data_path / sc["log_file"]
        stats = parser.parse_log_file(str(log_file), sc_id)
        print(f"  [{sc_id}] {stats['total']} events, {stats['errors']} errors")

    # ──────────────────────────────────────────
    # Phase 3-5: Classify, Score, Analyze per scenario
    # ──────────────────────────────────────────
    print("\n[Phase 3-5] Issue Classification + FMEA + Recurrence...")
    classifier = IssueClassifier()
    severity_engine = FMEASeverityEngine()

    all_results = {}

    for sc in manifest:
        sc_id = sc["scenario_id"]
        print(f"\n  --- {sc_id}: {sc['description']} ---")

        # Fresh recurrence analyzer per scenario (prevent cross-contamination)
        recurrence_analyzer = RecurrenceAnalyzer()

        # Get error events
        error_events = parser.get_error_events(sc_id)
        all_events = parser.get_all_events(sc_id)

        if not error_events:
            print(f"    No errors. Clean build.")
            all_results[sc_id] = {
                "evaluated_issues": [],
                "classification_summary": {"total_issues": 0},
                "severity_summary": {"total_issues": 0},
                "recurrence_results": [],
                "trend_analysis": {"trend_status": "INSUFFICIENT_DATA"},
            }
            continue

        # Step 3: Classify
        classified = classifier.classify_events(error_events)
        class_summary = classifier.get_classification_summary(classified)
        print(f"    Classified: {class_summary['by_category']}")

        # Step 4: FMEA Severity
        evaluated = severity_engine.evaluate_scenario(classified)
        sev_summary = severity_engine.get_scenario_severity_summary(evaluated)
        print(f"    Severity: {sev_summary['by_severity']} | "
              f"Max RPN: {sev_summary['max_rpn']} | "
              f"Avg RPN: {sev_summary['avg_rpn']}")

        # Step 5: Recurrence
        # Register history first
        recurrence_analyzer.register_build_history(evaluated)

        # Check for resolved markers in INFO logs
        for evt in all_events:
            if "resolved" in evt.get("message", "").lower() or \
               "fixed" in evt.get("message", "").lower():
                recurrence_analyzer.register_resolved([evt["message"]])

        current_build = sc.get("log_file", "").replace("_logs.json", "")
        # Use the actual build version from the issues
        if evaluated:
            current_build = evaluated[0].get("build_version", "NAV_25W12_RC3")

        recurrence_results = recurrence_analyzer.analyze_recurrence(
            evaluated, current_build
        )

        # Check recurrence statuses
        rec_statuses = {}
        for r in recurrence_results:
            status = r.get("recurrence_status", "UNKNOWN")
            rec_statuses[status] = rec_statuses.get(status, 0) + 1
        print(f"    Recurrence: {rec_statuses}")

        # Trend analysis
        trend = recurrence_analyzer.analyze_trend()
        print(f"    Trend: {trend.get('trend_status', 'N/A')}")

        all_results[sc_id] = {
            "evaluated_issues": recurrence_results,
            "classification_summary": class_summary,
            "severity_summary": sev_summary,
            "trend_analysis": trend,
        }

    # ──────────────────────────────────────────
    # Phase 6: Quality Gate Evaluation
    # ──────────────────────────────────────────
    print("\n[Phase 6] A-SPICE Quality Gate Evaluation...")
    gate_engine = ASPICEQualityGate()
    ota_simulator = OTARolloutSimulator()

    for sc in manifest:
        sc_id = sc["scenario_id"]
        if sc_id not in all_results:
            continue

        result = all_results[sc_id]
        issues = result["evaluated_issues"]

        # For gate evaluation: only count issues from the current build
        current_build_issues = [
            i for i in issues
            if i.get("build_version") == "NAV_25W12_RC3"
        ]
        # If no current build issues found, use all (single-build scenarios)
        if not current_build_issues and issues:
            current_build_issues = issues

        # Get distributions
        variant_dist = parser.get_variant_distribution(sc_id)
        region_dist = parser.get_region_distribution(sc_id)
        total_events = len(parser.get_all_events(sc_id))

        gate_eval = gate_engine.evaluate({
            "evaluated_issues": current_build_issues,
            "trend_analysis": result["trend_analysis"],
            "total_events": total_events,
            "variant_distribution": variant_dist,
            "region_distribution": region_dist,
        })

        # OTA simulation
        ota_sim = ota_simulator.simulate(
            gate_eval["ota_recommendation"], current_build_issues
        )

        result["gate_evaluation"] = gate_eval
        result["ota_simulation"] = ota_sim

        expected = sc["expected_gate_result"]
        actual = gate_eval["gate_result"]
        match = "✓" if expected == actual else "✗"
        print(f"  [{sc_id}] Expected: {expected:12s} | "
              f"Actual: {actual:12s} | {match} | "
              f"Score: {gate_eval['weighted_score']:.2f} | "
              f"OTA: {gate_eval['ota_recommendation']['strategy']}")

    parser.close()

    # ──────────────────────────────────────────
    # Phase 7: Report Generation
    # ──────────────────────────────────────────
    print("\n[Phase 7] Generating PM Dashboard & Reports...")
    reporter = ReportGenerator(output_dir=str(output_path))
    report_result = reporter.generate(all_results, manifest)

    # ──────────────────────────────────────────
    # Phase 8: Final Verification
    # ──────────────────────────────────────────
    print("\n[Phase 8] Verification Matrix")
    print("=" * 60)
    verification = report_result["verification_result"]
    print(f"  Result: {verification['verification_result']}")
    print(f"  Passed: {verification['passed']}/{verification['total']}")
    if verification["failed"] > 0:
        print(f"  Failed: {verification['failed']}")
        for d in verification["details"]:
            if not d["match"]:
                print(f"    ✗ {d['scenario_id']}: "
                      f"expected {d['expected']}, got {d['actual']}")

    print("\n" + "=" * 60)
    print("  Pipeline Complete!")
    print(f"  Dashboard: {report_result['dashboard']}")
    print(f"  Report: {report_result['report']}")
    print("=" * 60)

    return all_results, report_result


if __name__ == "__main__":
    run_pipeline()