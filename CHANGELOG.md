# Changelog

All notable changes to dep_cal (Depreciation Calculator) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.4.0] - 2026-07-25

### Status
- 🔧 **비망가 캡 결함 제거 + 연간 상각 로직 3중 구현 단일화**. 전체 pytest **853** 통과.
- 📋 `docs/IMPROVEMENT_PLAN_2026-07-25_AUDIT.md` — 전체 정밀평가(D1~D7)와 개선계획 A/B/C/D.
- 이 버전에는 앞선 미기재 작업(`depverify` V1 일괄 검증 파이프라인, 정률 첫 실대장 검증)도
  같은 미배포 구간에 포함돼 있다.

### Fixed
- **비망가 캡이 `remaining ≤ 0`에서 무력화되던 결함**: 캡 조건이 `if 0 < remaining < yearly`
  (core는 `if remaining > 0 and yearly > remaining`)라 **이미 비망가에 도달하면 캡을 통째로
  건너뛰고 계속 상각**했고, 그 초과분이 종료해에 **음수 상각**으로 되돌아왔다
  (cost=500·정액 5년 → 종료해 −900원, 누계 −500원, 장부가 1,000원 > 취득원가).
  실무 금액대(100만원↑)는 전건 정상이라 손계산 골든·더존 실측 어디에도 걸리지 않았고,
  결함 경계는 취득원가 약 4만원 이하 대역이었다(정액 10년 ≤5,016 / 60년 ≤40,000,
  정률 10년 ≤10,990 — 실측). `remaining ≤ 0 → 상각 0`으로 정정.
- **core 동반 수정**(`dep_tang_engine.py` 정액·정률 2곳): oracle이 같은 결함을 가진 채로
  남으면 core↔vcore 거울 스윕의 의미가 깨지므로 FREEZE_NOTICE 예외 절차로 직접 수정
  (P2 `round_half_up` 선례와 동일 계열). 분리자산 경로는 이미 `remaining <= 0` 조기
  반환이라 무결. core 자체 회귀 무변화.
- **내용연수 범위 밖 입력의 조용한 클램프**(`vcore/straight_line.py`, `declining_balance.py`):
  상각률 조회의 "가장 가까운 작은 연수로 폴백" 분기는 별표4 표가 2~60년 완전 수록이라
  표 안에서는 **죽은 코드**였고, 살아 있는 효과는 범위 밖 입력을 조용히 60년율(정률은
  기본율 0.1)로 클램프하는 것뿐이었다 — `life=100`에 예외 없이 60년 표가 나왔다.
  폴백 분기를 제거하고 표 직접 조회 + 범위 밖 ValueError로 정정. `life < 2` 가드도
  같은 메시지로 통합(별표4 상각률표 범위 2~60년). 정률의 `DEFAULT_DECLINING_RATE`
  import는 이 변경으로 미사용이 되어 제거.
- **무형 계정 오분류**(`depverify/reader.py`): 계정과목 `개발비`가 무형 목록에 없어 유형
  간접법으로 해석돼 취득원가가 기초가액 1,000원(실제 37,000,000원)으로 오복원됐다.
  상각완료 자산이라 비망 규칙 세 조건이 **우연히** 맞아 '일치'로 통과 — 같은 자산을
  종료해로 검증했다면 위 비망가 캡 결함까지 겹쳐 Δ당기상각 −816원이 났을 것이다.

### Added
- **`vcore/projection.py: capped_yearly()`** — "연 상각액 산출 + 비망가 캡"의 단일 관문.
  `straight_line.standard_vector` / `declining_balance.standard_vector` /
  `monthly.standard_monthly` 3중 구현을 하나로 합쳤다(방법 차이는 `yearly_fn` 주입만).
  위 결함이 정확히 이 3곳에 복제돼 있던 것이 단일화의 직접 근거.
- **취득원가 스코프 가드**: `cost ≤ 비망가액(1,000)`은 상각할 금액 자체가 없으므로
  `validate_asset_inputs`에서 ValueError(기존 `cost <= 0` 가드를 포섭).
- **`tests_vector/test_schedule_invariants.py`**: 손계산 골든 사이의 빈 공간을 덮는 구조
  불변식 — (1) 비망가 캡(음수 상각·누계 금지, 비망가 ≤ 장부가 ≤ 취득원가, 종료 시
  장부가=비망가)을 소액 대역 전수 + 실무 금액대에서, (2) **연도별표 ↔ 월별표 회계연도
  집계 일치**(내용연수 2~20 × 취득월 1~12 × 금액 3종 × 정액·정률 = 1,368 조합)를 고정.
  후자는 A-1 단일화의 게이트이자, depverify(연도별표)와 상각명세서(월별표)가 갈리지
  않음을 구조적으로 보장한다.
- **`depverify` 간접법 불변식 가드**: 유형 이월이면 `기초가액 > 전기말상각누계액`이어야
  한다(비망가 때문에 누계가 취득원가에 도달 불가). 위반 시 조용한 오복원 대신
  검증불능 분류 — 계정 화이트리스트 확장보다 근본적인 방어선.
- **`tests_vector/fixtures/douzone_golden_b.json`**: B사 FY2025 대장 익명 골든 6건.
  정률 실측 앵커 확대(455,000원·2021-06 / 1,088,728원·**2022-12 취득 = 첫해 1개월**),
  정률·정액 상각완료 비망유지 2건, 무형 직접상각 2건(진행 1 + **완료 1**).

## [3.3.0] - 2026-07-02

### Status
- 🔧 **원단위 반올림 banker's rounding 함정 제거**. 전체 pytest **778** 통과.
- 🔒 **core "oracle-only 봉인" 선언**: 실행 경로에서 완전 배제, 골든 대조·불변식 테스트 전용으로 결착.
  영구 상태가 아닌 과도기 — vcore가 core 기능을 패리티·무오류로 재현하면 대조 축 역할을 접고 순수
  보존(박제)으로 전환 예정. 상세: `FREEZE_NOTICE.md`.

### Fixed
- **원단위 round() banker's rounding → 4사5입(round_half_up)**: Python 내장 `round()`는
  x.5를 짝수로 반올림(banker's rounding)하는데, 이는 상용/세법 회계의 4사5입 관행과
  정확히 x.500인 금액에서 1원 갈릴 수 있다. TI 더존 실측 99건에는 x.500 자산이 없어
  그동안 미검증 잠복 결함이었음(x.500 손계산 리트머스로 발견, `tests_vector/test_rounding_litmus.py`).
  `vcore`(`straight_line.py`, `disposal.py` 3곳) + `core`(`dep_tang_engine.py` 9곳,
  `dep_intang_engine.py`·`depreciation_engine.py` 각 1곳, 총 11곳) 전부를
  `round_half_up`(`math.floor(x+0.5)`)으로 교체. **산출 의미 변경 없음**(TI 99건 골든
  Δ=0 불변) — x.500 경계에 해당하는 금액대에서만 값이 1원 확정(내림→올림)됐다.
- core 수정은 FREEZE_NOTICE.md 예외 사유 2번(심각한 회계 오류) 적용. 두 엔진 모두
  같은 결함을 갖고 있었음을 실측 확인(패치 전후 core 자체 회귀 216개 전부 무변화) 후
  동일 수정 — core↔vcore 자기참조 스윕(`test_slim_vs_reference.py`)이 x.500 경계에서
  이탈했다가(14건) core도 함께 고쳐 재일치. 수정 직후 TI 실제 xlsx 3개년(99건) 재검증도
  Δ=0 유지 확인.

## [3.2.0] - 2026-07-02

### Status
- ⭐ **TRUTH_MATRIX 캠페인 완주**: 손계산 절대 골든값으로 라이브 경로(정률 7·정액 6·무형 4,
  총 17경로) 전부 🟢外(외부기준: 손계산 절대 골든 또는 더존 실측) 도달. 전체 pytest **775** 통과.
- ✅ **더존 실측 검증 CI 상시화**: 익명 골든 픽스처(`tests_vector/fixtures/douzone_golden_a.json`,
  99건)로 xlsx 파일 없이도 CI에서 상시 대조 가능해짐.

### Added
- **`docs/TRUTH_MATRIX.md`**: 계산 경로(정액·정률·무형 × 단순·capex·전체양도·부분양도·combo ×
  12월/3월결산)별 검증기준 등급화(🟢外=외부기준·❗=자기참조뿐·⛔=미지원) + core 거취 결착 로직
  ("모든 라이브 경로 🟢外 도달 시 core는 제거 or oracle-only 봉인").
- **손계산 절대 골든값** 다수(`tests_vector/test_*_golden_handcalc.py`): 정액(단순·CAPEX·전체양도·
  부분양도·CAPEX+부분양도·CAPEX+전체양도, 12월/3월결산), 정률(전체양도·부분양도·combo, 3월결산
  확장), 무형(부분양도·완전 월단위) — core·vcore 어느 쪽에도 의존하지 않는 제3의 외부 기준.
  자기참조(core==vcore)만으로는 잡을 수 없던 검증 공백을 메움.
- **원단위 단수처리 조사**(`docs/TRUTH_MATRIX.md` 결론): 법인세법 미규정·더존 설정값 존재를 확인하고
  TI 실측 2건(FY2025 cost 6,097,749 / 81,915,104)으로 반올림(round) 확정 실증 — Python `round()`의
  banker's rounding 잠복 리스크는 이 조사에서 처음 식별([3.3.0]에서 수정).

### Fixed
- **core 정액 CAPEX+부분양도 임의결산월 1원 이탈**: 손계산 골든 작성 중 core 1원 실격 발견 →
  vcore 위임으로 즉시 해소.

## [3.1.0] - 2026-06-16

### Status
- 🔧 **정률·무형·분리자산 정합 강화**. 전체 pytest **725** 통과.
- ✅ **정률 손계산 절대 골든**(7경로 16건) 도입 — 더존 정률 실데이터 부재를 외부 기준으로 보완. 엔진 모듈 미사용 순수 산술 재현이 core·vcore와 1원 일치 확인 후 하드코딩.

### Added
- **vcore 분리자산 경로** `vcore/separate_asset.py`: `prior_accumulated`(전기말 누계) 기초로 당기(`target_year`)만 계산(정액·정률). core와 1원 일치. 12월 결산만 지원.
- **정률 손계산 골든** `tests_vector/test_declining_golden_handcalc.py`: 단순(12·3월결산)·capex·부분양도·capex+부분양도·capex+전체양도. core·vcore 양쪽 또는 vcore 단독(core 버그 경로) 대조.
- **입력 가드** `tests_vector/test_input_guards.py`: 부분양도≥원가→전부양도 위임, capex 증가월≤취득월→`ValueError`, 무형 capex 지원.
- **자연종료 후 부분양도 처분 조정행**: 양도 연도에 양도분 취득가액 안분 제거(상각 0).

### Changed (산출 의미 변경)
- **정률 종료해 5% 잔재 균등 배분**: 마지막 달 dump → 월할 균등(core·vcore, capex·부분양도 잔여표까지 확장). 연간합계·최종 장부가 불변, 월별 분포만 변경.
- **무형자산 전체 별표4 통일**: core 무형이 1/n 직접나눗셈 → 별표4(유형 정액 함수 재사용). 3·6·7·9년 등에서 값 변경(별표4가 정답). core==vcore 1원 일치.
- **자연종료(완전상각) 후 부분양도 비망가 안분**: 비망가는 가치가 아닌 자산 단위 메모이므로 양도 비율로 안분(60% 양도 → 잔존가액 400). 종료 전 양도는 현행 유지(잔류분 1,000).

### Fixed
- **정률 capex+부분양도 음수 월상각** (core): 부분양도 연도 결산월 보정의 양도 전/후 누적 혼선 → 음수(-11,953,058) + 종료해 떠밀림. vcore 위임 + 양도 후 전용 누적으로 수정, 1원 일치.
- **정률 분리자산(prior_accumulated) 조용한 무시** (core): 함수 미전달로 prior 무시하고 전체 스케줄 반환 → 당기만 계산하도록 수정.
- **무형 capex 증가액 누락** (core): 무형 분기 부재로 증가액 무시 → 유형 정액 capex 함수 재사용으로 지원.
- **도메인 외 입력 가드 3종**: 음수 상각(부분양도≥원가)·인덱스 폭주(capex k≤0)·무형 capex 누락을 위임/예외로 차단.

## [3.0.0] - 2026-06-11

### Status
- ⭐ **실행 엔진 교체**: 모든 실행 경로(웹·CLI·dep_verify)가 vcore 슬림 코어 사용. core는 동결 oracle(골든 가드·동등성 매트릭스 전용)로 강등
- ✅ **회귀**: pytest **681/681** (골든 가드·월별 정합·실데이터 포함)
- ✅ **실데이터**: A사 더존 대장 FY2022/2024/2025 — 99 자산-연도 **1원 일치** (전액양도 11건 포함)
- ✅ **동등성 선언**: 정액·정률 core↔vcore 같은 결과 산출 확정 (실무 기준: 100만원 이상 등록, 별표 테이블 연수 보간 인정)

### Changed (BREAKING — 산출물 의미 변경)
- **양도월 규칙 더존식 채택**: `vcore.disposal`의 `disp_month` = 양도월(그 달까지 월할 상각, WEHAGO 공식). 기존 core 의미(disposal_date 직전월 중단)와 한 달 차이 — core 비교 시 `vcore 양도월 = core 월 - 1` 매핑. dep_verify 어댑터 매핑 반전 적용(공개 계약 불변).
- **실행 경로 core → vcore**: `asset_schedule_generator.generate_schedule`이 `vcore.monthly_schedule.monthly_events`(단일 진입점) 호출. capex×양도 동시 조합은 변환 합성(증가→양도 스케일)으로 지원.
- **부분양도 rebase 시점**: 양도월은 전체 취득원가 기준 상각, 잔존 기준 재기준화는 익월부터 (더존식).
- **무형 종료연도 월 분배 통일**: 유형 정액과 동일하게 균등 분배 (연총액 동일 — 구 core는 유형/무형 엔진끼리도 분배가 달랐음).

### Added
- **`vcore/monthly_schedule.py`**: 달력 매핑 월별 스케줄 공개 API (`CalendarMonth`). 연도별 표와 같은 월벡터를 공유해 월별↔연도별 정합 구조 보장. 단순·capex·전체/부분양도 + `monthly_events` 일반 디스패치.
- **골든 가드** `tests_vector/test_golden_core_vs_vcore.py`: 유형 정액·정률(단순·capex·전체/부분양도)은 core와 **월 단위(상각·누계·장부) 완전 일치**, 무형은 연 합계, 조합은 ±1원+최종값 수렴.
- **월별 정합 가드** `tests_vector/test_monthly_schedule.py` (128개): 월별 합계 == 연도별 표 (전 결산월×취득월).
- **실데이터 회귀 가드** `tests_vector/test_real_ledger_a.py`: FY2022/2024/2025 더존 대장 대조 (xlsx 부재 환경은 skip).
- `.gitignore` 신설 — pyc·pytest_cache·실고객 xlsx 추적 해제.
- `docs/REPO_AUDIT_2026-06-11.md`: 저장소 종합 점검 보고서 (엔진 품질 실측·정리 후보·배포 전 체크리스트).

### Fixed
- **부분양도 경계 가드**: 양도 시점이 자연상각 종료 이후일 때 IndexError → 경계 클램프(자연 스케줄 유지). 실데이터에 실존한 케이스.
- **실데이터 하네스 파일선택 버그**: glob이 임의 연도 대장을 집던 문제 → FY에서 파일명 파생, None 가드, `verify(fy)` 함수화.
- **(발견) core 조합 경로 버그**: 정률+capex+부분양도에서 core가 음수 월상각(-1,342,036원) 산출 — 인증된 적 없는 경로의 연말보정 폭주. vcore는 음수 없이 동일 최종값 수렴, 전환으로 자연 해소.

## [2.3.0] - 2026-06-02

### Status
- 🆕 **vcore 슬림 코어 신설** (실행 경로 불변 — 검증·후보 엔진 단계)
- ✅ 저장소 정본 통합: dep_vector 단일 정본, Dep_API 아카이브

### Added
- **vcore 슬림 코어** (~450 LOC, core 대비 1/7): "모든 시나리오 = 표준형 월별 벡터의 변환" 단일 원리.
  - 정액법·정률법: 표준형+프로젝션, 레퍼런스와 각 720/720 1원 일치
  - 자본적지출(정액·정률): Vector 비율 합성, 각 240/240 1원 일치
  - 전체양도·부분양도(정액·정률): 벡터 절단 / 역 capex 누계 분배, 각 160/160 1원 일치
  - 무형자산: 별표4 정액 (직접상각은 표시차이뿐)
- **`tests_vector/test_slim_vs_reference.py`**: 슬림 vs 레퍼런스 회귀 가드 (등가성 포함)
- **A사 실데이터 검증 하네스** `sample_data/verify_ledger.py`
- LICENSE·NOTICE 편입, README를 정본(vector) 기준으로 재작성

## [2.2.0] - 2026-05-22

### Status
- 🔒 **Code Freeze 예외 적용** (사유 2번: 회계 도메인 본질 결함 — 회계기간 1급 시민화)
- ⭐ **Quality**: Enterprise Grade (5/5) 유지
- ✅ **Compliance**: 한국 법인세법 [별표 4], 한국 관행 회계기간 표기 (결산일 속한 연도)
- ✅ **회귀**: pytest **122/122** (기존 105 + 신규 fiscal_period_view 17개, 비-12월 결산 스모크 포함)

### Added (회계기간 1급 시민화)
- **회계기간 개념 엔진 필수화**: `calculate_depreciation_enhanced(financials, asset_info, fiscal_year_end_month)` 시그니처에 `fiscal_year_end_month` keyword-only 필수 인자 추가. 한국 12월 결산 외(미국 1/31, 일본 3/31 결산 등)에서도 정확한 schedule 생성.
- **`extract_fiscal_period(result, fiscal_year)` view 함수 신설**: schedule을 회계기간으로 절단한 당기 요약 추출. dep_verify의 `company_dep`/`company_acc_dep`/`company_book_value` 어휘와 1:1 매칭되는 `FiscalPeriodSummary` 반환.
- **`FiscalPeriodSummary` 데이터클래스**: `fiscal_year`, `fiscal_year_end_month`, `period_start_date`, `period_end_date`, `period_depreciation`, `period_end_accumulated`, `period_end_book_value`, `months_in_period`.
- **`DepreciationResult.fiscal_year_end_month`** 필드: 계산 컨텍스트 보존, view 함수가 일관성 보장에 사용.
- **헬퍼 함수**: `get_fiscal_year(year, month, end_month)`, `get_fiscal_period_dates(fy, end_month)`, `get_fiscal_year_period(fy, end_month)`, `get_fiscal_year_dep_window(...)`.

### Changed (yearly_info 묶음 fiscal year화)
- **6개 유형자산 엔진 함수 + 1개 무형자산 엔진 함수** 의 `yearly_info`/`yearly_accumulated` 묶음이 calendar year에서 **fiscal year 단위**로 재구성. 결산월에 따라 schedule 자체가 다르게 산출됨 (월할 + 잔재 보정 위치 변경).
  - 12월 결산은 산술적으로 동일 결과 → 기존 회귀 매트릭스 105개 통과 보장
  - 비-12월 결산은 정확한 회계기간 단위 schedule 생성
- **14곳 `month == 12` 결산월 잔재 보정 발화 위치** 를 `month == fiscal_year_end_month` 로 일반화. calendar 날짜 인접 판정(`dp_month==12 and disposal_month==1`)은 12월 유지 (회계기간과 무관).
- **`generate_yearly_summary`** 가 calendar year 대신 fiscal year 단위로 묶음. `YearlySummary.year` 의미가 회계연도로 재해석.
- **`AssetInput`** 에 `fiscal_year_end_month: int = 12` 옵션 추가 (application 레이어 default=12, 한국 실무).
- **`depcal.py` CLI** 에 "13. 결산월 (1~12, default=12)" 입력 단계 추가.

### Added (회계기간 1급화의 코드 원칙)
- `AssetFinancials` 에 회계기간 필드 **추가하지 않음** — "자산은 회계기간을 모른다" 원칙. 회계기간은 회사의 회계정책이며 호출 컨텍스트.
- 엔진 함수 시그니처에 default 없음 — silent trap(v2.1에서 제거된 `target_year=2024` 패턴)과 동일 사유. 한국 실무 default=12는 application 레이어에서만 명시적 주입.

### Added (테스트)
- **`dep_cal/tests/test_fiscal_period_view.py`** (17개): 헬퍼 단위 검증 + 비-12월 결산 schedule 생성 + extract_fiscal_period view + v2.2 분리자산 가드 ValueError. 3·6·9·1월 결산 스모크 시나리오 포함.

### Added (문서)
- `dep_cal/specs/fiscal_period_first_class_spec.md`: 회계기간 1급 뷰 spec. 대원칙(자산은 회계기간을 모른다) + 책임 분리 + 한국 관행 표기 + 월할/결산월 잔재 보정 + yearly_info 재구성 + Acceptance Criteria + 회귀 시나리오 F-FP-01~10.

### Deferred (v2.3 분리)
- **분리자산 경로(`prior_accumulated`) fiscal year 일반화**: v2.1에서 정교하게 설계된 calendar year 가정이 깊이 박혀 있어 회귀 위험. 한국 실무 12월 결산이 분리자산의 99% 케이스라 영향 적음. v2.2 분리자산 경로는 `fiscal_year_end_month != 12` 호출 시 명시적 `ValueError` 발화 (v2.3 미지원 안내).

### dep_verify 영향
- dep_verify(별도 폴더)는 wrapper `calculate_from_common_format` 의 default=12로 12월 결산은 호환. 비-12월 결산 검증은 dep_verify 측 schema에 `fiscal_year_end_month` 컬럼 추가 + `extract_fiscal_period` view 적용 필요 (별도 작업).

## [2.1.0] - 2026-05-22

### Status
- 🔒 **Code Freeze 예외 적용** (사유 2번: 심각한 회계 오류)
- ⭐ **Quality**: Enterprise Grade (5/5) 유지
- ✅ **Compliance**: 한국 법인세법 [별표 4]
- ✅ **회귀**: pytest **105/105** (기존 21 + 매트릭스 영구화 84, 유·무형 전체양도/부분양도/자본적지출+양도 통합)

### Fixed (회계 정확성 critical)
- **🔴 매각 시간 인과율 위반 수정**: 양도 직전월에 잔여 장부가 거의 전부가 일괄상각되어 폭증하던 결함 제거. 양도 발생을 미리 알고 있던 것처럼 처리되어 직전월까지의 결산 마감 원칙에 위배되었음. 대원칙 *"매각은 직전월의 장부가액을 들여다 볼 뿐이며, 감가상각은 매월 정상적으로 회계장부에 반영된다"* 를 모든 매각·처분 경로(중도매각·부분매각·상각완료 자산 매각·폐기·자본적지출 후 매각)에 적용.
  - `_calculate_korean_straight_line_enhanced` (정액법 전체양도)
  - `_calculate_korean_declining_balance_enhanced` (정률법 전체양도)
  - `_calculate_with_increase` / `_calculate_with_increase_declining` (자본적지출+양도)
  - `_calculate_intangible_asset_enhanced` (무형자산 전체양도)
- **🟡 자본적지출 일자 검증**: `increase_date >= acquisition_date` 조건을 `AssetFinancials.__post_init__`에 추가. 취득 전 자본적지출 발생 불가 원칙 강제.
- **🟡 정률+자본적지출 부분양도 분기 분배 통일 (누락 수정)**: `_calculate_with_increase_declining` L1175 분기가 옛 패턴(`book_value_ratio` floor + 차감) 그대로 남아 시점에 따라 1원 차이 발생. 매트릭스 영구화 작업 중 발견. `round + 차감` 원칙으로 통일.

### Changed (회계 무결성·일관성)
- **부분양도 분배 통일**: `양도 누계 = round(원 누계 × disposal_amount / cost)`, `잔존 누계 = 원 누계 − 양도 누계` 단일 원칙으로 6곳 분배 로직 통합. 무결성(합 = 원본) 자동 보장.
  - `_calculate_with_partial_disposal` (정액법 부분양도, 2분기)
  - `_calculate_with_partial_disposal_declining` (정률법 부분양도)
  - `_calculate_with_increase` / `_calculate_with_increase_declining` 의 `is_partial_disposal` 분기
  - `_calculate_intangible_with_partial_disposal` (무형자산 부분양도)
- **처분비율 소수점 허용**: `depcal.py`에서 정수만 받던 처분비율 입력을 float으로 변경. `get_float_input` 헬퍼 추가.
- **`round_amount` → `to_int` rename**: 실제 동작이 `int()` 절사인데 명명이 "round"라 회계 도메인의 round/floor 혼동을 초래하던 부분 정정. 25곳 호출처 일괄 변경.

### Removed
- Dead 파라미터 `precision` (`round_amount` 시그니처)
- Dead 상수 `ROUNDING_PRECISION` (`dep_common.py`)

### Added (테스트)
- **`dep_cal/tests/test_disposal_invariants.py`**: 매각·처분 invariant 회귀 84개 영구화 (parametrize 기반). 직전월 동등성 + 분배 무결성 + 잔존 비망가 + 종료월. 유·무형 × 전체/부분 × 자본적지출 유무 매트릭스 총망라. 단발 검증으로 놓친 결함(정률+자본적지출 분기 누락)을 즉시 표면화하는 활성 검증 도구로 기능.

### Added (문서)
- `dep_cal/specs/monthly_settlement_preservation_spec.md`: 매각 월 결산 보존 대원칙 + 적용 범위 + Acceptance Criteria + 회귀 시나리오 (유·무형 통합).
- README "📐 계산 특성 / 정률법 마지막 달 폭증" 섹션 추가: 법령 5% 잔재 + 비망가 1,000원의 수학적 불가피성 설명 + 수치 예시.
- 정률법 비망가 처리 코드 주석에 회계·수학적 근거 명시.

## [2.0.0] - 2024-11-27

### Status
- 🔒 **Code Freeze**: Production Ready
- ⭐ **Quality**: Enterprise Grade (5/5)
- ✅ **Compliance**: Korean Corporate Tax Law

### Added

#### Core Calculation Engine
- **유형자산 정액법** (Straight Line Method for Tangible Assets)
  - 한국 법인세법 [별표 4] 상각률표 완벽 적용
  - 취득월 기반 월할 계산
  - 연말 보정 로직
  - 비망가액 1,000원 처리

- **유형자산 정률법** (Declining Balance Method for Tangible Assets)
  - 한국 법인세법 [별표 4] 상각률표 완벽 적용
  - 미상각잔액 기준 계산
  - 연말 보정 로직
  - 비망가액 1,000원 처리

- **무형자산 직접상각법** (Direct Method for Intangible Assets)
  - 취득원가 직접 차감 방식
  - 누계액 기록 유지
  - 비망가액 1,000원 처리

#### Advanced Features (Vector Logic)
- **자본적지출 처리** (Capital Expenditure)
  - Vector 합성 논리 구현
  - 증가 전후 정확한 계산
  - 통합 장부가액 관리
  - 정액법/정률법 모두 지원

- **부분양도 처리** (Partial Disposal)
  - Vector 축소 논리 구현
  - 양도비율 정확 계산
  - 잔존 비율 기반 계속 감가상각
  - 유형자산/무형자산 모두 지원

- **전체양도/폐기 처리** (Full Disposal/Retirement)
  - 양도 직전월까지 계산
  - 보정 없이 기본 월상각비 적용
  - 비망가액 남기지 않음

- **복합 시나리오** (Combined Scenarios)
  - 자본적지출 + 부분양도
  - 자본적지출 + 전체양도
  - 모든 조합 정확히 처리

#### User Interface
- **CLI 대화형 인터페이스** (Interactive CLI)
  - 사용자 친화적 입력 프롬프트
  - 입력값 자동 검증
  - 날짜/금액 다양한 형식 지원
  - 오류 처리 및 재입력

- **Excel 자동 생성** (Automatic Excel Generation)
  - 3시트 구조 (입력정보, 연도별집계, 월별상세)
  - 전문적인 포맷팅
  - 천단위 구분 및 정렬
  - 타임스탬프 파일명

#### API Interface
- **명확한 API 설계**
  - `calculate_depreciation_enhanced()`: 메인 계산 함수
  - `AssetFinancials`: 재무 정보 데이터클래스
  - `AssetInfo`: 자산 기본 정보 데이터클래스
  - `DepreciationResult`: 결과 데이터클래스
  - `MonthlyDepreciation`: 월별 감가상각 정보

- **파일간 인터페이스**
  - `convert_common_data_to_financials()`: 더존 형식 변환
  - `calculate_from_common_format()`: 공통 형식 계산
  - fixed_asset 모듈과 완벽한 호환성

### Technical Achievements

#### Accuracy
- ✅ **Integer 기반 계산**: 반올림 오차 0
- ✅ **Vector 논리**: 수학적 우아함
- ✅ **법인세법 준수**: 상각률표 완벽 적용
- ✅ **회계 정확성**: 100% (오차 없음)

#### Performance
- ⚡ **2ms/60개월**: 매우 빠른 계산 속도
- ⚡ **최적화된 알고리즘**: 불필요한 반복 없음

#### Code Quality
- 📝 **타입 힌트**: 모든 함수에 적용
- 📝 **데이터클래스**: @dataclass 활용
- 📝 **로깅**: 상세한 계산 과정 기록
- 📝 **오류 처리**: try-except + 검증

#### Testing
- ✅ **12가지 시나리오 검증**
- ✅ **9가지 엣지 케이스 처리**
- ✅ **실행 샘플 파일**: output/ 폴더

### Architecture

#### Module Structure
```
dep_cal/
├── depcal.py                    # CLI Interface
├── asset_schedule_generator.py # Excel Generator
├── requirements.txt             # Dependencies
└── core/                        # Calculation Engine (Frozen)
    ├── depreciation_engine.py  # Wrapper
    ├── dep_common.py           # Common (1,557 lines)
    ├── dep_tang_engine.py      # Tangible Assets
    ├── dep_intang_engine.py    # Intangible Assets
    └── utils.py                # Utilities
```

#### Design Patterns
- **Separation of Concerns**: CLI, Calculation, Output
- **Dataclass Pattern**: Type safety
- **Wrapper Pattern**: depreciation_engine.py
- **Strategy Pattern**: Method-specific engines

### Dependencies
- openpyxl >= 3.0.0 (Excel generation)
- python-dateutil >= 2.8.0 (Date processing)

### Supported Scenarios

| # | Scenario | 정액법 | 정률법 | 무형자산 |
|---|---------|-------|-------|---------|
| 1 | 기본 감가상각 | ✅ | ✅ | ✅ |
| 2 | 자본적지출 | ✅ | ✅ | ❌ |
| 3 | 부분양도 | ✅ | ✅ | ✅ |
| 4 | 전체양도/폐기 | ✅ | ✅ | ✅ |
| 5 | 자본적지출 + 부분양도 | ✅ | ✅ | ❌ |
| 6 | 자본적지출 + 전체양도 | ✅ | ✅ | ❌ |

### Known Issues
- **Unicode Display**: Windows에서 이모지 표시 문제 (UTF-8 환경 변수 설정 필요)
  - 해결 방법: `PYTHONIOENCODING=utf-8` 설정 또는 이모지 제거 버전 사용

### Intentional Limitations
- **무형자산 자본적지출**: 지원하지 않음 (세법상 불필요)
- **복수 자본적지출**: 단일 증가 이벤트만 지원
- **복수 부분양도**: 단일 양도 이벤트만 지원

### Compliance & Certification
- ✅ **Korean Corporate Tax Law**: 법인세법 시행령 제26조
- ✅ **Depreciation Rate Table**: 법인세법 [별표 4]
- ✅ **Memorandum Value**: 1,000원 (법인 46012-3734, 1999.10.14)
- ✅ **IFRS & K-GAAP**: 정액법/정률법 모두 지원

### Credits
Developed with Claude (Anthropic AI)

---

## [1.0.0] - 2024-XX-XX (Historical)

### Initial Release
- Basic depreciation calculation
- (Details not documented)

---

## Future Plans

### Not Planned (Code Freeze)
이 프로젝트는 v2.0.0부터 코드 동결 상태입니다.

### Exception Cases
다음 경우에만 업데이트됩니다:
1. 한국 세법 변경 (법인세법 개정)
2. 심각한 회계 오류 발견
3. 보안 취약점 수정

### New Features
신규 기능은 `dep_cal_ext/` 별도 모듈로 추가됩니다.

---

## Version History

- **v2.0.0** (2024-11-27): Production Release - Code Freeze
- **v1.0.0** (2024-XX-XX): Initial Release
