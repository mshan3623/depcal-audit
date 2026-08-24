"""무형자산(별표4 직접상각) 손계산 절대 골든값 — core·vcore 독립 외부 기준.

배경(docs/TRUTH_MATRIX.md): 무형 경로는 그동안 외부기준 없이 자기참조뿐이었다(❗빈칸).
무형자산은 정액법으로 상각하되 [별표4] 정액 상각률을 쓴다(vcore.intangible = 유형 정액
슬림 재사용, core는 method=INTANGIBLE). **무형의 외부 진실은 별표4 상각률 그 자체다.**

핵심 앵커 — 내용연수 6년을 쓴다: 별표4 6년율 = 0.166 이라 연상각 = round(1억×0.166)
= 16,600,000 으로, 과거 core/dep_intang_engine 의 1/n 직접나눗셈(1억//6 = 16,666,666)과
'다르다'. 이 차이가 무형이 별표4를 쓰는지 검증하는 리트머스다(4·5·10년은 별표4=1/n이라
무차이라 못 잡음). 종료해에 비망가 1,000 강제.
"""
from vcore import intangible
from vcore.monthly_schedule import monthly_schedule
from core.depreciation_engine import calculate_depreciation_enhanced
from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod

RATE6 = 0.166                       # 별표4 정액율(6년)
ANNUAL6 = round(100_000_000 * RATE6)  # 16,600,000 — 별표4 연상각 (1/6=16,666,666과 다름)


def _vy(rows):
    return [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in rows]


def _core(fye=12, **kw):
    fin = AssetFinancials(cost=100_000_000, life_in_years=6, start_date="2026-01-15",
                          method=DepreciationMethod.INTANGIBLE, **kw)
    info = AssetInfo(asset_id="A", asset_name="특허권", asset_category="무형")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=fye)
    return [(s.year, s.months_count, s.yearly_depreciation,
             s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]


def test_star_table_rate_differs_from_reciprocal():
    """리트머스: 별표4 6년율(0.166)로 만든 연상각은 1/n 나눗셈과 반드시 달라야 한다."""
    assert ANNUAL6 == 16_600_000
    assert 100_000_000 // 6 == 16_666_666
    assert ANNUAL6 != 100_000_000 // 6            # 이 차이가 '별표4를 쓴다'의 증거


# ── 무형 단순 · 6년(별표4 0.166) · 12월 결산 ──────────────────────────────────
# 손계산(연단위 순수 산술 재현): FY2026~2030 = ANNUAL6(16,600,000) 5회, 종료해 FY2031 =
#   직전 장부가(17,000,000) − 비망가(1,000) = 16,999,000. 총상각 99,999,000, 최종 1,000.
GOLDEN_INTANG_SIMPLE = [
    (2026, 12, 16_600_000, 16_600_000, 83_400_000),
    (2027, 12, 16_600_000, 33_200_000, 66_800_000),
    (2028, 12, 16_600_000, 49_800_000, 50_200_000),
    (2029, 12, 16_600_000, 66_400_000, 33_600_000),
    (2030, 12, 16_600_000, 83_000_000, 17_000_000),
    (2031, 12, 16_999_000, 99_999_000,      1_000),   # 종료해(비망가 강제)
]


def _recon_simple_12():
    """연단위 독립 산술 재현(별표4율·비망가 규칙만 사용, 엔진 미호출)."""
    acc, book, rows = 0, 100_000_000, []
    for y in range(2026, 2032):
        dep = ANNUAL6 if y < 2031 else book - 1_000    # 종료해: 직전 장부가 − 비망가
        acc += dep
        book -= dep
        rows.append((y, 12, dep, acc, book))
    return rows


def test_vcore_intangible_simple_matches_handcalc():
    got = _vy(intangible.schedule(100_000_000, 6, 2026, 1, 12))
    assert got == GOLDEN_INTANG_SIMPLE
    assert got == _recon_simple_12()                  # 연단위 독립 산술 재현과 일치(외부 앵커)
    assert got[0][2] == ANNUAL6                        # 연상각 = 별표4(1/n 아님)
    assert got[-1][3] == 99_999_000 and got[-1][4] == 1_000


def test_core_intangible_simple_matches_handcalc():
    assert _core() == GOLDEN_INTANG_SIMPLE


# ── 무형 단순 · 6년 · 임의 결산월(3월) ────────────────────────────────────────
# 3월결산: FY2026=2026.01~03(3m), FY2027~2031=12m, FY2032=2031.04~12(9m).
# 첫 부분월 = ANNUAL6 × 3/12 = 4,150,000. 종료해 FY2032 = 직전 장부가 − 비망가.
GOLDEN_INTANG_SIMPLE_FYE3 = [
    (2026,  3,  4_150_000,  4_150_000, 95_850_000),   # 부분월 3개월
    (2027, 12, 16_600_000, 20_750_000, 79_250_000),
    (2028, 12, 16_600_000, 37_350_000, 62_650_000),
    (2029, 12, 16_600_000, 53_950_000, 46_050_000),
    (2030, 12, 16_600_000, 70_550_000, 29_450_000),
    (2031, 12, 16_600_000, 87_150_000, 12_850_000),
    (2032,  9, 12_849_000, 99_999_000,      1_000),   # 종료해(9개월, 비망가)
]


def test_vcore_intangible_simple_fye3_matches_handcalc():
    got = _vy(intangible.schedule(100_000_000, 6, 2026, 1, 3))
    assert got == GOLDEN_INTANG_SIMPLE_FYE3
    assert got[0][2] == ANNUAL6 * 3 // 12             # 부분월 = 별표4 연상각 × 3/12
    assert got[1][2] == ANNUAL6                        # 온전한 해 = 별표4 연상각
    assert got[-1][3] == 99_999_000 and got[-1][4] == 1_000


def test_core_intangible_simple_fye3_matches_handcalc():
    assert _core(fye=3) == GOLDEN_INTANG_SIMPLE_FYE3


# ── 무형 CAPEX · 6년 · 3월 결산 ──────────────────────────────────────────────
# 케이스: 1억/6년(0.166)/3월결산/2026-01 취득, 2027-06 자본적지출 +3,000만.
# 사건 전 FY2026·FY2027 = 무형 단순 3월결산(GOLDEN_INTANG_SIMPLE_FYE3[:2])과 동일 = 외부 앵커.
# 무결성: 누계+장부 = basis(원가+증가) = 130,000,000, 최종 비망가 1,000.
GOLDEN_INTANG_CAPEX_FYE3 = [
    (2026,  3,  4_150_000,   4_150_000,  95_850_000),   # capex 전 = 무형 단순 3월결산
    (2027, 12, 16_600_000,  20_750_000,  79_250_000),   # = 무형 단순 3월결산
    (2028, 12, 22_026_018,  42_776_018,  87_223_982),   # capex 연도(ratio, 장부 점프 상승)
    (2029, 12, 23_111_222,  65_887_240,  64_112_760),
    (2030, 12, 23_111_222,  88_998_462,  41_001_538),
    (2031, 12, 23_111_222, 112_109_684,  17_890_316),
    (2032,  9, 17_889_316, 129_999_000,       1_000),   # 종료해(9개월, 비망가)
]


def test_vcore_intangible_capex_fye3_matches_handcalc():
    got = _vy(intangible.schedule_with_increase(100_000_000, 6, 2026, 1, 30_000_000, 2027, 6, 3))
    assert got == GOLDEN_INTANG_CAPEX_FYE3
    assert got[:2] == GOLDEN_INTANG_SIMPLE_FYE3[:2]     # 사건 전 = 무형 단순(외부 앵커)
    assert got[-1][3] + got[-1][4] == 130_000_000       # 누계+장부 = basis(원가+증가)
    assert got[-1][4] == 1_000                          # 최종 장부가 = 비망가


def test_core_intangible_capex_fye3_matches_handcalc():
    got = _core(fye=3, increase_date="2027-06-10", increase_amount=30_000_000)
    assert got == GOLDEN_INTANG_CAPEX_FYE3


# ── 무형 전체양도 · 6년 · 3월 결산 ───────────────────────────────────────────
# 케이스: 1억/6년/3월결산/2026-01 취득, 2028-07 전체양도(더존식 양도월 포함).
# 월벡터를 양도월(2028-07)까지 절단. 종료해 없음(미완료) → 비망가 없음.
# FY2029(2028.04~2029.03)는 양도로 4개월(2028.04~07)만 남는다.
# 무결성(절단 항등): 양도월까지 누계+장부 = 원가 100,000,000.
GOLDEN_INTANG_FULL_FYE3 = [
    (2026,  3,  4_150_000,  4_150_000, 95_850_000),
    (2027, 12, 16_600_000, 20_750_000, 79_250_000),
    (2028, 12, 16_600_000, 37_350_000, 62_650_000),
    (2029,  4,  5_533_332, 42_883_332, 57_116_668),   # 양도연도: 양도월(4번째달)까지 절단
]


def test_vcore_intangible_full_disposal_fye3_matches_handcalc():
    got = _vy(intangible.schedule_full_disposal(100_000_000, 6, 2026, 1, 2028, 7, 3))
    assert got == GOLDEN_INTANG_FULL_FYE3
    assert got[:2] == GOLDEN_INTANG_SIMPLE_FYE3[:2]     # 사건 전 = 무형 단순(외부 앵커)
    assert got[-1][1] == 4                              # FY2029 = 2028.04~07 4개월 절단
    assert got[-1][3] + got[-1][4] == 100_000_000       # 절단 항등: 누계+장부 = 원가
    assert got[-1][4] != 1_000                          # 전체양도엔 비망가 없음


def test_core_intangible_full_disposal_fye3_matches_handcalc():
    got = _core(fye=3, disposal_date="2028-07-01", disposal_amount=0)
    assert got == GOLDEN_INTANG_FULL_FYE3


# ── 무형 부분양도 · 6년 · 12월 결산 ──────────────────────────────────────────
# 케이스: 1억/6년(0.166)/12월결산/2026-01 취득, 2028-07 부분양도 4,000만.
#   잔존비율 분모 = 취득원가 100,000,000, 잔존비율 = 1 − 40/100 = 0.6. 양도월까지 전체기준
#   상각 후 누계·장부 안분 차감(더존식 양도월 포함).
# 사건 전 FY2026·FY2027 = 무형 단순 12월(GOLDEN_INTANG_SIMPLE[:2])과 동일 = 외부 앵커.
# FY2028 양도연도: 양도월에 disposed 누계 제거 → 누계 점프 하강(33,200,000 → 29,880,000).
# 무결성: 최종 누계+장부 = cost−양도액 = 60,000,000, 최종 장부가 = 비망가 1,000.
GOLDEN_INTANG_PARTIAL = [
    (2026, 12, 16_600_000, 16_600_000, 83_400_000),   # 사건 전 = 무형 단순
    (2027, 12, 16_600_000, 33_200_000, 66_800_000),   # 사건 전 = 무형 단순
    (2028, 12, 13_833_332, 29_880_000, 30_120_000),   # 부분양도 연도(누계 점프 하강)
    (2029, 12,  9_960_000, 39_840_000, 20_160_000),
    (2030, 12,  9_960_000, 49_800_000, 10_200_000),
    (2031, 12, 10_199_000, 59_999_000,      1_000),   # 종료해(비망가 강제)
]


def test_vcore_intangible_partial_disposal_matches_handcalc():
    got = _vy(intangible.schedule_partial_disposal(100_000_000, 6, 2026, 1, 40_000_000, 2028, 7, 12))
    assert got == GOLDEN_INTANG_PARTIAL
    assert got[:2] == GOLDEN_INTANG_SIMPLE[:2]          # 사건 전 = 무형 단순(외부 앵커)
    assert got[0][2] == ANNUAL6                          # 연상각 = 별표4(1/n 아님)
    assert got[-1][3] + got[-1][4] == 60_000_000        # 누계+장부 = cost−양도액
    assert got[-1][4] == 1_000                          # 최종 장부가 = 비망가


def test_core_intangible_partial_disposal_matches_handcalc():
    got = _core(disposal_date="2028-07-01", disposal_amount=40_000_000)
    assert got == GOLDEN_INTANG_PARTIAL


# ── 무형 부분양도 · 6년 · 3월 결산 ───────────────────────────────────────────
# 3월결산: 양도 2028-07은 FY2029(2028.04~2029.03)에 발생. 사건 전 FY2026~2028 =
# 무형 단순 3월(GOLDEN_INTANG_SIMPLE_FYE3[:3])과 동일 = 외부 앵커.
# FY2029 양도연도 누계 점프 하강(37,350,000 → 32,369,999). 무결성: 누계+장부 = 60,000,000.
GOLDEN_INTANG_PARTIAL_FYE3 = [
    (2026,  3,  4_150_000,  4_150_000, 95_850_000),   # 사건 전 = 무형 단순 3월
    (2027, 12, 16_600_000, 20_750_000, 79_250_000),   # 사건 전 = 무형 단순 3월
    (2028, 12, 16_600_000, 37_350_000, 62_650_000),   # 사건 전 = 무형 단순 3월
    (2029, 12, 12_173_332, 32_369_999, 27_630_001),   # 부분양도 연도(누계 점프 하강)
    (2030, 12,  9_960_000, 42_329_999, 17_670_001),
    (2031, 12,  9_960_000, 52_289_999,  7_710_001),
    (2032,  9,  7_709_001, 59_999_000,      1_000),   # 종료해(9개월, 비망가)
]


def test_vcore_intangible_partial_disposal_fye3_matches_handcalc():
    got = _vy(intangible.schedule_partial_disposal(100_000_000, 6, 2026, 1, 40_000_000, 2028, 7, 3))
    assert got == GOLDEN_INTANG_PARTIAL_FYE3
    assert got[:3] == GOLDEN_INTANG_SIMPLE_FYE3[:3]     # 사건 전 = 무형 단순 3월(외부 앵커)
    assert got[-1][3] + got[-1][4] == 60_000_000        # 누계+장부 = cost−양도액
    assert got[-1][4] == 1_000                          # 최종 장부가 = 비망가


def test_core_intangible_partial_disposal_fye3_matches_handcalc():
    got = _core(fye=3, disposal_date="2028-07-01", disposal_amount=40_000_000)
    assert got == GOLDEN_INTANG_PARTIAL_FYE3


# ── 무형 완전 월단위 손계산 (TRUTH_MATRIX #4 — 연·부분월 → 월단위) ────────────
# 별표4 6년율(0.166)이 월 단위 분포까지 정확히 전파되는지 검증한다. 손계산 규칙(균일):
#   각 회계연도 내 월 base = 연상각 // 그해 개월수, **마지막 달(결산월)이 나머지를 흡수**.
#   누계 = 월 상각 누적, 장부가 = 원가 − 누계. 종료해는 (직전 장부가−비망가)를 같은 규칙으로 배분.
# 이 규칙으로 연 골든(GOLDEN_INTANG_SIMPLE[_FYE3])에서 72개월 전체 (상각,누계,장부)를 재구성해
# vcore 월 스케줄과 1원 대조 → 월↔연 정합을 손계산으로 고정. (엔진 월벡터 미사용 순수 재구성.)
def _recon_months(annual_rows):
    """연 골든 → 월별 (상각, 누계, 장부) 재구성. 각 회계연도 base=dep//개월, 마지막 달이 잔재 흡수."""
    exp, acc = [], 0
    for (_y, mc, dep, _accg, _bookg) in annual_rows:
        base = dep // mc
        rem = dep - base * mc
        for i in range(mc):
            amt = base + (rem if i == mc - 1 else 0)
            acc += amt
            exp.append((amt, acc, 100_000_000 - acc))
    return exp


def test_intangible_monthly_matches_handcalc():
    """무형 6년(별표4 0.166) 12월결산 — 72개월 전체를 연 골든에서 손계산 재구성과 1원 대조."""
    cal = monthly_schedule(100_000_000, 6, 2026, 1, 12, declining=False)
    got = [(m.amount, m.acc, m.book) for m in cal]
    assert got == _recon_months(GOLDEN_INTANG_SIMPLE)     # 72개월 완전 대조
    assert len(got) == 72
    assert cal[0].amount == ANNUAL6 // 12                 # 월 base = 별표4 연상각 // 12
    assert cal[0].amount == 1_383_333                     # 손계산 상수
    assert cal[0].amount != (100_000_000 // 6) // 12      # 1/n 월base(1,388,888) 아님 = 별표4 리트머스
    assert cal[11].amount == 1_383_337                    # 결산월(12월)이 잔재 4원 흡수
    assert cal[-1].book == 1_000                          # 최종 장부가 = 비망가
    assert sum(m.amount for m in cal) == 99_999_000       # 총상각 = 원가 − 비망가


def test_intangible_monthly_fye3_matches_handcalc():
    """무형 6년 3월결산 — 부분월(첫 3개월)·종료해(9개월) 포함 72개월 완전 손계산 대조."""
    cal = monthly_schedule(100_000_000, 6, 2026, 1, 3, declining=False)
    got = [(m.amount, m.acc, m.book) for m in cal]
    assert got == _recon_months(GOLDEN_INTANG_SIMPLE_FYE3)   # 72개월 완전 대조
    assert cal[0].amount == 1_383_333                     # 월 base = 별표4 (1/n 아님)
    assert cal[2].amount == 1_383_334                     # 부분월 결산월(2026-03)이 잔재 1원 흡수
    assert cal[-1].book == 1_000                          # 최종 장부가 = 비망가
    assert sum(m.amount for m in cal) == 99_999_000


# ── 무형 단순 · 3·7·9년 (P-d: 6년 단일 앵커 → 별표4≠1/n 전체 이탈연수 커버) ──
#   vcore/intangible.py 주석이 명시하는 이탈연수(3·6·7·9년) 중 6년만 골든이 있었다.
#   3·7·9년을 추가해 별표4율 사용을 전 이탈연수에서 고정한다. 산식은 6년과 동일:
#   연상각 = 4사5입(1억 × 별표4율), 종료해 = 직전 장부가 − 비망가(1,000).
#   리트머스(별표4 vs 1/n): 3년 33,300,000 vs 33,333,333 / 7년 14,200,000 vs
#   14,285,714 / 9년 11,100,000 vs 11,111,111 — 모두 달라야 별표4 사용의 증거.
RATE_BY_LIFE = {3: 0.333, 7: 0.142, 9: 0.111}     # 별표4 정액율(1/n 소수 3자리 절사)

GOLDEN_INTANG_3Y = [
    (2026, 12, 33_300_000, 33_300_000, 66_700_000),
    (2027, 12, 33_300_000, 66_600_000, 33_400_000),
    (2028, 12, 33_399_000, 99_999_000,      1_000),   # 종료해(비망가 강제)
]
GOLDEN_INTANG_7Y = [
    (2026, 12, 14_200_000, 14_200_000, 85_800_000),
    (2027, 12, 14_200_000, 28_400_000, 71_600_000),
    (2028, 12, 14_200_000, 42_600_000, 57_400_000),
    (2029, 12, 14_200_000, 56_800_000, 43_200_000),
    (2030, 12, 14_200_000, 71_000_000, 29_000_000),
    (2031, 12, 14_200_000, 85_200_000, 14_800_000),
    (2032, 12, 14_799_000, 99_999_000,      1_000),   # 종료해(비망가 강제)
]
GOLDEN_INTANG_9Y = [
    (2026, 12, 11_100_000, 11_100_000, 88_900_000),
    (2027, 12, 11_100_000, 22_200_000, 77_800_000),
    (2028, 12, 11_100_000, 33_300_000, 66_700_000),
    (2029, 12, 11_100_000, 44_400_000, 55_600_000),
    (2030, 12, 11_100_000, 55_500_000, 44_500_000),
    (2031, 12, 11_100_000, 66_600_000, 33_400_000),
    (2032, 12, 11_100_000, 77_700_000, 22_300_000),
    (2033, 12, 11_100_000, 88_800_000, 11_200_000),
    (2034, 12, 11_199_000, 99_999_000,      1_000),   # 종료해(비망가 강제)
]
_GOLDEN_BY_LIFE = {3: GOLDEN_INTANG_3Y, 7: GOLDEN_INTANG_7Y, 9: GOLDEN_INTANG_9Y}


def _core_life(life):
    fin = AssetFinancials(cost=100_000_000, life_in_years=life, start_date="2026-01-15",
                          method=DepreciationMethod.INTANGIBLE)
    info = AssetInfo(asset_id="A", asset_name="특허권", asset_category="무형")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=12)
    return [(s.year, s.months_count, s.yearly_depreciation,
             s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]


import pytest


@pytest.mark.parametrize("life", [3, 7, 9])
def test_vcore_intangible_odd_life_matches_handcalc(life):
    annual = round(100_000_000 * RATE_BY_LIFE[life])
    assert annual != 100_000_000 // life              # 리트머스: 별표4 ≠ 1/n
    got = _vy(intangible.schedule(100_000_000, life, 2026, 1, 12))
    assert got == _GOLDEN_BY_LIFE[life]
    assert all(r[2] == annual for r in got[:-1])      # 온전한 해 = 별표4 연상각
    assert got[-1][3] == 99_999_000 and got[-1][4] == 1_000


@pytest.mark.parametrize("life", [3, 7, 9])
def test_core_intangible_odd_life_matches_handcalc(life):
    assert _core_life(life) == _GOLDEN_BY_LIFE[life]
