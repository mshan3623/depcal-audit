"""원단위 round() 3곳 — x.500 리트머스 (banker's rounding 함정 반전 확인).

배경(docs/IMPROVEMENT_PLAN_2026-07-02.md P2): TI 더존 실측은 반올림(round) 확정이지만,
Python `round()`는 banker's rounding(x.5 → 짝수)이라 상용 4사5입과 정확히 x.500인
자산에서 1원 갈릴 수 있다. A사 데이터엔 그런 자산이 없어 미검증 잠복 리스크였다.

이 파일은 `vcore`의 round() 호출 3곳 각각에 대해 산식이 정확히 x.500이 되는 자산을
설계했다. round()를 명시적 4사5입(`round_half_up` = `math.floor(x + 0.5)`)으로
교체한 뒤 재실행해, 아래 GOLDEN 값이 banker's(내림) 대신 4사5입(올림)으로
반전됐음을 고정(pin)한다. (교체 전 banker's 값은 git 이력의 이전 버전 참고.)

core(dep_tang_engine.py 9곳·dep_intang_engine.py 1곳·depreciation_engine.py 1곳)도
동일 x.500 결함을 갖고 있었음을 실측으로 확인(banker's→half-up 교체가 core 자체
회귀 216개에 전혀 영향 없음)하고 함께 교체했다 — FREEZE_NOTICE.md 예외 사유 2번
(심각한 회계 오류)에 해당. core·vcore 모두 dep_common.round_half_up /
vcore.projection.round_half_up(동일 정의, 중복 정의)을 사용한다.

주의: 개선계획 문서의 예시("정액 5년 rate 0.2")는 실제로는 x.500을 만들 수 없다
(cost×0.2가 *.5가 되려면 cost가 정수가 아니어야 함 — 0.2=1/5라 정수 cost에서 분모 5의
배수 위치에 x.5가 생기지 않는다). 대신 rate가 1/8=0.125인 내용연수 8년을 사용한다.

round() 호출 3곳(vcore/straight_line.py:28, disposal.py:66, disposal.py:126)이 전부이며,
정률법의 int() 절사 사이트는 이번 리트머스 범위 밖(실측 미검증이라 건드리지 않음).
"""
from vcore import straight_line, disposal, monthly


def _vy(rows):
    return [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in rows]


# ── Site 1: straight_line.py:28 — round_half_up(cost × rate) ──────────────
# 내용연수 8년(rate=0.125=1/8), cost=100,000,004 → cost×rate = 12,500,000.5 (정확히 x.500).
# floor=12,500,000(짝수) → banker's는 내림에 머물렀으나, 4사5입은 올림 → 12,500,001.
# 취득월=1월이라 첫해 개월수=12 → yearly=(annual×12)//12=annual, 절사 개입 없이 순수 반영.
# 매년 동일 annual이 누적되므로 연차가 갈수록 book_value가 banker's 대비 1원씩 더 벌어진다.
GOLDEN_SITE1_HALF_UP = [
    (2026, 12, 12_500_001, 12_500_001, 87_500_003),
    (2027, 12, 12_500_001, 25_000_002, 75_000_002),
    (2028, 12, 12_500_001, 37_500_003, 62_500_001),
    (2029, 12, 12_500_001, 50_000_004, 50_000_000),
    (2030, 12, 12_500_001, 62_500_005, 37_499_999),
    (2031, 12, 12_500_001, 75_000_006, 24_999_998),
    (2032, 12, 12_500_001, 87_500_007, 12_499_997),
    (2033, 12, 12_498_997, 99_999_004,      1_000),   # 종료해(비망가 강제, round 사이트와 무관)
]


def test_site1_annual_depreciation_x500_pins_half_up_rounding():
    cost, life = 100_000_004, 8
    assert cost * 0.125 == 12_500_000.5                     # x.500 정확 성립(부동소수 확인)
    got = _vy(straight_line.schedule(cost, life, 2026, 1, 12))
    assert got == GOLDEN_SITE1_HALF_UP
    assert got[0][2] == 12_500_001                           # 4사5입: 올림 (banker's였다면 12,500,000)


# ── Site 2: disposal.py:66 — round_half_up(prev.acc × disposal_amount / cost) ──
# 1억의 절반(5천만/5년/12월결산), 2026-01 취득, 3,750만 부분양도 2026-06.
# 양도월(6월, 인덱스5) 직전 전체기준 누계 prev.acc=4,999,998.
# disposal_accumulated = round_half_up(4,999,998 × 37,500,000 / 50,000,000) = round_half_up(3,749,998.5)
#                       = 3,749,999 (banker's였다면 짝수 유지로 3,749,998).
# depreciation(당기 발생액 합)은 이 round와 무관 — disposal_accumulated는 누계의 기준선만
# 이동시키므로 accumulated/book_value에만 반영되고 depreciation 필드는 불변(격리 확인).
GOLDEN_SITE2_HALF_UP = [
    (2026, 12, 6_249_998,  2_499_999, 10_000_001),
    (2027, 12, 2_500_000,  4_999_999,  7_500_001),
    (2028, 12, 2_500_000,  7_499_999,  5_000_001),
    (2029, 12, 2_500_000,  9_999_999,  2_500_001),
    (2030, 12, 2_499_001, 12_499_000,      1_000),
]


def test_site2_partial_disposal_pre_completion_x500_pins_half_up_rounding():
    cost, life = 50_000_000, 5
    base = monthly.sl_monthly(cost, life, 1)
    prev_acc = base[5].acc                                    # 양도월(6월) 직전 전체기준 누계
    assert prev_acc * 37_500_000 / cost == 3_749_998.5         # x.500 정확 성립
    got = _vy(disposal.schedule_partial_disposal(cost, life, 2026, 1, 37_500_000, 2026, 6, 12))
    assert got == GOLDEN_SITE2_HALF_UP
    assert got[0][2] == 6_249_998                              # depreciation: round 사이트 영향 없음
    assert got[0][3] == 2_499_999                              # accumulated: 4사5입 값(올림)


# ── Site 3: disposal.py:126 — round_half_up(last.accumulated × disposal_amount / cost) ──
# 자연종료(5년 완전상각) 후 소액(75,000원) 부분양도, 2031-01(취득 후 60개월, d=60=life×12).
# last.accumulated(완전상각 누계) = cost − MEMORANDUM = 49,999,000.
# disp_acc = round_half_up(49,999,000 × 75,000 / 50,000,000) = round_half_up(74,998.5) = 74,999
#          (banker's였다면 짝수 유지로 74,998). 이 사이트는 자연종료 후 추가된 처분조정행에만 영향.
GOLDEN_SITE3_HALF_UP = [
    (2026, 12, 10_000_000, 10_000_000, 40_000_000),
    (2027, 12, 10_000_000, 20_000_000, 30_000_000),
    (2028, 12, 10_000_000, 30_000_000, 20_000_000),
    (2029, 12, 10_000_000, 40_000_000, 10_000_000),
    (2030, 12,  9_999_000, 49_999_000,      1_000),   # 자연종료(완전상각)
    (2031,  0,          0, 49_924_001,        999),   # 처분조정행(round 사이트 영향)
]


def test_site3_partial_disposal_post_completion_x500_pins_half_up_rounding():
    cost, life = 50_000_000, 5
    last_accumulated = cost - 1_000                            # MEMORANDUM
    assert last_accumulated * 75_000 / cost == 74_998.5         # x.500 정확 성립
    got = _vy(disposal.schedule_partial_disposal(cost, life, 2026, 1, 75_000, 2031, 1, 12))
    assert got == GOLDEN_SITE3_HALF_UP
    assert got[-1][3] == 49_924_001                             # 처분조정행 누계: 4사5입 값(올림)
    assert got[-1][4] == 999                                    # 처분조정행 장부가: 4사5입 값
