"""
NaviBuild-Sentinel v2 — Module 5: Report Generator

PM Dashboard (HTML) + 고객사 보고용 JSON 리포트 생성.
"""

import json
from pathlib import Path
from datetime import datetime


DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NaviBuild-Sentinel v2 — PM Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', -apple-system, sans-serif; background: #f5f5f5; color: #333; }
.header { background: #1a237e; color: #fff; padding: 24px 32px; }
.header h1 { font-size: 20px; font-weight: 500; }
.header .sub { font-size: 13px; opacity: 0.8; margin-top: 4px; }
.container { max-width: 1200px; margin: 0 auto; padding: 24px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
.card { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.card h3 { font-size: 13px; color: #666; font-weight: 500; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
.metric { font-size: 36px; font-weight: 600; }
.metric.pass { color: #2e7d32; }
.metric.hold { color: #c62828; }
.metric.conditional { color: #e65100; }
.metric.monitor { color: #1565c0; }
.metric-label { font-size: 12px; color: #999; margin-top: 4px; }
.checklist { list-style: none; }
.checklist li { padding: 8px 0; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 8px; font-size: 13px; }
.checklist .icon { width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; flex-shrink: 0; }
.checklist .pass-icon { background: #e8f5e9; color: #2e7d32; }
.checklist .fail-icon { background: #ffebee; color: #c62828; }
.checklist .blocking { font-weight: 600; }
.chart-container { position: relative; height: 250px; }
.ota-stages { display: flex; gap: 12px; margin-top: 12px; }
.ota-stage { flex: 1; padding: 12px; border-radius: 6px; background: #f8f9fa; text-align: center; }
.ota-stage .pct { font-size: 24px; font-weight: 600; color: #1a237e; }
.ota-stage .name { font-size: 11px; color: #666; margin-top: 4px; }
.ota-stage .duration { font-size: 11px; color: #999; }
.scenario-table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }
.scenario-table th { text-align: left; padding: 8px; background: #f8f9fa; border-bottom: 2px solid #e0e0e0; font-weight: 500; }
.scenario-table td { padding: 8px; border-bottom: 1px solid #f0f0f0; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.badge-pass { background: #e8f5e9; color: #2e7d32; }
.badge-hold { background: #ffebee; color: #c62828; }
.badge-conditional { background: #fff3e0; color: #e65100; }
.badge-monitor { background: #e3f2fd; color: #1565c0; }
.badge-critical { background: #c62828; color: #fff; }
.badge-high { background: #e65100; color: #fff; }
.badge-medium { background: #f9a825; color: #333; }
.badge-low { background: #e8f5e9; color: #2e7d32; }
.section-title { font-size: 16px; font-weight: 500; margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 2px solid #1a237e; }
</style>
</head>
<body>
<div class="header">
  <h1>NaviBuild-Sentinel v2 — PM Dashboard</h1>
  <div class="sub">Build: {{current_build}} | Generated: {{report_date}} | Scenarios: {{scenario_count}}</div>
</div>
<div class="container">

<!-- KPI Cards -->
<div class="grid">
  <div class="card">
    <h3>Overall Gate Result</h3>
    <div class="metric {{overall_gate_class}}">{{overall_gate_result}}</div>
    <div class="metric-label">Weighted Score: {{overall_score}}</div>
  </div>
  <div class="card">
    <h3>Total Issues</h3>
    <div class="metric">{{total_issues}}</div>
    <div class="metric-label">Across {{scenario_count}} scenarios</div>
  </div>
  <div class="card">
    <h3>Critical Issues</h3>
    <div class="metric {{critical_class}}">{{critical_count}}</div>
    <div class="metric-label">RPN ≥ 200</div>
  </div>
  <div class="card">
    <h3>Regressions</h3>
    <div class="metric {{regression_class}}">{{regression_count}}</div>
    <div class="metric-label">RESOLVED_THEN_RECURRED</div>
  </div>
</div>

<!-- Charts Row -->
<div class="grid">
  <div class="card">
    <h3>Issue Category Distribution</h3>
    <div class="chart-container"><canvas id="categoryChart"></canvas></div>
  </div>
  <div class="card">
    <h3>Severity Distribution</h3>
    <div class="chart-container"><canvas id="severityChart"></canvas></div>
  </div>
</div>

<!-- Quality Gate Checklist -->
<div class="section-title">A-SPICE Quality Gate Checklist</div>
<div class="card">
  <ul class="checklist">
    {{checklist_html}}
  </ul>
</div>

<!-- OTA Rollout -->
<div class="section-title">OTA Rollout Recommendation</div>
<div class="card">
  <h3>Strategy: {{ota_strategy}}</h3>
  <p style="font-size:13px;color:#666;margin-bottom:12px;">{{ota_description}}</p>
  <div class="ota-stages">
    {{ota_stages_html}}
  </div>
</div>

<!-- Scenario Results Table -->
<div class="section-title">Scenario Results (Expected vs Actual)</div>
<div class="card" style="overflow-x:auto;">
  <table class="scenario-table">
    <thead>
      <tr>
        <th>ID</th>
        <th>Description</th>
        <th>Issues</th>
        <th>Max RPN</th>
        <th>Expected</th>
        <th>Actual</th>
        <th>Match</th>
      </tr>
    </thead>
    <tbody>
      {{scenario_rows_html}}
    </tbody>
  </table>
</div>

</div>

<script>
// Category Distribution Chart
const catCtx = document.getElementById('categoryChart').getContext('2d');
new Chart(catCtx, {
  type: 'doughnut',
  data: {
    labels: {{category_labels}},
    datasets: [{
      data: {{category_data}},
      backgroundColor: ['#c62828','#e65100','#1565c0','#2e7d32','#6a1b9a','#00838f','#78909c'],
      borderWidth: 0,
    }]
  },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { font: { size: 11 } } } } }
});

// Severity Distribution Chart
const sevCtx = document.getElementById('severityChart').getContext('2d');
new Chart(sevCtx, {
  type: 'bar',
  data: {
    labels: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
    datasets: [{
      data: {{severity_data}},
      backgroundColor: ['#c62828','#e65100','#f9a825','#66bb6a'],
      borderWidth: 0, borderRadius: 4,
    }]
  },
  options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y',
    plugins: { legend: { display: false } },
    scales: { x: { beginAtZero: true, ticks: { stepSize: 1 } } } }
});
</script>
</body>
</html>"""


class ReportGenerator:
    """PM Dashboard + JSON Report Generator."""

    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, all_scenario_results, manifest):
        """
        Generate dashboard and report from all scenario results.
        
        Args:
            all_scenario_results: dict of {sc_id: gate_evaluation_result}
            manifest: list of scenario manifest entries
        """
        # Aggregate data
        agg = self._aggregate(all_scenario_results, manifest)

        # Generate HTML dashboard
        html = self._render_dashboard(agg)
        html_path = self.output_dir / "pm_dashboard.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Generate JSON report
        report = self._build_json_report(agg, all_scenario_results)
        json_path = self.output_dir / "gate_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # Generate verification matrix
        verification = self._build_verification_matrix(all_scenario_results, manifest)
        verify_path = self.output_dir / "verification_matrix.json"
        with open(verify_path, "w", encoding="utf-8") as f:
            json.dump(verification, f, indent=2, ensure_ascii=False)

        print(f"  ✓ Dashboard: {html_path}")
        print(f"  ✓ Report: {json_path}")
        print(f"  ✓ Verification: {verify_path}")

        return {
            "dashboard": str(html_path),
            "report": str(json_path),
            "verification": str(verify_path),
            "verification_result": verification,
        }

    def _aggregate(self, results, manifest):
        """Aggregate all scenario results."""
        total_issues = 0
        critical_count = 0
        regression_count = 0
        category_counts = {}
        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        scenario_summaries = []

        # Find the "representative" gate result for dashboard
        gate_results = []

        for sc_entry in manifest:
            sc_id = sc_entry["scenario_id"]
            if sc_id not in results:
                continue
            r = results[sc_id]
            gate = r.get("gate_evaluation", {})
            issues = r.get("evaluated_issues", [])

            gate_results.append(gate.get("gate_result", "N/A"))
            n_issues = len(issues)
            total_issues += n_issues

            max_rpn = 0
            for iss in issues:
                cat = iss.get("classified_category", "UNKNOWN")
                category_counts[cat] = category_counts.get(cat, 0) + 1
                sev = iss.get("severity_level", "LOW")
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
                if sev == "CRITICAL":
                    critical_count += 1
                if iss.get("recurrence_status") == "RESOLVED_THEN_RECURRED":
                    regression_count += 1
                max_rpn = max(max_rpn, iss.get("rpn", 0))

            scenario_summaries.append({
                "id": sc_id,
                "description": sc_entry["description"],
                "expected": sc_entry["expected_gate_result"],
                "actual": gate.get("gate_result", "N/A"),
                "n_issues": n_issues,
                "max_rpn": max_rpn,
                "match": sc_entry["expected_gate_result"] == gate.get("gate_result", ""),
            })

        # Representative gate: worst result
        if "HOLD" in gate_results:
            overall_gate = "HOLD"
        elif "CONDITIONAL" in gate_results:
            overall_gate = "CONDITIONAL"
        elif "MONITOR" in gate_results:
            overall_gate = "MONITOR"
        else:
            overall_gate = "PASS"

        # Get checklist and OTA from worst scenario
        worst_sc = None
        for sc_entry in manifest:
            sc_id = sc_entry["scenario_id"]
            if sc_id in results:
                g = results[sc_id].get("gate_evaluation", {})
                if g.get("gate_result") == overall_gate:
                    worst_sc = results[sc_id]
                    break
        if worst_sc is None and manifest:
            worst_sc = results.get(manifest[0]["scenario_id"], {})

        return {
            "total_issues": total_issues,
            "critical_count": critical_count,
            "regression_count": regression_count,
            "category_counts": category_counts,
            "severity_counts": severity_counts,
            "overall_gate": overall_gate,
            "scenario_summaries": scenario_summaries,
            "scenario_count": len(manifest),
            "worst_scenario": worst_sc,
        }

    def _render_dashboard(self, agg):
        """Render HTML dashboard from aggregated data."""
        html = DASHBOARD_TEMPLATE

        overall = agg["overall_gate"]
        overall_class = overall.lower()

        # Get checklist from worst scenario
        worst = agg.get("worst_scenario", {})
        gate_eval = worst.get("gate_evaluation", {})
        checklist = gate_eval.get("checklist", [])
        ota = gate_eval.get("ota_recommendation", {})

        # Checklist HTML
        checklist_html = ""
        for item in checklist:
            icon_class = "pass-icon" if item["passed"] else "fail-icon"
            icon_char = "✓" if item["passed"] else "✗"
            blocking_class = "blocking" if item["blocking"] else ""
            blocking_tag = " [BLOCKING]" if item["blocking"] else ""
            checklist_html += (
                f'<li class="{blocking_class}">'
                f'<span class="icon {icon_class}">{icon_char}</span>'
                f'<span>{item["id"]} — {item["description"]}{blocking_tag}: {item["detail"]}</span>'
                f'</li>\n'
            )

        # OTA stages HTML
        ota_stages_html = ""
        for stage in ota.get("stages", []):
            dur = f"{stage['duration_hours']}h" if stage.get("duration_hours") else "PM 승인"
            ota_stages_html += (
                f'<div class="ota-stage">'
                f'<div class="pct">{stage["percentage"]}%</div>'
                f'<div class="name">{stage["name"]}</div>'
                f'<div class="duration">{dur}</div>'
                f'</div>\n'
            )

        # Scenario rows HTML
        rows_html = ""
        for s in agg["scenario_summaries"]:
            exp_class = s["expected"].lower().replace("_", "")
            act_class = s["actual"].lower().replace("_", "")
            match_char = "✓" if s["match"] else "✗"
            match_color = "#2e7d32" if s["match"] else "#c62828"
            rows_html += (
                f'<tr>'
                f'<td><strong>{s["id"]}</strong></td>'
                f'<td>{s["description"]}</td>'
                f'<td>{s["n_issues"]}</td>'
                f'<td>{s["max_rpn"]}</td>'
                f'<td><span class="badge badge-{exp_class}">{s["expected"]}</span></td>'
                f'<td><span class="badge badge-{act_class}">{s["actual"]}</span></td>'
                f'<td style="color:{match_color};font-weight:600;">{match_char}</td>'
                f'</tr>\n'
            )

        # Category chart data
        cat_labels = json.dumps(list(agg["category_counts"].keys()))
        cat_data = json.dumps(list(agg["category_counts"].values()))

        # Severity chart data
        sev_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        sev_data = json.dumps([agg["severity_counts"].get(s, 0) for s in sev_order])

        # Score
        overall_score = gate_eval.get("weighted_score", 0)

        # Replace placeholders
        replacements = {
            "{{current_build}}": "NAV_25W12_RC3",
            "{{report_date}}": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "{{scenario_count}}": str(agg["scenario_count"]),
            "{{overall_gate_result}}": overall,
            "{{overall_gate_class}}": overall_class,
            "{{overall_score}}": f"{overall_score:.2f}",
            "{{total_issues}}": str(agg["total_issues"]),
            "{{critical_count}}": str(agg["critical_count"]),
            "{{critical_class}}": "hold" if agg["critical_count"] > 0 else "pass",
            "{{regression_count}}": str(agg["regression_count"]),
            "{{regression_class}}": "hold" if agg["regression_count"] > 0 else "pass",
            "{{checklist_html}}": checklist_html,
            "{{ota_strategy}}": ota.get("strategy", "N/A").upper(),
            "{{ota_description}}": ota.get("description", ""),
            "{{ota_stages_html}}": ota_stages_html or '<div class="ota-stage"><div class="name">배포 보류</div></div>',
            "{{scenario_rows_html}}": rows_html,
            "{{category_labels}}": cat_labels,
            "{{category_data}}": cat_data,
            "{{severity_data}}": sev_data,
        }

        for key, val in replacements.items():
            html = html.replace(key, val)

        return html

    def _build_json_report(self, agg, results):
        """Build structured JSON report."""
        return {
            "report_header": {
                "build_version": "NAV_25W12_RC3",
                "report_date": datetime.now().isoformat(),
                "generator": "NaviBuild-Sentinel v2",
                "gate_result": agg["overall_gate"],
            },
            "executive_summary": {
                "total_issues": agg["total_issues"],
                "critical_issues": agg["critical_count"],
                "regression_issues": agg["regression_count"],
                "category_distribution": agg["category_counts"],
                "severity_distribution": agg["severity_counts"],
            },
            "scenario_results": agg["scenario_summaries"],
            "verification": {
                "total_scenarios": agg["scenario_count"],
                "matched": sum(1 for s in agg["scenario_summaries"] if s["match"]),
                "mismatched": sum(1 for s in agg["scenario_summaries"] if not s["match"]),
            },
        }

    def _build_verification_matrix(self, results, manifest):
        """Build expected vs actual verification matrix."""
        matrix = []
        all_pass = True
        for sc in manifest:
            sc_id = sc["scenario_id"]
            expected = sc["expected_gate_result"]
            actual = "N/A"
            if sc_id in results:
                gate = results[sc_id].get("gate_evaluation", {})
                actual = gate.get("gate_result", "N/A")
            match = (expected == actual)
            if not match:
                all_pass = False
            matrix.append({
                "scenario_id": sc_id,
                "description": sc["description"],
                "expected": expected,
                "actual": actual,
                "match": match,
            })

        return {
            "verification_result": "ALL_PASS" if all_pass else "MISMATCH_FOUND",
            "total": len(matrix),
            "passed": sum(1 for m in matrix if m["match"]),
            "failed": sum(1 for m in matrix if not m["match"]),
            "details": matrix,
        }