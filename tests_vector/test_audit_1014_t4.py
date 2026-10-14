"""감사 2026-10-14 T4 — 회귀망 보강.

1. M4: 소멸법인 최종 의제사업연도에도 §26⑥(5% 최초 도달 해에 잔존가액 정리)이 적용돼야 한다.
2. 뮤테이션 생존 6종(감사 M10) — 테스트가 닿지 않던 경계를 봉인한다.
"""
import pytest

from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod
from core.depreciation_engine import calculate_depreciation_enhanced, convert_common_data_to_financials
from vcore import declining_balance, disposal, intangible, straight_line
from vcore.monthly_schedule import monthly_events
from vcore.rate_table import STATUTORY_PERMILLE

from tests_vector.test_declining_five_percent_statute import EARLY, GRID, _statute

COST = 100_000_000
ACQ_YEAR = 2006


# ── M4: 소멸법인 최종기의 §26⑥ ─────────────────────────────────────────────

def _extinction_statute(life, acq_month, end_year, end_month):
    """소멸 의제사업연도의 문언 기대값 [(FY, 상각액)] — 12월 결산.

    그 전 해까지는 §26⑥ 참조모델로 검증된 연도별 표(`test_declining_five_percent_statute`).
    마지막 해: 상각범위액 = 기초 미상각잔액 × 상각률 × 월수 ÷ 12(§26⑧), 그 결과 미상각잔액이
    처음 취득가액의 5% 이하가 되면 잔존가액을 가산(§26⑥) — 의제사업연도도 사업연도다.
    """
    full = declining_balance.schedule(COST, life, ACQ_YEAR, acq_month)
    if (end_year, end_month) >= (full[-1].fiscal_year, 12) or end_year > full[-1].fiscal_year:
        return None                                    # 상각이 이미 끝난 뒤 — 이 테스트 밖
    prev = [r for r in full if r.fiscal_year < end_year]
    if end_year == full[-1].fiscal_year and end_month >= full[-1].months:
        return None                                    # 자연 종료월 이후 소멸 — 이 테스트 밖
    book = COST - (prev[-1].accumulated if prev else 0)
    _, permille = STATUTORY_PERMILLE[life]
    n = end_month - (acq_month - 1 if end_year == ACQ_YEAR else 0)
    dep = min(book * permille * n // 12000, book - 1000)
    if (book - dep) * 20 <= COST:
        dep = book - 1000
    return [(r.fiscal_year, r.depreciation) for r in prev] + [(end_year, dep)]


def test_extinction_settles_residual_in_short_final_year_when_crossing():
    """감사 재현 — 1억·20년·2020-01, 2039-11 소멸: 11개월 상각 후 4,963,880(4.96%) → 그 해에 정리."""
    rows = disposal.schedule_extinction_declining(COST, 20, 2020, 1, 2039, 11)
    assert (rows[-1].fiscal_year, rows[-1].book_value) == (2039, 1000)


def test_extinction_matches_statute_over_grid():
    bad, n = [], 0
    for life, acq_month in GRID:
        last = declining_balance.schedule(COST, life, ACQ_YEAR, acq_month)[-1].fiscal_year
        for end_year in (last - 1, last):
            for end_month in (1, 6, 11):
                exp = _extinction_statute(life, acq_month, end_year, end_month)
                if exp is None or end_year <= ACQ_YEAR:
                    continue
                n += 1
                got = [(r.fiscal_year, r.depreciation) for r in disposal.schedule_extinction_declining(
                    COST, life, ACQ_YEAR, acq_month, end_year, end_month)]
                if got != exp:
                    bad.append((life, acq_month, end_year, end_month, got[-1], exp[-1]))
    assert n > 3000
    assert bad == []


# ── 뮤테이션 생존 6종 봉인 (감사 M10) ──────────────────────────────────────


_INFO = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")


def _core(method, fye=12, **kw):
    r = calculate_depreciation_enhanced(AssetFinancials(method=method, **kw), _INFO,
                                        fiscal_year_end_month=fye)
    return [(s.year, s.yearly_depreciation) for s in r.yearly_summary]


# M06(vcore)·M26(core): 미상각잔액이 **정확히** 취득가액 5%인 해 — §26⑥ '이하'의 등호.
# 원가 20,000원은 비망가 1,000원이 곧 5%라 등호가 실제로 성립한다(정상 금액대에서는 탐색으로 못 찾음).
# `<`로 바뀌면 그 해에 끝나지 않고 상각 0원 꼬리 행이 내용연수 끝까지 붙는다.
EXACT_5PCT = [(43, 2), (45, 2), (46, 2), (46, 6)]


def test_vcore_settles_at_exact_five_percent():
    for life, m in EXACT_5PCT:
        got = [(r.fiscal_year, r.depreciation)
               for r in declining_balance.schedule(20_000, life, ACQ_YEAR, m)]
        assert got == _statute(20_000, life, m), (life, m)


def test_core_settles_at_exact_five_percent():
    for life, m in EXACT_5PCT:
        got = _core(DepreciationMethod.DECLINING_BALANCE, cost=20_000, life_in_years=life,
                    start_date=f"{ACQ_YEAR}-{m:02d}-15")
        assert got == _statute(20_000, life, m), (life, m)


# M14: 소멸 등기월 = 자연 종료월 — 짧은 사업연도 재계산이 아니라 자연 종료 스케줄 그대로.
def test_extinction_in_natural_final_month_is_the_natural_schedule():
    for life, m in ((3, 1), (5, 7), (7, 12)):
        natural = straight_line.schedule(12_345_678, life, 2020, m)
        end = (2020 * 12 + m - 1) + life * 12 - 1
        rows = disposal.schedule_extinction(12_345_678, life, 2020, m, end // 12, end % 12 + 1)
        assert [(r.fiscal_year, r.depreciation, r.book_value) for r in rows] == \
            [(r.fiscal_year, r.depreciation, r.book_value) for r in natural]


# M20: 개발비 연상각액 끝수 — 현 규약(4사5입) 고정. 끝수 규칙은 사용자 결정 ④ 대기(§26①6에 끝수 규정 없음).
def test_development_cost_annual_rounds_half_up_current_rule():
    rows = intangible.schedule_development_cost(200_000_000, 3, 2026, 1)
    assert rows[0].depreciation == 66_666_667          # 200,000,000 ÷ 3 = 66,666,666.67


# M27: core 분리자산(전기말 누계로 당기만)도 5% 교차 해에 정리 — vcore 분리자산·전체계산과 같다.
def test_core_separate_asset_settles_in_crossing_year():
    for life, m in EARLY[:15] + EARLY[-5:]:
        full = declining_balance.schedule(COST, life, ACQ_YEAR, m)
        last, prev = full[-1], full[-2]
        got = _core(DepreciationMethod.DECLINING_BALANCE, cost=COST, life_in_years=life,
                    start_date=f"{ACQ_YEAR}-{m:02d}-15", prior_accumulated=prev.accumulated,
                    target_year=last.fiscal_year)
        assert dict(got).get(last.fiscal_year) == last.depreciation, (life, m, got)


# M28: core 전기말 확정 + 부분양도 — 계산 모델이 따로 놀아 전체 계산과 갈렸다(종료해 59,000원 미흡수,
# 그 밖의 해 1~3원). 정답 규약이 없는 조합이라 거절한다. 무형은 종전에 전부양도로 조용히 흘렀다.


@pytest.mark.parametrize("method", [DepreciationMethod.STRAIGHT_LINE, DepreciationMethod.INTANGIBLE])
def test_core_partial_disposal_with_prior_is_rejected(method):
    kw = dict(cost=COST, life_in_years=3, start_date=f"{ACQ_YEAR}-01-15",
              disposal_amount=COST * 40 // 100, disposal_date="2008-04-15")
    assert _core(method, **kw)                               # 확정 누계 없으면 계산된다
    with pytest.raises(ValueError, match="전기말확정"):
        _core(method, prior_accumulated=66_600_000, target_year=2008, **kw)


# ── core 하(下) 결함 (감사 2026-10-14) ───────────────────────────────────────

def test_core_straight_line_separate_asset_equals_full_computation():
    """정액 분리자산(전기말 누계로 당기만) == 전체 계산의 당기 — 종료해 잔재 흡수 포함.

    종전 core는 종료해에 연상각액만 상각해 잔재(1억·3년: 99,000원)를 남겼다. vcore 분리자산과
    전체 계산은 잔재를 종료해에 흡수한다.
    """
    bad = []
    for life in (3, 5, 6, 7, 9, 14, 41):
        for m in (1, 2, 7, 12):
            full = straight_line.schedule(COST, life, ACQ_YEAR, m)
            for prev, row in zip(full, full[1:]):
                got = dict(_core(DepreciationMethod.STRAIGHT_LINE, cost=COST, life_in_years=life,
                                 start_date=f"{ACQ_YEAR}-{m:02d}-15",
                                 prior_accumulated=prev.accumulated, target_year=row.fiscal_year))
                if got.get(row.fiscal_year, 0) != row.depreciation:
                    bad.append((life, m, row.fiscal_year, got.get(row.fiscal_year), row.depreciation))
    assert bad == []


def _common(method):
    return {'asset_code': 'A001', 'asset_type': '유형자산', 'asset_name': '자산',
            'useful_life': 5, 'beginning_amount': COST, 'acquisition_date': '2020-04-15',
            'depreciation_method': method}


@pytest.mark.parametrize("method,expected", [
    ("정률법", DepreciationMethod.DECLINING_BALANCE), ("정률", DepreciationMethod.DECLINING_BALANCE),
    ("declining_balance", DepreciationMethod.DECLINING_BALANCE),
    ("정액법", DepreciationMethod.STRAIGHT_LINE), (" 정액 ", DepreciationMethod.STRAIGHT_LINE)])
def test_core_common_format_method_aliases(method, expected):
    fin, _, _ = convert_common_data_to_financials(_common(method))
    assert fin.method == expected


@pytest.mark.parametrize("method", ["", "DB", "정율법", "생산량비례법"])
def test_core_common_format_unknown_method_is_rejected_not_straight_line(method):
    """종전엔 '정률법' 부분일치가 아니면 전부 정액 — '정률'·공란·오타가 조용히 정액으로 계산됐다."""
    with pytest.raises(ValueError, match="상각방법"):
        convert_common_data_to_financials(_common(method))


# 자본적지출 + 양도: 부분양도 판정 기준 = 통합 취득원가(원가 + 증가액) — vcore `is_full_disposal`과 같다.
# 종전 core는 원래 원가와만 비교해 '원가 ≤ 양도액 < 원가+증가액'을 전부양도로 계산했다(판단 2벌).
# 무형 capex + 부분양도도 정액과 같이 vcore 실행 경로로 — 종전엔 core 2단계 루프로 1~2원 이탈(09-23 M7(b)).

_METHODS = [(DepreciationMethod.STRAIGHT_LINE, False), (DepreciationMethod.DECLINING_BALANCE, True),
            (DepreciationMethod.INTANGIBLE, False)]


@pytest.mark.parametrize("method,declining", _METHODS)
@pytest.mark.parametrize("disp_pct", [40, 100, 110])          # 원가 대비 — 100·110은 통합원가(130) 미만
def test_core_capex_then_disposal_matches_vcore(method, declining, disp_pct):
    cost, inc = 10_000_000, 3_000_000
    for life, m in ((5, 1), (7, 4), (9, 11)):
        kw = dict(cost=cost, life_in_years=life, start_date=f"2020-{m:02d}-15",
                  increase_amount=inc, increase_date="2021-03-15",
                  disposal_amount=cost * disp_pct // 100, disposal_date="2022-08-15")
        got = _core(method, **kw)
        cal = monthly_events(cost, life, 2020, m, 12, declining, inc=(inc, 2021, 3),
                             disp=(cost * disp_pct // 100, 2022, 8))
        exp = {}
        for c in cal:
            exp[c.fiscal_year] = exp.get(c.fiscal_year, 0) + c.amount
        assert got == sorted(exp.items()), (method, disp_pct, life, m)
