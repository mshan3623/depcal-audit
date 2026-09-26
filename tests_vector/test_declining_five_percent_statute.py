"""정률법 잔존가액 가산 연도 — 시행령 §26⑥ 문언 참조모델.

§26⑥: 정률법 잔존가액(취득가액 5%)은 "미상각잔액이 **최초로** 취득가액의 100분의 5 이하가
되는 사업연도의 상각범위액에 가산"한다. 엔진은 이를 '내용연수 종료해'로 대신했는데, 둘은
5년에서만 항상 같은 해다. 종료해가 짧은 꼬리면(20년·둘째 달 취득 → 1개월) 직전 해에 이미
5% 이하가 되어, 708조합(2~60년 × 취득월 1~12) 중 139개에서 1년 늦게 정리했다
(외부 평가 2026-09-26. core·vcore·테스트 1,615건이 같은 해석을 공유해 대조로는 안 잡혔다).

참조모델은 엔진 코드를 쓰지 않는다 — 별표4 1000분율(법령 PDF 대조로 따로 고정된 표)만 빌린다.
내용연수 종료해에 5%를 넘어도 종료해에 정리하는 것은 문언이 아니라 더존 실측(B사 40건)
기준이며, 참조모델도 그 규칙을 둔다.
"""
import pytest

from vcore import declining_balance, disposal, separate_asset
from vcore.monthly_schedule import monthly_schedule
from vcore.rate_table import STATUTORY_PERMILLE
from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod
from core.depreciation_engine import calculate_depreciation_enhanced

COST = 100_000_000
ACQ_YEAR = 2006
LIVES = sorted(STATUTORY_PERMILLE)


def _statute(cost: int, life: int, acq_month: int):
    """§26⑥ 문언 그대로의 연도별 상각액 (12월 결산, 첫해 = 취득연도)."""
    _, permille = STATUTORY_PERMILLE[life]
    total = life * 12
    counts = [13 - acq_month]
    while sum(counts) < total:
        counts.append(min(12, total - sum(counts)))
    out, book = [], cost
    for i, months in enumerate(counts):
        dep = min(book * permille * months // 12000, book - 1000)
        if (book - dep) * 100 <= cost * 5 or i == len(counts) - 1:
            dep = book - 1000                         # 5% 이하 최초 도달 해(또는 종료해)에 잔액 전부
        out.append((ACQ_YEAR + i, dep))
        book -= dep
        if book == 1000:
            break
    return out


GRID = [(life, m) for life in LIVES for m in range(1, 13)]


def _fiscal_years_in_life(life: int, acq_month: int) -> int:
    rest = life * 12 - (13 - acq_month)
    return 1 + (rest + 11) // 12


EARLY = [(life, m) for life, m in GRID
         if len(_statute(COST, life, m)) < _fiscal_years_in_life(life, m)]


def test_reference_model_flags_the_evaluated_139_combos():
    """참조모델이 조기 종료로 판정하는 조합 = 평가서 139개 (≤25년은 20·22·23·24년 × 2월)."""
    assert len(GRID) == 708
    assert len(EARLY) == 139
    assert [c for c in EARLY if c[0] <= 25] == [(20, 2), (22, 2), (23, 2), (24, 2)]


@pytest.mark.parametrize("life,acq_month", GRID)
def test_vcore_yearly_matches_statute(life, acq_month):
    got = [(r.fiscal_year, r.depreciation)
           for r in declining_balance.schedule(COST, life, ACQ_YEAR, acq_month)]
    assert got == _statute(COST, life, acq_month)


@pytest.mark.parametrize("life,acq_month", EARLY)
def test_monthly_schedule_agrees_with_yearly(life, acq_month):
    """월별 스케줄(엑셀 상세표)도 같은 해에 끝나고, 연도로 묶으면 연도별 표와 같다."""
    months = monthly_schedule(COST, life, ACQ_YEAR, acq_month, declining=True)
    by_fy = {}
    for m in months:
        by_fy[m.fiscal_year] = by_fy.get(m.fiscal_year, 0) + m.amount
    assert sorted(by_fy.items()) == _statute(COST, life, acq_month)
    assert months[-1].book == 1000


@pytest.mark.parametrize("life,acq_month", EARLY)
def test_core_matches_statute(life, acq_month):
    fin = AssetFinancials(cost=COST, life_in_years=life, start_date=f"{ACQ_YEAR}-{acq_month:02d}-15",
                          method=DepreciationMethod.DECLINING_BALANCE)
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=12)
    assert [(s.year, s.yearly_depreciation) for s in r.yearly_summary] == \
        _statute(COST, life, acq_month)


def test_evaluator_example_structure_20_years():
    """구축물 1억·20년·2006-02: FY2025 기초 5,771,954 → 정상상각 808,073 후 4,963,881(4.96%)."""
    rows = declining_balance.schedule(COST, 20, ACQ_YEAR, 2)
    assert (rows[-1].fiscal_year, rows[-1].depreciation, rows[-1].book_value) == \
        (2025, 5_770_954, 1000)


@pytest.mark.parametrize("life,acq_month", EARLY[:20] + EARLY[-5:])
def test_separate_asset_year_equals_full_schedule(life, acq_month):
    """분리자산(전기말 누계로 당기만 계산)도 5% 교차 해에 정리하고 그 다음 해는 [] (당기 == 전체계산 당기)."""
    full = declining_balance.schedule(COST, life, ACQ_YEAR, acq_month)
    last, prev = full[-1], full[-2]
    got = separate_asset.schedule_separate_asset(COST, life, ACQ_YEAR, acq_month,
                                                 prev.accumulated, last.fiscal_year, declining=True)
    assert [(r.fiscal_year, r.depreciation, r.book_value) for r in got] == \
        [(last.fiscal_year, last.depreciation, 1000)]
    assert separate_asset.schedule_separate_asset(COST, life, ACQ_YEAR, acq_month,
                                                  last.accumulated, last.fiscal_year + 1,
                                                  declining=True) == []


def test_partial_disposal_in_crossing_year_last_month_is_not_ignored():
    """5% 교차로 당겨진 종료월(2025-12)에 부분양도 → 그 해 행에 잔류분 분배가 반영돼야 한다.

    종전 판정 `d >= life*12 - 1`은 내용연수 종료월(2026-01)만 자연종료로 봐, 당겨진 종료월의
    양도가 아무 흔적 없이 사라졌다(조용한 무시).
    """
    rows = disposal.schedule_partial_disposal_declining(COST, 20, ACQ_YEAR, 2,
                                                        60_000_000, 2025, 12)
    last = rows[-1]
    assert (last.fiscal_year, last.book_value) == (2025, 400)      # 비망 1,000 × 잔류 40%
