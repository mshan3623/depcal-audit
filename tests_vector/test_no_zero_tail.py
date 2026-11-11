"""정액 스케줄은 상각이 끝나는 해에서 끝난다 — 상각액 0인 꼬리 행이 없다 (INC-11 판정 2026-11-12).

별표4 정액률은 소수 셋째 자리라 상각률 × 내용연수 > 1인 연수가 35개 있다(30년: 0.034 × 30 = 1.02).
이런 연수는 내용연수 종료 전에 장부가가 비망가에 닿는다. 종전에는 내용연수 끝까지 0원 행을 붙였다
(취득월에 따라 1~24개월). 정률의 5% 교차 해 종료·분리자산 경로의 `[]`와 같은 규칙으로 통일한다.
연도별 상각액·누계·장부가는 바뀌지 않는다.
"""
import logging

import pytest

from vcore import capex, disposal, separate_asset, straight_line
from vcore.monthly_schedule import monthly_events, monthly_schedule
from vcore.rate_table import STATUTORY_PERMILLE

COST = 100_000_000
OVER = [n for n in range(2, 61) if STATUTORY_PERMILLE[n][0] * n > 1000]


def test_thirty_five_lives_complete_before_useful_life_ends():
    assert len(OVER) == 35 and {30, 41, 52} <= set(OVER) and not {5, 20, 40} & set(OVER)


@pytest.mark.parametrize("life", range(2, 61))
def test_straight_line_has_no_zero_rows_and_same_yearly_amounts(life):
    annual = straight_line.annual_depreciation(COST, life)
    for acq_month in range(1, 13):
        for fye in (3, 12):
            rows = straight_line.schedule(COST, life, 2026, acq_month, fye)
            assert all(r.depreciation > 0 for r in rows)
            assert rows[-1].book_value == 1000 and sum(r.depreciation for r in rows) == COST - 1000
            book = COST
            for r in rows[:-1]:                        # 평년: min(연 상각액 월할, 비망가까지 남은 금액)
                assert r.depreciation == min(annual * r.months // 12, book - 1000)
                book -= r.depreciation
            by_fy = {}
            for m in monthly_schedule(COST, life, 2026, acq_month, fye):
                by_fy[m.fiscal_year] = by_fy.get(m.fiscal_year, 0) + m.amount
            assert sorted(by_fy.items()) == [(r.fiscal_year, r.depreciation) for r in rows]


def test_pins_30_and_52_years():
    """30년·3월 취득: 종전 FY2056 2개월 0원 행. 52년·1월 취득: 종전 FY2076·2077 0원 행 2개."""
    assert [(r.fiscal_year, r.depreciation, r.book_value)
            for r in straight_line.schedule(COST, 30, 2026, 3)[-2:]] == \
        [(2054, 3_400_000, 1_966_667), (2055, 1_965_667, 1000)]
    assert [(r.fiscal_year, r.depreciation, r.book_value)
            for r in straight_line.schedule(COST, 52, 2026, 1)[-2:]] == \
        [(2074, 2_000_000, 2_000_000), (2075, 1_999_000, 1000)]


def test_capex_after_completion_is_rejected_not_deferred():
    """종전: 0원 구간의 자본적지출이 한 해 동안 상각되지 않다가 다음 해에 몰렸다
    (FY2076 0원·장부 10,001,000 → FY2077 10,000,000). 상각 종료 후 지출은 정률과 같이 거절한다."""
    with pytest.raises(ValueError, match="내용연수 종료 이후"):
        capex.schedule_with_increase(COST, 52, 2026, 1, 10_000_000, 2076, 3)
    with pytest.raises(ValueError, match="내용연수 종료 이후"):
        monthly_events(COST, 52, 2026, 1, inc=(10_000_000, 2076, 3))


def test_disposals_after_completion_follow_the_after_end_rules():
    full = disposal.schedule_full_disposal(COST, 41, 2026, 1, 2066, 3)
    assert (full[-1].fiscal_year, full[-1].book_value) == (2065, 1000)      # 0원 양도 행 없음
    part = disposal.schedule_partial_disposal(COST, 41, 2026, 1, 20_000_000, 2066, 3)
    assert (part[-1].fiscal_year, part[-1].depreciation, part[-1].book_value) == (2066, 0, 800)


def test_matches_separate_asset_path():
    """분리자산 경로는 같은 상황에서 처음부터 `[]`였다 — 이제 일반 경로도 그 해에 행이 없다."""
    assert separate_asset.schedule_separate_asset(COST, 41, 2026, 1, COST - 1000, 2066) == []
    assert all(r.fiscal_year != 2066 for r in straight_line.schedule(COST, 41, 2026, 1))


# ── core 거울 ───────────────────────────────────────────────────────────────
from core.depreciation_engine import calculate_depreciation_enhanced  # noqa: E402
from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod  # noqa: E402

_INFO = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")


def _core(cost, life, acq_month, fye, declining=False, **ev):
    logging.disable(logging.CRITICAL)
    try:
        fin = AssetFinancials(cost=cost, life_in_years=life, start_date=f"2026-{acq_month:02d}-15",
                              method=(DepreciationMethod.DECLINING_BALANCE if declining
                                      else DepreciationMethod.STRAIGHT_LINE), **ev)
        return calculate_depreciation_enhanced(fin, _INFO, fiscal_year_end_month=fye)
    finally:
        logging.disable(logging.NOTSET)


@pytest.mark.parametrize("life", OVER)
def test_core_mirror_has_no_zero_tail(life):
    for acq_month in (1, 3, 7):
        core = [(m.year, m.month, m.numeric_depreciation, m.accumulated_depreciation, m.book_value)
                for m in _core(COST, life, acq_month, 12).schedule]
        got = [(m.year, m.month, m.amount, m.acc, m.book)
               for m in monthly_schedule(COST, life, 2026, acq_month)]
        assert core == got


@pytest.mark.parametrize("declining", [False, True], ids=["정액", "정률"])
@pytest.mark.parametrize("disp", [(2031, 3), (2031, 8), (2032, 2)],
                         ids=["종료월", "종료해 같은 회계연도", "다음 회계연도"])
def test_core_mirror_partial_disposal_at_or_after_completion(declining, disp):
    """core는 종료월 부분양도를 무흔적으로 버리고(`>` 비교), 종료해와 같은 회계연도의 양도는 행을
    둘로 냈다. vcore는 각각 P-d MED-4·감사 G10에서 고쳤는데 core 거울이 빠져 있었다 —
    5년 자산에서도 재현되던 기존 결함(INC-27)."""
    fn = disposal.schedule_partial_disposal_declining if declining else disposal.schedule_partial_disposal
    got = [(r.fiscal_year, r.depreciation, r.accumulated, r.book_value)
           for r in fn(10_000_000, 5, 2026, 4, 4_000_000, *disp)]
    core = [(s.year, s.yearly_depreciation, s.accumulated_depreciation, s.ending_book_value)
            for s in _core(10_000_000, 5, 4, 12, declining, disposal_date=f"{disp[0]}-{disp[1]:02d}-01",
                           disposal_amount=4_000_000).yearly_summary]
    assert core == got
    assert got[-1][3] == 600 and len({r[0] for r in got}) == len(got)


def test_open_question_midyear_disposal_in_completion_year():
    """미판정(INC-28): 상각이 끝나는 해의 중도 전부양도.

    41년·7월 취득은 FY2066에 잔액 1,249,000원을 상각하고 끝난다. 엔진은 그 금액을 12개월에 고르게
    나누므로 3월 양도 시 312,249원이다. 평년 월할(2,500,000 × 3 ÷ 12 = 625,000, 잔액 한도 내)로
    보는 해석이 문언에 더 가까워 보이나 더존 실측이 없다. **현 동작을 정답으로 굳히지 않고** 두 값이
    갈린다는 사실만 고정한다 — 30년 건물 정액 실대장이 오면 판정한다.
    """
    row = disposal.schedule_full_disposal(COST, 41, 2026, 7, 2066, 3)[-1]
    by_even_split = 1_249_000 // 12 * 3
    by_ordinary_rate = 2_500_000 * 3 // 12
    assert (row.fiscal_year, row.months) == (2066, 3)
    assert by_even_split == 312_249 and by_ordinary_rate == 625_000
    assert row.depreciation in (by_even_split, by_ordinary_rate)
