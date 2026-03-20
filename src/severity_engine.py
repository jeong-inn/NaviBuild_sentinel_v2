"""
NaviBuild-Sentinel v2 — Module 3-2: FMEA-based Severity Engine

자동차 산업 표준 FMEA의 RPN(Risk Priority Number)을 SW 이슈에 적용.
RPN = Severity(S) × Occurrence(O) × Detection(D)

"""

from collections import defaultdict


# ──────────────────────────────────────────────
# FMEA Scoring Tables
# ──────────────────────────────────────────────

# Severity: 이슈 카테고리별 기본 심각도
SEVERITY_TABLE = {
    "CRASH": {
        "base_score": 9,
        "context_modifiers": {
            "ROUT": 10,   # 경로 계산 중 크래시 → 운전 중 화면 블랙아웃 가능
            "DISP": 9,    # 렌더링 크래시
            "HMI":  8,    # UI 프레임워크 크래시
            "SYS":  9,    # 시스템 워치독
        },
        "rationale": "프로세스 비정상 종료. 운전 중 발생 시 안전 관련."
    },
    "PERFORMANCE": {
        "base_score": 5,
        "context_modifiers": {
            "ROUT": 7,    # 경로 계산 지연 → 안내 누락 가능
            "DISP": 6,    # 렌더링 지연
            "SRCH": 4,    # 검색 지연 (비안전)
            "DATA": 5,    # 데이터 처리 지연
        },
        "rationale": "기능 저하. 직접 안전 위험은 낮지만 사용성 저하."
    },
    "DATA_ERROR": {
        "base_score": 6,
        "context_modifiers": {
            "DATA": 7,    # 지도 데이터 오류 → 잘못된 경로 가능
            "SRCH": 5,    # 검색 인덱스 오류
        },
        "rationale": "데이터 무결성 오류. 잘못된 경로 안내로 이어질 수 있음."
    },
    "ROUTE_ERROR": {
        "base_score": 8,
        "context_modifiers": {
            "ROUT": 9,    # 잘못된 경로 생성 → 고속도로 U턴 등 위험
        },
        "rationale": "경로 안내 오류. 직접적 안전 위험 가능."
    },
    "CONNECTIVITY": {
        "base_score": 3,
        "context_modifiers": {
            "CONN": 3,    # 연결 끊김 (오프라인 모드 가능)
            "OTA":  4,    # OTA 다운로드 실패
        },
        "rationale": "네트워크 오류. 오프라인 폴백 존재하므로 상대적 낮음."
    },
    "OTA_ISSUE": {
        "base_score": 7,
        "context_modifiers": {
            "OTA": 8,     # OTA 실패 → 업데이트 불가 또는 롤백 필요
        },
        "rationale": "OTA 오류. 배포 실패 시 고객 영향 큼."
    },
    "UNKNOWN": {
        "base_score": 4,
        "context_modifiers": {},
        "rationale": "분류 불가. 잠재 위험 불명확하므로 중간 수준 부여."
    },
}

# Occurrence: 발생 빈도 기반 점수 매핑
def _calc_occurrence_score(frequency, build_count=1):
    """
    빈도 + 빌드 수 기반 Occurrence 점수 (1-10).
    
    frequency: 현재 분석 대상 내 해당 이슈 발생 횟수
    build_count: 해당 이슈가 발생한 빌드 수 (재발 분석 후 입력)
    """
    # 단일 빌드 내 빈도
    if frequency >= 10:
        freq_score = 10
    elif frequency >= 5:
        freq_score = 9
    elif frequency >= 3:
        freq_score = 7
    elif frequency >= 2:
        freq_score = 5
    else:
        freq_score = 3

    # 다중 빌드 발생 가산
    if build_count >= 4:
        build_modifier = 2
    elif build_count >= 2:
        build_modifier = 1
    else:
        build_modifier = 0

    return min(10, freq_score + build_modifier)


# Detection: 탐지 난이도 기반 점수 매핑
DETECTION_TABLE = {
    # log_level 기반 초기 탐지 난이도
    "FATAL": 2,    # 빌드 시점에 즉시 탐지
    "ERROR": 4,    # 자동 테스트로 탐지 가능
    "WARN":  6,    # 필드 테스트에서 발견
    "INFO":  8,    # 고객 리포트로만 발견 (INFO인데 이슈인 경우)
}

# 자동 복구 여부에 따른 Detection 보정
RECOVERY_DETECTION_MODIFIER = {
    True: -2,   # 자동 복구 → 탐지 쉬움 (모니터링으로 잡힘)
    False: 0,
}


class FMEASeverityEngine:
    """
    FMEA RPN 기반 심각도 산출 엔진.
    
    RPN = S × O × D (범위: 1~1000)
    
    등급 분류:
      CRITICAL: RPN ≥ 200
      HIGH:     100 ≤ RPN < 200
      MEDIUM:   40 ≤ RPN < 100
      LOW:      RPN < 40
    """

    RPN_THRESHOLDS = {
        "CRITICAL": 200,
        "HIGH": 100,
        "MEDIUM": 40,
    }

    def __init__(self):
        pass

    def calculate_rpn(self, issue, cluster_frequency=1, build_count=1,
                      auto_recovered=False):
        """
        Calculate FMEA RPN for a single classified issue.
        
        Args:
            issue: classified issue dict from IssueClassifier
            cluster_frequency: 동일 클러스터 내 이슈 수
            build_count: 해당 이슈 패턴이 발생한 빌드 수
            auto_recovered: 자동 복구 여부
        
        Returns:
            dict with S, O, D scores, RPN, severity level, and rationale
        """
        category = issue["classified_category"]
        context = issue["context_id"]
        log_level = issue["log_level"]

        # ── Severity (S) ──
        cat_info = SEVERITY_TABLE.get(category, SEVERITY_TABLE["UNKNOWN"])
        s_score = cat_info["context_modifiers"].get(context, cat_info["base_score"])

        # ── Occurrence (O) ──
        o_score = _calc_occurrence_score(cluster_frequency, build_count)

        # ── Detection (D) ──
        d_score = DETECTION_TABLE.get(log_level, 6)
        d_score += RECOVERY_DETECTION_MODIFIER.get(auto_recovered, 0)
        d_score = max(1, min(10, d_score))

        # ── RPN ──
        rpn = s_score * o_score * d_score

        # ── Severity Level ──
        if rpn >= self.RPN_THRESHOLDS["CRITICAL"]:
            severity_level = "CRITICAL"
        elif rpn >= self.RPN_THRESHOLDS["HIGH"]:
            severity_level = "HIGH"
        elif rpn >= self.RPN_THRESHOLDS["MEDIUM"]:
            severity_level = "MEDIUM"
        else:
            severity_level = "LOW"

        return {
            "severity_score": s_score,
            "occurrence_score": o_score,
            "detection_score": d_score,
            "rpn": rpn,
            "severity_level": severity_level,
            "rationale": {
                "severity_reason": cat_info["rationale"],
                "severity_context": (
                    f"Context {context} modifier applied"
                    if context in cat_info.get("context_modifiers", {})
                    else "Base severity score used"
                ),
                "occurrence_reason": (
                    f"Frequency {cluster_frequency} in cluster, "
                    f"{build_count} build(s) affected"
                ),
                "detection_reason": (
                    f"Log level {log_level} (base detection={DETECTION_TABLE.get(log_level, 6)})"
                    + (", auto-recovered (detection easier)" if auto_recovered else "")
                ),
            }
        }

    def evaluate_scenario(self, classified_issues, build_history=None):
        """
        Evaluate all issues in a scenario.
        
        Args:
            classified_issues: list from IssueClassifier.classify_events()
            build_history: dict of {build_version: issue_count} for trend
        
        Returns:
            list of issues enriched with FMEA scores
        """
        if not classified_issues:
            return []

        # Count cluster frequencies
        cluster_freq = defaultdict(int)
        for issue in classified_issues:
            cluster_freq[issue["cluster_id"]] += 1

        # Determine build counts per cluster
        cluster_builds = defaultdict(set)
        for issue in classified_issues:
            cluster_builds[issue["cluster_id"]].add(issue["build_version"])

        # Check for auto-recovery patterns
        recovery_clusters = set()
        for issue in classified_issues:
            if "auto-reconnect" in issue["message"].lower() or \
               "recovered" in issue["message"].lower() or \
               "restored" in issue["message"].lower():
                recovery_clusters.add(issue["cluster_id"])

        # Calculate RPN for each issue
        evaluated = []
        for issue in classified_issues:
            cid = issue["cluster_id"]
            rpn_result = self.calculate_rpn(
                issue,
                cluster_frequency=cluster_freq[cid],
                build_count=len(cluster_builds[cid]),
                auto_recovered=(cid in recovery_clusters),
            )
            enriched = {**issue, **rpn_result}
            evaluated.append(enriched)

        return evaluated

    @staticmethod
    def get_scenario_severity_summary(evaluated_issues):
        """Generate severity summary for a scenario."""
        summary = {
            "total_issues": len(evaluated_issues),
            "by_severity": defaultdict(int),
            "max_rpn": 0,
            "avg_rpn": 0.0,
            "critical_issues": [],
            "high_issues": [],
        }

        total_rpn = 0
        for issue in evaluated_issues:
            level = issue["severity_level"]
            rpn = issue["rpn"]
            summary["by_severity"][level] += 1
            summary["max_rpn"] = max(summary["max_rpn"], rpn)
            total_rpn += rpn

            if level == "CRITICAL":
                summary["critical_issues"].append({
                    "message": issue["message"][:80],
                    "rpn": rpn,
                    "rationale": issue["rationale"],
                })
            elif level == "HIGH":
                summary["high_issues"].append({
                    "message": issue["message"][:80],
                    "rpn": rpn,
                })

        if evaluated_issues:
            summary["avg_rpn"] = round(total_rpn / len(evaluated_issues), 1)

        summary["by_severity"] = dict(summary["by_severity"])
        return summary


if __name__ == "__main__":
    engine = FMEASeverityEngine()

    # Quick test with mock issue
    mock_issue = {
        "classified_category": "CRASH",
        "context_id": "DISP",
        "log_level": "FATAL",
        "message": "Map rendering engine crashed",
        "cluster_id": "CLU-0001",
        "build_version": "NAV_25W12_RC3",
    }

    result = engine.calculate_rpn(mock_issue, cluster_frequency=5, build_count=2)
    print("NaviBuild-Sentinel v2 — FMEA Severity Engine Test")
    print("=" * 50)
    print(f"Issue: {mock_issue['message']}")
    print(f"  S={result['severity_score']} × "
          f"O={result['occurrence_score']} × "
          f"D={result['detection_score']} = "
          f"RPN {result['rpn']}")
    print(f"  → Severity Level: {result['severity_level']}")
    print(f"  → Rationale: {result['rationale']}")