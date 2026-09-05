"""입력 가드 회귀 테스트.

정상 도메인 밖 입력(사건금액≥원가, 증가월≤취득월, 무형 capex)에서 엔진이
조용히 틀린 값을 내지 않도록 막는 가드를 고정한다. 정밀 분석(2026-06-16)에서
재현된 결함 #1·#3·#4 대응.
"""
import pytest

from core.depreciation_engine import calculate_depreciation_enhanced
from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod
from vcore import capex, disposal, monthly_schedule, separate_asset
from vcore import declining_balance, straight_line

_INFO = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")


@pytest.mark.parametrize("declining", [False, True])
def test_partial_disposal_ge_cost_delegates_to_full(declining):
    """양도액 ≥ 원가인 부분양도는 전부양도(절단)로 위임 — 음수 상각 금지."""
    cost, life = 1_000_000, 5
    pfn = (disposal.schedule_partial_disposal_declining if declining
           else disposal.schedule_partial_disposal)
    ffn = (disposal.schedule_full_disposal_declining if declining
           else disposal.schedule_full_disposal)
    rows = pfn(cost, life, 2020, 1, 1_500_000, 2022, 6)     # 양도액 > 원가
    full = ffn(cost, life, 2020, 1, 2022, 6)
    assert all(r.depreciation >= 0 for r in rows), "음수 월상각 발생"
    key = lambda rs: [(r.fiscal_year, r.depreciation, r.accumulated, r.book_value) for r in rs]
    assert key(rows) == key(full)


@pytest.mark.parametrize("declining", [False, True])
def test_capex_at_or_before_acquisition_raises(declining):
    """증가월 ≤ 취득월(k≤0)은 base[k-1] 인덱스 오류로 폭주 → 명시적 ValueError."""
    fn = (capex.schedule_with_increase_declining if declining
          else capex.schedule_with_increase)
    with pytest.raises(ValueError):
        fn(1_000_000, 5, 2020, 1, 500_000, 2020, 1)        # 증가월 = 취득월 (k=0)
    with pytest.raises(ValueError):
        fn(1_000_000, 5, 2020, 6, 500_000, 2020, 1)        # 증가월 < 취득월 (k<0)


def test_intangible_capex_supported_via_vcore():
    """무형 + capex: vcore(별표4 정액)로 위임 지원. 증가액 반영(누락 아님) + 최종 비망가."""
    fin = AssetFinancials(cost=10_000_000, life_in_years=5, start_date="2026-04-15",
                          method=DepreciationMethod.INTANGIBLE,
                          increase_date="2027-06-10", increase_amount=3_000_000)
    r = calculate_depreciation_enhanced(fin, _INFO, fiscal_year_end_month=12)
    assert r.schedule, "무형 capex가 지원돼야 함(빈 스케줄 아님)"
    total = sum(m.numeric_depreciation for m in r.schedule)
    assert total == 12_999_000, "증가액 반영: (1,000만+300만)−비망가 1,000"
    assert r.schedule[-1].book_value == 1_000


# ── vcore 진입점 공통 가드 (정밀 분석 2026-07-10, P-b) ──────────────────

_SCHEDULES = [straight_line.schedule, declining_balance.schedule]


@pytest.mark.parametrize("fn", _SCHEDULES)
def test_life_under_two_raises(fn):
    """내용연수 < 2는 별표4 상각률표 밖 — 미가드 시 60년율/기본율로 조용히 폴백해 오답."""
    with pytest.raises(ValueError):
        fn(1_000_000, 1, 2020, 1)
    with pytest.raises(ValueError):
        fn(1_000_000, 0, 2020, 1)


@pytest.mark.parametrize("fn", _SCHEDULES)
def test_nonpositive_cost_raises(fn):
    """취득원가 ≤ 0 — 미가드 시 음수 상각·ZeroDivision으로 이어짐."""
    with pytest.raises(ValueError):
        fn(0, 5, 2020, 1)
    with pytest.raises(ValueError):
        fn(-1_000_000, 5, 2020, 1)


@pytest.mark.parametrize("fn", _SCHEDULES)
def test_life_over_sixty_raises(fn):
    """내용연수 > 60도 별표4 상각률표 밖 — 조용히 60년율로 클램프되면 안 된다.

    상각률표는 2~60년 완전 수록이라 "가장 가까운 작은 연수로 폴백" 분기는 표 안에서
    죽은 코드였고, 살아 있는 효과가 범위 밖 클램프뿐이었다(life=100 → 60년율로
    예외 없이 그럴듯한 표 산출, 2026-07-25 발견).
    """
    with pytest.raises(ValueError):
        fn(1_000_000, 61, 2020, 1)
    with pytest.raises(ValueError):
        fn(1_000_000, 100, 2020, 1)
    fn(1_000_000, 60, 2020, 1)       # 표 경계(60년)는 정상 통과


@pytest.mark.parametrize("fn", _SCHEDULES)
def test_cost_at_or_below_memorandum_raises(fn):
    """취득원가 ≤ 비망가액(1,000) — 상각할 금액 자체가 없다(취득원가−비망가 ≤ 0).

    미가드 시 전 연도 상각 0으로 흐르다 종료해에 음수 상각으로 마감된다
    (cost=500·정액 5년 → 종료해 −900, 누계 −500, 장부 1,000 > 취득원가).
    """
    with pytest.raises(ValueError):
        fn(1_000, 5, 2020, 1)
    with pytest.raises(ValueError):
        fn(500, 5, 2020, 1)
    fn(1_001, 5, 2020, 1)            # 경계 바로 위는 정상 통과


@pytest.mark.parametrize("fn", _SCHEDULES)
def test_month_out_of_range_raises(fn):
    """취득월·결산월 1~12 범위 밖 — 미가드 시 조용히 재해석된 표 반환."""
    with pytest.raises(ValueError):
        fn(1_000_000, 5, 2020, 13)                       # 취득월 13
    with pytest.raises(ValueError):
        fn(1_000_000, 5, 2020, 1, fiscal_end_month=0)    # 결산월 0


@pytest.mark.parametrize("declining", [False, True])
def test_disposal_before_acquisition_raises(declining):
    """양도월 < 취득월(d<0)은 base[:d+1] 음수 슬라이스로 '뒤에서 절단'된 오답 표 → ValueError."""
    ffn = (disposal.schedule_full_disposal_declining if declining
           else disposal.schedule_full_disposal)
    pfn = (disposal.schedule_partial_disposal_declining if declining
           else disposal.schedule_partial_disposal)
    with pytest.raises(ValueError):
        ffn(1_000_000, 5, 2024, 6, 2024, 3)              # 전체양도: 양도 2024-03 < 취득 2024-06
    with pytest.raises(ValueError):
        pfn(1_000_000, 5, 2024, 6, 400_000, 2024, 3)     # 부분양도: 동일 시나리오


@pytest.mark.parametrize("declining", [False, True])
def test_capex_after_completion_raises(declining):
    """자연종료 이후 자본적지출(k≥n)은 조용한 무시(k=n)/IndexError(k>n) → 명시적 ValueError."""
    fn = (capex.schedule_with_increase_declining if declining
          else capex.schedule_with_increase)
    with pytest.raises(ValueError):
        fn(1_000_000, 5, 2020, 1, 500_000, 2025, 1)      # k=60=n (종료 직후 달)
    with pytest.raises(ValueError):
        fn(1_000_000, 5, 2020, 1, 500_000, 2026, 6)      # k>n


def test_capex_nonpositive_amount_raises():
    """자본적지출 금액 ≤ 0 — 음수는 미지원 감액으로 조용히 스케일다운됨 → ValueError."""
    with pytest.raises(ValueError):
        capex.schedule_with_increase(1_000_000, 5, 2020, 1, 0, 2021, 6)
    with pytest.raises(ValueError):
        capex.schedule_with_increase(1_000_000, 5, 2020, 1, -500_000, 2021, 6)


def test_monthly_events_bypass_paths_guarded():
    """monthly_events는 apply_increase 등을 직접 호출하는 실행 경로(상각명세서 진입점) —
    상위 가드를 우회하므로 단일 관문 가드가 여기서도 발화해야 한다 (결함 HIGH-2)."""
    with pytest.raises(ValueError):   # capex 증가월 = 취득월 (k=0): 미가드 시 월상각 폭주 실측
        monthly_schedule.monthly_events(12_000_000, 5, 2020, 1, inc=(500_000, 2020, 1))
    with pytest.raises(ValueError):   # 양도월 < 취득월
        monthly_schedule.monthly_events(12_000_000, 5, 2024, 6, disp=(None, 2024, 3))
    with pytest.raises(ValueError):   # 부분양도 금액 0
        monthly_schedule.monthly_events(12_000_000, 5, 2020, 1, disp=(0, 2022, 6))


@pytest.mark.parametrize("declining", [False, True])
def test_separate_asset_time_guards(declining):
    """분리자산: 취득 전 연도 요청은 ValueError, 내용연수 종료 후는 상각 없음([])."""
    with pytest.raises(ValueError):   # 취득 전 연도 — 미가드 시 정상 상각행 반환 실측
        separate_asset.schedule_separate_asset(12_000_000, 5, 2020, 4, 2_000_000, 2019,
                                               declining=declining)
    with pytest.raises(ValueError):   # 음수 누계
        separate_asset.schedule_separate_asset(12_000_000, 5, 2020, 4, -1, 2022,
                                               declining=declining)
    rows = separate_asset.schedule_separate_asset(12_000_000, 5, 2020, 4, 2_000_000, 2030,
                                                  declining=declining)
    assert rows == [], "내용연수 종료(2025) 후 연도는 추가 상각이 없어야 함"


# ── core 경계: 조용한 기본값 대체 금지 (정밀 분석 2026-07-10, P-c) ──────

def _common_data(**overrides):
    # asset_code가 없으면 AssetInfo.__post_init__이 '자산코드는 필수입니다'로 먼저 막아,
    # 정작 검사 대상인 날짜 가드까지 실행이 닿지 못한다(감사 G14: 공허 통과).
    base = {'asset_code': 'A001',
            'asset_type': '유형자산', 'asset_name': '테스트자산', 'useful_life': 5,
            'beginning_amount': 12_000_000, 'acquisition_date': '2020-04-15',
            'depreciation_method': '정액법'}
    base.update(overrides)
    return base


def test_invalid_acquisition_date_raises_not_default():
    """잘못된 취득일자를 '2020-01-01' 기본값으로 조용히 대체하면 수년치 스케줄이 왜곡됨 →
    변환은 ValueError, 공통 포맷 진입점은 calculation_success=False로 명시 실패해야 한다."""
    from core.depreciation_engine import (calculate_from_common_format,
                                     convert_common_data_to_financials)
    with pytest.raises(ValueError):
        convert_common_data_to_financials(_common_data(acquisition_date='2020-13-99'))
    r = calculate_from_common_format(_common_data(acquisition_date='날짜아님'), target_year=2022)
    assert r['calculation_success'] is False
    assert r['phase3_depreciation'] == 0


def test_conversion_failure_no_dummy_asset():
    """변환 실패 시 더미 자산(cost=1, life=5) 반환 금지 — 예외 전파로 명시 실패."""
    from core.depreciation_engine import convert_common_data_to_financials
    with pytest.raises(ValueError):
        convert_common_data_to_financials({})       # 필수 필드 전부 누락
