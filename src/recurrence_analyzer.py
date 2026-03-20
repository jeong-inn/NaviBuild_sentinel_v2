"""
NaviBuild-Sentinel v2 — Module 3-3: Recurrence Analyzer

3-Layer 재발 탐지:
  Layer 1: Exact Match (error_code + context)
  Layer 2: Fuzzy Match (TF-IDF cosine > 0.7)
  Layer 3: Trend Detection (시계열 선형 회귀)

출력 분류:
  FIRST_OCCURRENCE / RECURRING / RESOLVED_THEN_RECURRED /
  TREND_WORSENING / TREND_IMPROVING / TREND_STABLE
"""

import re
from collections import defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class RecurrenceAnalyzer:
    """
    3-Layer Recurrence Detection Engine.
    
    빌드 버전 간 이슈 히스토리를 추적하여 재발 여부를 판단.
    """

    FUZZY_THRESHOLD = 0.70     # Fuzzy match 임계치
    TREND_SLOPE_THRESHOLD = 0.3  # 추세 판정 임계치

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=300,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        # 빌드별 이슈 히스토리
        self.build_issues = defaultdict(list)  # {build: [issues]}
        self.resolved_issues = []              # 해결된 이슈 목록

    def _preprocess(self, text):
        text = text.lower()
        text = re.sub(r'0x[0-9a-f]+', 'HEX', text)
        text = re.sub(r'\b\d{4,}\b', 'NUM', text)
        text = re.sub(r'[_/\\.]', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()

    def register_build_history(self, evaluated_issues):
        """
        Register issues from evaluated results into build history.
        Call this for each scenario to build up the history DB.
        """
        for issue in evaluated_issues:
            build = issue["build_version"]
            self.build_issues[build].append({
                "message": issue["message"],
                "category": issue["classified_category"],
                "error_code": issue.get("error_code"),
                "context_id": issue["context_id"],
                "cluster_id": issue["cluster_id"],
                "rpn": issue.get("rpn", 0),
            })

    def register_resolved(self, resolved_list):
        """Register resolved issues (from INFO logs indicating fixes)."""
        self.resolved_issues.extend(resolved_list)

    def analyze_recurrence(self, current_issues, current_build):
        """
        Analyze recurrence for current build's issues.
        
        Args:
            current_issues: evaluated issues for current build
            current_build: current build version string
        
        Returns:
            list of issues enriched with recurrence info
        """
        # Get historical issues (excluding current build)
        historical = []
        historical_builds = set()
        for build, issues in self.build_issues.items():
            if build != current_build:
                for iss in issues:
                    iss["_from_build"] = build
                    historical.append(iss)
                    historical_builds.add(build)

        results = []
        for issue in current_issues:
            recurrence = self._check_recurrence(
                issue, historical, historical_builds
            )
            results.append({**issue, **recurrence})

        return results

    def _check_recurrence(self, issue, historical, historical_builds):
        """
        Check if an issue is a recurrence using 3 layers.
        """
        if not historical:
            return {
                "recurrence_status": "FIRST_OCCURRENCE",
                "recurrence_detail": "No historical data available",
                "matched_builds": [],
                "recurrence_layer": None,
            }

        # ── Layer 1: Exact Match ──
        exact_matches = []
        for hist in historical:
            if (issue.get("error_code") and
                    hist.get("error_code") == issue["error_code"] and
                    hist["context_id"] == issue["context_id"]):
                exact_matches.append(hist["_from_build"])

        if exact_matches:
            # Check if it was resolved
            was_resolved = self._check_if_resolved(issue)
            if was_resolved:
                return {
                    "recurrence_status": "RESOLVED_THEN_RECURRED",
                    "recurrence_detail": (
                        f"Exact match found in {len(set(exact_matches))} previous build(s). "
                        f"Was marked as resolved but has reappeared."
                    ),
                    "matched_builds": list(set(exact_matches)),
                    "recurrence_layer": "EXACT",
                }
            else:
                return {
                    "recurrence_status": "RECURRING",
                    "recurrence_detail": (
                        f"Exact match (error_code + context) in "
                        f"{len(set(exact_matches))} build(s)."
                    ),
                    "matched_builds": list(set(exact_matches)),
                    "recurrence_layer": "EXACT",
                }

        # ── Layer 2: Fuzzy Match ──
        fuzzy_matches = self._fuzzy_match(issue, historical)
        if fuzzy_matches:
            matched_builds = list(set(m["build"] for m in fuzzy_matches))
            was_resolved = self._check_if_resolved(issue)
            if was_resolved:
                status = "RESOLVED_THEN_RECURRED"
            else:
                status = "RECURRING"

            return {
                "recurrence_status": status,
                "recurrence_detail": (
                    f"Fuzzy match (cosine similarity > {self.FUZZY_THRESHOLD}) "
                    f"found in {len(matched_builds)} build(s). "
                    f"Best similarity: {fuzzy_matches[0]['similarity']:.3f}"
                ),
                "matched_builds": matched_builds,
                "recurrence_layer": "FUZZY",
                "fuzzy_matches": fuzzy_matches[:3],  # Top 3
            }

        # ── No match found ──
        return {
            "recurrence_status": "FIRST_OCCURRENCE",
            "recurrence_detail": "No matching historical issues found.",
            "matched_builds": [],
            "recurrence_layer": None,
        }

    def _fuzzy_match(self, issue, historical):
        """
        Layer 2: TF-IDF cosine similarity matching.
        """
        if not historical:
            return []

        current_msg = self._preprocess(issue["message"])
        hist_messages = [self._preprocess(h["message"]) for h in historical]

        all_messages = [current_msg] + hist_messages
        try:
            vectors = self.vectorizer.fit_transform(all_messages)
        except ValueError:
            return []

        current_vec = vectors[0:1]
        hist_vecs = vectors[1:]

        similarities = cosine_similarity(current_vec, hist_vecs)[0]

        matches = []
        for idx, sim in enumerate(similarities):
            if sim >= self.FUZZY_THRESHOLD:
                matches.append({
                    "build": historical[idx]["_from_build"],
                    "message": historical[idx]["message"][:80],
                    "similarity": round(float(sim), 4),
                    "category": historical[idx]["category"],
                })

        matches.sort(key=lambda x: x["similarity"], reverse=True)
        return matches

    def _check_if_resolved(self, issue):
        """Check if this issue pattern was previously marked as resolved."""
        issue_msg_lower = issue["message"].lower()
        for resolved in self.resolved_issues:
            resolved_lower = resolved.lower()
            # Simple heuristic: check if key terms overlap
            issue_terms = set(issue_msg_lower.split())
            resolved_terms = set(resolved_lower.split())
            overlap = issue_terms & resolved_terms
            # If significant overlap with a resolved message
            if len(overlap) >= 3:
                return True
        return False

    def analyze_trend(self, category=None):
        """
        Layer 3: Time-series trend analysis across builds.
        
        Args:
            category: optional category filter
        
        Returns:
            dict with trend analysis results
        """
        # Build ordering (by version string)
        sorted_builds = sorted(self.build_issues.keys())
        if len(sorted_builds) < 3:
            return {
                "trend_status": "INSUFFICIENT_DATA",
                "detail": f"Need at least 3 builds, have {len(sorted_builds)}",
            }

        # Count issues per build
        counts = []
        for build in sorted_builds:
            issues = self.build_issues[build]
            if category:
                count = sum(1 for i in issues if i["category"] == category)
            else:
                count = len(issues)
            counts.append(count)

        # Linear regression for trend
        x = np.arange(len(counts), dtype=float)
        y = np.array(counts, dtype=float)

        if len(x) < 2:
            slope = 0.0
        else:
            # Least squares fit
            n = len(x)
            slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / \
                    (n * np.sum(x ** 2) - np.sum(x) ** 2 + 1e-10)

        if slope > self.TREND_SLOPE_THRESHOLD:
            trend_status = "TREND_WORSENING"
        elif slope < -self.TREND_SLOPE_THRESHOLD:
            trend_status = "TREND_IMPROVING"
        else:
            trend_status = "TREND_STABLE"

        return {
            "trend_status": trend_status,
            "slope": round(float(slope), 4),
            "build_counts": dict(zip(sorted_builds, [int(c) for c in counts])),
            "detail": (
                f"Linear slope={slope:.3f} across {len(sorted_builds)} builds. "
                f"{'↑ Increasing' if slope > 0 else '↓ Decreasing' if slope < 0 else '→ Stable'} "
                f"trend for {'all categories' if not category else category}."
            ),
        }


if __name__ == "__main__":
    print("NaviBuild-Sentinel v2 — Recurrence Analyzer Test")
    print("=" * 50)

    analyzer = RecurrenceAnalyzer()

    # Register some history
    mock_history = [
        {
            "message": "Route calculation timeout: path_engine exceeded 3000ms",
            "classified_category": "PERFORMANCE",
            "error_code": "E-ABC123",
            "context_id": "ROUT",
            "cluster_id": "CLU-0001",
            "build_version": "NAV_25W10_RC2",
            "rpn": 120,
        }
    ]
    analyzer.register_build_history(mock_history)
    analyzer.register_resolved(["Issue E-resolved: Route timeout confirmed fixed"])

    # Test current issue
    current = [{
        "message": "Route calculation timeout: path_engine exceeded 3000ms threshold",
        "classified_category": "PERFORMANCE",
        "error_code": "E-ABC123",
        "context_id": "ROUT",
        "cluster_id": "CLU-0002",
        "build_version": "NAV_25W12_RC3",
        "rpn": 120,
        "log_level": "ERROR",
    }]

    results = analyzer.analyze_recurrence(current, "NAV_25W12_RC3")
    for r in results:
        print(f"Message: {r['message'][:60]}...")
        print(f"  → Status: {r['recurrence_status']}")
        print(f"  → Layer: {r['recurrence_layer']}")
        print(f"  → Detail: {r['recurrence_detail']}")