"""부분양도 잔류분의 비망가 = 1,000 × 잔류비율 (사용자 결정 2026-11-12).

비망가는 가치가 아니라 자산 단위 메모다. 부분양도가 없는 자산은 어느 내용연수에서나 1,000원으로
끝나고, 일부를 양도한 자산은 메모도 취득가액 비율로 따라 나가 잔류분만큼 남는다 — 대장의 최종
장부가만 보고 "원래 자산의 몇 %가 남았는가"를 읽을 수 있다(800원 = 20% 양도).

종전에는 800원이 별표4 정액률 × 연수 > 1인 연수(21·30·41년 등)에서만 나오고 나머지(4·5·8·10·
20·40년)는 1,000원이라, 값이 연수에 따라 갈려 지표로 쓸 수 없었다(평가 2026-11-10 E1).
"""
import pytest

from vcore import capex, declining_balance, disposal, straight_line
from vcore.monthly_schedule import monthly_events

LIVES = list(range(2, 61))
COST, SOLD = 50_000_000, 10_000_000          # 20% 양도 → 잔류분 비망가 800


@pytest.mark.parametrize("life", LIVES)
def test_no_partial_disposal_always_ends_at_1000(life):
    for fye in (3, 12):
        assert straight_line.schedule(COST, life, 2000, 3, fye)[-1].book_value == 1000
        assert declining_balance.schedule(COST, life, 2000, 3, fye)[-1].book_value == 1000
        assert capex.schedule_with_increase(COST, life, 2000, 3, SOLD, 2001, 3, fye)[-1].book_value == 1000


@pytest.mark.parametrize("fn", [disposal.schedule_partial_disposal,
                                disposal.schedule_partial_disposal_declining], ids=["정액", "정률"])
@pytest.mark.parametrize("life", LIVES)
def test_partial_disposal_before_end_leaves_proportional_memorandum(fn, life):
    for fye in (3, 12):
        rows = fn(COST, life, 2000, 3, SOLD, 2001, 1, fye)
        assert rows[-1].book_value == 800
        assert rows[-1].accumulated == COST - SOLD - 800
        assert all(r.depreciation >= 0 for r in rows)


@pytest.mark.parametrize("fn", [disposal.schedule_partial_disposal,
                                disposal.schedule_partial_disposal_declining], ids=["정액", "정률"])
@pytest.mark.parametrize("life", (4, 5, 20, 21, 30, 40, 41))
def test_disposal_timing_does_not_change_final_memorandum(fn, life):
    """상각 종료 전에 팔든 후에 팔든 잔류분의 최종 비망가는 같다."""
    before = fn(COST, life, 2000, 3, SOLD, 2001, 1)
    after = fn(COST, life, 2000, 3, SOLD, 2000 + life + 2, 1)
    assert before[-1].book_value == after[-1].book_value == disposal.residual_memorandum(COST, SOLD)


@pytest.mark.parametrize("sold,memo", [(5_000_000, 900), (12_500_000, 750), (25_000_000, 500),
                                       (37_500_000, 250), (45_000_000, 100)])
def test_memorandum_reads_back_remaining_ratio(sold, memo):
    assert disposal.residual_memorandum(COST, sold) == memo
    assert disposal.schedule_partial_disposal(COST, 5, 2000, 3, sold, 2001, 1)[-1].book_value == memo


def test_capex_then_partial_disposal_uses_combined_basis():
    """증가 후 부분양도: 분모는 통합 취득원가(1.3억) — 4천만 양도 → 잔류 9/13 → 692원."""
    for declining in (False, True):
        rows = monthly_events(100_000_000, 5, 2026, 1, declining=declining,
                              inc=(30_000_000, 2027, 6), disp=(40_000_000, 2028, 7))
        assert rows[-1].book == 692 and rows[-1].acc == 90_000_000 - 692
