# Code Freeze Notice

## Status: 🔒 Oracle-Only 봉인 (과도기 — 박제 전 단계)

**Effective Date**: 2024-11-27
**Current Version**: 3.3.0(dep_vector) (v2.2.0 + 원단위 round_half_up 수정, 2026-07-02)
**Status**: Oracle-Only 봉인 — vcore 회귀 대조 축 전용, 실행 경로 완전 배제

---

## What is Code Freeze?

이 모듈은 **프로덕션 준비 완료** 상태로, 다음 사유 외에는 **코드 수정이 금지**됩니다:

1. **심각한 회계 오류**: 계산 결과의 정확성에 영향을 주는 버그 발견 시
2. **보안 취약점**: 보안 패치가 필요한 경우

(과거 사유 "한국 세법 변경"은 2026-07-02 oracle-only 봉인 선언으로 제외 — 아래 참조.
세법 변경은 `vcore/`에만 반영하고, core 대조 테스트는 그 시점 상각률표 기준 스냅샷으로 그대로 둔다.)

---

## Oracle-Only 봉인 선언 (2026-07-02)

`docs/TRUTH_MATRIX.md` 결착 로직 발동(모든 라이브 경로가 vcore 외부기준 검증 완료) 시점에
core의 거취를 결착한다.

- **core는 실행 경로에서 완전 배제**된다. 라이브 의존은 `dep_common`의 상수·타입
  (`STRAIGHT_LINE_RATES`, `DECLINING_BALANCE_RATES`, `DepreciationMethod`,
  `AssetFinancials`, `AssetInfo` 등 데이터클래스/enum)뿐이고, 계산 로직 호출은
  `tests_vector/`·`tests/`의 골든 대조·불변식 테스트에만 남는다.
- `core/dep_intang_engine.py`는 실행 경로 미사용(무형자산은 `vcore/intangible.py`가
  유형 정액 슬림을 재사용) — 불변식 테스트(`tests/test_disposal_invariants.py`)가
  직접 호출하므로 코드는 보존하되 **테스트 전용**으로 취급한다.
- 세법 변경 시 수정은 `vcore/`에만 반영한다. core 대조 테스트는 그 시점 상각률표
  기준 스냅샷으로 동결.

**이 봉인은 영구 상태가 아니라 과도기다.** 장기 목표(사용자 방향 결정, 2026-07-02) —
vcore가 core의 모든 기능을 병렬·독립적으로 오류 없이 재현한다고 확인되면(패리티는
사실상 충족, 무오류 확인은 core-vcore 상호대조로 계속 진행 중), core는 대조 축
역할 자체를 접고 순수 보존(박제)으로 넘어간다. 그 전까지는 core-vcore 이탈이
발견될 때마다 어느 쪽이 확실히 틀렸는지 판정해 고친다(제거하고 우회하지 않는다) —
2026-07-02 원단위 round() 수정(아래 v3.3.0)이 그 실례다.

---

## v3.3.0(dep_vector) Code Freeze 예외 적용 (2026-07-02)

위 사유 2번(심각한 회계 오류)에 해당하는 변경 사항. `dep_tang_engine.py`·`dep_intang_engine.py`·
`depreciation_engine.py`의 원단위 `round()` 11곳이 Python 내장 banker's rounding(x.5→짝수)을
그대로 쓰고 있었음을 발견 — 상용/세법 4사5입 관행과 정확히 x.500인 금액에서 1원 갈릴 수 있는
미검증 잠복 결함이었다(TI 실측 99건엔 x.500 자산이 없어 그동안 미발견). `dep_common.round_half_up`
로 전부 교체. 패치 전후 core 자체 회귀(`tests/` 216개) 전부 무변화로 안전성 확인 후 적용 —
상세는 `CHANGELOG.md` [3.3.0] 참조.

**주의**: 이 수정이 바로 위 "Oracle-Only 봉인 선언"이 명시한 원칙(core 자체의 확실한
결함이 발견되면 봉인보다 정확성 수정 우선)의 첫 실례다.

---

## v2.2.0 Code Freeze 예외 적용 (2026-05-22)

위 사유 2번(회계 도메인 본질 결함 — 회계기간 1급 시민화)에 해당하는 변경 사항. 회계 도메인 사용자 검증 + **pytest 122/122** (기존 105 + 신규 비-12월 결산 17개) 회귀 모두 통과.

### 회계 도메인 1급 시민화

- **회계기간(fiscal year) 개념 엔진 필수화**: `calculate_depreciation_enhanced(financials, asset_info, fiscal_year_end_month)` 시그니처에 결산월을 필수 keyword 인자로. 한국 12월 결산 외(미국 1월, 일본 3월 등) 정확한 schedule 산출. 대원칙 *"자산은 회계기간을 모른다. 회계기간은 회사의 회계정책이며 호출 컨텍스트"* 적용.
- **연말 보정 발화 위치 일반화**: 14곳 `month == 12` 결산월 잔재 보정 의미를 `month == fiscal_year_end_month` 로 일반화. calendar 날짜 인접 판정은 12월 유지.
- **yearly_info 묶음 fiscal year화**: 6개 유형자산 엔진 함수 + 1개 무형자산 엔진 함수의 회기 묶음을 calendar year → fiscal year 단위로 재구성. 비-12월 결산에서 부분 연도(취득·처분·내용연수 마지막) 상각개월수가 정확하게 회계기간 기준으로 산출.
- **`extract_fiscal_period(result, fiscal_year)` view 함수 신설**: schedule을 회계기간 단위로 절단한 당기 요약 추출. dep_verify의 `company_dep`/`company_acc_dep`/`company_book_value` 어휘와 1:1 매칭.

### 영향 함수

- 유형자산 (dep_tang_engine.py): `_calculate_korean_straight_line_enhanced`, `_calculate_korean_declining_balance_enhanced`, `_calculate_with_increase`, `_calculate_with_increase_declining`, `_calculate_with_partial_disposal`, `_calculate_with_partial_disposal_declining`
- 무형자산 (dep_intang_engine.py): `_calculate_intangible_asset_enhanced`, `_calculate_intangible_with_partial_disposal`

### v2.3로 분리

- **분리자산 경로(`prior_accumulated`) fiscal year 일반화**: v2.1에서 정교히 설계된 calendar year 가정이 깊이 박혀 회귀 위험. 한국 12월 결산이 분리자산의 99% 케이스라 실무 영향 적음. v2.2 분리자산 경로는 `fiscal_year_end_month != 12` 호출 시 명시적 `ValueError` 발화 (v2.3 미지원 안내).

### 호환성

- `calculate_from_common_format` wrapper: `fiscal_year_end_month=12` default (한국 실무) — dep_verify 등 외부 호출자 호환.
- 엔진 직접 호출자(`asset_schedule_generator.py`): `fiscal_year_end_month` 명시 주입 (default=12).
- depcal.py CLI: "13. 결산월 (1~12, default=12)" 입력 단계 추가.
- 12월 결산 회귀 매트릭스 105개 동일 결과 보장 (월할 산술 동등성).

### 신규 spec / 문서

- `dep_cal/specs/fiscal_period_first_class_spec.md` — 대원칙, 책임 분리, 한국 관행, yearly_info 재구성, Acceptance Criteria, 회귀 시나리오 F-FP-01~10.

### 테스트

- **`dep_cal/tests/test_fiscal_period_view.py`** (17개): 헬퍼 단위 + 비-12월 결산 스모크(3·6·9·1월) + extract_fiscal_period view + v2.2 분리자산 가드.

---

## v2.1.0 Code Freeze 예외 적용 (2026-05-22)

위 사유 2번(심각한 회계 오류)에 해당하는 변경 사항. 회계 도메인 사용자 검증 + **pytest 105/105** (기존 21 + 매트릭스 영구화 84) 회귀 모두 통과.

### 회계 정확성 critical 수정

- **🔴 매각 시간 인과율 위반 수정**: 양도 직전월에 비망가 잔액상각이 잘못 발화하던 결함 제거. 대원칙 "매각은 직전월의 장부가액을 들여다 볼 뿐, 감가상각은 매월 정상적으로 회계장부에 반영된다"를 모든 매각·처분 경로(중도매각·부분매각·상각완료 자산 매각·폐기·자본적지출 후 매각)에 적용. 영향 함수: `_calculate_korean_straight_line_enhanced`, `_calculate_korean_declining_balance_enhanced`, `_calculate_intangible_asset_enhanced`, `_calculate_with_increase`, `_calculate_with_increase_declining`, `_calculate_intangible_with_partial_disposal`.
- **🟡 자본적지출 일자 검증**: `increase_date >= acquisition_date` 조건을 `AssetFinancials.__post_init__`에 추가.
- **🟡 정률+자본적지출 부분양도 분기 누락 수정**: `_calculate_with_increase_declining` L1175 분기가 옛 패턴(`book_value_ratio` floor + 차감) 그대로 남아 시점에 따라 1원 차이 발생. 매트릭스 영구화 작업 중 발견·즉시 수정. `round + 차감` 원칙으로 통일.

### 회계 무결성·일관성

- **부분양도 분배 통일**: 양도 누계 = `round(원 누계 × disposal_amount / cost)`, 잔존 = 차감. 6곳 분배 로직을 단일 원칙으로 통합 (유·무형 부분양도 + 자본적지출+부분양도).
- **처분비율 소수점 허용**: `depcal.py`에서 정수만 허용하던 처분비율을 float으로 변경 (코어 엔진은 기존부터 float 처리).

### 명명·구조 정리

- `round_amount` → `to_int` 명명 정정 (실제 동작이 `int()` 절사라 명명 오류 시정). dead `precision` 파라미터 및 `ROUNDING_PRECISION` 상수 제거.

### 테스트

- **`dep_cal/tests/test_disposal_invariants.py`**: 매각·처분 invariant 회귀 84개 영구화. 직전월 동등성 + 분배 무결성 + 잔존 비망가 + 종료월. parametrize 기반. 향후 결함 즉시 표면화.

### 문서

- **신규 spec**: `dep_cal/specs/monthly_settlement_preservation_spec.md` — 대원칙 + 적용 범위 + Acceptance Criteria.
- **신규 메모리 문서**: 부분양도 시 감가상각 종료 자산의 비망가 처리 결정 근거.
- **정률법 마지막 달 폭증 문서화**: README + 코드 주석 (법령 5% 잔재 + 비망가 1,000원의 수학적 불가피).

---

## Why Code Freeze?

### 1. 검증 완료 (Verified)

- ✅ **12가지 시나리오 테스트** 모두 통과 (tests/test_depreciation_scenarios.py)
- ✅ **한국 법인세법 준수** (법인세법 시행령 제26조, [별표 4])
- ✅ **회계 정확성 100%** (Integer 기반 계산, 반올림 오차 0)
- ✅ **Vector 논리 구현** (자본적지출, 부분양도)

### 2. 안정성 보장 (Stability)

- 이 모듈을 기반으로 다른 모듈들이 개발되었습니다
- 코드 변경 시 의존 모듈들의 예상치 못한 오류 발생 가능
- 안정적인 기반 유지 필요

### 3. 법적 준수 (Compliance)

- 한국 법인세법 기반 계산 로직
- 세법 변경 시에만 업데이트 필요
- 임의 수정 시 법적 준수성 위험

---

## Core Files (Frozen)

다음 파일들은 **절대 수정 금지**입니다:

```
dep_cal/core/
├── dep_common.py          # 공통 데이터 구조 및 유틸리티
├── dep_tang_engine.py     # 유형자산 감가상각 계산 엔진
├── dep_intang_engine.py   # 무형자산 감가상각 계산 엔진
├── depreciation_engine.py # 통합 계산 Wrapper
└── utils.py               # 공통 유틸리티 함수
```

---

## Supported Scenarios (v2.0.0)

| # | 시나리오 | 정액법 | 정률법 | 무형자산 |
|---|---------|-------|-------|---------|
| 1 | 기본 감가상각 | ✅ | ✅ | ✅ |
| 2 | 자본적지출 | ✅ | ✅ | ❌ |
| 3 | 부분양도 | ✅ | ✅ | ✅ |
| 4 | 전체양도/폐기 | ✅ | ✅ | ✅ |
| 5 | 자본적지출 + 부분양도 | ✅ | ✅ | ❌ |
| 6 | 자본적지출 + 전체양도 | ✅ | ✅ | ❌ |

**총 12가지 시나리오 완벽 지원**

---

## What Can Be Modified?

다음 파일들은 **사용자 편의를 위해 수정 가능**합니다:

### 1. CLI Interface (User-facing)
- `depcal.py`: CLI 사용자 인터페이스
- 입력 프롬프트 개선, 메시지 수정 가능
- **단, core 계산 로직은 절대 수정 금지**

### 2. Excel Generator (Output)
- `asset_schedule_generator.py`: Excel 파일 생성기
- 출력 포맷, 시트 구조 수정 가능
- **단, 계산 로직은 절대 수정 금지**

### 3. Documentation
- `README.md`: 프로젝트 설명
- `CHANGELOG.md`: 버전 히스토리
- 문서는 언제든지 개선 가능

### 4. Tests
- `tests/`: 테스트 코드
- 테스트 추가/개선 가능
- **단, 기존 테스트 삭제 금지**

---

## Exception Handling Process

만약 코드 수정이 **절대 필요한 경우**:

### Step 1: 이슈 확인
- 세법 변경인가?
- 회계 오류인가?
- 보안 취약점인가?

### Step 2: 백업 생성
```bash
# 전체 폴더 백업
zip -r dep_cal_backup_YYYYMMDD.zip dep_cal/
```

### Step 3: 수정 및 테스트
```bash
# 테스트 실행
python tests/test_depreciation_scenarios.py

# 12가지 시나리오 모두 통과해야 함
```

### Step 4: 버전 업데이트
- `core/__init__.py`의 `__version__` 업데이트
- `CHANGELOG.md`에 변경 사항 기록

---

## New Features

신규 기능이 필요한 경우:

### Option 1: Extension Module (권장)
```
dep_cal_ext/
├── extended_scenarios.py  # 신규 시나리오
├── custom_logic.py         # 커스텀 로직
└── README.md
```

### Option 2: Wrapper Layer
```python
# custom_wrapper.py
from dep_cal.core.depreciation_engine import calculate_depreciation_enhanced

def calculate_with_custom_logic(...):
    # dep_cal은 그대로 사용
    result = calculate_depreciation_enhanced(...)

    # 추가 로직 적용
    modified_result = apply_custom_logic(result)

    return modified_result
```

---

## Contact & Issues

- **버그 리포트**: GitHub Issues (if applicable)
- **세법 변경 확인**: 국세청 법령정보 (https://www.nts.go.kr)
- **문의**: 프로젝트 관리자

---

## Version History

- **v3.3.0(dep_vector)** (2026-07-02): Oracle-Only 봉인 선언 + 원단위 round_half_up 수정. Code Freeze 사유 2번 적용.
- **v2.2.0** (2026-05-22): 회계기간(fiscal year) 1급 시민화 — 비-12월 결산 지원. Code Freeze 사유 2번 적용.
- **v2.1.0** (2026-05-22): 회계 정확성 maintenance (매각 시간 인과율 수정, 부분양도 분배 통일, 매트릭스 84개 영구화 등). Code Freeze 사유 2번 적용.
- **v2.0.0** (2024-11-27): Production Release - **Code Freeze**
- **v1.0.0** (2024-XX-XX): Initial Release

---

## Final Notes

> "If it ain't broke, don't fix it."

이 모듈은 **완벽하게 작동**하며, **법적으로 준수**되고, **철저히 검증**되었습니다.
불필요한 수정은 오히려 **위험**을 초래할 수 있습니다.

**안정성을 최우선으로** 생각해주세요.

---

**Effective Date**: 2024-11-27
**Last Updated**: 2026-07-02 (v3.3.0(dep_vector) — Oracle-Only 봉인 선언)
**Status**: Active (Oracle-Only 봉인, 박제 전 과도기)
