"""
NaviBuild-Sentinel v2 — Module 2: DLT Log Parser & CAN Decoder

AUTOSAR DLT 포맷 로그를 파싱하여 구조화된 이벤트로 변환.
SQLite DB에 저장하여 후속 분석 모듈이 활용.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime


# ──────────────────────────────────────────────
# DLT Context Mapping (AUTOSAR Standard)
# ──────────────────────────────────────────────

DLT_CONTEXT_DESCRIPTIONS = {
    "ROUT": "Route Engine",
    "DISP": "Map Display",
    "SRCH": "POI Search",
    "CONN": "Connectivity",
    "HMI":  "User Interface",
    "DATA": "Map Data",
    "SYS":  "System",
    "OTA":  "OTA Update",
}

LOG_LEVEL_PRIORITY = {
    "FATAL": 1, "ERROR": 2, "WARN": 3,
    "INFO": 4, "DEBUG": 5, "VERBOSE": 6,
}


class DLTLogParser:
    """
    AUTOSAR DLT 로그 파서.
    
    실제 DLT는 바이너리 프로토콜이지만, 시뮬레이션에서는 JSON으로 모사.
    파서는 DLT 스펙의 논리적 필드 구조를 따름:
    - Storage Header: timestamp, ecu_source
    - Standard Header: msg_id(CAN ID), dlc
    - Extended Header: app_id, context_id, log_level
    - Payload: message body
    """

    def __init__(self, db_path="data/events.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with event schema."""
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_id TEXT,
                timestamp TEXT,
                bus_channel TEXT,
                can_msg_id TEXT,
                dlc INTEGER,
                payload_hex TEXT,
                ecu_source TEXT,
                app_id TEXT,
                context_id TEXT,
                context_name TEXT,
                log_level TEXT,
                log_level_priority INTEGER,
                message TEXT,
                build_version TEXT,
                vehicle_variant TEXT,
                region TEXT,
                issue_type TEXT,
                error_code TEXT,
                is_error INTEGER DEFAULT 0
            )
        """)
        # Index for common query patterns
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_scenario 
            ON events(scenario_id)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_build 
            ON events(build_version, is_error)
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_issue_type
            ON events(issue_type)
        """)
        self.conn.commit()

    def parse_log_file(self, filepath, scenario_id):
        """
        Parse a single JSON log file and insert events into DB.
        
        Args:
            filepath: Path to the JSON log file
            scenario_id: Scenario identifier (e.g., "SC01")
        
        Returns:
            dict with parse statistics
        """
        filepath = Path(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            raw_logs = json.load(f)

        stats = {
            "total": 0,
            "errors": 0,
            "by_level": {},
            "by_context": {},
            "by_issue_type": {},
        }

        rows = []
        for log in raw_logs:
            parsed = self._parse_single_entry(log, scenario_id)
            rows.append(parsed)

            # Collect stats
            stats["total"] += 1
            level = parsed["log_level"]
            ctx = parsed["context_id"]
            stats["by_level"][level] = stats["by_level"].get(level, 0) + 1
            stats["by_context"][ctx] = stats["by_context"].get(ctx, 0) + 1
            if parsed["is_error"]:
                stats["errors"] += 1
                itype = parsed["issue_type"] or "UNCLASSIFIED"
                stats["by_issue_type"][itype] = stats["by_issue_type"].get(itype, 0) + 1

        # Batch insert
        self.conn.executemany("""
            INSERT INTO events (
                scenario_id, timestamp, bus_channel, can_msg_id, dlc,
                payload_hex, ecu_source, app_id, context_id, context_name,
                log_level, log_level_priority, message, build_version,
                vehicle_variant, region, issue_type, error_code, is_error
            ) VALUES (
                :scenario_id, :timestamp, :bus_channel, :can_msg_id, :dlc,
                :payload_hex, :ecu_source, :app_id, :context_id, :context_name,
                :log_level, :log_level_priority, :message, :build_version,
                :vehicle_variant, :region, :issue_type, :error_code, :is_error
            )
        """, rows)
        self.conn.commit()

        return stats

    def _parse_single_entry(self, log_entry, scenario_id):
        """Parse a single log entry into structured event dict."""
        context_id = log_entry.get("context_id", "SYS")
        log_level = log_entry.get("log_level", "INFO")
        issue_type = log_entry.get("_issue_type")
        error_code = log_entry.get("_error_code")

        is_error = 1 if log_level in ("FATAL", "ERROR") or issue_type else 0

        return {
            "scenario_id": scenario_id,
            "timestamp": log_entry.get("timestamp", ""),
            "bus_channel": log_entry.get("bus_channel", "CAN0"),
            "can_msg_id": log_entry.get("msg_id", "0x6FF"),
            "dlc": log_entry.get("dlc", 8),
            "payload_hex": log_entry.get("payload_hex", ""),
            "ecu_source": log_entry.get("ecu_source", "NAV_MAIN"),
            "app_id": log_entry.get("app_id", "NAVI"),
            "context_id": context_id,
            "context_name": DLT_CONTEXT_DESCRIPTIONS.get(context_id, "Unknown"),
            "log_level": log_level,
            "log_level_priority": LOG_LEVEL_PRIORITY.get(log_level, 6),
            "message": log_entry.get("message", ""),
            "build_version": log_entry.get("build_version", ""),
            "vehicle_variant": log_entry.get("vehicle_variant", ""),
            "region": log_entry.get("region", ""),
            "issue_type": issue_type,
            "error_code": error_code,
            "is_error": is_error,
        }

    def get_error_events(self, scenario_id):
        """Retrieve all error events for a scenario."""
        cursor = self.conn.execute("""
            SELECT * FROM events 
            WHERE scenario_id = ? AND is_error = 1
            ORDER BY timestamp
        """, (scenario_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_all_events(self, scenario_id):
        """Retrieve all events for a scenario."""
        cursor = self.conn.execute("""
            SELECT * FROM events 
            WHERE scenario_id = ? 
            ORDER BY timestamp
        """, (scenario_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_build_history(self, issue_type=None):
        """Get issue counts per build version, optionally filtered by type."""
        if issue_type:
            cursor = self.conn.execute("""
                SELECT build_version, COUNT(*) as count
                FROM events 
                WHERE is_error = 1 AND issue_type = ?
                GROUP BY build_version
                ORDER BY build_version
            """, (issue_type,))
        else:
            cursor = self.conn.execute("""
                SELECT build_version, COUNT(*) as count
                FROM events 
                WHERE is_error = 1
                GROUP BY build_version
                ORDER BY build_version
            """)
        return {row["build_version"]: row["count"] for row in cursor.fetchall()}

    def get_variant_distribution(self, scenario_id):
        """Get error distribution by vehicle variant."""
        cursor = self.conn.execute("""
            SELECT vehicle_variant, COUNT(*) as count
            FROM events
            WHERE scenario_id = ? AND is_error = 1
            GROUP BY vehicle_variant
        """, (scenario_id,))
        return {row["vehicle_variant"]: row["count"] for row in cursor.fetchall()}

    def get_region_distribution(self, scenario_id):
        """Get error distribution by region."""
        cursor = self.conn.execute("""
            SELECT region, COUNT(*) as count
            FROM events
            WHERE scenario_id = ? AND is_error = 1
            GROUP BY region
        """, (scenario_id,))
        return {row["region"]: row["count"] for row in cursor.fetchall()}

    def clear_scenario(self, scenario_id):
        """Clear all events for a scenario."""
        self.conn.execute("DELETE FROM events WHERE scenario_id = ?", (scenario_id,))
        self.conn.commit()

    def clear_all(self):
        """Clear all events."""
        self.conn.execute("DELETE FROM events")
        self.conn.commit()

    def close(self):
        self.conn.close()


def parse_all_scenarios(data_dir="data"):
    """Parse all generated scenario logs."""
    data_path = Path(data_dir)
    manifest_path = data_path / "scenario_manifest.json"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    parser = DLTLogParser(db_path=str(data_path / "events.db"))
    parser.clear_all()

    all_stats = {}
    for scenario in manifest:
        sc_id = scenario["scenario_id"]
        log_file = data_path / scenario["log_file"]
        stats = parser.parse_log_file(log_file, sc_id)
        all_stats[sc_id] = stats
        print(f"  [{sc_id}] Parsed {stats['total']} events, "
              f"{stats['errors']} errors | "
              f"Levels: {stats['by_level']} | "
              f"Issues: {stats['by_issue_type']}")

    parser.close()
    print(f"\n✓ All scenarios parsed into {data_path}/events.db")
    return all_stats


if __name__ == "__main__":
    print("NaviBuild-Sentinel v2 — DLT Log Parser")
    print("=" * 50)
    parse_all_scenarios()