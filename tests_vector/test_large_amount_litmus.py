"""대형 금액 리트머스 (A-4) — 10⁹·10¹¹·10¹³·10¹⁵원 × 단순·자본적지출·부분양도 3경로.

배경: 2026-07-25 정밀평가가 일회성 프로브로 이 대역을 훑고 "합계+비망 = 취득원가 정확
일치"를 확인했지만 테스트로 남기지 않아, 회귀가 잡히지 않는 상태였다.
A-4 = 그 프로브의 상시화. 실무 금액대(≤10⁹)와 소액 대역은
`test_schedule_invariants.py`가 이미 덮으므로 여기서는 그 위 대역만 본다.

이 대역이 위험한 이유는 상각률·안분비율이 float이기 때문이다. 특히 부분양도 누계 안분
(`disposal.py`)은 `prev.acc * disposal_amount / cost`라 중간곱이 10³⁰까지 커진다.
float 유효자릿수(53비트 ≈ 9×10¹⁵)를 넘으면 1원이 조용히 갈린다.

여기서 고정하는 것은 두 층이다:

  (1) **닫힘·건전성** — 상각합 + 비망가 = 총원가, 음수 없음, 장부가 이탈 없음.
      단순·capex 경로에서는 실질 검증이다(D1 음수상각 결함이 이 등식을 깼다).
      부분양도 경로는 잔류분 기준(취득원가 − 양도액)으로 같은 등식을 건다.

  (2) **안분 정확도** — (1)만으로는 부족하다. 부분양도의 양도분 누계는
      `disposal_book = 양도액 − disposal_accumulated`로 차감 정의되므로, 안분이
      1원 틀려도 닫힘 등식은 그대로 성립한다(구성상 자기정합). 즉 (1)은 안분 오차를
      원리적으로 탐지할 수 없다. 그래서 float 결과를 **정수 정확 4사5입**과 직접
      대조한다.

안분 정확도의 실측 경계(2026-07-29, 31,692조합/자릿수 격자):

    1e9 0 / 1e11 0 / 1e12 0 / 1e13 0 | 1e14 5건(0.02%) / 1e15 42건(0.13%)
    / 1e16 1,007건(3.18%) / 1e17 8,587건(27.1%, 최대 4원)

따라서 안분 정확도가 보장되는 대역은 **10¹³까지**이고, 이 파일은 거기까지만 exact를
주장한다. 10¹⁴ 이상의 1원 오차는 별건(계획서 D8)으로 기록했다 — 가드도 없이 조용히
어긋나므로 "조용한 오답 금지" 도크트린 위반이지만, 수정은 A-4 범위 밖이다.
"""
import pytest

from vcore import capex, declining_balance as db, disposal, monthly, straight_line as sl
from vcore.projection import MEMORANDUM, round_half_up

# A-4가 지정한 대역. 10⁹는 test_schedule_invariants의 실무 상한과 맞물리는 이음매.
MAGNITUDES = [10**9, 10**11, 10**13, 10**15]
_MAG_IDS = ["1e9", "1e11", "1e13", "1e15"]

# 안분 정확도가 실측으로 보장되는 상한 (위 docstring 격자 참조).
EXACT_ALLOCATION_MAX = 10**13


def _exact_half_up(num: int, den: int) -> int:
    """정수만으로 계산한 4사5입 몫 — float 개입 없음(오라클)."""
    return (2 * num + den) // (2 * den)


def _assert_closes(rows, total_cost):
    """상각합 + 비망가 = 총원가, 그리고 경로상 건전성."""
    for r in rows:
        assert r.depreciation >= 0, f"음수 상각 {r}"
        assert r.accumulated >= 0, f"음수 누계 {r}"
        assert MEMORANDUM <= r.book_value <= total_cost, f"장부가 이탈 {r}"
    assert rows[-1].book_value == MEMORANDUM
    assert rows[-1].accumulated == total_cost - MEMORANDUM
    assert sum(r.depreciation for r in rows) + MEMORANDUM == total_cost


# ── (1) 닫힘·건전성 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("mod", [sl, db], ids=["정액", "정률"])
@pytest.mark.parametrize("cost", MAGNITUDES, ids=_MAG_IDS)
@pytest.mark.parametrize("life", [2, 5, 20, 60])
def test_simple_path_closes_at_large_amounts(mod, cost, life):
    """단순 경로 — 취득월 1·6·12 전부에서 닫힌다."""
    for acq_month in (1, 6, 12):
        _assert_closes(mod.schedule(cost, life, 2020, acq_month, 12), cost)


@pytest.mark.parametrize("fn", [capex.schedule_with_increase,
                                capex.schedule_with_increase_declining],
                         ids=["정액", "정률"])
@pytest.mark.parametrize("cost", MAGNITUDES, ids=_MAG_IDS)
def test_capex_path_closes_at_large_amounts(fn, cost):
    """자본적지출 경로 — 총원가가 (취득원가 + 증가액)로 커져도 닫힌다.

    증가액을 원가의 0.5·1·3배까지 넣는 이유는, 증가 시점 이후 스케일 루프가
    원가보다 큰 금액을 다루기 때문이다(10¹⁵ × 3 = 3×10¹⁵로 float 한계에 더 근접).
    """
    for inc in (cost // 2, cost, cost * 3):
        _assert_closes(fn(cost, 10, 2020, 1, inc, 2023, 6, 12), cost + inc)


@pytest.mark.parametrize("fn", [disposal.schedule_partial_disposal,
                                disposal.schedule_partial_disposal_declining],
                         ids=["정액", "정률"])
@pytest.mark.parametrize("cost", MAGNITUDES, ids=_MAG_IDS)
def test_partial_disposal_path_closes_at_large_amounts(fn, cost):
    """부분양도 경로 — 잔류분 기준(취득원가 − 양도액)으로 닫힌다.

    양도 전 구간은 전체기준으로 상각되므로 상각합 자체는 잔류분 기준을 넘는다.
    닫힘은 종료 시점의 누계·장부가로 본다: 잔류분 종료누계 = (원가 − 양도액) − 비망가.
    """
    for k in (2, 3, 7):
        disposal_amount = cost // k
        residual_basis = cost - disposal_amount
        rows = fn(cost, 10, 2020, 1, disposal_amount, 2023, 6, 12)
        for r in rows:
            assert r.depreciation >= 0, f"음수 상각 {r}"
            assert r.accumulated >= 0, f"음수 누계 {r}"
        assert rows[-1].book_value == MEMORANDUM
        assert rows[-1].accumulated == residual_basis - MEMORANDUM


# ── (2) 안분 정확도 — float vs 정수 정확연산 ──────────────────────────────
@pytest.mark.parametrize("monthly_fn", [monthly.sl_monthly, monthly.db_monthly],
                         ids=["정액", "정률"])
@pytest.mark.parametrize("cost", [m for m in MAGNITUDES if m <= EXACT_ALLOCATION_MAX],
                         ids=[i for i, m in zip(_MAG_IDS, MAGNITUDES)
                              if m <= EXACT_ALLOCATION_MAX])
def test_partial_disposal_allocation_matches_exact_integer_arithmetic(monthly_fn, cost):
    """`round_half_up(prev.acc × 양도액 / 원가)`가 정수 정확 4사5입과 일치하는가.

    닫힘 등식(위 (1))은 이 오차를 구조적으로 탐지하지 못한다(양도분 장부가가 차감
    정의라 1원 틀려도 총합은 맞는다). 그래서 안분값 자체를 직접 대조한다.

    격자: 내용연수 3종 × 양도비율 c/2~c/39 × 전 경과월 = 자릿수당 31,692조합.
    위 docstring의 경계 실측과 **같은 격자**다(좁히면 10¹⁴ 오차 5건을 놓쳐 경계 주장이
    테스트로 뒷받침되지 않는다 — 실제로 c/11까지로 좁히면 10¹⁴가 통과해버린다).
    """
    for life in (5, 10, 20):
        base = monthly_fn(cost, life, 1)
        for k in range(2, 40):
            disposal_amount = cost // k
            for d in range(1, len(base)):
                acc = base[d].acc
                assert round_half_up(acc * disposal_amount / cost) == \
                    _exact_half_up(acc * disposal_amount, cost), \
                    f"안분 불일치 cost={cost} life={life} 양도=c/{k} 경과월={d}"
