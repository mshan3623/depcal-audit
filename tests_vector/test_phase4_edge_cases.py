"""Phase 4 가드 — vcore 에지케이스와 core 오라클의 조용한 기본값 (감사 G6·G8·G9·G10·G18·G21).

관통하는 명제: **조용한 기본값 금지.** 계산할 수 없거나 규약이 없으면 그럴듯한 값을 내는
대신 그렇다고 말한다. core는 vcore의 거울이므로, 오라클이 오타 입력에 그럴듯한 값을 내면
거울 스윕이 vcore의 결함을 가린다.
"""
import pytest

from vcore import declining_balance, disposal, straight_line
from vcore.monthly_schedule import monthly_events
from vcore.separate_asset import schedule_separate_asset

COST = 12_000_000
MEMORANDUM = 1_000


# ── G6: 분리자산 정액 종료해 강제 ──────────────────────────────────────────

def test_separate_asset_straight_line_forces_terminal_year_like_declining():
    """prior_accumulated가 스케줄과 어긋나도 종료해는 비망가로 끝난다.

    이 경로의 prior_accumulated는 **외부 확정값**이라 어긋난 채로 들어올 수 있다.
    강제하지 않으면 정률은 비망가로 끝나고 정액만 잔액이 남아, 방법에 따라 결과가 갈리고
    다음 해는 `[]`(추가 상각 없음)라 그 잔액이 영구히 남는다(감사 G6).
    """
    sl = schedule_separate_asset(COST, 5, 2020, 1, prior_accumulated=9_000_000,
                                 target_year=2024)
    db = schedule_separate_asset(COST, 5, 2020, 1, prior_accumulated=9_000_000,
                                 target_year=2024, declining=True)
    assert sl[0].book_value == MEMORANDUM
    assert (sl[0].depreciation, sl[0].book_value) == (db[0].depreciation, db[0].book_value)


def test_separate_asset_normal_years_unchanged():
    """평년과 정합한 prior에서는 종전 동작 그대로 — 강제가 평소 경로를 건드리지 않는다."""
    mid = schedule_separate_asset(COST, 5, 2020, 1, prior_accumulated=4_800_000,
                                  target_year=2022)
    assert (mid[0].depreciation, mid[0].book_value) == (2_400_000, 4_800_000)
    term = schedule_separate_asset(COST, 5, 2020, 1, prior_accumulated=9_600_000,
                                   target_year=2024)
    assert (term[0].depreciation, term[0].book_value) == (2_399_000, MEMORANDUM)


# ── G9: 종료해 월 배분이 사건과 무관해야 한다 ──────────────────────────────

@pytest.mark.parametrize("declining", [False, True])
def test_terminal_month_split_same_for_held_and_post_completion_disposal(declining):
    """자연종료 후 전부양도는 자를 것이 없다 — 종료해 월 배분이 보유와 같아야 한다.

    종전에는 절단 여부와 무관하게 `truncated=True`를 세워 종료해 균등 재배분을 건너뛰었고,
    같은 자산의 월별 명세서가 사건에 따라 달라졌다(감사 G9: 정률 종료해가 dump vs 균등).
    """
    held = monthly_events(30_000_000, 5, 2020, 1, declining=declining)
    sold = monthly_events(30_000_000, 5, 2020, 1, declining=declining, disp=(None, 2026, 6))
    assert [m.amount for m in held] == [m.amount for m in sold]


def test_real_truncation_still_skips_terminal_settlement():
    """실제로 잘리는 양도는 종전대로 절단된다 — G9 수정이 진짜 양도를 건드리지 않았다."""
    sold = monthly_events(30_000_000, 5, 2020, 1, disp=(None, 2022, 6))
    assert (sold[-1].year, sold[-1].month) == (2022, 6)
    assert len(sold) == 30


# ── G8: 표현할 수 없으면 조용히 넘기지 않는다 ──────────────────────────────

def test_partial_disposal_after_completion_raises_instead_of_vanishing():
    """자연종료 후 부분양도가 월별 API에서 무흔적으로 사라지던 자리(감사 G8).

    연도별 API는 같은 사건에 조정을 반영한다. 같은 사건이 API마다 다르게 보이면 안 되므로,
    월벡터로 표현할 수 없다는 사실을 말한다.
    """
    with pytest.raises(ValueError, match="자연종료 시점 이후의 부분양도"):
        monthly_events(COST, 5, 2020, 1, disp=(7_200_000, 2026, 6))
    # 연도별 API는 조정행으로 표시한다 — 사건이 사라지지 않는다
    rows = disposal.schedule_partial_disposal(COST, 5, 2020, 1, 7_200_000, 2026, 6)
    assert rows[-1].fiscal_year == 2026 and rows[-1].book_value == 400


# ── G10: 회계연도 라벨 유일성 ──────────────────────────────────────────────

def test_terminal_month_partial_disposal_keeps_fiscal_year_unique():
    """종료월 부분양도의 조정이 별도 행이 아니라 종료해 행에 병합된다.

    같은 FY에 행이 둘이면 `next(r for r in sch if r.fiscal_year == fy)`류 소비자가
    첫 행만 보고 양도를 통째로 놓친다(감사 G10).
    """
    rows = disposal.schedule_partial_disposal(COST, 5, 2020, 1, 7_200_000, 2024, 12)
    fys = [r.fiscal_year for r in rows]
    assert len(fys) == len(set(fys))
    last = next(r for r in rows if r.fiscal_year == 2024)
    assert (last.accumulated, last.book_value) == (4_799_600, 400)   # 양도분 안분 제거 반영


# ── G21: 입력 타입 강제 ────────────────────────────────────────────────────

@pytest.mark.parametrize("kwargs", [
    {"cost": 12_000_000.5},
    {"acq_month": 1.0},
    {"fiscal_end_month": 12.0},
])
def test_non_integer_inputs_are_rejected(kwargs):
    """소수 입력이 그대로 흘러 장부가액 9,600,000.5 같은 값을 내던 자리(감사 G21).

    원 단위 대조 도구에서 소수 금액은 그 자체로 오답이다.
    """
    args = {"cost": COST, "life_years": 5, "acq_year": 2020, "acq_month": 1}
    args.update({k: v for k, v in kwargs.items() if k != "fiscal_end_month"})
    fye = kwargs.get("fiscal_end_month", 12)
    with pytest.raises(ValueError, match="정수여야 합니다"):
        straight_line.schedule(args["cost"], args["life_years"], args["acq_year"],
                               args["acq_month"], fye)


def test_bool_is_not_accepted_as_integer():
    """bool은 int의 하위형이라 따로 막지 않으면 통과한다."""
    with pytest.raises(ValueError, match="정수여야 합니다"):
        straight_line.schedule(COST, 5, 2020, True, 12)


# ── G18: core 오라클의 조용한 기본값 ───────────────────────────────────────

def _common(**over):
    d = {'asset_code': 'A001', 'asset_type': '유형자산', 'asset_name': '테스트자산',
         'useful_life': 5, 'beginning_amount': COST, 'acquisition_date': '2020-04-15',
         'depreciation_method': '정액법'}
    d.update(over)
    return d


@pytest.mark.parametrize("bad", ['2020-13-99', '날짜아님', '2020/13/01', ''])
def test_core_rejects_unparseable_dates_instead_of_defaulting_to_2020(bad):
    """`parse_date_safe`가 어떤 오류든 2020-01-01을 돌려주던 자리 (감사 G18-①·②).

    그 탓에 상위 날짜 가드가 죽은 코드였고, 오타 날짜가 `calculation_success=True`에
    그럴듯한 상각액(2,400,000원)까지 냈다.
    """
    from core.dep_common import parse_date_safe
    with pytest.raises(ValueError):
        parse_date_safe(bad)


def test_core_common_format_reports_failure_for_bad_date():
    """공통 포맷 진입점은 명시 실패로 변환한다 — 예외를 밖으로 던지지는 않는다."""
    from core.depreciation_engine import calculate_from_common_format
    r = calculate_from_common_format(_common(acquisition_date='2020-13-99'), target_year=2022)
    assert r['calculation_success'] is False and r['phase3_depreciation'] == 0


def test_core_propagates_domain_error_instead_of_empty_result():
    """도메인 가드 위반이 '장부가 0의 빈 결과'로 축약되던 자리 (감사 G18-③).

    빈 결과는 전액 양도된 자산과 구분되지 않는다.
    """
    from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod
    from core.depreciation_engine import calculate_depreciation_enhanced
    fin = AssetFinancials(cost=COST, life_in_years=5, start_date="2022-04-15",
                          method=DepreciationMethod.STRAIGHT_LINE,
                          disposal_date="2021-01-15",          # 취득 전 부분양도
                          disposal_amount=6_000_000)
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    with pytest.raises(ValueError, match="스케줄이 없습니다"):
        calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=12)


def test_core_rejects_unsupported_declining_prior_partial_combo():
    """정률 + 전기말확정 + 부분양도는 분기가 없어 조용히 전액양도로 처리됐다 (감사 G18-④).

    정답 규약이 확립되지 않은 조합이므로 그럴듯한 오답 대신 거절한다.
    """
    from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod
    from core.depreciation_engine import calculate_depreciation_enhanced
    fin = AssetFinancials(cost=COST, life_in_years=5, start_date="2020-01-15",
                          method=DepreciationMethod.DECLINING_BALANCE,
                          disposal_date="2023-06-30", disposal_amount=7_200_000,
                          prior_accumulated=8_000_000, target_year=2023)
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    with pytest.raises(ValueError, match="지원하지 않습니다"):
        calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=12)
