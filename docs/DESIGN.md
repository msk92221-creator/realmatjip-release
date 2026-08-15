# 찐맛집 탐색기 (realmatjip) — 확정 설계 문서

버전: design-v1.0 (2026-08-15 확정)
상태: Phase 0 진행 중. 점수 가중치는 시뮬레이션 결과 확인 후 확정 예정.

---

## 0. 확정된 결정사항

| # | 결정 | 내용 |
|---|------|------|
| D1 | 데이터 소스 | Google Places API + 수동 Import로 시작. 자동 다중 플랫폼 수집은 하지 않되 provider adapter 구조는 유지 |
| D2 | 저장소 | 소스코드 repository는 Private. 업데이트 APK 전용 repository를 별도 Public으로 생성. Android APK에 GitHub Token 미포함 |
| D3 | Backend | 개인 PC/서버에서 FastAPI 실행. Android와는 Tailscale로 연결. Cloud 배포 제외 |
| D4 | 지도 | Google Maps 기반. 단 지도 provider가 business logic과 결합하지 않도록 추상화 |
| D5 | 광고 사전확률 | `ad_prior=0.30`은 상수가 아니라 `ScoringConfig`의 설정값. 수동 라벨 30개 이상이 쌓이면 observed prior로 교체 |
| D6 | 점수 알고리즘 | Overall Score Version A(기본)와 Version B(평점 비중 축소)를 병행 테스트. 가중치는 Phase 0 시뮬레이션 후 확정 |
| D7 | 근거 강도 | `evidence_strength = n_eff/(n_eff+8)` — Overall에 가산하지 않고 UI/explanation 전용. n_eff는 이미 수축에 반영되므로 이중 보상 방지. 향후 실데이터 검증 후 최대 1~2점 confidence/tie-break 용도로만 구조 개방 |
| D8 | 랭킹 invariant | 고정 기대 순위를 강제하지 않는다. invariant: A는 raw 대비 크게 하락 / B·D 상위권 / E는 B/D 아래 / C는 manipulation 위험 높되 바이럴만으로 과잉 처벌 금지 / A↔C 순위는 신호에 맡김 |
| D9 | c_rating | 기본 10 유지 (fixture 순위 보정용 조정 금지). 후보 6/8/10/12 민감도를 리포트에 상시 출력, 실데이터 확보 후 empirical calibration |
| D10 | 중복 탐지 임계값 | bigram/0.89/최소16자를 v1 기본값으로 하되 config 값. 후보 0.85~0.95 민감도 테스트 가능 |
| D11 | 플랫폼 검증 게이트 | 중복 제외 리뷰 수 ≥3 AND 유효 가중치 합 ≥1.5 (이중 조건). 저품질/광고/중복 리뷰가 많다는 이유만으로 검증 통과 금지 |
| D12 | 버전/설정 | `score_algorithm_version = "v0.1-phase0"`. 모든 상수는 `ScoringConfig` 하나로 관리, scoring 함수 내 magic number 금지 |
| D13 | 캐시 분리 | **evaluation cache와 production analysis_cache는 완전히 별개.** evaluation script(force_refresh)는 production 파이프라인을 우회하며 결과를 production cache에 쓰지 않는다. production 캐시는 오직 analyze-pending job을 통해서만 채워진다. (Phase 3A.4 확정) |

Phase 0의 목적: **"내가 생각하는 찐맛집 순위와 알고리즘 순위가 일치하는지" 검증.**
직관 기대 순위: B(로컬 찐맛집) > D(오래된 노포) > E(플랫폼 편차) > A(광고 다수) > C(바이럴 폭증).

---

## 1. 전체 아키텍처

```
Android App (Kotlin/Compose, 단일 모듈)
   │  REST (Tailscale)
   ▼
Backend (FastAPI 단일 프로세스)
   ├── Restaurant/Search API
   ├── Review Import (google_places / manual_import provider)
   ├── Review Analyzer (GLM, Tier-0 규칙)
   ├── Scoring Engine (순수 파이썬 패키지)
   └── Backup/Export
   ▼
SQLite   →   GLM API

앱 자체 업데이트: 별도 Public Release Repo (GitHub Releases)
```

데이터 레이어: `RAW(raw_payload) → NORMALIZED(reviews) → ENRICHED(review_analysis) → SCORED(가중치) → AGGREGATED(restaurant_scores)`.
원본 보존, LLM/스코어링 재계산 가능, scoring algorithm version 관리.

## 2. 데이터 소스 전략 (D1)

- 초기: Google Places(장소 정보 + 리뷰 최대 5개/장소) + 사람이 정리한 JSON 수동 import.
- 모든 provider는 내부적으로 동일한 normalized review schema로 변환 (`app/providers/` 구조 예약).
- 공개 API/공개 페이지만 사용. 인증 우회·robots 위반 수집 금지. 개인 이용 목적, 재배표 금지.

## 3. Database Schema (SQLite) — Phase 1 구현 완료

구현 위치: `backend/app/db/models.py` (SQLAlchemy 2.0). 초기 schema는 `create_all` +
`app_settings.schema_version` 스탬프로 관리(진화 시 Alembic 도입).

테이블: `restaurants`, `reviews`(text_hash·raw_payload·duplicate_of 포함),
`review_analysis`, `manual_labels`, `restaurant_scores`(batch_id별 이력, algorithm_version 함께,
terms_a/b·platforms JSON = explanation 렌더링 소스), `analysis_cache`, `jobs`, `app_settings`.

주요 인덱스: `reviews(restaurant_id)`, `reviews(text_hash)`,
`restaurant_scores(algorithm_version, overall_a)`, `restaurant_scores(batch_id)`.

## 4. Review Analysis Schema

LLM/목 분석기 공통 출력 (런타임 검증 대상):

```python
ad_probability, ad_confidence, authenticity, specificity, local_probability  # 0~1
sentiment: {food, service, price, atmosphere, accessibility}  # 0~1 or None
visit_context: {repeat_visit, wait_time_mentioned, menu_specificity, negative_points_present}
signals: ad_signals / authentic_signals  # 고정 enum + 원문 인용(quote) 필수
pseudo_rating: 1~5 or None   # 별점 없는 리뷰(블로그) 전용
flags: {insufficient_text, needs_manual_review}
```

- Signal 어휘 고정(enum): ad=`explicit_sponsorship, catalog_listing, all_positive_no_drawback, marketing_usp_repeat, template_style, cta_outlink, photo_promo` / authentic=`repeat_visit, specific_menu_eval, negative_point, wait_time, price_detail, local_context, visit_timing, long_term_patron`
- 할루시네이션 방지: 모든 signal은 원문 quote를 포함해야 하며 검증 계층이 실제 존재하는 인용인지 확인. 근거 없는 `local_probability`는 0.5로 강제.

## 5. Review Weight v1 (확정 공식)

### 5.1 유효 광고확률

```
p_eff = 수동 라벨 존재 시 라벨 매핑값 (ad=0.95, ad_likely=0.70, ambiguous=0.50, normal=0.05)
       아니면 conf·p_llm + (1−conf)·ad_prior        # ad_prior: 설정값(기본 0.30, 관측값으로 교체 가능)
```

### 5.2 가중치

```
w = 0.05 + 0.95 · [ (1−p_eff)^(2.5·0.7) · f_qual^0.2 · f_src^0.05 · f_rev^0.05 ] · f_time
```

| 인자 | 정의 |
|------|------|
| f_ad | `(1−p_eff)^2.5` (지수 0.7 적용) |
| f_qual | `0.5 + 0.5·(0.6·authenticity + 0.4·specificity)` — 하한 0.5로 진솔한 짧은 리뷰 과살상 방지 |
| f_src | google 1.00 / naver·kakao맵 0.95 / manual 0.90 / 커뮤니티 0.85 / 블로그 0.80 (평점 신뢰도 편향 기준. "블로그=광고" 규칙 아님) |
| f_rev | 리뷰어 리뷰수 ≥20: 1.0 / ≥5: 0.8 / <5: 0.6 / 미상: 0.85 |
| f_time | 0~3개월 1.00 / 3~6 0.90 / 6~12 0.80 / 1~2년 0.65 / 2년+ 0.45 (곱셈 직접 적용) |

- 근거 유지(w≈0.09), p=0.5→w≈0.34, p=0.2→w≈0.70, p=0→w≈0.93, p=1→w=0.05(floor).
- **캘리브레이션 기록**: 초기안(기하평균 α_ad=0.35, f_ad=1−p)은 p=0.8에서 w≈0.4로 설계 의도(§8 표, ≈0.1)와 크게 벗어져 사전 검증에서 위 공식으로 수정함.
- Near-duplicate(정규화 char **bigram** Jaccard ≥ 0.89, 정규화 16자 미만은 판단 제외, 식당 내 탐색) 클러스터 멤버는 대표 리뷰(최초) 외 `w×0.1`. — Phase 0 실측으로 확정: 3-gram/0.80은 스팸 복붙과 정상 단어 변형을 구분하지 못함.

## 6. Restaurant Score — Version A / B 병행

공통 하위 점수(모두 베이지안 수축 `shrunk = (Σwv + C·μ)/(Σw + C)`):

```
rating_adjusted = shrunk(r01, w, μ_r=데이터셋 전체 평균, C=10)
ad_free  = shrunk(1−p_eff, w, 0.70, 8)
trust    = shrunk(0.6(1−p_eff)+0.3·auth+0.1·spec, w, 0.60, 8)
local    = shrunk(local_probability, w, 0.35, 12)
repeat   = shrunk(1[repeat_visit], w, 0.08, 6)
food/value = shrunk(sentiment.*) — 근거 가중치 부족 시 None
```

식당 레벨 신호(리뷰 내용과 분리된 메타데이터 — 이중처벌 방지):

```
consistency = 플랫폼별 shrunk 평점의 sd 기반. 게이트(D11): 중복 제외 리뷰 수 ≥3 AND Σw ≥1.5.
              k=1 → 0.45, k=2 → ×0.85, k≥3 → ×1.0.
              조작 위험이 만든 인위적 일관성은 ×(1−manipulation) 할인.
longevity   = min(연도span/4, 1) × (1 − 실제 연도별 가중평균 sd/0.15)
manipulation = clamp01(0.55·burst01 + 0.45·dup01)
               burst01 = clamp01((최대월 등록수/활성월 중앙값 − 2.5)/10), 원시 등록 건수 기준
evidence_strength = n_eff/(n_eff+8)  # D7: Overall 미반영, 표시 전용
```

Overall (가중치는 provisional, D6):

```
A안: 55·rating + 12·consistency + 8·repeat + 8·local + 7·longevity + 10·trust − 12·manipulation
B안(평점 비중 축소): 45·rating + 14·consistency + 10·repeat + 10·local + 8·longevity + 13·trust − 12·manipulation
```

- 게이트: `n_eff = Σw < 2.0` → 점수 없음("데이터 부족"). 리뷰 2개·평점 5.0 식당이 상위에 오는 문제 차단.
- 추세(최근 3개월 vs 6~12개월)는 점수 미반영, 표시 전용.
- 로컬 배지: `local_evidence = Σw·1[local_prob≥0.6] ≥ 2.0`일 때만.
- **Phase 0 결과** (docs/PHASE0_FINDINGS.md): 순위 D > B > E > C > A (A/B안 동일). 구조 결함 5건 수정 반영. 남은 결정: B/D 스왑(longevity vs 근거강도) — 근거 강도 항목 신설을 권고, 가중치는 실데이터 전 확정 보류.

## 7. 광고성 판단 파이프라인

```
수집 → 정규화 → exact hash 제거 → near-dup 클러스터링
→ Tier 0(규칙): 길이<8자 등 → LLM 미호출, 기본값 분석
→ Tier 1(GLM): temperature 0, JSON 강제, 근거 quote 필수
→ 캐시(text_hash+model+prompt_version) → 비용 가드(월 상한)
```

- Calibration: 수동 라벨이 골든셋. threshold 0.7에서 FP률 <10% 게이트를 통과해야 prompt_version 승격.
- 표시 필터: 기본 p<0.7 / 엄격 p<0.4 / 매우 엄격 p<0.2 (설정으로 조정).
- 어휘 원칙: "광고 리뷰" 등 단정 표현 금지, "광고 가능성이 높은 리뷰" 사용.

## 8. Backend (Phase 1)

FastAPI 단일 프로세스 + SQLite + httpx. 인증은 단일 bearer token(환경변수).
노출: Tailscale/LAN만 (D3). API 목록은 이전 설계 검토안 그대로(/api/restaurants, /{id}, /reviews/{id}/label, /api/admin/*, /api/backup/export, /api/meta).

## 9. Android (Phase 2)

- 단일 `:app` 모듈 + 패키지 분리(core/data/domain/feature). MVVM(ViewModel+StateFlow), Hilt, Retrofit+kotlinx.serialization, Room, DataStore, Navigation Compose.
- **지도 추상화(D4)**: domain은 `MapViewport`, `RestaurantMarker` 순수 모델만 사용. Google Maps Compose는 `feature/map`의 구현 디테일로 격리하고, 검색/필터/점수 로직은 지도 SDK 타입을 전혀 참조하지 않는다.
- 하단 네비: 홈/지도/검색/저장/설정. 상세 화면에 점수 기여도 설명 UI. Developer 메뉴(라벨링, 재계산, export).

## 10. 앱 업데이트 (Phase 4)

- 별도 **public release 저장소**(D2)의 GitHub Releases 사용. 토큰 없이 `releases/latest` 조회(24h 스로틀 + ETag).
- 자산: `realmatjip-universal.apk` + `.apk.sha256` + `update-config.json`(minimumVersion/mandatory 포함, 머신러너블은 별도 자산으로 — 릴리즈 노트와 분리).
- 흐름: 버전 비교(SemVer, pre-release/draft 제외) → 다이얼로그 → OkHttp 다운로드(진행률) → SHA-256 검증(불일치 시 설치 금지·파일 삭제) → FileProvider + 사용자 동의 설치.
- 실패 시에도 앱 사용 가능. 자동 설치 금지.
- CI: tag push → test/lint → sign(secrets) → sha256 → release 생성.

## 11. 보안 원칙

1. GLM key는 Backend 환경변수만. APK에 LLM/수집 시크릿 금지 (Maps 키는 패키지+서명 제한 필수).
2. Backend는 Tailscale/LAN 한정. 공인 노출 금지.
3. 업데이트: HTTPS 고정, checksum 불일치 설치 금지, 사용자 동의 없는 설치 금지.
4. Signing keystore: CI 시크릿 + 암호화 백업(분실 시 업데이트 불가).
5. 수집: 공개 API/페이지 준수, 인증 우회 금지, 개인 이용 목적.

## 12. Phase 계획

| Phase | 범위 | 상태 |
|-------|------|------|
| 0 | Scoring 패키지 + fixture(5식당/175리뷰) + 목 분석기 + Weight v1 + Overall A/B + 기여도 분해 + 순위 비교 + 단위테스트 + 가중치 분석 보고 | **완료** (93 테스트, v0.1-phase0, 결정 D7~D12 반영) |
| 1 | FastAPI + SQLite: DB models, schema 관리, fixture seed, list/detail/review API, score 조회, manual label, recalculation, jobs, stats, backup/export, meta | **완료** |
| 2 | Android(Compose): 목록/상세/검색/지도/즐겨찾기/설정/Developer, Room 캐시·즐겨찾기, DataStore 설정, 수동 라벨·재계산 UI. 백엔드·스코어링 변경 없음 | **완료** (단위 44 + 계측 1 테스트, 에뮬레이터 E2E 검증) |
| 3 | 실데이터(Google Places + 수동 import) + GLM 실연동 + 비용 가드 | **완료** (3A Golden P=R=F1=1.000 / 3B 실 API E2E 통과 — 25곳 검색·11곳 Import·LLM 50/50·앱 내 E2E) |
| 4 | GitHub Release 업데이트 + CI | **완료** (SemVer/스로틀/ETag/SHA-256/사용자 동의 설치 + release.yml) |

Phase 0 산출물 위치: `backend/` (순수 파이썬, 의존성 없음), 보고서 `backend/simulation/REPORT.md`.
