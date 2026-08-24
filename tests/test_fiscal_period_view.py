"""v2.2 fiscal year 1급 뷰 회귀 (비-12월 결산 스모크 시나리오)

검증 차원:
- 결산월에 따라 첫 회계기간 상각개월수가 달라진다 (3월 결산 vs 12월 결산)
- extract_fiscal_period view가 schedule을 회계기간으로 정확히 절단
- 같은 결산월 가정 하 정상연도 합계 = 연간 정상상각비 (월할 동등성)
- 비-12월 결산(3·6·9·1월) 스모크
"""

import pytest

# import 경로 통일 — depreciation_engine 내부의 `from dep_common import *` 와 같은
# `dep_common` 모듈을 가리키도록 한다 (sys.path 에 _core_dir 가 들어 있어 가능).
from core.dep_tang_engine import _calculate_korean_straight_line_enhanced as sl
from core.dep_common import (
    AssetInfo,
    AssetFinancials,
    DepreciationMethod,
    get_fiscal_year,
    get_fiscal_year_period,
    get_fiscal_period_dates,
)
from core.depreciation_engine import (
    calculate_depreciation_enhanced,
    extract_fiscal_period,
)


# ============================================================
# 헬퍼 검증 (단위 테스트)
# ============================================================

def test_get_fiscal_year_korean_convention():
    """한국 관행: fiscal_year = 결산일이 속한 연도"""
    # 12월 결산
    assert get_fiscal_year(2025, 6, 12) == 2025
    assert get_fiscal_year(2025, 12, 12) == 2025
    # 3월 결산: FY2025 = 2024-04~2025-03
    assert get_fiscal_year(2024, 4, 3) == 2025
    assert get_fiscal_year(2025, 3, 3) == 2025
    assert get_fiscal_year(2025, 4, 3) == 2026
    # 1월 결산(미국 Walmart 등): FY2026 = 2025-02~2026-01
    assert get_fiscal_year(2025, 2, 1) == 2026
    assert get_fiscal_year(2026, 1, 1) == 2026


def test_get_fiscal_year_period_calendar_coordinates():
    """fiscal_year의 calendar 좌표 (시작년월, 종료년월)"""
    assert get_fiscal_year_period(2025, 12) == (2025, 1, 2025, 12)
    assert get_fiscal_year_period(2025, 3) == (2024, 4, 2025, 3)
    assert get_fiscal_year_period(2025, 6) == (2024, 7, 2025, 6)
    assert get_fiscal_year_period(2026, 1) == (2025, 2, 2026, 1)


def test_get_fiscal_period_dates_format():
    """기간 시작·종료일 YYYY-MM-DD 포맷, 월말 자동 계산"""
    assert get_fiscal_period_dates(2025, 12) == ("2025-01-01", "2025-12-31")
    assert get_fiscal_period_dates(2025, 3) == ("2024-04-01", "2025-03-31")
    assert get_fiscal_period_dates(2026, 1) == ("2025-02-01", "2026-01-31")
    # 윤년 검증 (2024년 2월 = 29일)
    assert get_fiscal_period_dates(2024, 2) == ("2023-03-01", "2024-02-29")


# ============================================================
# 비-12월 결산 schedule 생성 시나리오 (F-FP-02~05)
# ============================================================

COST = 12_000_000
LIFE = 5
START = "2025-03-15"


@pytest.mark.parametrize("end_month,first_fy,expected_first_months", [
    (12, 2025, 10),  # 12월 결산: 2025-03 ~ 2025-12 = 10개월
    (3, 2025, 1),    # 3월 결산: FY2025 = 2024-04~2025-03, 2025-03만 = 1개월
    (6, 2025, 4),    # 6월 결산: FY2025 = 2024-07~2025-06, 2025-03~06 = 4개월
    (9, 2025, 7),    # 9월 결산: FY2025 = 2024-10~2025-09, 2025-03~09 = 7개월
    (1, 2026, 11),   # 1월 결산: FY2026 = 2025-02~2026-01, 2025-03~2026-01 = 11개월
])
def test_first_fiscal_period_months_by_end_month(end_month, first_fy, expected_first_months):
    """결산월에 따라 자산의 첫 회계기간 상각개월수가 달라진다."""
    schedule = sl(
        cost=COST, life_years=LIFE, start_date=START,
        fiscal_year_end_month=end_month,
    )
    first_period_months = sum(
        1 for m in schedule
        if get_fiscal_year(m.year, m.month, end_month) == first_fy
    )
    assert first_period_months == expected_first_months


# ============================================================
# 같은 결산월 가정 하 정상연도 합계 = 연간 정상상각비 (F-FP-07)
# ============================================================

@pytest.mark.parametrize("end_month", [12, 3, 6, 9, 1])
def test_full_fiscal_period_sum_equals_annual_standard(end_month):
    """정상연도(취득·처분 없는 12개월 회계기간)의 합 = 연간 정상상각비.

    cost=12,000,000 / life=5 → 표준 연간상각 = 2,400,000원
    """
    schedule = sl(
        cost=COST, life_years=LIFE, start_date=START,
        fiscal_year_end_month=end_month,
    )

    # 어떤 fiscal year가 12개월 full year인지 찾아서 합산
    fy_counts = {}
    for m in schedule:
        fy = get_fiscal_year(m.year, m.month, end_month)
        fy_counts[fy] = fy_counts.get(fy, 0) + 1

    full_fy_list = [fy for fy, n in fy_counts.items() if n == 12]
    assert full_fy_list, "12개월 full fiscal year가 적어도 하나 있어야"

    expected_annual = round(COST * 0.200)  # 5년 정액 상각률 0.200
    for fy in full_fy_list:
        fy_total = sum(
            m.monthly_depreciation for m in schedule
            if get_fiscal_year(m.year, m.month, end_month) == fy
        )
        assert fy_total == expected_annual, (
            f"FY{fy} (end_month={end_month}): 합 {fy_total:,} != 기대 {expected_annual:,}"
        )


# ============================================================
# extract_fiscal_period view (F-FP-10 dep_verify 어휘 매칭)
# ============================================================

def test_extract_fiscal_period_basic_12():
    """12월 결산 회사의 view 추출."""
    fin = AssetFinancials(
        cost=COST, life_in_years=LIFE, start_date=START,
        method=DepreciationMethod.STRAIGHT_LINE,
    )
    info = AssetInfo(asset_id="T1", asset_name="테스트자산")
    result = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=12)

    view = extract_fiscal_period(result, 2026)
    assert view.fiscal_year == 2026
    assert view.fiscal_year_end_month == 12
    assert view.period_start_date == "2026-01-01"
    assert view.period_end_date == "2026-12-31"
    assert view.months_in_period == 12
    # 2026년은 full year (취득 2025-03이라 첫해 10개월 후 2026년 = 12개월)
    assert view.period_depreciation == round(COST * 0.200)


def test_extract_fiscal_period_basic_march():
    """3월 결산 회사: FY2025 = 2024-04~2025-03, 2025-03만 1개월 상각."""
    fin = AssetFinancials(
        cost=COST, life_in_years=LIFE, start_date=START,
        method=DepreciationMethod.STRAIGHT_LINE,
    )
    info = AssetInfo(asset_id="T2", asset_name="3월결산자산")
    result = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=3)

    view = extract_fiscal_period(result, 2025)
    assert view.fiscal_year == 2025
    assert view.fiscal_year_end_month == 3
    assert view.period_start_date == "2024-04-01"
    assert view.period_end_date == "2025-03-31"
    assert view.months_in_period == 1  # 2025-03만


def test_depreciation_result_preserves_fiscal_year_end_month():
    """DepreciationResult에 fiscal_year_end_month 컨텍스트 보존."""
    fin = AssetFinancials(
        cost=COST, life_in_years=LIFE, start_date=START,
        method=DepreciationMethod.STRAIGHT_LINE,
    )
    info = AssetInfo(asset_id="T3", asset_name="컨텍스트보존")
    result = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=6)
    assert result.fiscal_year_end_month == 6


# ============================================================
# 분리자산 경로 v2.2 가드 (12월 외 ValueError)
# ============================================================

def test_partial_disposal_separate_asset_rejects_non_december_v22():
    """v2.2 분리자산 경로는 12월 결산만 지원, 비-12월은 ValueError."""
    with pytest.raises(ValueError, match="v2.2"):
        sl(
            cost=COST, life_years=LIFE, start_date=START,
            prior_accumulated=1_000_000, target_year=2025,
            fiscal_year_end_month=3,
        )
