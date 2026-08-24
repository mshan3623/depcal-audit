"""업무용승용차 적법성 점검 — 재계산 대조가 원리적으로 못 잡는 축.

verdict는 "대장에 적힌 방법대로 다시 계산하면 회사 값이 나오는가"를 본다. 그래서 대장이
법령에 어긋난 방법을 써도 그 방법대로 맞으면 '일치'가 난다 — 계산은 맞고 적법성은 틀린
거짓 일치다. 이 파일은 그 축이 살아 있음을 고정한다.

법인세법 시행령 §50조의2 ③: 업무용승용차는 §26①2·§28①2에도 **불구하고** 정액법·5년.
"""
import pytest

from depverify.compliance import (ANNUAL_DEDUCTION_CAP, check_vehicles,
                                  summary_lines)
from depverify.verdict import verify_all


def _car(**over):
    """정률 5년으로 잘못 잡힌 차량. 회사계상과 재계산이 일치하도록 값을 맞춰둔다."""
    a = dict(fy=2025, fye=12, intang=False, cost=40_000_000, life=5,
             acq_y=2023, acq_m=1, disposed=False, method="정률법",
             prev_acc=0, exp_dep=0, exp_acc=0, exp_bk=0,
             account="차량운반구", asset_name="제네시스 G80")
    a.update(over)
    return a


def test_wrong_method_is_flagged():
    f = check_vehicles([_car()])
    assert len(f) == 1
    assert f[0].issue == "업무용승용차 상각 요건 불일치"
    assert "정률법" in f[0].detail and "정액법" in f[0].detail
    assert "50조의2" in f[0].basis


def test_wrong_life_is_flagged():
    f = check_vehicles([_car(method="정액법", life=8)])
    assert len(f) == 1
    assert "내용연수 8년" in f[0].detail


def test_compliant_car_is_not_flagged():
    """정액 5년이면 요건 충족 — 잡음을 만들지 않는다."""
    assert check_vehicles([_car(method="정액법", life=5)]) == []


@pytest.mark.parametrize("account,name", [
    ("차량운반구", "카니발"), ("공구와기구", "업무용승용차 리스"),
    ("기타유형자산", "승용자동차"), ("차량", "5톤트럭"),
])
def test_vehicle_candidates_are_detected_broadly(account, name):
    """후보는 넓게 잡는다 — 좁게 잡아 놓치는 쪽이 감사에서 더 위험하다.

    해당 여부(화물차·승합차 제외, 영업용 제외)는 감사인이 확정한다.
    """
    assert check_vehicles([_car(account=account, asset_name=name)])


def test_non_vehicle_is_ignored():
    assert check_vehicles([_car(account="비품", asset_name="책상")]) == []


def test_intangible_is_never_a_vehicle():
    assert check_vehicles([_car(intang=True)]) == []


def test_deduction_cap_is_flagged():
    """법 §27조의2 ③ 800만원 한도 초과 가능성 안내."""
    f = check_vehicles([_car(method="정액법", life=5,
                             exp_dep=ANNUAL_DEDUCTION_CAP + 1)])
    assert len(f) == 1
    assert f[0].issue == "감가상각비 손금 한도 초과 가능"
    assert "27조의2" in f[0].basis


def test_cap_not_flagged_at_exactly_the_limit():
    assert check_vehicles([_car(method="정액법", life=5,
                                exp_dep=ANNUAL_DEDUCTION_CAP)]) == []


def test_summary_records_that_the_check_ran_even_when_clean():
    """점검 항목이 없어도 '검사했다'는 사실이 조서에 남아야 한다."""
    lines = summary_lines([])
    assert len(lines) == 1 and "업무용승용차 점검" in lines[0]


def test_recalculation_says_match_while_compliance_flags_it():
    """핵심: 재계산은 '일치'인데 적법성은 위반인 자산이 존재한다.

    이 조합이 성립하지 않으면 적법성 점검 축은 존재 이유가 없다.
    """
    from vcore.declining_balance import schedule as db
    rows = db(40_000_000, 5, 2023, 1)
    cur = [r for r in rows if r.fiscal_year == 2025][0]
    prev = [r for r in rows if r.fiscal_year == 2024][0]
    car = _car(exp_dep=cur.depreciation, exp_acc=cur.accumulated,
               exp_bk=cur.book_value, prev_acc=prev.accumulated)

    assert verify_all([car]).counts()["일치"] == 1      # 재계산은 통과시킨다
    assert check_vehicles([car])                        # 적법성은 잡아낸다
