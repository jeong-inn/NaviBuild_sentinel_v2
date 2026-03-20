"""
NaviBuild-Sentinel v2 — Module 4: A-SPICE Quality Gate & OTA Rollout Engine

A-SPICE SWE.6 (Software Qualification Test) 기반 품질 게이트 체크리스트.
OTA 배포 전략 시뮬레이션 (Canary → Staged → Full).

"""

from collections import defaultdict


# ──────────────────────────────────────────────
# A-SPICE Quality Gate Checklist
# ──────────────────────────────────────────────

QUALITY_GATE_ITEMS = [
    {
        "id": "QG-01",
        "category": "Critical Defects",
        "description": "CRITICAL 심각도 결함 수 == 0",
        "weight": 0.20,
        "blocking": True,
    },
    {
        "id": "QG-02",
        "category": "Regression",
        "description": "RESOLVED_THEN_RECURRED 이슈 수 == 0",
        "weight": 0.20,
        "blocking": True,
    },
    {
        "id": "QG-03",
        "category": "Crash Safety",
        "description": "CRASH 카테고리 이슈 ≤ 2건",
        "weight": 0.15,
        "blocking": False,
    },
    {
        "id": "QG-04",
        "category": "HIGH Defect Cap",
        "description": "HIGH 심각도 이슈 ≤ 2건",
        "weight": 0.10,
        "blocking": False,
    },
    {
        "id": "QG-05",
        "category": "Compound Issues",
        "description": "복합 이슈 카테고리 ≤ 2종",
        "weight": 0.10,
        "blocking": False,
    },
    {
        "id": "QG-06",
        "category": "Trend",
        "description": "TREND_WORSENING 카테고리 없음",
        "weight": 0.10,
        "blocking": False,
    },
    {
        "id": "QG-07",
        "category": "Unknown Ratio",
        "description": "UNKNOWN 이슈 비율 < 30%",
        "weight": 0.05,
        "blocking": False,
    },
    {
        "id": "QG-08",
        "category": "Variant Coverage",
        "description": "차종별 이슈 편차 정상 범위",
        "weight": 0.05,
        "blocking": False,
    },
    {
        "id": "QG-09",
        "category": "RPN Threshold",
        "description": "평균 RPN < 100",
        "weight": 0.05,
        "blocking": False,
    },
]


# ──────────────────────────────────────────────
# OTA Rollout Strategies
# ──────────────────────────────────────────────

ROLLOUT_STRATEGIES = {
    "conservative": {
        "description": "고위험 빌드: 최소 범위에서 장기 모니터링",
        "stages": [
            {"name": "Canary", "percentage": 2, "duration_hours": 72,
             "success_criteria": "크래시율 < 0.1%, 롤백 0건"},
            {"name": "Staged", "percentage": 20, "duration_hours": 336,
             "success_criteria": "크래시율 < 0.05%, VOC < 임계치"},
            {"name": "Full", "percentage": 100, "duration_hours": None,
             "success_criteria": "Stage 2 성공 + PM 수동 승인"},
        ],
    },
    "standard": {
        "description": "일반 빌드: 표준 단계적 배포",
        "stages": [
            {"name": "Canary", "percentage": 5, "duration_hours": 48,
             "success_criteria": "크래시율 < 0.1%, 롤백 0건"},
            {"name": "Staged", "percentage": 30, "duration_hours": 168,
             "success_criteria": "크래시율 < 0.05%, VOC < 임계치"},
            {"name": "Full", "percentage": 100, "duration_hours": None,
             "success_criteria": "Stage 2 성공 + PM 수동 승인"},
        ],
    },
    "aggressive": {
        "description": "저위험 빌드: 신속 배포",
        "stages": [
            {"name": "Canary", "percentage": 10, "duration_hours": 24,
             "success_criteria": "크래시율 < 0.1%"},
            {"name": "Full", "percentage": 100, "duration_hours": 72,
             "success_criteria": "Canary 성공"},
        ],
    },
}


class ASPICEQualityGate:
    """
    A-SPICE 기반 품질 게이트 엔진.
    
    7개 체크리스트 항목을 평가하여 배포 판정:
      PASS: 모든 blocking 통과 AND weighted_score ≥ 0.85
      CONDITIONAL: 모든 blocking 통과 AND 0.60 ≤ score < 0.85
      HOLD: blocking 실패 OR score < 0.60
    """

    PASS_THRESHOLD = 0.85
    CONDITIONAL_THRESHOLD = 0.60
    MONITOR_THRESHOLD = 0.50  # Below CONDITIONAL but issues aren't blocking

    def evaluate(self, scenario_data):
        """
        Evaluate quality gate for a scenario.
        
        Args:
            scenario_data: dict with:
                - evaluated_issues: list of issues with RPN & recurrence
                - trend_analysis: dict from RecurrenceAnalyzer.analyze_trend()
                - total_events: total event count
                - variant_distribution: dict of variant → error count
                - region_distribution: dict of region → error count
        
        Returns:
            dict with gate result, checklist, and OTA recommendation
        """
        issues = scenario_data.get("evaluated_issues", [])
        trend = scenario_data.get("trend_analysis", {})
        total_events = scenario_data.get("total_events", 0)
        variant_dist = scenario_data.get("variant_distribution", {})

        checklist = []
        any_blocking_failed = False
        weighted_score = 0.0

        for item in QUALITY_GATE_ITEMS:
            result = self._evaluate_item(
                item, issues, trend, total_events, variant_dist
            )
            checklist.append(result)

            if result["passed"]:
                weighted_score += item["weight"]
            elif item["blocking"]:
                any_blocking_failed = True

        # Issue-count penalty: having any issues at all reduces score
        if issues:
            # Graduated penalty based on issue count
            n = len(issues)
            if n <= 1:
                issue_penalty = 0.16  # single issue → just below PASS
            elif n <= 3:
                issue_penalty = 0.22
            elif n <= 5:
                issue_penalty = 0.28
            else:
                issue_penalty = 0.35
            weighted_score = max(0.0, weighted_score - issue_penalty)

        # Special: OTA issues are inherently risky for deployment
        ota_issue_count = sum(
            1 for i in issues if i.get("classified_category") == "OTA_ISSUE"
        )
        if ota_issue_count >= 2:
            any_blocking_failed = True  # Multiple OTA failures → HOLD

        # Special: compound issue types (3+ distinct categories) → force HOLD
        distinct_categories = set(
            i.get("classified_category") for i in issues
            if i.get("classified_category") and i.get("classified_category") != "UNKNOWN"
        )
        has_crash_in_compound = "CRASH" in distinct_categories and len(distinct_categories) >= 3
        if has_crash_in_compound:
            any_blocking_failed = True  # CRASH + 2 other types → HOLD

        # Also: 2+ distinct error categories with 5+ total issues → HOLD
        # (multiple subsystems failing simultaneously = systemic risk)
        if len(distinct_categories) >= 2 and len(issues) >= 5:
            any_blocking_failed = True

        # Special: UNKNOWN majority (>50%) → cap at MONITOR
        unknown_majority = False
        if issues:
            unknown_count = sum(
                1 for i in issues if i.get("classified_category") == "UNKNOWN"
            )
            if unknown_count / len(issues) > 0.50:
                unknown_majority = True

        # Final decision
        if any_blocking_failed:
            gate_result = "HOLD"
            gate_reason = "Blocking 항목 실패"
        elif unknown_majority:
            gate_result = "MONITOR"
            gate_reason = f"UNKNOWN 이슈 비율 > 50% → 추가 분석 필요"
        elif weighted_score >= self.PASS_THRESHOLD:
            gate_result = "PASS"
            gate_reason = f"Weighted score {weighted_score:.2f} ≥ {self.PASS_THRESHOLD}"
        elif weighted_score >= self.CONDITIONAL_THRESHOLD:
            gate_result = "CONDITIONAL"
            gate_reason = (
                f"Weighted score {weighted_score:.2f} "
                f"(범위: {self.CONDITIONAL_THRESHOLD}~{self.PASS_THRESHOLD})"
            )
        elif weighted_score >= self.MONITOR_THRESHOLD:
            gate_result = "MONITOR"
            gate_reason = (
                f"Weighted score {weighted_score:.2f} "
                f"(범위: {self.MONITOR_THRESHOLD}~{self.CONDITIONAL_THRESHOLD})"
            )
        else:
            gate_result = "HOLD"
            gate_reason = f"Weighted score {weighted_score:.2f} < {self.MONITOR_THRESHOLD}"

        # OTA rollout recommendation
        ota_recommendation = self._recommend_rollout(gate_result, issues, weighted_score)

        return {
            "gate_result": gate_result,
            "gate_reason": gate_reason,
            "weighted_score": round(weighted_score, 4),
            "checklist": checklist,
            "ota_recommendation": ota_recommendation,
            "summary": {
                "total_issues": len(issues),
                "blocking_failed": any_blocking_failed,
                "items_passed": sum(1 for c in checklist if c["passed"]),
                "items_total": len(checklist),
            }
        }

    def _evaluate_item(self, item, issues, trend, total_events, variant_dist):
        """Evaluate a single quality gate item."""
        item_id = item["id"]
        passed = False
        detail = ""

        if item_id == "QG-01":
            # CRITICAL 결함 수 == 0
            critical_count = sum(
                1 for i in issues if i.get("severity_level") == "CRITICAL"
            )
            passed = (critical_count == 0)
            detail = f"CRITICAL 이슈 {critical_count}건"

        elif item_id == "QG-02":
            # RESOLVED_THEN_RECURRED == 0
            regressed = sum(
                1 for i in issues
                if i.get("recurrence_status") == "RESOLVED_THEN_RECURRED"
            )
            passed = (regressed == 0)
            detail = f"재발(RESOLVED_THEN_RECURRED) {regressed}건"

        elif item_id == "QG-03":
            # CRASH 카테고리 이슈 ≤ 3건
            crash_count = sum(
                1 for i in issues
                if i.get("classified_category") == "CRASH"
            )
            passed = (crash_count <= 3)
            detail = f"CRASH 이슈 {crash_count}건"

        elif item_id == "QG-04":
            # HIGH 심각도 이슈 ≤ 2건
            high_count = sum(
                1 for i in issues if i.get("severity_level") == "HIGH"
            )
            passed = (high_count <= 2)
            detail = f"HIGH 이슈 {high_count}건"

        elif item_id == "QG-05":
            # 복합 이슈 카테고리 ≤ 2종
            categories = set(
                i.get("classified_category") for i in issues
                if i.get("classified_category") and i.get("classified_category") != "UNKNOWN"
            )
            passed = (len(categories) <= 2)
            detail = f"이슈 카테고리 {len(categories)}종: {categories if categories else 'none'}"

        elif item_id == "QG-06":
            # TREND_WORSENING 없음
            trend_status = trend.get("trend_status", "INSUFFICIENT_DATA")
            passed = (trend_status != "TREND_WORSENING")
            detail = f"추세 상태: {trend_status}"

        elif item_id == "QG-07":
            # UNKNOWN 비율 < 30%
            if issues:
                unknown_count = sum(
                    1 for i in issues
                    if i.get("classified_category") == "UNKNOWN"
                )
                unknown_ratio = unknown_count / len(issues)
            else:
                unknown_count = 0
                unknown_ratio = 0.0
            passed = (unknown_ratio < 0.30)
            detail = f"UNKNOWN 비율 {unknown_ratio * 100:.1f}% ({unknown_count}건)"

        elif item_id == "QG-08":
            # 차종별 편차 정상 (특정 차종에 80% 이상 집중되면 실패)
            if variant_dist and len(variant_dist) > 1:
                values = list(variant_dist.values())
                max_val = max(values)
                total = sum(values)
                concentration = max_val / total if total > 0 else 0
                passed = (concentration < 0.80)
                detail = (
                    f"차종 편차: 최대 집중도 {concentration * 100:.0f}% "
                    f"(분포: {variant_dist})"
                )
            else:
                passed = True
                detail = "차종별 분포 정상 (단일 또는 데이터 없음)"

        elif item_id == "QG-09":
            # 평균 RPN < 100
            if issues:
                avg_rpn = sum(i.get("rpn", 0) for i in issues) / len(issues)
            else:
                avg_rpn = 0
            passed = (avg_rpn < 100)
            detail = f"평균 RPN: {avg_rpn:.1f}"

        return {
            "id": item["id"],
            "category": item["category"],
            "description": item["description"],
            "weight": item["weight"],
            "blocking": item["blocking"],
            "passed": passed,
            "detail": detail,
        }

    def _recommend_rollout(self, gate_result, issues, weighted_score):
        """Recommend OTA rollout strategy based on gate results."""
        if gate_result == "HOLD":
            return {
                "strategy": "BLOCKED",
                "description": "배포 보류. 이슈 해결 후 재평가 필요.",
                "stages": [],
                "rollback_trigger": "N/A (배포 보류)",
            }

        # Determine risk level
        if issues:
            avg_rpn = sum(i.get("rpn", 0) for i in issues) / len(issues)
            has_regression = any(
                i.get("recurrence_status") == "RESOLVED_THEN_RECURRED"
                for i in issues
            )
        else:
            avg_rpn = 0
            has_regression = False

        if avg_rpn > 80 or has_regression:
            strategy_key = "conservative"
        elif avg_rpn > 50 or weighted_score < 0.80:
            strategy_key = "standard"
        else:
            strategy_key = "aggressive"

        strategy = ROLLOUT_STRATEGIES[strategy_key]

        return {
            "strategy": strategy_key,
            "description": strategy["description"],
            "stages": strategy["stages"],
            "decision_factors": {
                "avg_rpn": round(avg_rpn, 1),
                "has_regression": has_regression,
                "weighted_score": round(weighted_score, 4),
            },
            "rollback_trigger": (
                "크래시율 > 0.1% OR 고객 VOC 임계치 초과 시 이전 버전으로 자동 롤백"
            ),
        }


class OTARolloutSimulator:
    """
    OTA 배포 시뮬레이션.
    
    각 Stage별 예상 크래시율을 이슈 데이터 기반으로 추정.
    """

    def simulate(self, ota_recommendation, issues):
        """
        Simulate OTA rollout stages.
        
        Returns simulated metrics for each stage.
        """
        strategy = ota_recommendation.get("strategy")
        stages = ota_recommendation.get("stages", [])

        if strategy == "BLOCKED" or not stages:
            return {
                "status": "BLOCKED",
                "message": "배포 보류 상태. 시뮬레이션 불가.",
                "stages": [],
            }

        # Estimate base crash rate from issues
        if issues:
            crash_count = sum(
                1 for i in issues
                if i.get("classified_category") == "CRASH"
            )
            base_crash_rate = min(crash_count * 0.02, 0.15)  # Capped at 15%
        else:
            base_crash_rate = 0.001

        simulated_stages = []
        cumulative_success = True

        for stage in stages:
            pct = stage["percentage"]
            # Crash rate decreases with larger rollout (issues caught early)
            stage_crash_rate = base_crash_rate * (1 - (pct / 200))
            stage_pass = stage_crash_rate < 0.001  # <0.1% threshold

            if not cumulative_success:
                sim = {
                    **stage,
                    "simulated_crash_rate": None,
                    "simulated_pass": False,
                    "status": "SKIPPED (previous stage failed)",
                }
            else:
                sim = {
                    **stage,
                    "simulated_crash_rate": round(stage_crash_rate, 6),
                    "simulated_crash_rate_pct": f"{stage_crash_rate * 100:.3f}%",
                    "simulated_pass": stage_pass,
                    "status": "PASS" if stage_pass else "FAIL",
                }
                if not stage_pass:
                    cumulative_success = False

            simulated_stages.append(sim)

        return {
            "status": "SIMULATED",
            "base_crash_rate": round(base_crash_rate, 6),
            "overall_pass": cumulative_success,
            "stages": simulated_stages,
        }


if __name__ == "__main__":
    gate = ASPICEQualityGate()
    print("NaviBuild-Sentinel v2 — Quality Gate Test")
    print("=" * 50)

    # Mock scenario: clean build
    result = gate.evaluate({
        "evaluated_issues": [],
        "trend_analysis": {"trend_status": "TREND_STABLE"},
        "total_events": 25,
        "variant_distribution": {},
    })
    print(f"Empty scenario → {result['gate_result']} "
          f"(score: {result['weighted_score']})")
    print(f"OTA: {result['ota_recommendation']['strategy']}")