"""정률 분리자산(prior_accumulated) 회귀 가드.

분리자산 = 전기말 누계만 알고 당기만 계산하는 경로(기중 인수/시스템 이전). 과거 정률은
prior_accumulated를 조용히 무시하고 전체 스케줄을 반환하는 버그가 있었다(2026-06-16 수정).

불변식: 분리자산 당기 결과 == 전체 계산의 해당 연도 (전년말 누계를 prior로 주면). 전체
계산은 손계산 골든(test_declining_golden_handcalc)으로 검증됐으므로 이게 외부기준 가드다.
"""
import pytest

from core.depreciation_engine import calculate_depreciation_enhanced
from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod
from vcore import separate_asset

_INFO = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
COST, LIFE = 10_000_000, 5


def _full_yearly():
    r = calculate_depreciation_enhanced(
        AssetFinancials(cost=COST, life_in_years=LIFE, start_date="2026-01-15",
                        method=DepreciationMethod.DECLINING_BALANCE),
        _INFO, fiscal_year_end_month=12)
    return {s.year: (s.yearly_depreciation, s.accumulated_depreciation, s.ending_book_value)
            for s in r.yearly_summary}


@pytest.mark.parametrize("year", [2027, 2028, 2029, 2030])
def test_declining_separate_asset_matches_full_schedule(year):
    """정률 분리자산 당기 == 전체 계산 당기 (전년말 누계를 prior로). 종료해(2030) 포함."""
    full = _full_yearly()
    prior = full[year - 1][1]                          # 전년말 누계
    r = calculate_depreciation_enhanced(
        AssetFinancials(cost=COST, life_in_years=LIFE, start_date="2026-01-15",
                        method=DepreciationMethod.DECLINING_BALANCE,
                        prior_accumulated=prior, target_year=year),
        _INFO, fiscal_year_end_month=12)
    got = [(s.year, s.yearly_depreciation, s.accumulated_depreciation, s.ending_book_value)
           for s in r.yearly_summary]
    assert got == [(year, *full[year])]


def test_declining_separate_asset_not_silently_ignored():
    """과거 버그(전체 스케줄 반환) 회귀 가드: 분리자산은 당기 1행만."""
    r = calculate_depreciation_enhanced(
        AssetFinancials(cost=COST, life_in_years=LIFE, start_date="2026-01-15",
                        method=DepreciationMethod.DECLINING_BALANCE,
                        prior_accumulated=6_985_990, target_year=2028),
        _INFO, fiscal_year_end_month=12)
    assert len(r.yearly_summary) == 1
    assert r.yearly_summary[0].year == 2028


def test_declining_separate_asset_non_december_rejected():
    """분리자산 정률도 정액과 동일하게 비-12월 결산은 미지원(ValueError → 빈 결과)."""
    r = calculate_depreciation_enhanced(
        AssetFinancials(cost=COST, life_in_years=LIFE, start_date="2026-01-15",
                        method=DepreciationMethod.DECLINING_BALANCE,
                        prior_accumulated=4_000_000, target_year=2028),
        _INFO, fiscal_year_end_month=3)
    assert len(r.schedule) == 0                        # 가드 발화 → 빈 스케줄


def _full_yearly_method(declining):
    m = DepreciationMethod.DECLINING_BALANCE if declining else DepreciationMethod.STRAIGHT_LINE
    r = calculate_depreciation_enhanced(
        AssetFinancials(cost=COST, life_in_years=LIFE, start_date="2026-01-15", method=m),
        _INFO, fiscal_year_end_month=12)
    return {s.year: (s.months_count, s.yearly_depreciation,
                     s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary}


@pytest.mark.parametrize("declining", [False, True])
@pytest.mark.parametrize("year", [2027, 2028, 2029, 2030])
def test_vcore_separate_asset_matches_core(declining, year):
    """vcore 분리자산 == core 분리자산 (정액·정률, 종료해 포함). 전년말 누계를 prior로."""
    full = _full_yearly_method(declining)
    prior = full[year - 1][2]                          # 전년말 누계
    v = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value)
         for r in separate_asset.schedule_separate_asset(
             COST, LIFE, 2026, 1, prior, year, 12, declining)]
    m = DepreciationMethod.DECLINING_BALANCE if declining else DepreciationMethod.STRAIGHT_LINE
    r = calculate_depreciation_enhanced(
        AssetFinancials(cost=COST, life_in_years=LIFE, start_date="2026-01-15", method=m,
                        prior_accumulated=prior, target_year=year),
        _INFO, fiscal_year_end_month=12)
    c = [(s.year, s.months_count, s.yearly_depreciation,
          s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]
    assert v == c


def test_vcore_separate_asset_rejects_non_december():
    with pytest.raises(ValueError):
        separate_asset.schedule_separate_asset(COST, LIFE, 2026, 1, 4_000_000, 2028, 3, True)
