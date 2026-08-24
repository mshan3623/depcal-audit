"""매각·처분 invariant 회귀 (v2.1 매트릭스 84개 영구화)

대원칙 (더존식: 양도월 포함 — 양도월까지 상각 후 익월부터 중단/잔존):
- 매각은 그저 양도월의 장부가액을 들여다 볼 뿐이다.
- 감가상각은 매월 정상적으로 회계장부에 반영될 것이다.

검증 차원:
- 양도월 동등성: 정상모드(매각 없음)와 매각모드의 monthly/accumulated/book_value 일치
- 분배 무결성 (부분양도): 양도 누계 = 4사5입(원 누계 × ratio), 잔존 = 차감
- 잔존 비망가 (부분양도): 잔존 자산의 내용연수 종료월 book_value = 1,000원
- 종료월 (전체양도): schedule의 마지막 레코드 = 양도월(포함)
"""

import pytest
from functools import partial

from core.dep_tang_engine import (
    _calculate_korean_straight_line_enhanced as _sl_raw,
    _calculate_korean_declining_balance_enhanced as _dec_raw,
    _calculate_with_partial_disposal as _sl_p_raw,
    _calculate_with_partial_disposal_declining as _dec_p_raw,
    _calculate_with_increase as _sl_inc_raw,
    _calculate_with_increase_declining as _dec_inc_raw,
)
# ⚠️ dep_intang_engine은 실행 경로 밖이다(1/n 나눗셈 — 별표4와 어긋남, 2026-06-16 이후
# core·vcore 모두 별표4 정액으로 통일). 아래 검사는 **값이 아니라 양도 불변식(구조)** 을
# 고정하므로 그 전환과 무관하게 유효하다. 이 파일의 통과를 무형 상각액의 정확성 근거로
# 읽지 말 것 — 무형 수치의 oracle은 별표4다 (tests_vector/test_intangible_golden_handcalc).
from core.dep_intang_engine import (
    _calculate_intangible_asset_enhanced as _intang_raw,
    _calculate_intangible_with_partial_disposal as _intang_p_raw,
)
from core.dep_common import round_half_up

# v2.2: 기존 매트릭스(84개)는 12월 결산 가정에서 작성됨. 같은 결과 보장을 위해
# fiscal_year_end_month=12 default를 wrapper로 주입. 비-12월 시나리오는 별도 테스트.
sl = partial(_sl_raw, fiscal_year_end_month=12)
dec = partial(_dec_raw, fiscal_year_end_month=12)
sl_p = partial(_sl_p_raw, fiscal_year_end_month=12)
dec_p = partial(_dec_p_raw, fiscal_year_end_month=12)
sl_inc = partial(_sl_inc_raw, fiscal_year_end_month=12)
dec_inc = partial(_dec_inc_raw, fiscal_year_end_month=12)
intang = partial(_intang_raw, fiscal_year_end_month=12)
intang_p = partial(_intang_p_raw, fiscal_year_end_month=12)


# ============================================================
# Fixture 값
# ============================================================
COST = 100_000_000
LIFE = 5
START = "2022-01-15"
INC_AMOUNT = 20_000_000
INC_DATE = "2023-06-10"
COST_BASIS_INC = COST + INC_AMOUNT  # 자본적지출 합산 cost


def pick(schedule, year, month):
    for r in schedule:
        if r.year == year and r.month == month:
            return r
    return None


def next_month_of(year, month):
    return (year, month + 1) if month < 12 else (year + 1, 1)


# ============================================================
# 시나리오 데이터
# ============================================================

# 전체양도: (label, disposal_date, 양도월_year, 양도월_month) — 더존식 양도월 포함(마지막 상각월=양도월)
FULL_SCEN = [
    ("양도4월_중간", "2025-04-15", 2025, 4),
    ("양도1월_전년12", "2025-01-10", 2025, 1),
    ("양도12월_연말", "2025-12-20", 2025, 12),
    ("양도6월_중도", "2025-06-10", 2025, 6),
]

# 부분양도: (label, disposal_amount, disposal_date, 양도월_year, 양도월_month) — 더존식 양도월 포함(전체기준 마지막 상각월=양도월)
PARTIAL_SCEN = [
    ("부분30%_4월", 30_000_000, "2025-04-15", 2025, 4),
    ("부분50%_6월", 50_000_000, "2025-06-10", 2025, 6),
    ("부분70%_12월", 70_000_000, "2025-12-20", 2025, 12),
    ("부분25%_1월", 25_000_000, "2025-01-10", 2025, 1),
]


# ============================================================
# 1. 유형자산 전체양도 (정액법·정률법)
# ============================================================
@pytest.mark.parametrize("eng", [sl, dec], ids=["straight_line", "declining"])
@pytest.mark.parametrize("label,disp,py,pm", FULL_SCEN, ids=[s[0] for s in FULL_SCEN])
def test_tangible_full_disposal_prev_month_equivalence(eng, label, disp, py, pm):
    """양도월(포함) monthly/accumulated/book_value가 정상모드와 0원 차이 일치."""
    sN = eng(cost=COST, life_years=LIFE, start_date=START)
    sD = eng(cost=COST, life_years=LIFE, start_date=START, disposal_date=disp)
    rN = pick(sN, py, pm)
    rD = pick(sD, py, pm)
    assert rN is not None and rD is not None
    assert rN.monthly_depreciation == rD.monthly_depreciation
    assert rN.accumulated_depreciation == rD.accumulated_depreciation
    assert rN.book_value == rD.book_value


@pytest.mark.parametrize("eng", [sl, dec], ids=["straight_line", "declining"])
@pytest.mark.parametrize("label,disp,py,pm", FULL_SCEN, ids=[s[0] for s in FULL_SCEN])
def test_tangible_full_disposal_schedule_ends_at_prev_month(eng, label, disp, py, pm):
    """전체양도 schedule의 마지막 레코드 = 양도월(포함)."""
    sD = eng(cost=COST, life_years=LIFE, start_date=START, disposal_date=disp)
    assert (sD[-1].year, sD[-1].month) == (py, pm)


# ============================================================
# 2. 자본적지출 + 유형자산 전체양도
# ============================================================
@pytest.mark.parametrize("eng", [sl_inc, dec_inc], ids=["sl_inc", "dec_inc"])
@pytest.mark.parametrize("label,disp,py,pm", FULL_SCEN, ids=[s[0] for s in FULL_SCEN])
def test_tangible_inc_full_disposal_prev_month_equivalence(eng, label, disp, py, pm):
    sN = eng(cost=COST, life_years=LIFE, start_date=START,
             increase_amount=INC_AMOUNT, increase_date=INC_DATE,
             disposal_date=None, disposal_amount=0)
    sD = eng(cost=COST, life_years=LIFE, start_date=START,
             increase_amount=INC_AMOUNT, increase_date=INC_DATE,
             disposal_date=disp, disposal_amount=0)
    rN = pick(sN, py, pm)
    rD = pick(sD, py, pm)
    assert rN.monthly_depreciation == rD.monthly_depreciation
    assert rN.accumulated_depreciation == rD.accumulated_depreciation
    assert rN.book_value == rD.book_value


# ============================================================
# 3. 유형자산 부분양도 (정액법·정률법)
# ============================================================
@pytest.mark.parametrize("eng_n,eng_p", [(sl, sl_p), (dec, dec_p)], ids=["sl", "dec"])
@pytest.mark.parametrize("label,da,disp,py,pm", PARTIAL_SCEN, ids=[s[0] for s in PARTIAL_SCEN])
def test_tangible_partial_disposal_prev_month_equivalence(eng_n, eng_p, label, da, disp, py, pm):
    sN = eng_n(cost=COST, life_years=LIFE, start_date=START)
    sP = eng_p(cost=COST, life_years=LIFE, start_date=START,
               disposal_amount=da, disposal_date=disp)
    rN = pick(sN, py, pm)
    rP = pick(sP, py, pm)
    assert rN.monthly_depreciation == rP.monthly_depreciation
    assert rN.accumulated_depreciation == rP.accumulated_depreciation
    assert rN.book_value == rP.book_value


@pytest.mark.parametrize("eng_n,eng_p", [(sl, sl_p), (dec, dec_p)], ids=["sl", "dec"])
@pytest.mark.parametrize("label,da,disp,py,pm", PARTIAL_SCEN, ids=[s[0] for s in PARTIAL_SCEN])
def test_tangible_partial_disposal_distribution_integrity(eng_n, eng_p, label, da, disp, py, pm):
    """양도 누계 = 4사5입(원 누계 × disposal_amount / cost), 잔존 누계 = 차감 (무결성)."""
    sN = eng_n(cost=COST, life_years=LIFE, start_date=START)
    sP = eng_p(cost=COST, life_years=LIFE, start_date=START,
               disposal_amount=da, disposal_date=disp)
    rN = pick(sN, py, pm)
    ny, nm = next_month_of(py, pm)
    rP_next = pick(sP, ny, nm)
    assert rP_next is not None
    orig_acc = int(rN.accumulated_depreciation)
    rem_acc = int(rP_next.accumulated_depreciation) - int(rP_next.monthly_depreciation)
    disp_acc = orig_acc - rem_acc
    expected_disp_acc = round_half_up(orig_acc * da / COST)
    assert disp_acc == expected_disp_acc
    assert disp_acc + rem_acc == orig_acc


@pytest.mark.parametrize("eng_p", [sl_p, dec_p], ids=["sl_p", "dec_p"])
@pytest.mark.parametrize("label,da,disp,py,pm", PARTIAL_SCEN, ids=[s[0] for s in PARTIAL_SCEN])
def test_tangible_partial_disposal_remaining_memorandum(eng_p, label, da, disp, py, pm):
    """잔존 자산이 내용연수 종료월에 book_value = 1,000원 (비망가) 도달."""
    sP = eng_p(cost=COST, life_years=LIFE, start_date=START,
               disposal_amount=da, disposal_date=disp)
    assert int(sP[-1].book_value) == 1000


# ============================================================
# 4. 자본적지출 + 유형자산 부분양도
# ============================================================
@pytest.mark.parametrize("eng", [sl_inc, dec_inc], ids=["sl_inc", "dec_inc"])
@pytest.mark.parametrize("label,da,disp,py,pm", PARTIAL_SCEN, ids=[s[0] for s in PARTIAL_SCEN])
def test_tangible_inc_partial_disposal_prev_month_equivalence(eng, label, da, disp, py, pm):
    sN = eng(cost=COST, life_years=LIFE, start_date=START,
             increase_amount=INC_AMOUNT, increase_date=INC_DATE,
             disposal_date=None, disposal_amount=0)
    sP = eng(cost=COST, life_years=LIFE, start_date=START,
             increase_amount=INC_AMOUNT, increase_date=INC_DATE,
             disposal_amount=da, disposal_date=disp)
    rN = pick(sN, py, pm)
    rP = pick(sP, py, pm)
    assert rN.monthly_depreciation == rP.monthly_depreciation
    assert rN.accumulated_depreciation == rP.accumulated_depreciation
    assert rN.book_value == rP.book_value


@pytest.mark.parametrize("eng", [sl_inc, dec_inc], ids=["sl_inc", "dec_inc"])
@pytest.mark.parametrize("label,da,disp,py,pm", PARTIAL_SCEN, ids=[s[0] for s in PARTIAL_SCEN])
def test_tangible_inc_partial_disposal_distribution_integrity(eng, label, da, disp, py, pm):
    sN = eng(cost=COST, life_years=LIFE, start_date=START,
             increase_amount=INC_AMOUNT, increase_date=INC_DATE,
             disposal_date=None, disposal_amount=0)
    sP = eng(cost=COST, life_years=LIFE, start_date=START,
             increase_amount=INC_AMOUNT, increase_date=INC_DATE,
             disposal_amount=da, disposal_date=disp)
    rN = pick(sN, py, pm)
    ny, nm = next_month_of(py, pm)
    rP_next = pick(sP, ny, nm)
    assert rP_next is not None
    orig_acc = int(rN.accumulated_depreciation)
    rem_acc = int(rP_next.accumulated_depreciation) - int(rP_next.monthly_depreciation)
    disp_acc = orig_acc - rem_acc
    expected_disp_acc = round_half_up(orig_acc * da / COST_BASIS_INC)
    assert disp_acc == expected_disp_acc
    assert disp_acc + rem_acc == orig_acc


# ============================================================
# 5. 무형자산 전체양도
# ============================================================
@pytest.mark.parametrize("label,disp,py,pm", FULL_SCEN, ids=[s[0] for s in FULL_SCEN])
def test_intangible_full_disposal_prev_month_equivalence(label, disp, py, pm):
    sN = intang(cost=COST, life_years=LIFE, start_date=START)
    sD = intang(cost=COST, life_years=LIFE, start_date=START, disposal_date=disp)
    rN = pick(sN, py, pm)
    rD = pick(sD, py, pm)
    assert rN.monthly_depreciation == rD.monthly_depreciation
    assert rN.accumulated_depreciation == rD.accumulated_depreciation
    assert rN.book_value == rD.book_value


@pytest.mark.parametrize("label,disp,py,pm", FULL_SCEN, ids=[s[0] for s in FULL_SCEN])
def test_intangible_full_disposal_schedule_ends_at_prev_month(label, disp, py, pm):
    sD = intang(cost=COST, life_years=LIFE, start_date=START, disposal_date=disp)
    assert (sD[-1].year, sD[-1].month) == (py, pm)


# ============================================================
# 6. 무형자산 부분양도
# ============================================================
@pytest.mark.parametrize("label,da,disp,py,pm", PARTIAL_SCEN, ids=[s[0] for s in PARTIAL_SCEN])
def test_intangible_partial_disposal_prev_month_equivalence(label, da, disp, py, pm):
    sN = intang(cost=COST, life_years=LIFE, start_date=START)
    sP = intang_p(cost=COST, life_years=LIFE, start_date=START,
                  disposal_amount=da, disposal_date=disp)
    rN = pick(sN, py, pm)
    rP = pick(sP, py, pm)
    assert rN.monthly_depreciation == rP.monthly_depreciation
    assert rN.accumulated_depreciation == rP.accumulated_depreciation
    assert rN.book_value == rP.book_value


@pytest.mark.parametrize("label,da,disp,py,pm", PARTIAL_SCEN, ids=[s[0] for s in PARTIAL_SCEN])
def test_intangible_partial_disposal_distribution_integrity(label, da, disp, py, pm):
    sN = intang(cost=COST, life_years=LIFE, start_date=START)
    sP = intang_p(cost=COST, life_years=LIFE, start_date=START,
                  disposal_amount=da, disposal_date=disp)
    rN = pick(sN, py, pm)
    ny, nm = next_month_of(py, pm)
    rP_next = pick(sP, ny, nm)
    assert rP_next is not None
    orig_acc = int(rN.accumulated_depreciation)
    rem_acc = int(rP_next.accumulated_depreciation) - int(rP_next.monthly_depreciation)
    disp_acc = orig_acc - rem_acc
    expected_disp_acc = round_half_up(orig_acc * da / COST)
    assert disp_acc == expected_disp_acc
    assert disp_acc + rem_acc == orig_acc


@pytest.mark.parametrize("label,da,disp,py,pm", PARTIAL_SCEN, ids=[s[0] for s in PARTIAL_SCEN])
def test_intangible_partial_disposal_remaining_memorandum(label, da, disp, py, pm):
    sP = intang_p(cost=COST, life_years=LIFE, start_date=START,
                  disposal_amount=da, disposal_date=disp)
    assert int(sP[-1].book_value) == 1000
