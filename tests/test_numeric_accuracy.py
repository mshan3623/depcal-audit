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
감가상각 숫자 정확성 검증 테스트
Depreciation Numeric Accuracy Tests

기존 12개 smoke test(파일 생성/크기)를 보완하여,
엔진이 산출하는 실제 숫자의 회계적 정합성을 검증한다.

검증 전략:
  - Excel 생성 전 단계인 MonthlyScheduleGenerator.generate_schedule()의
    구조화된 데이터를 직접 검증한다 (Excel 파싱 불필요).
  - 특정 snapshot 값이 아닌 회계 불변식(항등식, 단조성, 총합)을
    중심으로 검증하여 엔진 로직의 구조적 정확성을 보장한다.
"""

from asset_schedule_generator import AssetInput, MonthlyScheduleGenerator


def _get_schedule(asset_name, acquisition_date, acquisition_cost, useful_life,
                  asset_type, depreciation_method, **kwargs):
    """테스트 헬퍼: 스케줄 데이터를 리스트로 반환"""
    ai = AssetInput(
        asset_name=asset_name,
        acquisition_date=acquisition_date,
        acquisition_cost=acquisition_cost,
        useful_life=useful_life,
        asset_type=asset_type,
        depreciation_method=depreciation_method,
        **kwargs
    )
    return MonthlyScheduleGenerator(ai).generate_schedule()


# ──────────────────────────────────────────────
# Test 1: 유형자산 정액법 — 회계 항등식·균등성·최종값
# ──────────────────────────────────────────────

def test_straight_line_numeric_invariants():
    """
    유형자산 정액법 핵심 숫자 불변식 검증

    입력:
      취득원가 10,000,000원, 내용연수 5년, 취득일 2023-01-01
      잔존가액 0, 비망가액 1,000원 (한국세법 기본)

    기대값 근거:
      - 감가상각대상금액 = 10,000,000 - 1,000 = 9,999,000원
      - 월 감가상각비 ≈ 9,999,000 / 60 = 166,650원 (Integer 나눗셈으로 약간 상이)
      - 매월: book_value + accumulated_dep == 취득원가 (10,000,000)
      - 최종월: book_value == 비망가액 (1,000원)
      - 총합: Σ monthly_dep == 9,999,000원
    """
    COST = 10_000_000
    MEMORANDUM = 1_000
    DEPRECIABLE = COST - MEMORANDUM  # 9,999,000

    schedule = _get_schedule("서버", "2023-01-01", COST, 5, "유형자산", "정액법")

    # 1) 60개월 스케줄
    assert len(schedule) == 60, f"내용연수 5년 = 60개월이어야 함, 실제: {len(schedule)}"

    # 2) 매월 회계 항등식: book_value + accumulated_dep == 취득원가
    for i, r in enumerate(schedule):
        identity = r["book_value"] + r["accumulated_dep"]
        assert identity == COST, (
            f"월 {i+1} 회계 항등식 위반: "
            f"bv({r['book_value']}) + acc({r['accumulated_dep']}) = {identity} ≠ {COST}"
        )

    # 3) 모든 값이 정수 (Integer 기반 계산 보장)
    for i, r in enumerate(schedule):
        assert isinstance(r["monthly_dep"], int), f"월 {i+1} monthly_dep이 정수가 아님"
        assert isinstance(r["book_value"], int), f"월 {i+1} book_value가 정수가 아님"
        assert isinstance(r["accumulated_dep"], int), f"월 {i+1} accumulated_dep이 정수가 아님"

    # 4) 총합 = 감가상각대상금액
    total = sum(r["monthly_dep"] for r in schedule)
    assert total == DEPRECIABLE, (
        f"총 감가상각비 불일치: {total} ≠ {DEPRECIABLE}"
    )

    # 5) 최종 장부가액 = 비망가액
    assert schedule[-1]["book_value"] == MEMORANDUM, (
        f"최종 장부가액이 비망가액과 불일치: {schedule[-1]['book_value']} ≠ {MEMORANDUM}"
    )

    # 6) 정액법 균등성: 월 감가상각비 편차가 전체 평균의 1% 이내
    #    (Integer 나눗셈에 의한 최종월 조정 허용)
    deps = [r["monthly_dep"] for r in schedule]
    avg = DEPRECIABLE / 60
    for i, d in enumerate(deps):
        assert abs(d - avg) / avg < 0.01, (
            f"월 {i+1} 감가상각비 {d}가 평균 {avg:.0f}에서 1% 이상 벗어남"
        )


# ──────────────────────────────────────────────
# Test 2: 유형자산 정률법 — 체감 패턴·항등식·최종값
# ──────────────────────────────────────────────

def test_declining_balance_numeric_invariants():
    """
    유형자산 정률법 핵심 숫자 불변식 검증

    입력:
      취득원가 30,000,000원, 내용연수 5년, 취득일 2022-01-01

    기대값 근거:
      - 정률법 상각률: 법인세법 [별표 4]에 의한 5년 상각률 적용
      - 연간 감가상각비는 전년 대비 감소해야 함 (체감 패턴)
      - 마지막 해에 비망가액 1,000원까지 일시 상각 가능 (균등상각 전환)
      - 매월: book_value + accumulated_dep == 취득원가 (30,000,000)
    """
    COST = 30_000_000
    MEMORANDUM = 1_000
    DEPRECIABLE = COST - MEMORANDUM

    schedule = _get_schedule("차량", "2022-01-01", COST, 5, "유형자산", "정률법")

    # 1) 매월 회계 항등식
    for i, r in enumerate(schedule):
        identity = r["book_value"] + r["accumulated_dep"]
        assert identity == COST, (
            f"월 {i+1} 회계 항등식 위반: "
            f"bv({r['book_value']}) + acc({r['accumulated_dep']}) = {identity} ≠ {COST}"
        )

    # 2) 연도별 감가상각비 집계
    yearly_dep = {}
    for r in schedule:
        yearly_dep.setdefault(r["year"], 0)
        yearly_dep[r["year"]] += r["monthly_dep"]
    years = sorted(yearly_dep.keys())

    # 3) 체감 패턴: 처음 2년간은 반드시 감소
    #    (마지막 해는 비망가액 도달을 위한 균등상각 전환이 있을 수 있어 예외)
    assert yearly_dep[years[0]] > yearly_dep[years[1]], (
        f"정률법 체감 위반: {years[0]}년({yearly_dep[years[0]]}) > "
        f"{years[1]}년({yearly_dep[years[1]]})이어야 함"
    )

    # 4) 총합 = 감가상각대상금액
    total = sum(r["monthly_dep"] for r in schedule)
    assert total == DEPRECIABLE, (
        f"총 감가상각비 불일치: {total} ≠ {DEPRECIABLE}"
    )

    # 5) 최종 장부가액 = 비망가액
    assert schedule[-1]["book_value"] == MEMORANDUM, (
        f"최종 장부가액: {schedule[-1]['book_value']} ≠ {MEMORANDUM}"
    )

    # 6) 누적 감가상각비 단조 증가
    for i in range(1, len(schedule)):
        assert schedule[i]["accumulated_dep"] >= schedule[i-1]["accumulated_dep"], (
            f"누적 감가상각비 단조 증가 위반: 월 {i} → {i+1}"
        )


# ──────────────────────────────────────────────
# Test 3: 무형자산 정액법 — 총합·Integer·최종값
# ──────────────────────────────────────────────

def test_intangible_straight_line_numeric_invariants():
    """
    무형자산 정액법 핵심 숫자 불변식 검증

    입력:
      취득원가 5,000,000원, 내용연수 10년, 취득일 2021-01-01

    기대값 근거:
      - 무형자산도 비망가액 1,000원 적용
      - 감가상각대상금액 = 5,000,000 - 1,000 = 4,999,000원
      - 120개월 균등 상각: 월 ≈ 41,658원
      - 직접상각법이므로 장부에서 직접 차감
    """
    COST = 5_000_000
    MEMORANDUM = 1_000
    DEPRECIABLE = COST - MEMORANDUM

    schedule = _get_schedule("특허", "2021-01-01", COST, 10, "무형자산", "정액법")

    # 1) 120개월 스케줄
    assert len(schedule) == 120, f"내용연수 10년 = 120개월, 실제: {len(schedule)}"

    # 2) 총합 = 감가상각대상금액
    total = sum(r["monthly_dep"] for r in schedule)
    assert total == DEPRECIABLE, (
        f"총 감가상각비 불일치: {total} ≠ {DEPRECIABLE}"
    )

    # 3) 최종 장부가액 = 비망가액
    assert schedule[-1]["book_value"] == MEMORANDUM, (
        f"최종 장부가액: {schedule[-1]['book_value']} ≠ {MEMORANDUM}"
    )

    # 4) 모든 값이 정수
    for i, r in enumerate(schedule):
        for key in ("monthly_dep", "book_value", "accumulated_dep"):
            assert isinstance(r[key], int), f"월 {i+1} {key}가 정수가 아님: {type(r[key])}"

    # 5) 매월 회계 항등식
    for i, r in enumerate(schedule):
        identity = r["book_value"] + r["accumulated_dep"]
        assert identity == COST, (
            f"월 {i+1} 회계 항등식 위반: {identity} ≠ {COST}"
        )

    # 6) 계산방법이 무형자산 전용인지 확인
    assert "무형자산" in schedule[0]["calc_method"] or "intang" in schedule[0]["calc_method"].lower(), (
        f"무형자산 전용 계산방법이 아님: {schedule[0]['calc_method']}"
    )


# ──────────────────────────────────────────────
# Test 4: 자본적지출 반영 — 장부가액 점프·항등식 전환
# ──────────────────────────────────────────────

def test_capital_expenditure_book_value_jump():
    """
    자본적지출(증가) 시점 전후 숫자 정합성 검증

    입력:
      취득원가 100,000,000원, 내용연수 20년, 취득일 2020-01-01
      자본적지출 20,000,000원 @ 2023-06-30

    기대값 근거:
      - 증가 전: book_value + accumulated_dep == 100,000,000 (원래 취득원가)
      - 증가 후: book_value + accumulated_dep == 120,000,000 (원래 + 증가)
      - 증가 시점에서 장부가액이 증가금액만큼 점프
      - 증가 후 월 상각비가 증가 전보다 커야 함
        (잔여 감가상각대상금액이 늘었으므로)
    """
    ORIGINAL_COST = 100_000_000
    INCREASE = 20_000_000
    COMBINED_COST = ORIGINAL_COST + INCREASE  # 120,000,000

    schedule = _get_schedule(
        "건물", "2020-01-01", ORIGINAL_COST, 20, "유형자산", "정액법",
        increase_date="2023-06-30", increase_amount=INCREASE
    )

    # 증가 직전월(2023-05)과 증가 반영월(2023-06) 찾기
    pre_increase = None
    post_increase = None
    for r in schedule:
        if r["year"] == 2023 and r["month"] == 5:
            pre_increase = r
        if r["year"] == 2023 and r["month"] == 6:
            post_increase = r

    assert pre_increase is not None, "2023-05 데이터 없음"
    assert post_increase is not None, "2023-06 데이터 없음"

    # 1) 증가 전 회계 항등식: bv + acc == 원래 취득원가
    pre_identity = pre_increase["book_value"] + pre_increase["accumulated_dep"]
    assert pre_identity == ORIGINAL_COST, (
        f"증가 전 항등식 위반: {pre_identity} ≠ {ORIGINAL_COST}"
    )

    # 2) 증가 후 회계 항등식: bv + acc == 원래 + 증가
    post_identity = post_increase["book_value"] + post_increase["accumulated_dep"]
    assert post_identity == COMBINED_COST, (
        f"증가 후 항등식 위반: {post_identity} ≠ {COMBINED_COST}"
    )

    # 3) 장부가액 점프: 증가 후 장부가액 > 증가 전 장부가액
    #    (증가금액 20M > 1개월 상각비이므로 반드시 성립)
    assert post_increase["book_value"] > pre_increase["book_value"], (
        f"장부가액 점프 없음: 증가 전 {pre_increase['book_value']}, "
        f"증가 후 {post_increase['book_value']}"
    )

    # 4) 증가 후 월 상각비 > 증가 전 월 상각비
    assert post_increase["monthly_dep"] > pre_increase["monthly_dep"], (
        f"자본적지출 후 상각비 미증가: "
        f"전 {pre_increase['monthly_dep']}, 후 {post_increase['monthly_dep']}"
    )

    # 5) 최종 장부가액 = 비망가액
    assert schedule[-1]["book_value"] == 1_000, (
        f"최종 장부가액: {schedule[-1]['book_value']} ≠ 1,000"
    )

    # 6) 총합 = 통합 취득원가 - 비망가액
    total = sum(r["monthly_dep"] for r in schedule)
    assert total == COMBINED_COST - 1_000, (
        f"총합 불일치: {total} ≠ {COMBINED_COST - 1_000}"
    )


# ──────────────────────────────────────────────
# Test 5: 무형자산 부분양도 — 양도 직전까지 history 보존
# ──────────────────────────────────────────────

def test_intangible_partial_disposal_preserves_history_before_disposal():
    """
    무형자산 부분양도: 양도 직전월까지 기본 스케줄과 history가 일치해야 한다.

    양도월(2025-12)부터는 잔존자산 기준으로 값이 달라질 수 있다.
    그러나 양도 이전 기간(2023-01 ~ 2025-11)의 monthly_dep, accumulated_dep,
    book_value는 양도 없는 기본 스케줄과 동일해야 한다.

    회계적 근거:
      부분양도는 미래 시점의 사건이다. 과거 기간의 감가상각비는
      이미 확정된 회계 기록이므로 소급 변경되어서는 안 된다.
      양도 시점에 취득원가·감가상각누계액을 양도비율만큼 제거하고,
      잔존자산에 대해 이후 기간만 재계산하는 것이 올바른 처리다.

    입력:
      취득원가 10,000,000원, 내용연수 5년, 취득일 2023-01-01
      부분양도 4,000,000원 (40%) @ 2025-12-31

    기대:
      - 2023-01 ~ 2025-11 (35개월): base와 partial이 완전히 동일
      - 2025-12 이후: 값이 달라질 수 있음 (잔존자산 기준)
    """
    COST = 10_000_000
    DISPOSAL_AMOUNT = 4_000_000  # 40%
    DISPOSAL_DATE = "2025-12-31"
    DISPOSAL_YEAR, DISPOSAL_MONTH = 2025, 12

    # 기본 스케줄 (양도 없음)
    base = _get_schedule("소프트웨어", "2023-01-01", COST, 5, "무형자산", "정액법")

    # 부분양도 스케줄
    partial = _get_schedule(
        "소프트웨어", "2023-01-01", COST, 5, "무형자산", "정액법",
        disposal_date=DISPOSAL_DATE, disposal_amount=DISPOSAL_AMOUNT
    )

    # 양도 직전월(2025-11)까지의 레코드를 추출
    base_before = [
        r for r in base
        if (r["year"] < DISPOSAL_YEAR)
        or (r["year"] == DISPOSAL_YEAR and r["month"] < DISPOSAL_MONTH)
    ]
    partial_before = [
        r for r in partial
        if (r["year"] < DISPOSAL_YEAR)
        or (r["year"] == DISPOSAL_YEAR and r["month"] < DISPOSAL_MONTH)
    ]

    # 양도 이전 기간의 레코드 수가 동일해야 함
    assert len(base_before) == len(partial_before), (
        f"양도 이전 레코드 수 불일치: base={len(base_before)}, partial={len(partial_before)}"
    )

    # 양도 직전월까지 3가지 값이 모두 일치해야 함
    mismatches = []
    for b, p in zip(base_before, partial_before):
        ym = f"{b['year']}-{b['month']:02d}"
        if b["monthly_dep"] != p["monthly_dep"]:
            mismatches.append(
                f"{ym} monthly_dep: base={b['monthly_dep']}, partial={p['monthly_dep']}"
            )
        if b["accumulated_dep"] != p["accumulated_dep"]:
            mismatches.append(
                f"{ym} accumulated_dep: base={b['accumulated_dep']}, partial={p['accumulated_dep']}"
            )
        if b["book_value"] != p["book_value"]:
            mismatches.append(
                f"{ym} book_value: base={b['book_value']}, partial={p['book_value']}"
            )

    assert not mismatches, (
        f"양도 직전월까지 history 불일치 ({len(mismatches)}건):\n"
        + "\n".join(mismatches[:10])
        + ("\n..." if len(mismatches) > 10 else "")
    )
