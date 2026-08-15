# 찐맛집 탐색기 (realmatjip)

광고 가능성이 높은 리뷰의 영향력을 낮춰 "실제로 갈 가치가 높은 식당"을 찾는 개인용 Android 맛집 앱 + 백엔드.
설계: [docs/DESIGN.md](docs/DESIGN.md) / Phase 0 분석: [docs/PHASE0_FINDINGS.md](docs/PHASE0_FINDINGS.md)

## 현재 상태

- **Phase 0 (scoring engine)** — 완료. `v0.1-phase0`, 93개 scoring 테스트.
  시뮬레이션: `python -m simulation.run` → `simulation/REPORT.md`
- **Phase 1 (FastAPI + SQLite 백엔드)** — 완료. fixture 시드 + 재계산 잡 + API 전체, 16개 API 테스트.
- **Phase 2 (Android 앱)** — 완료. 단위 테스트 44개 + 계측 UI 테스트 1개 통과, 에뮬레이터 E2E 완료.
- **Phase 3A (수동 Import + LLM 분석)** — 완료. JSON/CSV Import(preview/commit), ReviewAnalyzer
  추상화(Mock/Zai), 프롬프트 v1 분리, quote 검증, 비용 가드, 분석 잡(캐시/부분실패), calibration.
  Golden Set 59리뷰 fresh baseline P=R=F1=1.000 (threshold 0.7, glm-4.5-flash).
- **Phase 3B (Google Places Provider + 실데이터 E2E)** — 완료. Places API (New) 연동
  (검색/상세/리뷰 5개 샘플), 매칭(exact/50m/name+address), Import preview/commit 중복 방지,
  Android Developer 검색 UI. **실 API E2E 통과**: 25곳 검색 → 10곳+1곳 Import → LLM 50/50
  분석($0.11) → 9곳 스코어링+1곳 근거부족 게이트 → 앱 내 검색/Import 완료.
  (FieldMask 헤더 오타 등 실측 버그 2건 수정 — 백엔드 202 테스트 통과)
- **Phase 4 (GitHub Releases 업데이트 + CI)** — 완료. SemVer 비교, 24h 스로틀 + ETag,
  update-config.json(minimumVersion/mandatory), APK 다운로드 + SHA-256 검증(불일치 시
  삭제), FileProvider 사용자 동의 설치, 홈 자동 확인 + 설정 수동 확인 + Developer 강제 확인.
  CI: tag push → 테스트 → 서명 빌드 → sha256 → 릴리즈(`.github/workflows/release.yml`).

## Android 실행

```bash
cd android
# local.properties 에 sdk.dir 와 MAPS_API_KEY(선택) 설정 필요
./gradlew assembleDebug        # APK: app/build/outputs/apk/debug/
./gradlew testDebugUnitTest    # 단위 테스트
./gradlew connectedDebugAndroidTest  # 계측 테스트 (에뮬레이터/기기 필요)
```

기본 백엔드 주소는 `http://10.0.2.2:8000`(에뮬레이터 기준)이며 앱 설정 화면에서 변경한다.
빌드 환경(이 PC): JDK 21(`~/realmatjip-tools`), Gradle wrapper 9.7, AGP 9.3.1, SDK 37.

## Phase 3A 환경변수

```bash
ZAI_API_KEY=...          # 필수 (실 LLM 분석용)
ZAI_MODEL=glm-4.5-air    # 기본값, 다른 모델로 교체 가능
ZAI_BASE_URL=https://api.z.ai/api/paas/v4
REALMATJIP_ANALYZER=zai  # 또는 mock
MAX_REVIEWS_PER_JOB=200
MAX_ESTIMATED_TOKENS_PER_JOB=300000
MAX_ESTIMATED_COST_PER_JOB=2.0
ZAI_PRICE_INPUT_PER_1K=0.0006   # USD (보수적 추정)
ZAI_PRICE_OUTPUT_PER_1K=0.0022
```

## 구조

```
backend/
├── app/
│   ├── config.py             # ScoringConfig — 모든 상수 (algorithm_version = v0.1-phase0)
│   ├── models.py             # 도메인 모델 (Restaurant, Review)
│   ├── analysis.py           # ReviewAnalysis 스키마 + signal enum
│   ├── scoring/              # 순수 scoring 엔진 (DB/API 무의존 — Phase 0 그대로)
│   ├── db/                   # SQLAlchemy ORM, mappers, seed, database
│   ├── jobs/                 # 재계산 잡 러너
│   ├── api/                  # restaurants / reviews / admin / system 라우터
│   ├── core/                 # settings(환경변수), security(단일 bearer token)
│   └── main.py               # 앱 팩토리 (create_app)
├── fixtures/                 # 5식당·175리뷰 synthetic dataset + mock analyzer
├── simulation/               # REPORT.md 생성기
└── tests/                    # 109개 테스트
```

## 실행

```bash
cd backend
python -m pip install -r requirements.txt

# 테스트 (전체 109개)
python -m unittest

# 서버 실행 (개인 PC/서버, Tailscale 전제)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 또는 fixture만 시드 (서버 없이)
python -m app.db.seed --reset
```

환경변수: `REALMATJIP_DB`(SQLite 경로, 기본 reamatjip.db), `REALMATJIP_AUTH_TOKEN`
(설정 시 모든 /api에 Bearer 인증 필요, 미설정 시 인증 없음 — Tailscale/LAN 전제).

## API 요약

| Method | Path | 용도 |
|---|---|---|
| GET | `/api/restaurants` | 목록 (q/category/local_only/min_overall/bbox/sort) |
| GET | `/api/restaurants/{id}` | 상세 + 점수 분해(explanation) + 플랫폼 통계 |
| GET | `/api/restaurants/{id}/reviews` | 리뷰 + 분석 요약 (ad_filter: off/basic/strict/very_strict) |
| POST | `/api/reviews/{id}/label` | 수동 라벨 (ad/ad_likely/ambiguous/normal, null=해제) — LLM보다 우선 |
| POST | `/api/admin/seed` | fixture 시드 |
| POST | `/api/admin/recalculate` | 전체 점수 재계산 잡 (LLM 호출 없음) |
| GET | `/api/admin/jobs/{id}` | 잡 진행률 |
| GET | `/api/admin/stats` | 수집/분석/라벨 통계 |
| GET | `/api/backup/export` | 전체 JSON 덤프 |
| GET | `/api/meta` | 버전/필터 임계값 등 |

## 로드맵

Phase 2: Android 앱(Compose) → Phase 3: 실데이터 수집 + GLM 실연동 → Phase 4: GitHub Releases 업데이트.
