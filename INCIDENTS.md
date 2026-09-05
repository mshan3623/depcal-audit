# 사건 및 결함 등록부 (INCIDENTS)

이 파일이 있는 이유는 하나다: **같은 패턴이 두 번째로 나타났을 때 그것을 '두 번째'라고 부를 수
있기 위해서.** 개별 결함은 CHANGELOG가 기록한다. 여기 적는 것은 *패턴*이다 — 어떤 종류의 실수가
반복되는지, 그리고 그 종류를 다시 못 하게 막은 자리가 어디인지.

한 결함을 고치는 것과 그 결함의 *계열*을 못 나오게 막는 것은 다른 일이다. 국소 수정만 반복하면
같은 계열이 다른 파일에서 다시 나온다 — INC-01 → INC-04, INC-03 → INC-05가 실제로 그랬다.

**기입 규칙**
- 1건이라도 산출물 숫자가 틀렸거나 검출 채널이 없었던 것으로 밝혀지면 등록한다.
- **1차/2차**는 패턴 기준이다. 2차면 국소 수정으로 닫지 말고 구조 처방을 요구한다.
- **봉인 위치**는 "다시 나오면 실패하는 테스트"의 이름이다. 문서가 아니라 실행되는 것이어야 한다.
- 봉인이 없으면 `미봉인`이라고 적는다. 비워두지 않는다.

## 등록부

| ID | 발생일 | 증상 및 결함 요약 | 1차/2차 | 조치 유형 | 재발 방지 봉인 위치 |
|---|---|---|---|---|---|
| INC-01 | 2026-07-02 | `round()` banker's rounding → x.500 자산 1원 오차 | 1차 (패턴 **원단위 산술**) | 구조 — `round_half_up` 단일화, core 동반 | `test_rounding_litmus` |
| INC-02 | 2026-07-25 | 비망 캡 `0 < remaining < yearly` 판단이 3곳에 중복 | 1차 (패턴 **N중 구현**) | 구조 — `capped_yearly` 단일 관문 | `test_schedule_invariants` |
| INC-03 | 2026-08-11 | 파서 2벌 → 같은 대장에서 거짓 일치 + 거짓 불일치 동시 발생 | 1차 (패턴 **판단 2벌**) | 구조 — `classify_asset` 1벌, 두 저장소가 공유 | `FITNESS_AUDIT_2026-08-11.md` §8-10 |
| INC-04 | 2026-09-03 | float 상각률 곱셈이 정확한 정수 결과를 1원 하향 (정액 9연수·정률 8연수). 2026-07-25 D8이 "실무 영향 없음"으로 닫았던 오판 | **2차** (INC-01 계열) | 구조 — 별표4 1000분율 정수 산술 관문 2개 | `test_integer_arithmetic_litmus` (272건) |
| INC-05 | 2026-09-03 | 엑셀 시트1 「처분 제거액」이 vcore와 다른 산식(직전월·`int()` 절사). 같은 파일 안에서 시트1↔시트3 불일치 | **2차** (INC-03 계열) | 구조 — `disposal.disposal_split` 1벌(3벌 통합) | `test_depreciation_scenarios.py::_assert_excel_matches_vcore` |
| INC-06 | 2026-09-03 | 엑셀 연도별집계가 달력연도 / CLI 전체양도+capex가 부분양도로 오해석돼 양도 후 30개월 상각 지속 | 1차 (패턴 **생성기가 vcore 밖에서 재계산**) | 구조 — 생성기를 vcore 벡터의 소비자로, 전부양도 판정 `is_full_disposal` 1곳 | `test_scenario_13_non_december_fiscal_year_end`, `test_capex_full_disposal_encoded_as_original_cost_is_rejected` |
| INC-07 | 2026-09-03 | 공허 통과 테스트 — 날짜 가드를 검사한다면서 `asset_code` 누락으로 다른 예외에 걸려 GREEN | 1차 (패턴 **테스트가 대상에 닿지 않음**) | 국소 + 그 아래 결함(INC-08) 노출 | `tests_vector/test_input_guards.py` (asset_code 보강) |
| INC-08 | 2026-09-05 | core `parse_date_safe`가 어떤 오류든 2020-01-01 반환 → 상위 날짜 가드가 죽은 코드. `'2020-13-99'`가 `calculation_success=True`에 2,400,000원 산출 | 1차 (패턴 **조용한 기본값**) | 구조 — 예외 전파, 도메인 오류 삼킴 금지 4계열 | `test_phase4_edge_cases.py::test_core_rejects_unparseable_dates_instead_of_defaulting_to_2020` |
| INC-09 | 2026-09-03 | depverify 대장 합계행을 통제합계로 쓰지 않음 — 자산행이 구조행으로 오판돼 사라져도 검출 채널이 **전무** | 1차 (패턴 **완전성 채널 부재**) | 구조 — `ControlTotal` 대사 게이트, 종료코드 1 | `test_depverify_completeness.py::test_control_total_detects_dropped_asset_row` |
| INC-10 | 2026-09-03 | depverify 무형 양도·상각완료 후 양도가 **항상 '차이'** — 비교식이 간접법(유형) 전제 | 1차 (패턴 **거짓 경보**) | 국소 — 실측 앵커 확보 전까지 '검증불능(비교식미확립)' fail-closed | `test_depverify_completeness.py::test_intangible_disposal_is_unverifiable_not_a_difference` |
| INC-11 | 2026-09-05 | 정액 41년 등 12개 연수에서 상각이 내용연수 종료 **전에** 끝나고 vcore가 상각액 0인 꼬리 행을 붙임. 분리자산 경로는 같은 상황에서 `[]` | — (**미판정**) | 미결 — 실측 앵커 0건이라 어느 쪽이 옳은지 코드가 정하지 못함 | `test_golden_handcalc_other_lives.py::test_straight_line_41_years_completes_before_useful_life_ends` (현 동작을 굳히지 않고 사실만 고정) |

## 반복된 패턴 — 다음에 볼 자리

- **원단위 산술** (INC-01 → INC-04): 금액 계산에 float가 끼면 1원이 조용히 사라진다. 새 산식을
  넣을 때 정수로 쓸 수 있는지 먼저 본다.
- **판단 2벌** (INC-03 → INC-05): 같은 판단이 두 곳에 있으면 언젠가 갈린다. "여기서도 한 번 더
  계산한다"가 보이면 그 자체가 결함 신호다.
- **조용한 기본값** (INC-07 → INC-08): 예외를 삼키고 그럴듯한 값을 돌려주는 코드는, 그 값이
  틀렸다는 사실까지 함께 숨긴다. `except`가 값을 돌려주면 의심한다.
- **완전성 채널 부재** (INC-09): 완전성은 방향이 반대다. 기록을 뒤져서는 '빠진 것'이 안 나온다.
  외부에서 온 통제합계와 맞추는 길이 있는지 본다.

## 미해소 게이트

- **실대장 표본 5~10개사** — 표 엔트리별 실측이 내용연수 5년 하나뿐이다. INC-04가 5년 **밖에서만**
  발화한 것이 이 빈칸의 결과다. 표본이 들어오면 7·9·14·41년 자산을 우선 대조한다.
  (`docs/IMPROVEMENT_PLAN_2026-09-05.md` 트랙 B2)
- **INC-11 판정** — 위 표본이 확보되면 그 자리에서 결정한다.
