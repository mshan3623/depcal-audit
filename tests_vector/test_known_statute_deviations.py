"""법령 문언과 다른 채로 **의도적으로 유지하는** 엔진 규약 — 알려진 편차 고정.

외부 평가 2026-09-26이 법령 문언 참조모델로 찾은 이탈 중, 더존 실측 앵커가 없어 어느 쪽을
따를지 정하지 않은 두 가지를 여기 둔다(사용자 결정 2026-09-26: 실측 앵커가 생길 때까지
현행 유지). 이 테스트는 현행 동작이 옳다는 주장이 아니다 — **편차가 있다는 사실과 크기**를
고정해, 동작을 바꾸는 사람이 이 파일을 먼저 고치게 만든다. 목록: docs/TRUTH_MATRIX.md
「법령 문언과의 알려진 편차」.
"""
from vcore import capex, straight_line
from vcore.rate_table import STATUTORY_PERMILLE

COST = 100_000_000


# ── ② 정액법 종료해 잔재 흡수 ─────────────────────────────────────────────
# 별표4 정액률 × 내용연수 < 1인 연수는 내용연수가 끝나도 잔재가 남는다. 엔진은 종료해에 잔액을
# 전부 상각하지만, 문언(§26② 1호 정액법 + §26⑥ 본문 잔존가액 0)상 매년 상각범위액은
# 취득가액 × 상각률이라 잔재는 다음 사업연도 몫이다 → 종료해에 상각부인액이 생긴다.
# 반대 방향(× 내용연수 > 1, 올림표 연수)은 INC-11 — test_golden_handcalc_other_lives.py.

def test_residual_lives_are_the_truncated_table_entries():
    under = [n for n, (sl, _) in sorted(STATUTORY_PERMILLE.items()) if sl * n < 1000]
    assert under == [3, 6, 7, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 27, 37]


def test_straight_line_final_year_absorbs_residual_beyond_statutory_range():
    rows = straight_line.schedule(COST, 6, 2020, 1)
    statutory_cap = COST * 166 // 1000                        # 16,600,000
    assert rows[-1].fiscal_year == 2025
    assert rows[-1].depreciation == 16_999_000                 # 엔진
    assert rows[-1].depreciation - statutory_cap == 399_000    # = 1억 × (1 − 0.166×6) − 1,000
    # 문언이면 FY2025 16,600,000, FY2026 399,000(잔재 − 비망). 엔진에는 FY2026 행이 없다.
    assert all(r.fiscal_year <= 2025 for r in rows)


# ── ③ 자본적지출: 회계식(잔존내용연수 안분 + 월할) ─────────────────────────
# 엔진: 증가 직전월 장부가 B 기준으로 증가월부터 월 상각을 (B + 증가액) / B 배, 원래 종료월에 끝.
# 문언: 정액 상각범위액 = (취득가액 + 자본적지출) × 상각률, 기중 지출분도 월할하지 않는다
# (법인46012-3342). 총액은 같고 연도 배분만 다르다. 더존 자본적지출 실측도 0건.

ENGINE_CAPEX = [(2024, 20_000_000), (2025, 21_428_571), (2026, 22_857_142),
                (2027, 22_857_142), (2028, 22_856_145)]
STATUTE_CAPEX = [(2024, 20_000_000), (2025, 22_000_000), (2026, 22_000_000),
                 (2027, 22_000_000), (2028, 22_000_000), (2029, 1_999_000)]


def test_capex_is_spread_over_remaining_life_not_statutory():
    rows = capex.schedule_with_increase(COST, 5, 2024, 1, 10_000_000, 2025, 7)
    assert [(r.fiscal_year, r.depreciation) for r in rows] == ENGINE_CAPEX
    assert sum(d for _, d in ENGINE_CAPEX) == sum(d for _, d in STATUTE_CAPEX) == 109_999_000
    statute = dict(STATUTE_CAPEX)
    assert statute[2025] - 21_428_571 == 571_429                # 엔진이 시인부족
    assert 22_857_142 - statute[2026] == 857_142                # 엔진이 상각부인
