"""정률법 5% 교차 판정의 기준 = **이벤트 후** 취득가액 (INC-18).

§26⑥: 잔존가액(취득가액 5%)은 미상각잔액이 최초로 **취득가액**의 5% 이하가 되는 사업연도에 가산한다.
§72⑤2: 자본적 지출이 있으면 "그 금액을 가산한 금액"이 취득가액이다. 부분양도 후 잔존 자산의
취득가액은 양도분을 뺀 금액이다.

INC-16은 교차 해를 **증가 전 원가**로 정한 base 벡터를 이벤트 경로가 그대로 스케일하게 만들었다.
자본적지출로 장부가가 커져도 base가 이미 잘려 있어, 통합 취득가액의 5%를 넘는 잔액을 한 해
먼저 일괄 정리했다(1억·20년 + 3천만: FY2039 7,609,815 — 정답은 FY2039 1,065,512, FY2040 정리).

오라클: 같은 엔진에서 5% 규칙만 끈 결과(이벤트 스케일 로직은 공유)에, 회계연도 말 장부가와
그 시점 취득가액으로 '최초 교차 해 정리'를 연 단위로 적용한 것. 교차 판정만 독립으로 검증한다.
"""
import pytest

from vcore import capex, disposal, monthly
from vcore.monthly_schedule import monthly_events
from vcore.projection import standard_month_counts

from tests_vector.test_declining_five_percent_statute import EARLY

COST = 100_000_000
ACQ_YEAR = 2006


def _ym(acq_month: int, k: int):
    """취득 후 k개월째의 (연, 월)."""
    t = ACQ_YEAR * 12 + (acq_month - 1) + k
    return t // 12, t % 12 + 1


def _rule_off(monkeypatch):
    """5% 교차 절단을 끈다 — 내용연수 종료해에만 정리(INC-16 이전 동작)."""
    monkeypatch.setattr(monthly, "db_month_counts",
                        lambda cost, life, m: standard_month_counts(m, life))
    monkeypatch.setattr(monthly, "cut_at_five_percent", lambda months, bases: months,
                        raising=False)


def _expected(rows_off, basis_at_fy):
    """규칙을 끈 연도별 표에 §26⑥ 최초 교차 해 정리를 적용한 기대값 [(FY, 상각액)]."""
    out, book = [], None
    for i, r in enumerate(rows_off):
        start = r.book_value + r.depreciation if book is None else book
        if i < len(rows_off) - 1 and r.book_value * 20 <= basis_at_fy(r.fiscal_year):
            out.append((r.fiscal_year, start - 1000))
            return out
        out.append((r.fiscal_year, r.depreciation))
        book = r.book_value
    return out


def _after(dy, dm, new, old):
    """양도월(dy-dm) 익월부터 새 취득가액. 12월 결산이라 FY 라벨 = 달력연도 — 양도월이 결산월이면
    그 해 말은 아직 종전 기준이다."""
    return lambda fy: new if (fy > dy or (fy == dy and dm < 12)) else old


def _yearly_pairs(rows):
    return [(r.fiscal_year, r.depreciation) for r in rows]


def test_capex_golden_settles_at_useful_life_end_not_early():
    """증가 후 FY2039 잔액 6,545,303은 통합 취득가액 1.3억의 5%(6,500,000) 초과 → FY2040에 정리."""
    rows = capex.schedule_with_increase_declining(100_000_000, 20, 2020, 2, 30_000_000, 2020, 7)
    assert [(r.fiscal_year, r.depreciation, r.book_value) for r in rows[-2:]] == \
        [(2039, 1_065_512, 6_545_303), (2040, 6_544_303, 1000)]


INC_RATIOS = (10, 30, 100)          # 원가 대비 증가액 %


@pytest.mark.parametrize("life,acq_month", EARLY)
@pytest.mark.parametrize("pct", INC_RATIOS)
def test_capex_crossing_uses_cost_plus_increase(monkeypatch, life, acq_month, pct):
    inc = COST * pct // 100
    iy, im = _ym(acq_month, 6)
    got = capex.schedule_with_increase_declining(COST, life, ACQ_YEAR, acq_month, inc, iy, im)
    for r in got[:-1]:                              # 조기 정리 금지: 비종료 해는 5% 초과여야 한다
        assert r.book_value * 20 > COST + inc, (r, COST + inc)
    with monkeypatch.context() as mp:
        _rule_off(mp)
        off = capex.schedule_with_increase_declining(COST, life, ACQ_YEAR, acq_month, inc, iy, im)
    assert _yearly_pairs(got) == _expected(off, lambda fy: COST + inc)


DISP_RATIOS = (30, 60)              # 원가 대비 양도액 %


@pytest.mark.parametrize("life,acq_month", EARLY)
@pytest.mark.parametrize("pct", DISP_RATIOS)
def test_partial_disposal_crossing_uses_remaining_cost(monkeypatch, life, acq_month, pct):
    d_amt = COST * pct // 100
    dy, dm = _ym(acq_month, 18)
    got = disposal.schedule_partial_disposal_declining(COST, life, ACQ_YEAR, acq_month, d_amt, dy, dm)
    with monkeypatch.context() as mp:
        _rule_off(mp)
        off = disposal.schedule_partial_disposal_declining(COST, life, ACQ_YEAR, acq_month,
                                                           d_amt, dy, dm)
    assert _yearly_pairs(got) == _expected(off, _after(dy, dm, COST - d_amt, COST))


def _events_by_fy(months):
    by = {}
    for m in months:
        by[m.fiscal_year] = by.get(m.fiscal_year, 0) + m.amount
    return sorted(by.items())


@pytest.mark.parametrize("life,acq_month", EARLY)
def test_monthly_events_capex_then_partial_disposal(monkeypatch, life, acq_month):
    """실행 경로(엑셀 상세표): 증가 → 부분양도. 기준 = 원가 → 원가+증가 → 그 뒤 잔존 취득가액."""
    inc, d_amt = COST * 30 // 100, COST * 40 // 100
    iy, im = _ym(acq_month, 6)
    dy, dm = _ym(acq_month, 30)
    kw = dict(declining=True, inc=(inc, iy, im), disp=(d_amt, dy, dm))
    got = monthly_events(COST, life, ACQ_YEAR, acq_month, **kw)
    with monkeypatch.context() as mp:
        _rule_off(mp)
        off = monthly_events(COST, life, ACQ_YEAR, acq_month, **kw)
    off_rows = [_Row(fy, dep, book) for fy, dep, book in _fy_rows(off)]
    assert _events_by_fy(got) == _expected(off_rows, _after(dy, dm, COST + inc - d_amt, COST + inc))


class _Row:
    def __init__(self, fy, dep, book):
        self.fiscal_year, self.depreciation, self.book_value = fy, dep, book


def _fy_rows(months):
    rows = {}
    for m in months:
        dep, _ = rows.get(m.fiscal_year, (0, None))
        rows[m.fiscal_year] = (dep + m.amount, m.book)
    return [(fy, dep, book) for fy, (dep, book) in sorted(rows.items())]


@pytest.mark.parametrize("life,acq_month", EARLY[:10])
def test_no_event_paths_unchanged(life, acq_month):
    """이벤트 없는 정률 월별은 INC-16 동작 그대로 — 절단 함수가 원가 단일 구간에서 같은 결과."""
    natural = monthly.db_monthly(COST, life, acq_month)
    recut = monthly.cut_at_five_percent(monthly.db_monthly_uncut(COST, life, acq_month), [(0, COST)])
    assert [(m.fy_index, m.amount, m.acc, m.book) for m in recut] == \
        [(m.fy_index, m.amount, m.acc, m.book) for m in natural]


# ── core 오라클 거울 — core도 INC-16에서 같은 해석(원가 기준)을 공유해 미러 대조가 결함을 가렸다 ──

def _core_yearly(**kw):
    from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod
    from core.depreciation_engine import calculate_depreciation_enhanced
    fin = AssetFinancials(method=DepreciationMethod.DECLINING_BALANCE, **kw)
    r = calculate_depreciation_enhanced(fin, AssetInfo(asset_id="A", asset_name="자산",
                                                       asset_category="비품"),
                                        fiscal_year_end_month=12)
    return [(s.year, s.yearly_depreciation) for s in r.yearly_summary]


def test_core_capex_golden():
    got = _core_yearly(cost=100_000_000, life_in_years=20, start_date="2020-02-15",
                       increase_amount=30_000_000, increase_date="2020-07-15")
    assert got[-2:] == [(2039, 1_065_512), (2040, 6_544_303)]


@pytest.mark.parametrize("life,acq_month", EARLY)
@pytest.mark.parametrize("pct", INC_RATIOS)
def test_core_capex_matches_vcore(life, acq_month, pct):
    inc = COST * pct // 100
    iy, im = _ym(acq_month, 6)
    core = _core_yearly(cost=COST, life_in_years=life, start_date=f"{ACQ_YEAR}-{acq_month:02d}-15",
                        increase_amount=inc, increase_date=f"{iy}-{im:02d}-15")
    v = capex.schedule_with_increase_declining(COST, life, ACQ_YEAR, acq_month, inc, iy, im)
    assert core == _yearly_pairs(v)


@pytest.mark.parametrize("life,acq_month", EARLY)
@pytest.mark.parametrize("pct", DISP_RATIOS)
def test_core_partial_disposal_matches_vcore(life, acq_month, pct):
    d_amt = COST * pct // 100
    dy, dm = _ym(acq_month, 18)
    core = _core_yearly(cost=COST, life_in_years=life, start_date=f"{ACQ_YEAR}-{acq_month:02d}-15",
                        disposal_amount=d_amt, disposal_date=f"{dy}-{dm:02d}-15")
    v = disposal.schedule_partial_disposal_declining(COST, life, ACQ_YEAR, acq_month, d_amt, dy, dm)
    assert core == _yearly_pairs(v)
