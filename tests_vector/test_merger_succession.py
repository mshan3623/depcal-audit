"""합병 승계자산 — 소멸법인(등기월까지) + 존속법인(다음 달부터)의 월수 이음매.

시행령 문언대로면 §26⑧⑨의 "1월 미만의 일수는 1월로 한다"가 양쪽에 각각 걸려 등기월이
중복 계산된다(합산 13개월). 이 저장소는 중복을 배제하는 쪽을 택했다(사용자 결정,
2026-08-27) — 그 결정이 코드에서 흔들리지 않도록 이음매를 불변식으로 고정한다.
"""
import pytest

from vcore.disposal import schedule_full_disposal
from vcore.separate_asset import schedule_merger_succession, schedule_separate_asset
from vcore.straight_line import annual_depreciation, schedule

COST, LIFE, ACQ_Y, ACQ_M = 12_000_000, 5, 2024, 5      # 연 상각 2,400,000


def _split(merger_year, merger_month, cost=COST, life=LIFE,
           acq_y=ACQ_Y, acq_m=ACQ_M):
    """(소멸법인 최종 회계연도 행, 존속법인 승계연도 행 리스트)."""
    gone = schedule_full_disposal(cost, life, acq_y, acq_m, merger_year, merger_month, 12)
    last = gone[-1]
    kept = schedule_merger_succession(cost, life, acq_y, acq_m, last.accumulated,
                                      merger_year, merger_month, merger_year)
    return last, kept


def test_merger_month_is_not_counted_twice():
    """등기월은 소멸법인에만 — 두 법인 월수 합이 그해 12개월."""
    for merger_month in range(1, 12):
        last, kept = _split(2026, merger_month)
        assert last.months == merger_month
        assert kept[0].months == 12 - merger_month


def test_split_year_total_equals_single_company_amount():
    """쪼개도 그해 상각액 합은 단일 법인이었을 때와 같다(월할 절사 2회로 최대 1원 부족)."""
    solo = next(r for r in schedule(COST, LIFE, ACQ_Y, ACQ_M) if r.fiscal_year == 2026)
    for merger_month in range(1, 12):
        last, kept = _split(2026, merger_month)
        total = last.depreciation + kept[0].depreciation
        assert solo.depreciation - 1 <= total <= solo.depreciation


def test_headline_case_2026_05():
    """2026-05 합병: 소멸 5개월 1,000,000 + 존속 7개월 1,400,000 = 연 2,400,000."""
    last, kept = _split(2026, 5)
    assert (last.months, last.depreciation) == (5, 1_000_000)
    assert (kept[0].months, kept[0].depreciation) == (7, 1_400_000)
    assert last.depreciation + kept[0].depreciation == annual_depreciation(COST, LIFE)


def test_december_merger_leaves_nothing_for_survivor():
    """12월 등기: 그해는 소멸법인이 전부 상각 — 존속법인 몫 없음."""
    assert _split(2026, 12)[1] == []


def test_year_after_merger_is_a_full_year():
    """승계 다음 해부터는 평년 12개월 — 누계는 승계분을 이어받는다."""
    last, kept = _split(2026, 5)
    nxt = schedule_merger_succession(COST, LIFE, ACQ_Y, ACQ_M, kept[0].accumulated,
                                     2026, 5, 2027)
    assert nxt[0].months == 12
    assert nxt[0].accumulated == kept[0].accumulated + nxt[0].depreciation


def test_entry_after_depreciation_ended_yields_nothing():
    """종료해의 상각 가능 월(취득월−1)을 지나 승계하면 그해 상각분이 없다."""
    # 2024-05 취득·5년 → 종료해 2029, 상각 가능 월은 1~4월.
    assert schedule_merger_succession(COST, LIFE, ACQ_Y, ACQ_M, 0, 2029, 6, 2029) == []


def test_start_month_default_keeps_existing_behavior():
    """start_month 기본값(1)은 기존 분리자산 경로를 바꾸지 않는다."""
    base = schedule_separate_asset(COST, LIFE, ACQ_Y, ACQ_M, 3_000_000, 2026)
    assert schedule_separate_asset(COST, LIFE, ACQ_Y, ACQ_M, 3_000_000, 2026,
                                   start_month=1) == base
    assert base[0].months == 12


@pytest.mark.parametrize("bad", [0, 13])
def test_start_month_out_of_range_raises(bad):
    with pytest.raises(ValueError):
        schedule_separate_asset(COST, LIFE, ACQ_Y, ACQ_M, 0, 2026, start_month=bad)
