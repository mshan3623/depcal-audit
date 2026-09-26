"""1년 미만 사업연도 — 더존 실측 골든 (2026-09-26 확보).

표본 법인: 12월 결산, 설립 첫 사업연도가 4개월이고 약 1년 반 뒤 흡수합병으로 소멸했다.
그래서 한 법인 안에 **짧은 첫 사업연도**(제1기 4개월)와 **짧은 마지막 의제사업연도**
(2026년 1~2월, 법 §8②)가 모두 있다. 전 자산 정률 5년(0.451). 계산에 필요한 월 단위 값과
금액만 옮기고 법인 식별정보(설립·등기 일자 등)는 뺐다.
원천: 그 법인의 더존 감가상각비명세서 — 기초가액·전기말상각누계액·당기상각비.
"""
from vcore import declining_balance, straight_line
from vcore.disposal import (schedule_extinction, schedule_extinction_declining,
                            schedule_full_disposal_declining)
from vcore.rate_table import STATUTORY_PERMILLE


# ── 짧은 첫 사업연도 (신설법인 제1기, 법 §6) ─────────────────────────────
# 문언상 제1기가 1년 미만이면 시행령 §28② 환산내용연수(내용연수 × 12 ÷ 사업연도 월수) 대상이다.
# 더존은 환산하지 않고 사용월수 ÷ 12로 월할했다 — 엔진과 같다. 제1기 4개월(1월 미만 일수 → 1월),
# 환산내용연수 5 × 12 / 4 = 15년.

FIRST_YEAR_ASSET = dict(cost=2_190_000, acq_year=2024, acq_month=12)   # 제1기 12월 취득
LEDGER_ACC_END_FY2025 = 1_032_876                                      # 대장 전기말상각누계액(2026 기준)


def test_short_first_year_declining_matches_douzone_monthly_proration():
    rows = {r.fiscal_year: r for r in declining_balance.schedule(
        FIRST_YEAR_ASSET["cost"], 5, FIRST_YEAR_ASSET["acq_year"], FIRST_YEAR_ASSET["acq_month"])}
    assert (rows[2024].months, rows[2024].depreciation) == (1, 82_307)   # 2,190,000 × 0.451 × 1/12
    assert rows[2025].accumulated == LEDGER_ACC_END_FY2025


def test_converted_useful_life_does_not_match_douzone():
    """§28② 환산(15년) 두 해석 모두 대장과 다르다 — 더존은 첫해 환산내용연수를 쓰지 않는다."""
    cost, d15, d5 = FIRST_YEAR_ASSET["cost"], STATUTORY_PERMILLE[15][1], STATUTORY_PERMILLE[5][1]
    for first in (cost * d15 * 1 // 4000,       # 환산율 × 사용월수 ÷ 사업연도 월수
                  cost * d15 * 1 // 12000):     # 환산율 × 사용월수 ÷ 12
        acc_2025 = first + (cost - first) * d5 // 1000
        assert acc_2025 != LEDGER_ACC_END_FY2025


# ── 짧은 마지막 의제사업연도 (합병소멸, 법 §8②) ─────────────────────────
# 2026-01-01 ~ 합병등기일(2월) → 2개월. 더존은 이 기간을 2개월짜리 사업연도로 보고
# 연 상각액 × 2 ÷ 12(시행령 §26⑧), 끝수는 등기월이 흡수한다. 양도 경로(월 base × 2)는
# 결산월 끝수 보정이 없어 5건 중 4건에서 1원 적었다(외부 평가 후속 실측 2026-09-26, INC-17).

# (취득원가, 취득연, 취득월, 대장 전기말상각누계액, 대장 당기상각비)
EXTINCTION_LEDGER = [
    (12_035_000, 2025, 6, 3_166_207, 666_637),
    (2_190_000, 2024, 12, 1_032_876, 86_977),
    (1_028_990, 2025, 2, 425_401, 45_369),
    (9_028_000, 2025, 4, 3_053_721, 449_066),
    (1_265_050, 2025, 5, 380_358, 66_499),
]


def test_extinction_short_final_year_matches_douzone():
    for cost, y, m, prev_acc, dep in EXTINCTION_LEDGER:
        rows = schedule_extinction_declining(cost, 5, y, m, 2026, 2)
        assert (rows[-2].fiscal_year, rows[-2].accumulated) == (2025, prev_acc)
        assert (rows[-1].fiscal_year, rows[-1].months, rows[-1].depreciation) == (2026, 2, dep)


def test_disposal_path_is_not_the_short_year_rule():
    """양도(12개월 사업연도 중 제거) 규약은 소멸법인 최종기에 쓰면 안 된다 — 4/5건 1원 부족."""
    short = [dep - schedule_full_disposal_declining(cost, 5, y, m, 2026, 2)[-1].depreciation
             for cost, y, m, _, dep in EXTINCTION_LEDGER]
    assert short == [1, 1, 1, 0, 1]


def test_straight_line_short_final_year_is_annual_times_months_over_12():
    """정액도 같은 규칙 — 마지막 의제사업연도 = 연 상각액 × 월수 ÷ 12(절사)."""
    cost, life = 10_000_007, 7                                 # 연 1,420,001 — 월 끝수가 남는 값
    annual = straight_line.annual_depreciation(cost, life)
    for m in range(1, 12):
        last = schedule_extinction(cost, life, 2024, 1, 2026, m)[-1]
        assert (last.fiscal_year, last.months, last.depreciation) == (2026, m, annual * m // 12)


def test_extinction_after_natural_end_changes_nothing():
    """상각이 끝난 뒤 소멸하면 짧은 사업연도가 상각에 영향이 없다 — 자연완료 표 그대로."""
    natural = declining_balance.schedule(2_190_000, 5, 2019, 1)
    assert schedule_extinction_declining(2_190_000, 5, 2019, 1, 2026, 2) == natural
