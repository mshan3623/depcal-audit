# -*- coding: utf-8 -*-
# Copyright 2026 Han Myeong Su
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
감가상각 계산 시나리오 테스트
Depreciation Calculation Scenario Tests

12가지 핵심 시나리오에 대한 자동 테스트
pytest 및 직접 실행 모두 지원
"""

import sys
import os
from datetime import datetime

# 직접 실행 모드(python tests/test_depreciation_scenarios.py) 지원용 — pytest 경유 시 no-op
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from asset_schedule_generator import (
    AssetInput,
    MonthlyScheduleGenerator,
    generate_depreciation_schedule,
)


class ScenarioResults:
    """테스트 결과 수집 (직접 실행 모드용)"""
    def __init__(self):
        self.passed = []
        self.failed = []
        self.total = 0

    def add_pass(self, test_name: str):
        self.passed.append(test_name)
        self.total += 1
        print(f"  [PASS] {test_name}")

    def add_fail(self, test_name: str, error: str):
        self.failed.append((test_name, error))
        self.total += 1
        print(f"  [FAIL] {test_name}: {error}")

    def summary(self):
        print("\n" + "=" * 80)
        print(f"테스트 결과 요약")
        print("=" * 80)
        print(f"전체: {self.total}개")
        print(f"성공: {len(self.passed)}개")
        print(f"실패: {len(self.failed)}개")

        if self.failed:
            print("\n실패한 테스트:")
            for test_name, error in self.failed:
                print(f"  - {test_name}: {error}")

        print("=" * 80)
        return len(self.failed) == 0


def _assert_output_file(output_path):
    """공통 검증: 파일 존재 및 최소 크기"""
    assert os.path.exists(output_path), f"파일이 생성되지 않았습니다: {output_path}"
    file_size = os.path.getsize(output_path)
    assert file_size > 5000, f"파일 크기가 너무 작습니다: {file_size} bytes"


def _generate_monthly_schedule(**kwargs):
    """Excel 생성 전 구조화된 월별 스케줄을 직접 가져온다."""
    asset_input = AssetInput(**kwargs)
    return MonthlyScheduleGenerator(asset_input).generate_schedule()


def _row_by_year_month(schedule, year, month):
    """특정 연월의 월별 레코드를 찾는다."""
    for row in schedule:
        if row["year"] == year and row["month"] == month:
            return row
    raise AssertionError(f"{year}-{month:02d} 레코드를 찾을 수 없습니다")


def test_scenario_01_tangible_straight_line_basic():
    """
    시나리오 1: 유형자산 정액법 - 기본

    자산: 서버장비
    취득일: 2023-03-15
    취득원가: 10,000,000원
    내용연수: 5년
    """
    output_path = generate_depreciation_schedule(
        asset_name="서버장비",
        acquisition_date="2023-03-15",
        acquisition_cost=10000000,
        useful_life=5,
        asset_type="유형자산",
        depreciation_method="정액법"
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_02_tangible_declining_balance_basic():
    """
    시나리오 2: 유형자산 정률법 - 기본

    자산: 차량운반구
    취득일: 2022-06-01
    취득원가: 30,000,000원
    내용연수: 5년
    """
    output_path = generate_depreciation_schedule(
        asset_name="차량운반구",
        acquisition_date="2022-06-01",
        acquisition_cost=30000000,
        useful_life=5,
        asset_type="유형자산",
        depreciation_method="정률법"
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_03_intangible_basic():
    """
    시나리오 3: 무형자산 정액법 - 기본

    자산: 특허권
    취득일: 2021-01-01
    취득원가: 5,000,000원
    내용연수: 10년
    """
    output_path = generate_depreciation_schedule(
        asset_name="특허권",
        acquisition_date="2021-01-01",
        acquisition_cost=5000000,
        useful_life=10,
        asset_type="무형자산",
        depreciation_method="정액법"
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_04_tangible_straight_line_increase():
    """
    시나리오 4: 유형자산 정액법 + 자본적지출

    자산: 건물
    취득일: 2020-01-01
    취득원가: 100,000,000원
    내용연수: 20년
    증가일: 2023-06-30
    증가금액: 20,000,000원
    """
    output_path = generate_depreciation_schedule(
        asset_name="건물",
        acquisition_date="2020-01-01",
        acquisition_cost=100000000,
        useful_life=20,
        asset_type="유형자산",
        depreciation_method="정액법",
        increase_date="2023-06-30",
        increase_amount=20000000
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_05_tangible_declining_balance_increase():
    """
    시나리오 5: 유형자산 정률법 + 자본적지출

    자산: 기계장치
    취득일: 2021-03-15
    취득원가: 50,000,000원
    내용연수: 8년
    증가일: 2024-07-01
    증가금액: 10,000,000원
    """
    output_path = generate_depreciation_schedule(
        asset_name="기계장치",
        acquisition_date="2021-03-15",
        acquisition_cost=50000000,
        useful_life=8,
        asset_type="유형자산",
        depreciation_method="정률법",
        increase_date="2024-07-01",
        increase_amount=10000000
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_06_tangible_straight_line_partial_disposal():
    """
    시나리오 6: 유형자산 정액법 + 부분양도

    자산: 비품
    취득일: 2022-01-01
    취득원가: 8,000,000원
    내용연수: 5년
    처분일: 2025-06-30
    처분금액: 4,800,000원 (60%)
    """
    output_path = generate_depreciation_schedule(
        asset_name="비품",
        acquisition_date="2022-01-01",
        acquisition_cost=8000000,
        useful_life=5,
        asset_type="유형자산",
        depreciation_method="정액법",
        disposal_date="2025-06-30",
        disposal_amount=4800000  # 60%
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_07_tangible_declining_balance_partial_disposal():
    """
    시나리오 7: 유형자산 정률법 + 부분양도

    자산: 공구기구
    취득일: 2023-04-01
    취득원가: 6,000,000원
    내용연수: 4년
    처분일: 2025-09-30
    처분금액: 3,000,000원 (50%)
    """
    output_path = generate_depreciation_schedule(
        asset_name="공구기구",
        acquisition_date="2023-04-01",
        acquisition_cost=6000000,
        useful_life=4,
        asset_type="유형자산",
        depreciation_method="정률법",
        disposal_date="2025-09-30",
        disposal_amount=3000000  # 50%
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_08_intangible_partial_disposal():
    """
    시나리오 8: 무형자산 정액법 + 부분양도

    자산: 소프트웨어
    취득일: 2023-01-01
    취득원가: 10,000,000원
    내용연수: 5년
    처분일: 2025-12-31
    처분금액: 4,000,000원 (40%)
    """
    output_path = generate_depreciation_schedule(
        asset_name="소프트웨어",
        acquisition_date="2023-01-01",
        acquisition_cost=10000000,
        useful_life=5,
        asset_type="무형자산",
        depreciation_method="정액법",
        disposal_date="2025-12-31",
        disposal_amount=4000000  # 40%
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_09_tangible_straight_line_full_disposal():
    """
    시나리오 9: 유형자산 정액법 + 전체양도

    자산: 사무용가구
    취득일: 2023-01-01
    취득원가: 3,000,000원
    내용연수: 5년
    처분일: 2025-03-31
    처분금액: 3,000,000원 (100%)
    """
    output_path = generate_depreciation_schedule(
        asset_name="사무용가구",
        acquisition_date="2023-01-01",
        acquisition_cost=3000000,
        useful_life=5,
        asset_type="유형자산",
        depreciation_method="정액법",
        disposal_date="2025-03-31",
        disposal_amount=3000000  # 100%
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_10_tangible_declining_balance_full_disposal():
    """
    시나리오 10: 유형자산 정률법 + 전체양도

    자산: 전산장비
    취득일: 2023-06-01
    취득원가: 5,000,000원
    내용연수: 4년
    처분일: 2025-05-31
    처분금액: 5,000,000원 (100%)
    """
    output_path = generate_depreciation_schedule(
        asset_name="전산장비",
        acquisition_date="2023-06-01",
        acquisition_cost=5000000,
        useful_life=4,
        asset_type="유형자산",
        depreciation_method="정률법",
        disposal_date="2025-05-31",
        disposal_amount=5000000  # 100%
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_11_tangible_straight_line_increase_partial_disposal():
    """
    시나리오 11: 유형자산 정액법 + 자본적지출 + 부분양도

    자산: 건물(복합)
    취득일: 2020-01-01
    취득원가: 50,000,000원
    내용연수: 20년
    증가일: 2023-06-30
    증가금액: 10,000,000원
    처분일: 2025-12-31
    처분금액: 30,000,000원 (원래 취득원가의 60%)
    """
    output_path = generate_depreciation_schedule(
        asset_name="건물(복합)",
        acquisition_date="2020-01-01",
        acquisition_cost=50000000,
        useful_life=20,
        asset_type="유형자산",
        depreciation_method="정액법",
        increase_date="2023-06-30",
        increase_amount=10000000,
        disposal_date="2025-12-31",
        disposal_amount=30000000  # 원래 취득원가의 60%
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_scenario_12_tangible_declining_balance_increase_full_disposal():
    """
    시나리오 12: 유형자산 정률법 + 자본적지출 + 전체양도

    자산: 기계장치(복합)
    취득일: 2021-03-01
    취득원가: 40,000,000원
    내용연수: 10년
    증가일: 2024-06-30
    증가금액: 8,000,000원
    처분일: 2026-03-31
    처분금액: 40,000,000원 (원래 취득원가 100%)
    """
    output_path = generate_depreciation_schedule(
        asset_name="기계장치(복합)",
        acquisition_date="2021-03-01",
        acquisition_cost=40000000,
        useful_life=10,
        asset_type="유형자산",
        depreciation_method="정률법",
        increase_date="2024-06-30",
        increase_amount=8000000,
        disposal_date="2026-03-31",
        disposal_amount=40000000  # 원래 취득원가 100%
    )
    try:
        _assert_output_file(output_path)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


def test_numeric_straight_line_basic_monthly_and_terminal_values():
    """
    숫자 검증 1: 기본 정액법의 월별/최종 숫자 검증.

    기대값 근거:
    - 상각대상액 = 10,000,000 - 비망가액 1,000 = 9,999,000원
    - 내용연수 5년 → 총 60개월
    - 완전 정액법이면 총 상각액 9,999,000원과 최종 장부가액 1,000원이 맞아야 한다.
    - 첫 해는 2023-03 취득이므로 10개월 × 166,666 = 1,666,660원이 아니라,
      엔진이 연간 2,000,000원을 12개월로 배분한 정수 로직에 따라 10개월 합계가 1,666,666원이다.
    """
    schedule = _generate_monthly_schedule(
        asset_name="서버장비",
        acquisition_date="2023-03-15",
        acquisition_cost=10000000,
        useful_life=5,
        asset_type="유형자산",
        depreciation_method="정액법",
    )

    assert len(schedule) == 60
    assert schedule[0]["monthly_dep"] == 166666
    assert sum(row["monthly_dep"] for row in schedule if row["year"] == 2023) == 1666666
    assert schedule[-1]["accumulated_dep"] == 9999000
    assert schedule[-1]["book_value"] == 1000


def test_numeric_declining_balance_yearly_charge_decreases_and_memorandum_floor():
    """
    숫자 검증 2: 기본 정률법의 연도별 체감 패턴과 최종 비망가 검증.

    기대값 근거:
    - README/FREEZE_NOTICE가 말하는 핵심은 정수 기반 회계 정확성과 비망가액 1,000원 유지다.
    - 정률법은 기초 장부가액 × 상각률로 계산되므로, 연도별 상각액은 일반적으로 감소해야 한다.
    - 원칙(2026-06): 종료해 연간상각액(잔액 전액=기초장부가-비망가)을 먼저 확정한 뒤 그해
      월수로 월할 균등 배분한다. 따라서 종료월에 잔재를 한 번에 dump하지 않고(스파이크 없음),
      종료해 월상각은 반올림 차이(±수 원)만 있을 뿐 균등하며, 최종 장부가는 비망가 1,000원이다.
    """
    schedule = _generate_monthly_schedule(
        asset_name="차량운반구",
        acquisition_date="2022-06-01",
        acquisition_cost=30000000,
        useful_life=5,
        asset_type="유형자산",
        depreciation_method="정률법",
    )

    yearly = {
        year: sum(row["monthly_dep"] for row in schedule if row["year"] == year)
        for year in sorted({row["year"] for row in schedule})
    }

    assert yearly[2023] > yearly[2024] > yearly[2025] > yearly[2026]
    # 종료해(2027) 월별: 연간상각액을 월할 균등 배분 → dump 스파이크 없음, 반올림 차이만 존재
    terminal = [row["monthly_dep"] for row in schedule if row["year"] == 2027]
    assert max(terminal) - min(terminal) <= len(terminal)        # 균등 배분(반올림 차이만)
    assert schedule[-1]["monthly_dep"] == 401463                 # 종료월 = 균등 base + 보정
    assert schedule[-1]["book_value"] == 1000
    assert schedule[-1]["accumulated_dep"] == 29999000


def test_numeric_intangible_straight_line_full_life_totals_match():
    """
    숫자 검증 3: 무형자산 정액 상각의 총액/최종월 보정 검증.

    기대값 근거:
    - 상각대상액 = 5,000,000 - 1,000 = 4,999,000원
    - 연간 상각 500,000원, 월 배분은 정수 나눗셈으로 대부분 41,666원.
    - 종료연도(499,000원)는 유형 정액과 동일하게 균등 분배(41,583원)하고
      마지막 달에 잔액 보정(41,587원). (vcore 통일 분배 — 구 무형 엔진은
      마지막 달에만 캡을 흡수했으나 연총액은 동일)
    """
    schedule = _generate_monthly_schedule(
        asset_name="특허권",
        acquisition_date="2021-01-01",
        acquisition_cost=5000000,
        useful_life=10,
        asset_type="무형자산",
        depreciation_method="정액법",
    )

    assert len(schedule) == 120
    assert schedule[0]["monthly_dep"] == 41666
    assert sum(row["monthly_dep"] for row in schedule if row["year"] == 2021) == 500000
    assert schedule[-1]["monthly_dep"] == 41587
    assert schedule[-1]["accumulated_dep"] == 4999000
    assert schedule[-1]["book_value"] == 1000


def test_numeric_straight_line_partial_disposal_rebases_remaining_asset():
    """
    숫자 검증 4: 정액법 부분양도 후 잔존자산 기준으로 재기준화(rebase)되는지 검증.

    기대값 근거 (더존식 — 양도월까지 전체 기준 상각, 익월부터 잔존 기준):
    - 양도월(2025-06)까지는 전체 취득원가 기준 상각 → 6월 월상각 133,333원,
      6월 말 장부+누계 합계는 여전히 8,000,000원.
    - 2025-06 양도(취득원가 4,800,000원, 60%) 분배는 6월 말에 발생 →
      7월부터 잔존자산(3,200,000원) 기준: 장부+누계 = 3,200,000원,
      월상각비 53,333원 수준으로 축소.
    """
    schedule = _generate_monthly_schedule(
        asset_name="비품",
        acquisition_date="2022-01-01",
        acquisition_cost=8000000,
        useful_life=5,
        asset_type="유형자산",
        depreciation_method="정액법",
        disposal_date="2025-06-30",
        disposal_amount=4800000,
    )

    may_2025 = _row_by_year_month(schedule, 2025, 5)
    jun_2025 = _row_by_year_month(schedule, 2025, 6)
    jul_2025 = _row_by_year_month(schedule, 2025, 7)
    dec_2026 = _row_by_year_month(schedule, 2026, 12)

    assert may_2025["book_value"] + may_2025["accumulated_dep"] == 8000000
    assert jun_2025["book_value"] + jun_2025["accumulated_dep"] == 8000000   # 양도월 포함 상각(더존식)
    assert jun_2025["monthly_dep"] == 133333
    assert jul_2025["book_value"] + jul_2025["accumulated_dep"] == 3200000   # 익월부터 잔존 기준
    assert jul_2025["monthly_dep"] == 53333
    assert dec_2026["book_value"] == 1000
    assert dec_2026["accumulated_dep"] == 3199000


def run_all_tests():
    """모든 테스트 실행 (직접 실행 모드)"""
    print("=" * 80)
    print("dep_cal 감가상각 계산기 공식 테스트")
    print("=" * 80)
    print(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results = ScenarioResults()

    scenarios = [
        ("1/12", "기본 시나리오 - 유형자산 정액법", test_scenario_01_tangible_straight_line_basic),
        ("2/12", "기본 시나리오 - 유형자산 정률법", test_scenario_02_tangible_declining_balance_basic),
        ("3/12", "기본 시나리오 - 무형자산 정액법", test_scenario_03_intangible_basic),
        ("4/12", "자본적지출 - 유형자산 정액법", test_scenario_04_tangible_straight_line_increase),
        ("5/12", "자본적지출 - 유형자산 정률법", test_scenario_05_tangible_declining_balance_increase),
        ("6/12", "부분양도 - 유형자산 정액법", test_scenario_06_tangible_straight_line_partial_disposal),
        ("7/12", "부분양도 - 유형자산 정률법", test_scenario_07_tangible_declining_balance_partial_disposal),
        ("8/12", "부분양도 - 무형자산 정액법", test_scenario_08_intangible_partial_disposal),
        ("9/12", "전체양도 - 유형자산 정액법", test_scenario_09_tangible_straight_line_full_disposal),
        ("10/12", "전체양도 - 유형자산 정률법", test_scenario_10_tangible_declining_balance_full_disposal),
        ("11/12", "복합 - 유형자산 정액법 + 자본적지출 + 부분양도", test_scenario_11_tangible_straight_line_increase_partial_disposal),
        ("12/12", "복합 - 유형자산 정률법 + 자본적지출 + 전체양도", test_scenario_12_tangible_declining_balance_increase_full_disposal),
    ]

    for num, label, test_fn in scenarios:
        print(f"\n[{num}] {label}")
        try:
            test_fn()
            results.add_pass(label)
        except Exception as e:
            results.add_fail(label, str(e))

    # 결과 요약
    all_passed = results.summary()

    if all_passed:
        print("\n[SUCCESS] 모든 테스트가 통과했습니다!")
        return 0
    else:
        print("\n[FAILED] 일부 테스트가 실패했습니다.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
