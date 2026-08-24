"""달력 매핑 월별 스케줄(vcore.monthly_schedule) 정합 가드.

월별 상세(엑셀 시트3)와 연도별 표(시트2)가 같은 값을 말해야 하므로,
월별 합계가 연도별 schedule_* 결과와 행 단위로 일치하는지 검증한다.
"""
import pytest

from vcore import declining_balance, disposal, straight_line, capex
from vcore.monthly_schedule import (
    monthly_schedule, monthly_with_increase, monthly_full_disposal, monthly_partial_disposal,
)

FYES = [12, 9, 6, 3, 1]


def _group_by_fy(cal_months, fye):
    """달력 월별 레코드를 회계연도(결산일 기준 연도 라벨)로 집계."""
    rows = {}
    order = []
    for m in cal_months:
        fy = m.year if m.month <= fye else m.year + 1
        if fy not in rows:
            rows[fy] = [0, 0, None, None]   # months, dep, acc, book
            order.append(fy)
        r = rows[fy]
        r[0] += 1
        r[1] += m.amount
        r[2], r[3] = m.acc, m.book
    return [(fy, *rows[fy]) for fy in order]


@pytest.mark.parametrize("declining", [False, True])
@pytest.mark.parametrize("fye", FYES)
@pytest.mark.parametrize("acq_month", range(1, 13))
def test_simple_monthly_matches_yearly(declining, fye, acq_month):
    """단순 시나리오: 월별 합계 == 연도별 schedule (전 결산월×취득월)."""
    cost, life = 12_000_000, 5
    cal = monthly_schedule(cost, life, 2026, acq_month, fye, declining)
    mod = declining_balance if declining else straight_line
    ref = mod.schedule(cost, life, 2026, acq_month, fye)
    got = _group_by_fy(cal, fye)
    exp = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in ref]
    assert got == exp


def test_calendar_labels():
    """첫 달 = 취득연월, 길이 = 내용연수 개월."""
    cal = monthly_schedule(10_000_000, 4, 2026, 4)
    assert (cal[0].year, cal[0].month) == (2026, 4)
    assert (cal[-1].year, cal[-1].month) == (2030, 3)
    assert len(cal) == 48


@pytest.mark.parametrize("declining", [False, True])
def test_capex_monthly_matches_yearly(declining):
    cost, life, inc = 10_000_000, 5, 3_000_000
    cal = monthly_with_increase(cost, life, 2026, 4, inc, 2027, 6, 12, declining)
    fn = capex.schedule_with_increase_declining if declining else capex.schedule_with_increase
    ref = fn(cost, life, 2026, 4, inc, 2027, 6, 12)
    exp = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in ref]
    assert _group_by_fy(cal, 12) == exp


@pytest.mark.parametrize("declining", [False, True])
def test_full_disposal_monthly_matches_yearly(declining):
    cost, life = 10_000_000, 5
    cal = monthly_full_disposal(cost, life, 2026, 4, 2028, 7, 12, declining)
    fn = disposal.schedule_full_disposal_declining if declining else disposal.schedule_full_disposal
    ref = fn(cost, life, 2026, 4, 2028, 7, 12)
    exp = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in ref]
    assert _group_by_fy(cal, 12) == exp
    assert (cal[-1].year, cal[-1].month) == (2028, 7)   # 양도월 포함(더존식)


@pytest.mark.parametrize("declining", [False, True])
def test_partial_disposal_monthly_matches_yearly(declining):
    cost, life, amt = 10_000_000, 5, 3_000_000
    cal = monthly_partial_disposal(cost, life, 2026, 4, amt, 2028, 7, 12, declining)
    fn = disposal.schedule_partial_disposal_declining if declining else disposal.schedule_partial_disposal
    ref = fn(cost, life, 2026, 4, amt, 2028, 7, 12)
    exp = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in ref]
    assert _group_by_fy(cal, 12) == exp


def _terminal_fy_amounts(cal, fye=12):
    """달력 월별에서 마지막(종료) 회계연도의 월 감가상각비 리스트."""
    rows = {}
    order = []
    for m in cal:
        fy = m.year if m.month <= fye else m.year + 1
        if fy not in rows:
            rows[fy] = []
            order.append(fy)
        rows[fy].append(m.amount)
    return rows[order[-1]]


@pytest.mark.parametrize("declining", [False, True])
def test_capex_terminal_year_no_dump(declining):
    """자본적지출 후 만기보유 시 종료해 월상각에 dump 스파이크가 없어야 한다.

    불변식: 어떤 취득가액 변동 사건이든 잔여표는 '연간액 확정→월할 균등→마지막달 보정'을
    따른다. 따라서 종료해 어떤 달도 다른 달의 2배를 넘지 않는다(정률 5% 잔재 dump 금지).
    """
    cost, life, inc = 100_000_000, 5, 30_000_000
    cal = monthly_with_increase(cost, life, 2025, 4, inc, 2026, 7, 12, declining)
    amts = _terminal_fy_amounts(cal)
    assert max(amts) <= 2 * min(amts), f"종료해 dump 스파이크: {amts}"


@pytest.mark.parametrize("declining", [False, True])
def test_partial_disposal_terminal_year_no_dump(declining):
    """부분양도 후 만기보유 시 종료해 월상각에 dump 스파이크가 없어야 한다."""
    cost, life, amt = 100_000_000, 5, 40_000_000
    cal = monthly_partial_disposal(cost, life, 2025, 4, amt, 2026, 7, 12, declining)
    amts = _terminal_fy_amounts(cal)
    assert max(amts) <= 2 * min(amts), f"종료해 dump 스파이크: {amts}"


def test_partial_disposal_after_natural_end_removes_disposed_portion():
    """자연종료(완전상각) 후 부분양도: 양도분 취득가액 안분 제거 + 잔존가액(비망가) 안분.

    비망가는 가치가 아닌 자산 단위 메모이므로, 자산 일부 처분 시 메모도 취득가액 비율로
    안분된다(30% 양도 → 잔류분 비망가 700). 추가 상각은 없고(상각 0) 양도 연도에 처분
    조정행을 더한다. 양도 전 구간은 자연상각 그대로(불변).
    """
    cost, life = 10_000_000, 4                      # 자연종료 2030-03 (2026-04 취득)
    rows = disposal.schedule_partial_disposal(cost, life, 2026, 4, 3_000_000, 2031, 6, 12)
    natural = straight_line.schedule(cost, life, 2026, 4, 12)
    # 양도 전(자연상각) 구간 불변
    assert [(r.fiscal_year, r.depreciation, r.book_value) for r in rows[:-1]] == \
           [(r.fiscal_year, r.depreciation, r.book_value) for r in natural]
    # 양도 연도(2031) 처분 조정행: 상각 0, 양도분 안분 제거
    adj = rows[-1]
    assert adj.fiscal_year == 2031
    assert adj.depreciation == 0
    assert adj.accumulated == 6_999_300            # 9,999,000 − round(9,999,000×0.3)
    assert adj.book_value == 700                   # 1,000 × 잔류 70% (비망가 안분)
