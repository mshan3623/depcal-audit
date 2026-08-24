"""스케줄 구조 불변식 — 개별 골든값이 아니라 "어떤 입력에도 성립해야 하는 성질"을 넓게 건다.

손계산 골든은 특정 좌표의 정답을 고정하고, 이 파일은 좌표 사이의 빈 공간을 덮는다.
2026-07-25 정밀평가에서 골든이 촘촘한 실무 금액대(100만원↑)를 벗어난 소액 구간에
음수 상각 결함이 잠복해 있던 것이 계기다.

고정하는 불변식:
  1. 비망가 캡 — 상각액·누계는 음수일 수 없고, 장부가는 비망가 아래·취득원가 위로
     벗어날 수 없다. 종료 시 장부가 = 비망가.
  2. 연도별표 ↔ 월별표 정합 — 같은 벡터에서 나오므로 회계연도 집계가 완전히 같아야 한다
     (A-1 연간 로직 단일화의 게이트: 3중 구현을 capped_yearly로 합친 뒤에도 유지).
"""
import pytest

from vcore import declining_balance as db, straight_line as sl
from vcore.monthly_schedule import monthly_schedule
from vcore.projection import MEMORANDUM

_METHODS = [(sl, False), (db, True)]


def _assert_sound(rows, cost):
    """스케줄 1개가 비망가 캡 불변식을 만족하는지."""
    for r in rows:
        assert r.depreciation >= 0, f"음수 상각 {r}"
        assert r.accumulated >= 0, f"음수 누계 {r}"
        assert MEMORANDUM <= r.book_value <= cost, f"장부가 이탈 {r}"
    assert rows[-1].book_value == MEMORANDUM
    assert rows[-1].accumulated == cost - MEMORANDUM


@pytest.mark.parametrize("mod,_declining", _METHODS)
@pytest.mark.parametrize("life", [2, 5, 10, 20, 40, 60])
def test_memorandum_cap_holds_in_small_cost_band(mod, _declining, life):
    """소액 구간(비망가 바로 위 ~ 4만원) 전수 — 과거 음수 상각이 발화하던 대역.

    결함 경계 실측(2026-07-25): 정액 life10 ≤5,016 / life60 ≤40,000,
    정률 life10 ≤10,990. 캡이 `0 < remaining` 조건이라 비망가 도달 후 무력화된 탓.
    """
    for cost in range(MEMORANDUM + 1, 40_001, 97):
        _assert_sound(mod.schedule(cost, life, 2020, 1, 12), cost)


@pytest.mark.parametrize("mod,_declining", _METHODS)
@pytest.mark.parametrize("acq_month", [1, 6, 12])
def test_memorandum_cap_holds_in_practical_range(mod, _declining, acq_month):
    """실무 금액대 — 소액 수정이 정상 구간을 건드리지 않았음을 함께 고정."""
    for cost in (1_000_000, 12_345_678, 999_999_999):
        for life in (2, 5, 15, 40):
            _assert_sound(mod.schedule(cost, life, 2020, acq_month, 12), cost)


def _yearly_from_monthly(cal):
    rows, order = {}, []
    for c in cal:
        if c.year not in rows:
            rows[c.year] = [c.year, 0, 0, 0]
            order.append(c.year)
        r = rows[c.year]
        r[1] += c.amount
        r[2], r[3] = c.acc, c.book        # 회계연도 마지막 월의 누계·장부가
    return [tuple(rows[y]) for y in order]


@pytest.mark.parametrize("mod,declining", _METHODS)
@pytest.mark.parametrize("cost", [1_000_000, 3_333_333, 999_999_999])
def test_yearly_table_matches_monthly_table(mod, declining, cost):
    """연도별표 == 월별표 회계연도 집계 (내용연수 2~20 × 취득월 1~12 = 228 조합/파라미터).

    연도별표는 depverify가, 월별표는 상각명세서(엑셀)가 소비한다. 두 표가 갈리면
    "검증은 통과했는데 명세서 숫자가 다른" 상태가 되므로 구조적으로 고정한다.
    """
    for life in range(2, 21):
        for m in range(1, 13):
            yearly = [(r.fiscal_year, r.depreciation, r.accumulated, r.book_value)
                      for r in mod.schedule(cost, life, 2020, m, 12)]
            monthly = _yearly_from_monthly(
                monthly_schedule(cost, life, 2020, m, 12, declining))
            assert yearly == monthly, f"life={life} acq_month={m} 연/월 표 불일치"
