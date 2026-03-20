"""
NaviBuild-Sentinel v2 — Module 1: Synthetic CAN/DLT Log Generator

차량용 내비게이션 Embedded SW의 CAN 버스 메시지 및 AUTOSAR DLT 로그를 모사.
12개 시나리오별로 현실적인 로그 데이터를 생성.
"""

import json
import random
import hashlib
from datetime import datetime, timedelta
from pathlib import Path


# ──────────────────────────────────────────────
# Constants: CAN/DLT Protocol Simulation
# ──────────────────────────────────────────────

CAN_IDS = {
    "NAV_ROUTE":  "0x601",   # 경로 계산 관련
    "NAV_DISP":   "0x602",   # 지도 표시 관련
    "NAV_SRCH":   "0x603",   # POI 검색
    "NAV_CONN":   "0x604",   # 텔레매틱스 연동
    "NAV_HMI":    "0x605",   # HMI 이벤트
    "NAV_DATA":   "0x606",   # 지도 데이터
    "NAV_SYS":    "0x607",   # 시스템
    "NAV_OTA":    "0x608",   # OTA 업데이트
}

DLT_CONTEXTS = {
    "ROUT": "Route Engine",
    "DISP": "Map Display",
    "SRCH": "POI Search",
    "CONN": "Connectivity",
    "HMI":  "User Interface",
    "DATA": "Map Data",
    "SYS":  "System",
    "OTA":  "OTA Update",
}

DLT_LOG_LEVELS = ["FATAL", "ERROR", "WARN", "INFO", "DEBUG"]

VEHICLE_VARIANTS = ["IW_GEN5", "IW_GEN5_HEV", "IW_GEN4", "IW_GEN5_EV"]
REGIONS = ["KR", "US", "EU", "CN"]

BUILD_VERSIONS = [
    "NAV_25W08_RC1",
    "NAV_25W09_RC1",
    "NAV_25W10_RC2",
    "NAV_25W11_RC1",
    "NAV_25W12_RC3",  # 현재 빌드
]


# ──────────────────────────────────────────────
# Log Entry Templates
# ──────────────────────────────────────────────

ERROR_TEMPLATES = {
    "CRASH": [
        ("DISP", "Map rendering engine crashed: OpenGL context lost during tile composition"),
        ("DISP", "Fatal exception in display module: null pointer dereference at render_frame()"),
        ("ROUT", "Route calculation process terminated unexpectedly: SIGSEGV in pathfinder_core"),
        ("SYS",  "System watchdog triggered: NAV_MAIN process unresponsive for 5000ms"),
        ("HMI",  "HMI framework crash: UI thread deadlock detected during screen transition"),
    ],
    "PERFORMANCE": [
        ("ROUT", "Route calculation timeout: path_engine exceeded 3000ms threshold"),
        ("ROUT", "Path calculation deadline exceeded: 4200ms for 150km route segment"),
        ("DISP", "Map tile rendering latency spike: 850ms per frame (target: 33ms)"),
        ("SRCH", "POI search response time degraded: 2800ms for radius query"),
        ("DATA", "Map data decompression stalled: LZ4 decode blocked for 1200ms"),
    ],
    "DATA_ERROR": [
        ("DATA", "Map data integrity check failed: CRC mismatch on tile_KR_L12_3842"),
        ("DATA", "POI database index corrupted: B-tree node overflow in category_restaurant"),
        ("DATA", "Road network topology error: disconnected segment at node_id=8834021"),
        ("SRCH", "Search index inconsistency: duplicate POI entries for region_KR_Seoul"),
    ],
    "ROUTE_ERROR": [
        ("ROUT", "Invalid route generated: U-turn on highway segment hwy_KR_001_S"),
        ("ROUT", "Route guidance mismatch: announced exit does not match calculated path"),
        ("ROUT", "Alternative route calculation failed: no valid path between waypoints"),
        ("ROUT", "ETA calculation error: estimated time diverges >30% from historical data"),
    ],
    "CONNECTIVITY": [
        ("CONN", "Telematics connection lost: MQTT broker unreachable for 30s"),
        ("CONN", "Real-time traffic data sync failed: HTTP 503 from TMAP server"),
        ("OTA",  "OTA manifest download interrupted: connection reset during delta check"),
    ],
    "OTA_ISSUE": [
        ("OTA",  "OTA update verification failed: signature mismatch on package NAV_25W12"),
        ("OTA",  "Post-update health check failed: route_engine startup timeout after OTA apply"),
        ("OTA",  "OTA rollback triggered: critical module version incompatibility detected"),
    ],
}

INFO_TEMPLATES = [
    ("SYS",  "NAV system boot completed: all modules initialized in 2.3s"),
    ("ROUT", "Route calculation completed successfully: 45km, ETA 38min"),
    ("DISP", "Map rendering pipeline stable: avg 28fps over last 60s"),
    ("CONN", "Telematics connection established: latency 45ms"),
    ("DATA", "Map data update applied: version 2025.03.12_KR"),
    ("OTA",  "OTA health check passed: all modules report nominal status"),
    ("HMI",  "User interaction logged: destination search initiated"),
    ("SRCH", "POI search completed: 23 results in 340ms"),
]


def _gen_timestamp(base_time, offset_seconds):
    """Generate ISO timestamp with millisecond precision."""
    dt = base_time + timedelta(seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{random.randint(0, 999):03d}"


def _gen_can_payload():
    """Generate random CAN payload hex string (8 bytes)."""
    return " ".join(f"{random.randint(0, 255):02X}" for _ in range(8))


def _gen_error_code(issue_type, context):
    """Generate deterministic error code from type + context."""
    seed = f"{issue_type}_{context}"
    h = hashlib.md5(seed.encode()).hexdigest()[:6].upper()
    return f"E-{h}"


def _make_log_entry(
    timestamp, build_version, context_id, log_level, message,
    vehicle_variant=None, region=None, issue_type=None
):
    """Create a single structured log entry in CAN/DLT format."""
    can_id = CAN_IDS.get(f"NAV_{context_id}", "0x6FF")
    entry = {
        "timestamp": timestamp,
        "bus_channel": "CAN0",
        "msg_id": can_id,
        "dlc": 8,
        "payload_hex": _gen_can_payload(),
        "ecu_source": "NAV_MAIN",
        "app_id": "NAVI",
        "context_id": context_id,
        "log_level": log_level,
        "message": message,
        "build_version": build_version,
        "vehicle_variant": vehicle_variant or random.choice(VEHICLE_VARIANTS),
        "region": region or random.choice(REGIONS),
    }
    if issue_type:
        entry["_issue_type"] = issue_type
        entry["_error_code"] = _gen_error_code(issue_type, context_id)
    return entry


# ──────────────────────────────────────────────
# Scenario Generators
# ──────────────────────────────────────────────

def _add_normal_traffic(logs, build, base_time, count=20):
    """Add normal INFO-level log entries as background traffic."""
    for i in range(count):
        ctx, msg = random.choice(INFO_TEMPLATES)
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, i * 30 + random.randint(0, 10)),
            build, ctx, "INFO", msg
        ))


def scenario_sc01(base_time):
    """SC01: 정상 빌드, 이슈 없음 → PASS"""
    logs = []
    build = "NAV_25W12_RC3"
    _add_normal_traffic(logs, build, base_time, count=25)
    return logs, "SC01", "PASS", "정상 빌드, 이슈 없음"


def scenario_sc02(base_time):
    """SC02: 경로계산 타임아웃 단발 → CONDITIONAL"""
    logs = []
    build = "NAV_25W12_RC3"
    _add_normal_traffic(logs, build, base_time, count=20)
    # 단발성 PERFORMANCE 이슈 1건
    ctx, msg = ERROR_TEMPLATES["PERFORMANCE"][0]
    logs.append(_make_log_entry(
        _gen_timestamp(base_time, 300), build, ctx, "ERROR", msg,
        issue_type="PERFORMANCE"
    ))
    return logs, "SC02", "CONDITIONAL", "경로계산 타임아웃 단발"


def scenario_sc03(base_time):
    """SC03: 지도렌더링 크래시 반복 → HOLD"""
    logs = []
    build = "NAV_25W12_RC3"
    _add_normal_traffic(logs, build, base_time, count=15)
    # CRASH 반복 5건
    for i in range(5):
        ctx, msg = ERROR_TEMPLATES["CRASH"][0]  # 동일 크래시 반복
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 100 + i * 60), build, ctx, "FATAL", msg,
            issue_type="CRASH"
        ))
    return logs, "SC03", "HOLD", "지도렌더링 크래시 반복"


def scenario_sc04(base_time):
    """SC04: 이전 빌드 해결 이슈 재발 → HOLD"""
    logs = []
    build_prev = "NAV_25W10_RC2"
    build_curr = "NAV_25W12_RC3"

    # 이전 빌드: 이슈 발생
    ctx, msg = ERROR_TEMPLATES["ROUTE_ERROR"][0]
    logs.append(_make_log_entry(
        _gen_timestamp(base_time - timedelta(days=14), 200),
        build_prev, ctx, "ERROR", msg, issue_type="ROUTE_ERROR"
    ))
    # 이전 빌드: 해결 마킹 (INFO 로그)
    logs.append(_make_log_entry(
        _gen_timestamp(base_time - timedelta(days=7), 100),
        "NAV_25W11_RC1", "ROUT", "INFO",
        "Issue E-resolved: Invalid route on highway segment confirmed fixed"
    ))
    # 현재 빌드: 동일 이슈 재발
    _add_normal_traffic(logs, build_curr, base_time, count=10)
    logs.append(_make_log_entry(
        _gen_timestamp(base_time, 400), build_curr, ctx, "ERROR", msg,
        issue_type="ROUTE_ERROR"
    ))
    return logs, "SC04", "HOLD", "이전 빌드 해결 이슈 재발"


def scenario_sc05(base_time):
    """SC05: 경로오류 + 데이터오류 혼재 → HOLD"""
    logs = []
    build = "NAV_25W12_RC3"
    _add_normal_traffic(logs, build, base_time, count=10)
    # ROUTE_ERROR 3건
    for i in range(3):
        ctx, msg = random.choice(ERROR_TEMPLATES["ROUTE_ERROR"])
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 150 + i * 80), build, ctx, "ERROR", msg,
            issue_type="ROUTE_ERROR"
        ))
    # DATA_ERROR 3건
    for i in range(3):
        ctx, msg = random.choice(ERROR_TEMPLATES["DATA_ERROR"])
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 400 + i * 60), build, ctx, "ERROR", msg,
            issue_type="DATA_ERROR"
        ))
    return logs, "SC05", "HOLD", "경로오류 + 데이터오류 혼재"


def scenario_sc06(base_time):
    """SC06: 자동복구 확인된 이슈 → CONDITIONAL"""
    logs = []
    build = "NAV_25W12_RC3"
    _add_normal_traffic(logs, build, base_time, count=15)
    # 이슈 발생
    ctx, msg = ERROR_TEMPLATES["CONNECTIVITY"][0]
    logs.append(_make_log_entry(
        _gen_timestamp(base_time, 200), build, ctx, "WARN", msg,
        issue_type="CONNECTIVITY"
    ))
    # 자동 복구
    logs.append(_make_log_entry(
        _gen_timestamp(base_time, 235), build, "CONN", "INFO",
        "Telematics connection restored: auto-reconnect successful after 35s"
    ))
    return logs, "SC06", "CONDITIONAL", "자동복구 확인된 이슈"


def scenario_sc07(base_time):
    """SC07: 미분류 패턴 다수 → MONITOR"""
    logs = []
    build = "NAV_25W12_RC3"
    _add_normal_traffic(logs, build, base_time, count=10)
    unknown_messages = [
        ("SYS",  "Unrecognized IPC message type 0xAF from module nav_aux"),
        ("SYS",  "Unexpected state transition in module lifecycle: INIT→SUSPEND"),
        ("DATA", "Unknown data format version 7 in tile header, expected version 5"),
        ("HMI",  "Unhandled event type EVENT_CUSTOM_0x3B in UI state machine"),
        ("ROUT", "Undefined behavior flag set in route optimizer: flag_0x1C"),
    ]
    for i, (ctx, msg) in enumerate(unknown_messages):
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 100 + i * 50), build, ctx, "WARN", msg,
            issue_type="UNKNOWN"
        ))
    return logs, "SC07", "MONITOR", "미분류 패턴 다수"


def scenario_sc08(base_time):
    """SC08: 복합 크래시+성능+경로 → HOLD"""
    logs = []
    build = "NAV_25W12_RC3"
    _add_normal_traffic(logs, build, base_time, count=8)
    # CRASH 2건
    for i in range(2):
        ctx, msg = ERROR_TEMPLATES["CRASH"][i]
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 50 + i * 40), build, ctx, "FATAL", msg,
            issue_type="CRASH"
        ))
    # PERFORMANCE 2건
    for i in range(2):
        ctx, msg = ERROR_TEMPLATES["PERFORMANCE"][i + 2]
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 200 + i * 50), build, ctx, "ERROR", msg,
            issue_type="PERFORMANCE"
        ))
    # ROUTE_ERROR 2건
    for i in range(2):
        ctx, msg = ERROR_TEMPLATES["ROUTE_ERROR"][i + 1]
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 400 + i * 40), build, ctx, "ERROR", msg,
            issue_type="ROUTE_ERROR"
        ))
    return logs, "SC08", "HOLD", "복합 크래시+성능+경로"


def scenario_sc09(base_time):
    """SC09: 특정 차종(IW_GEN5)만 발생 → CONDITIONAL"""
    logs = []
    build = "NAV_25W12_RC3"
    _add_normal_traffic(logs, build, base_time, count=15)
    # IW_GEN5에서만 CRASH 발생 3건
    for i in range(3):
        ctx, msg = ERROR_TEMPLATES["CRASH"][3]
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 200 + i * 100), build, ctx, "FATAL", msg,
            vehicle_variant="IW_GEN5", issue_type="CRASH"
        ))
    # 다른 차종에서는 정상
    for variant in ["IW_GEN4", "IW_GEN5_HEV", "IW_GEN5_EV"]:
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 500 + random.randint(0, 100)),
            build, "SYS", "INFO",
            f"System health check passed for variant {variant}",
            vehicle_variant=variant
        ))
    return logs, "SC09", "CONDITIONAL", "특정 차종(IW_GEN5)만 발생"


def scenario_sc10(base_time):
    """SC10: 특정 지역(KR)만 발생 → CONDITIONAL"""
    logs = []
    build = "NAV_25W12_RC3"
    _add_normal_traffic(logs, build, base_time, count=12)
    # KR 지역 DATA_ERROR 3건
    for i in range(3):
        ctx, msg = ERROR_TEMPLATES["DATA_ERROR"][i]
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 150 + i * 70), build, ctx, "ERROR", msg,
            region="KR", issue_type="DATA_ERROR"
        ))
    # 다른 지역 정상
    for region in ["US", "EU", "CN"]:
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 500 + random.randint(0, 50)),
            build, "DATA", "INFO",
            f"Map data validation passed for region {region}",
            region=region
        ))
    return logs, "SC10", "CONDITIONAL", "특정 지역(KR)만 발생"


def scenario_sc11(base_time):
    """SC11: OTA 업데이트 후 신규 이슈 → HOLD"""
    logs = []
    build = "NAV_25W12_RC3"
    # OTA 적용 로그
    logs.append(_make_log_entry(
        _gen_timestamp(base_time, 0), build, "OTA", "INFO",
        "OTA update applied: NAV_25W11_RC1 → NAV_25W12_RC3"
    ))
    _add_normal_traffic(logs, build, base_time, count=8)
    # OTA 후 이슈 3건
    for i, (ctx, msg) in enumerate(ERROR_TEMPLATES["OTA_ISSUE"]):
        logs.append(_make_log_entry(
            _gen_timestamp(base_time, 100 + i * 120), build, ctx, "ERROR", msg,
            issue_type="OTA_ISSUE"
        ))
    # 추가 크래시
    ctx, msg = ERROR_TEMPLATES["CRASH"][4]
    logs.append(_make_log_entry(
        _gen_timestamp(base_time, 500), build, ctx, "FATAL", msg,
        issue_type="CRASH"
    ))
    return logs, "SC11", "HOLD", "OTA 업데이트 후 신규 이슈"


def scenario_sc12(base_time):
    """SC12: 점진적 성능 저하 추세 → HOLD"""
    logs = []
    # 과거 빌드들에서 점진적 성능 저하
    perf_counts = [1, 1, 2, 3, 5]  # 빌드별 PERFORMANCE 이슈 수 증가 추세
    for build_idx, build in enumerate(BUILD_VERSIONS):
        build_time = base_time - timedelta(days=(4 - build_idx) * 7)
        _add_normal_traffic(logs, build, build_time, count=8)
        for i in range(perf_counts[build_idx]):
            ctx, msg = random.choice(ERROR_TEMPLATES["PERFORMANCE"])
            logs.append(_make_log_entry(
                _gen_timestamp(build_time, 100 + i * 60),
                build, ctx, "ERROR", msg, issue_type="PERFORMANCE"
            ))
    return logs, "SC12", "HOLD", "점진적 성능 저하 추세"


# ──────────────────────────────────────────────
# Main Generator
# ──────────────────────────────────────────────

ALL_SCENARIOS = [
    scenario_sc01, scenario_sc02, scenario_sc03, scenario_sc04,
    scenario_sc05, scenario_sc06, scenario_sc07, scenario_sc08,
    scenario_sc09, scenario_sc10, scenario_sc11, scenario_sc12,
]


def generate_all_scenarios(output_dir="data"):
    """Generate log files for all 12 scenarios."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    random.seed(42)  # 재현성 보장
    base_time = datetime(2026, 3, 15, 8, 0, 0)
    manifest = []

    for scenario_fn in ALL_SCENARIOS:
        logs, sc_id, expected_gate, description = scenario_fn(base_time)
        # Sort by timestamp
        logs.sort(key=lambda x: x["timestamp"])

        filename = f"{sc_id.lower()}_logs.json"
        filepath = output_path / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)

        manifest.append({
            "scenario_id": sc_id,
            "description": description,
            "expected_gate_result": expected_gate,
            "log_file": filename,
            "log_count": len(logs),
            "error_count": sum(1 for l in logs if l.get("_issue_type")),
        })
        print(f"  [{sc_id}] {description}: {len(logs)} logs, "
              f"{manifest[-1]['error_count']} errors → expected: {expected_gate}")

    # Save manifest
    manifest_path = output_path / "scenario_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n✓ {len(manifest)} scenarios generated in {output_path}/")
    return manifest


if __name__ == "__main__":
    print("NaviBuild-Sentinel v2 — Log Generator")
    print("=" * 50)
    generate_all_scenarios()