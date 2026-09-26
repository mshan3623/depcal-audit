"""개발비 — 시행령 §26①6 문언: 신고내용연수에 따라 경과월수에 비례 (별표4 아님).

일반 무형은 별표4 정액이지만, 개발비는 "20년의 범위에서 연단위로 신고한 내용연수에 따라 매
사업연도별 경과월수에 비례하여 상각"한다 → 연 상각액 = 취득가액 ÷ 내용연수. 별표4율과 1/n은
4·5·8·10·20년에서만 같다(외부 평가 2026-09-26 ④).

더존이 개발비를 1/n으로 계산하는지는 실측이 없다(B사 개발비 1건은 이미 상각 완료). 대장이
별표4로 계산했다면 depverify는 3·6·7·9년 개발비에서 '차이'를 낸다 — 문언상 상각범위액과의
차이이므로 그대로 보고한다.
"""
import pytest

from depverify.verdict import verify_asset
from vcore import intangible, straight_line

COST = 100_000_000


def test_three_years_is_one_third_not_byeolpyo4():
    rows = intangible.schedule_development_cost(COST, 3, 2026, 1)
    assert [(r.fiscal_year, r.depreciation, r.book_value) for r in rows] == [
        (2026, 33_333_333, 66_666_667),
        (2027, 33_333_333, 33_333_334),
        (2028, 33_332_334, 1_000),                 # 종료해: 잔액 − 비망 1,000
    ]
    assert straight_line.schedule(COST, 3, 2026, 1)[0].depreciation == 33_300_000   # 별표4 0.333


def test_seven_years_matches_evaluator_figure():
    assert intangible.schedule_development_cost(COST, 7, 2026, 1)[0].depreciation == 14_285_714


def test_first_year_is_elapsed_months_proportional():
    """7월 사용개시 → 첫해 6개월: 33,333,333 × 6 ÷ 12 (절사)."""
    rows = intangible.schedule_development_cost(COST, 3, 2026, 7)
    assert (rows[0].months, rows[0].depreciation) == (6, 16_666_666)
    assert rows[-1].book_value == 1_000 and sum(r.depreciation for r in rows) == COST - 1_000


@pytest.mark.parametrize("life", [4, 5, 8, 10, 20])
@pytest.mark.parametrize("acq_month", [1, 4, 12])
@pytest.mark.parametrize("fye", [12, 3])
def test_equals_byeolpyo4_where_one_over_n_is_the_statutory_rate(life, acq_month, fye):
    """1/n = 별표4율인 연수에서는 일반 무형(별표4) 표와 1원까지 같아야 한다."""
    dev = intangible.schedule_development_cost(COST, life, 2020, acq_month, fye)
    sl = straight_line.schedule(COST, life, 2020, acq_month, fye)
    assert dev == sl


@pytest.mark.parametrize("life", [0, 21, 2.5])
def test_life_outside_statutory_range_is_rejected(life):
    with pytest.raises(ValueError):
        intangible.schedule_development_cost(COST, life, 2026, 1)


def test_full_disposal_stops_at_disposal_month():
    """양도 연도는 월 base(연 상각 // 12) × 양도월까지 — 정액 양도 규약과 같다(결산월 잔재 미도달)."""
    rows = intangible.schedule_full_disposal_development_cost(COST, 3, 2026, 1, 2027, 6)
    assert [(r.fiscal_year, r.months, r.depreciation) for r in rows] == [
        (2026, 12, 33_333_333), (2027, 6, (33_333_333 // 12) * 6)]


# ── depverify 라우팅 — 계정과목 '개발비'만 1/n ────────────────────────────
def _dev(**over):
    a = {"fy": 2027, "intang": True, "cost": COST, "life": 3, "acq_y": 2026, "acq_m": 1,
         "disposed": False, "method": "정액법", "account": "개발비",
         "exp_dep": 33_333_333, "exp_acc": 33_333_333, "exp_bk": 33_333_334,
         "prev_acc": 33_333_333}
    a.update(over)
    return a


def test_depverify_matches_development_cost_by_statute():
    assert verify_asset(_dev()).status == "일치"


def test_depverify_flags_byeolpyo4_valued_development_cost():
    """대장이 별표4(0.333)로 계산한 개발비 → 문언상 상각범위액과 차이."""
    v = verify_asset(_dev(exp_dep=33_300_000, exp_acc=33_300_000, exp_bk=33_400_000,
                          prev_acc=33_300_000))
    assert v.status == "차이"


def test_depverify_keeps_byeolpyo4_for_other_intangibles():
    """같은 수치라도 계정과목이 소프트웨어면 별표4 — 1/n 값은 차이."""
    assert verify_asset(_dev(account="소프트웨어")).status == "차이"


def test_depverify_development_cost_life_over_20_is_unverifiable():
    v = verify_asset(_dev(life=25))
    assert v.status == "검증불능" and "가드발동" in v.reason
