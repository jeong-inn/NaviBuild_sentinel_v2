# NaviBuild-Sentinel v2

**차량용 내비게이션 Embedded SW 빌드 품질 분석 및 A-SPICE 기반 릴리즈 판정 자동화 엔진**

![NaviBuild-Sentinel Demo](https://github.com/user-attachments/assets/b225a07a-7628-463d-8c1d-6aeb2bf49556)

내비게이션 SW 빌드 로그를 AUTOSAR DLT 프로토콜 수준에서 파싱하고, TF-IDF 기반 이슈 클러스터링과 FMEA RPN 심각도 산출로 빌드 릴리즈 판정을 자동화하는 개발 PL용 품질 엔진입니다.

---

## 프로젝트 배경

내비게이션 SW 개발 PL은 매 빌드마다 두 가지 기술적 판단을 해야 합니다.

1. **이 이슈가 이전에 발생한 것과 같은 root cause인가?** — 동일 이슈도 로그 메시지 표현이 달라 수동 판단이 어려움
2. **이 빌드를 릴리즈해도 되는가?** — 심각도, 빈도, 재발 여부를 종합한 정량적 기준이 필요

이 프로젝트는 두 판단을 TF-IDF 유사도 분석과 FMEA RPN 스코어링으로 자동화하고, A-SPICE 프로세스 기반 품질 게이트로 릴리즈 판정까지 연결합니다.

---

## 아키텍처

```
[Phase 1] CAN/DLT Log Generation (12 scenarios)
     │
     ▼
[Phase 2] DLT Log Parser → SQLite Event DB
     │
     ▼
[Phase 3] TF-IDF Issue Classifier + Cosine Similarity Clustering
     │
     ▼
[Phase 4] FMEA RPN Severity Scoring (S × O × D)
     │
     ▼
[Phase 5] 3-Layer Recurrence Detection (Exact / Fuzzy / Trend)
     │
     ▼
[Phase 6] A-SPICE Quality Gate (9 items) + OTA Rollout Strategy
     │
     ▼
[Phase 7] PM Dashboard (HTML) + JSON Report + Verification Matrix
```

---

## 핵심 기술 요소

### 1. CAN/DLT 프로토콜 기반 로그 시뮬레이션
AUTOSAR DLT(Diagnostic Log and Trace) 규격을 모사한 로그 구조를 사용합니다. CAN 버스 메시지 ID, DLT App/Context ID, 차종(vehicle_variant), 지역(region) 등 실제 차량 Embedded 시스템의 로그 필드를 반영했습니다.

### 2. TF-IDF + 코사인 유사도 이슈 분류
단순 키워드 매칭이 아닌 TF-IDF 벡터화 기반 분류를 사용합니다. 동일 이슈가 다른 표현으로 나타나는 경우(예: "Route timeout 3000ms" vs "Path calculation exceeded deadline")도 유사도 기반으로 같은 이슈로 매핑합니다.

- 유사도 ≥ 0.75 → KNOWN (기존 이슈 확정)
- 0.45 ~ 0.75 → SIMILAR (유사 이슈 후보)
- < 0.45 → NEW (신규 이슈)

### 3. FMEA RPN 심각도 산출
자동차 산업 표준 FMEA의 Risk Priority Number를 SW 이슈에 적용합니다.

```
RPN = Severity(S) × Occurrence(O) × Detection(D)

CRITICAL: RPN ≥ 200   →  배포 HOLD
HIGH:     100~199      →  CONDITIONAL
MEDIUM:   40~99        →  MONITOR
LOW:      < 40         →  PASS
```

Severity는 이슈 카테고리와 DLT Context별 가중치를 적용하고, Detection은 로그 레벨과 자동복구 여부를 반영합니다.

### 4. 3-Layer 재발 탐지
| Layer | 방식 | 판정 |
|-------|------|------|
| Layer 1 | error_code + context exact match | RECURRING / RESOLVED_THEN_RECURRED |
| Layer 2 | TF-IDF cosine similarity > 0.70 | RECURRING (fuzzy) |
| Layer 3 | 빌드 간 선형 회귀 추세 분석 | TREND_WORSENING / IMPROVING / STABLE |

### 5. A-SPICE 품질 게이트
A-SPICE SWE.6(Software Qualification Test)에서 영감받은 9개 항목의 품질 체크리스트를 자동 평가합니다.

| ID | 항목 | Blocking |
|----|------|----------|
| QG-01 | CRITICAL 결함 수 == 0 | Yes |
| QG-02 | RESOLVED_THEN_RECURRED == 0 | Yes |
| QG-03 | CRASH 이슈 ≤ 3건 | No |
| QG-04 | HIGH 이슈 ≤ 2건 | No |
| QG-05 | 복합 카테고리 ≤ 2종 | No |
| QG-06 | TREND_WORSENING 없음 | No |
| QG-07 | UNKNOWN 비율 < 30% | No |
| QG-08 | 차종별 편차 정상 | No |
| QG-09 | 평균 RPN < 100 | No |

### 6. OTA 단계별 롤아웃 시뮬레이션
이슈 데이터 기반으로 3가지 배포 전략(Conservative / Standard / Aggressive)을 자동 추천합니다.

```
Conservative: Canary 2% (72h) → Staged 20% (336h) → Full
Standard:     Canary 5% (48h) → Staged 30% (168h) → Full
Aggressive:   Canary 10% (24h) → Full (72h)
```

---

## 검증 결과

12개 시나리오 Expected vs Actual **전수 일치 (12/12 ALL_PASS)**

| ID | 시나리오 | Expected | Actual | Match |
|----|---------|----------|--------|-------|
| SC01 | 정상 빌드, 이슈 없음 | PASS | PASS | ✓ |
| SC02 | 경로계산 타임아웃 단발 | CONDITIONAL | CONDITIONAL | ✓ |
| SC03 | 지도렌더링 크래시 반복 | HOLD | HOLD | ✓ |
| SC04 | 이전 빌드 해결 이슈 재발 | HOLD | HOLD | ✓ |
| SC05 | 경로오류 + 데이터오류 혼재 | HOLD | HOLD | ✓ |
| SC06 | 자동복구 확인된 이슈 | CONDITIONAL | CONDITIONAL | ✓ |
| SC07 | 미분류 패턴 다수 | MONITOR | MONITOR | ✓ |
| SC08 | 복합 크래시+성능+경로 | HOLD | HOLD | ✓ |
| SC09 | 특정 차종(IW_GEN5)만 발생 | CONDITIONAL | CONDITIONAL | ✓ |
| SC10 | 특정 지역(KR)만 발생 | CONDITIONAL | CONDITIONAL | ✓ |
| SC11 | OTA 업데이트 후 신규 이슈 | HOLD | HOLD | ✓ |
| SC12 | 점진적 성능 저하 추세 | HOLD | HOLD | ✓ |

---

## 실행 방법

### 요구사항
- Python 3.10+
- 패키지: scikit-learn, numpy, scipy, jinja2

### 설치 및 실행

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 파이프라인 실행
cd src
python main.py
```

실행하면 `data/`(로그 + DB)와 `output/`(대시보드 + 리포트)이 자동 생성됩니다.

### 산출물 확인

```bash
# PM 대시보드 열기 (브라우저)
open output/pm_dashboard.html        # macOS
start output/pm_dashboard.html       # Windows

# 검증 결과 확인
cat output/verification_matrix.json
```

---

## 프로젝트 구조

```
navibuild_sentinel_v2/
├── requirements.txt
├── README.md
└── src/
    ├── main.py                    # 전체 파이프라인 오케스트레이션
    ├── log_generator.py           # CAN/DLT 로그 12개 시나리오 생성
    ├── log_parser.py              # DLT 파싱 → SQLite 저장
    ├── issue_classifier.py        # TF-IDF + 코사인 유사도 클러스터링
    ├── severity_engine.py         # FMEA RPN 심각도 산출
    ├── recurrence_analyzer.py     # 3-Layer 재발 탐지
    ├── release_gate.py            # A-SPICE 품질 게이트 + OTA 시뮬레이션
    ├── report_generator.py        # 대시보드 HTML + JSON 리포트
    ├── data/                      # (자동 생성) 시나리오 로그 + SQLite DB
    └── output/                    # (자동 생성) 대시보드 + 리포트
        ├── pm_dashboard.html      # PM 대시보드 (Chart.js)
        ├── gate_report.json       # 고객사 보고용 리포트
        └── verification_matrix.json
```

---

## 기술 스택

| 항목 | 내용 | 선택 근거 |
|------|------|----------|
| Python 3.10+ | 메인 언어 | 데이터 분석 + 시뮬레이션 |
| scikit-learn | TF-IDF, cosine_similarity | 경량 ML, 설명 가능한 분류 |
| numpy/scipy | 선형 회귀 추세 분석 | 최소 도구로 시계열 판정 |
| SQLite | 이벤트 저장소 | Embedded DB, 서버 불필요 |
| Chart.js | 대시보드 차트 | 정적 HTML, 어디서든 열림 |
| pytest | 시나리오 검증 | Expected vs Actual 자동화 |

---
