"""슬림 엔진(vcore) ↔ 레퍼런스 엔진(core) 회귀 가드.

검증 1: 모든 (취득원가·내용연수·취득월·결산월) 조합에서 회계연도별
        (연도, 개월, 당기상각, 누계, 기말장부) 벡터가 레퍼런스와 1원 단위 일치.
검증 2: calendar-shift 등가성 — 임의 결산월(F,M) shape == 표준형(12, M_std) shape.
"""
import pytest

from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod
from core.depreciation_engine import calculate_depreciation_enhanced
from vcore import straight_line, declining_balance, capex, disposal, intangible
from vcore.projection import standard_acq_month

METHODS = {
    "straight_line": (DepreciationMethod.STRAIGHT_LINE, straight_line),
    "declining_balance": (DepreciationMethod.DECLINING_BALANCE, declining_balance),
}

COSTS = [12_000_000, 10_000_000, 7_000_000, 99_999_999]
LIVES = [4, 5, 10]
FYES = [12, 9, 6, 3, 1]
ACQ_MONTHS = list(range(1, 13))
ACQ_YEAR = 2026


def _reference_rows(method_enum, cost, life, acq_month, fye):
    fin = AssetFinancials(cost=cost, life_in_years=life,
                          start_date=f"{ACQ_YEAR:04d}-{acq_month:02d}-01", method=method_enum)
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=fye)
    return [(s.year, s.months_count, s.yearly_depreciation,
             s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]


def _slim_rows(mod, cost, life, acq_month, fye):
    return [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value)
            for r in mod.schedule(cost, life, ACQ_YEAR, acq_month, fiscal_end_month=fye)]


@pytest.mark.parametrize("method", list(METHODS))
@pytest.mark.parametrize("fye", FYES)
@pytest.mark.parametrize("acq_month", ACQ_MONTHS)
def test_slim_matches_reference(method, fye, acq_month):
    """슬림 엔진이 레퍼런스와 회계연도 단위 1원까지 일치 (cost×life 전 조합)."""
    menum, mod = METHODS[method]
    for cost in COSTS:
        for life in LIVES:
            ref = _reference_rows(menum, cost, life, acq_month, fye)
            got = _slim_rows(mod, cost, life, acq_month, fye)
            assert got == ref, (
                f"{method} cost={cost} life={life} 결산월={fye} 취득월={acq_month}\n"
                f"  REF={ref}\n  GOT={got}")


@pytest.mark.parametrize("method", list(METHODS))
@pytest.mark.parametrize("fye", FYES)
@pytest.mark.parametrize("acq_month", ACQ_MONTHS)
def test_calendar_shift_equivalence(method, fye, acq_month):
    """임의 (결산월 F, 취득월 M) shape == 표준형(12월결산, M_std) shape."""
    _, mod = METHODS[method]
    m_std = standard_acq_month(fye, acq_month)
    for cost in COSTS:
        for life in LIVES:
            a = [(r.months, r.depreciation, r.book_value)
                 for r in mod.schedule(cost, life, ACQ_YEAR, acq_month, fiscal_end_month=fye)]
            b = [(r.months, r.depreciation, r.book_value)
                 for r in mod.schedule(cost, life, ACQ_YEAR, m_std, fiscal_end_month=12)]
            assert a == b, (
                f"{method} 등가성 깨짐 cost={cost} life={life} 결산월={fye} "
                f"취득월={acq_month} (M_std={m_std})")


INC_AMTS = [3_000_000, 5_000_000]
INC_OFFSETS = [5, 13, 27, 40]   # 취득 후 증가 시점(개월)
_CAPEX_ACQ = (2026, 4)


CAPEX_FNS = {
    "straight_line": (DepreciationMethod.STRAIGHT_LINE, capex.schedule_with_increase),
    "declining_balance": (DepreciationMethod.DECLINING_BALANCE, capex.schedule_with_increase_declining),
}


def _ref_capex_rows(method_enum, cost, life, acq, inc_amt, inc, fye):
    fin = AssetFinancials(cost=cost, life_in_years=life,
                          start_date=f"{acq[0]:04d}-{acq[1]:02d}-01", method=method_enum,
                          increase_amount=inc_amt,
                          increase_date=f"{inc[0]:04d}-{inc[1]:02d}-01")
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=fye)
    return [(s.year, s.months_count, s.yearly_depreciation,
             s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]


@pytest.mark.parametrize("method", list(CAPEX_FNS))
@pytest.mark.parametrize("fye", FYES)
@pytest.mark.parametrize("k", INC_OFFSETS)
def test_capex_matches_reference(method, fye, k):
    """자본적지출(정액·정률) 슬림이 레퍼런스와 회계연도 1원 일치."""
    menum, fn = CAPEX_FNS[method]
    for cost in [10_000_000, 12_000_000, 7_000_000]:
        for life in [4, 5]:
            if k >= life * 12 - 1:
                continue
            for inc_amt in INC_AMTS:
                idx = (_CAPEX_ACQ[0] * 12 + _CAPEX_ACQ[1]) + k
                inc = (idx // 12, idx % 12 + 1)
                ref = _ref_capex_rows(menum, cost, life, _CAPEX_ACQ, inc_amt, inc, fye)
                got = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value)
                       for r in fn(cost, life, _CAPEX_ACQ[0], _CAPEX_ACQ[1],
                                   inc_amt, inc[0], inc[1], fye)]
                assert got == ref, (
                    f"{method} capex cost={cost} life={life} 결산월={fye} 증가={inc_amt}@k{k}\n"
                    f"  REF={ref}\n  GOT={got}")


DISPOSAL_FNS = {
    "straight_line": (DepreciationMethod.STRAIGHT_LINE, disposal.schedule_full_disposal),
    "declining_balance": (DepreciationMethod.DECLINING_BALANCE, disposal.schedule_full_disposal_declining),
}
DISP_OFFSETS = [3, 10, 18, 30, 45]   # 취득 후 양도 시점(개월)


def _ref_disposal_rows(method_enum, cost, life, acq, disp, fye):
    fin = AssetFinancials(cost=cost, life_in_years=life,
                          start_date=f"{acq[0]:04d}-{acq[1]:02d}-01", method=method_enum,
                          disposal_date=f"{disp[0]:04d}-{disp[1]:02d}-01")
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=fye)
    return [(s.year, s.months_count, s.yearly_depreciation,
             s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]


@pytest.mark.parametrize("method", list(DISPOSAL_FNS))
@pytest.mark.parametrize("fye", FYES)
@pytest.mark.parametrize("d", DISP_OFFSETS)
def test_full_disposal_matches_reference(method, fye, d):
    """전체양도(정액·정률) 슬림이 레퍼런스와 회계연도 1원 일치."""
    menum, fn = DISPOSAL_FNS[method]
    acq = (2026, 4)
    idx = (acq[0] * 12 + acq[1]) + d
    disp = (idx // 12, idx % 12 + 1)
    # core·vcore 모두 양도월 포함(더존식) → 동일 양도월 사용
    disp_v = disp
    for cost in [10_000_000, 12_000_000, 7_000_000]:
        for life in [4, 5]:
            ref = _ref_disposal_rows(menum, cost, life, acq, disp, fye)
            got = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value)
                   for r in fn(cost, life, acq[0], acq[1], disp_v[0], disp_v[1], fye)]
            assert got == ref, (
                f"{method} 전체양도 cost={cost} life={life} 결산월={fye} 양도={disp}(d={d})\n"
                f"  REF={ref}\n  GOT={got}")


PARTIAL_FNS = {
    "straight_line": (DepreciationMethod.STRAIGHT_LINE, disposal.schedule_partial_disposal),
    "declining_balance": (DepreciationMethod.DECLINING_BALANCE, disposal.schedule_partial_disposal_declining),
}
DISP_AMTS = [3_000_000, 5_000_000]


def _ref_partial_rows(method_enum, cost, life, acq, disp_amt, disp, fye):
    fin = AssetFinancials(cost=cost, life_in_years=life,
                          start_date=f"{acq[0]:04d}-{acq[1]:02d}-01", method=method_enum,
                          disposal_date=f"{disp[0]:04d}-{disp[1]:02d}-01", disposal_amount=disp_amt)
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=fye)
    return [(s.year, s.months_count, s.yearly_depreciation,
             s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]


@pytest.mark.parametrize("method", list(PARTIAL_FNS))
@pytest.mark.parametrize("fye", FYES)
@pytest.mark.parametrize("d", [10, 18, 30, 45])
def test_partial_disposal_matches_reference(method, fye, d):
    """부분양도(정액·정률) 슬림이 레퍼런스와 회계연도 1원 일치."""
    menum, fn = PARTIAL_FNS[method]
    acq = (2026, 4)
    idx = (acq[0] * 12 + acq[1]) + d
    disp = (idx // 12, idx % 12 + 1)
    # core·vcore 모두 양도월 포함(더존식) → 동일 양도월 사용
    disp_v = disp
    for cost in [10_000_000, 12_000_000]:
        for life in [4, 5]:
            if d >= life * 12:
                continue
            for damt in DISP_AMTS:
                ref = _ref_partial_rows(menum, cost, life, acq, damt, disp, fye)
                got = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value)
                       for r in fn(cost, life, acq[0], acq[1], damt, disp_v[0], disp_v[1], fye)]
                assert got == ref, (
                    f"{method} 부분양도 cost={cost} life={life} 결산월={fye} "
                    f"양도액={damt} 양도={disp}(d={d})\n  REF={ref}\n  GOT={got}")


@pytest.mark.parametrize("fye", FYES)
@pytest.mark.parametrize("life", [3, 4, 5, 6, 7, 9, 10])
def test_intangible_uses_byeolpyo4_rate(fye, life):
    """무형자산 = 별표4 정액 상각률 (= 유형 정액 슬림). 1/내용연수 직접 나눗셈 아님."""
    for cost in [12_000_000, 10_000_000, 7_000_000]:
        intang = intangible.schedule(cost, life, 2026, 4, fye)
        tangible = straight_line.schedule(cost, life, 2026, 4, fye)
        assert [(r.fiscal_year, r.depreciation, r.book_value) for r in intang] == \
               [(r.fiscal_year, r.depreciation, r.book_value) for r in tangible]


def test_intangible_byeolpyo4_differs_from_one_over_n():
    """6년(별표4=0.166≠1/6) 무형 상각액은 별표4 기준 — 1/n 직접나눗셈과 다름을 못박음."""
    rows = intangible.schedule(12_000_000, 6, 2026, 1, 12)   # 1월 취득 → 첫해 12개월
    # 별표4: round(12,000,000 × 0.166) = 1,992,000 (1/6 직접이면 2,000,000)
    assert rows[0].depreciation == 1_992_000


def test_final_book_value_is_memorandum():
    """모든 케이스에서 최종 장부가액 = 비망가 1,000원."""
    for _, mod in METHODS.values():
        for cost in COSTS:
            for life in LIVES:
                for fye in FYES:
                    rows = mod.schedule(cost, life, ACQ_YEAR, 4, fiscal_end_month=fye)
                    assert rows[-1].book_value == 1000
