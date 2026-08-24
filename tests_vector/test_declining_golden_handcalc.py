"""정률법 손계산 절대 골든값 — core·vcore 독립 외부 기준.

정률 더존 실측은 2026-07 B사 대장으로 확보됐으나(`test_real_ledger_b.py`,
FY2025 6건 — 절사 규칙까지 실증), 그 실측이 덮는 건 **단순 × 12월결산**뿐이다.
CAPEX·부분/전체양도·임의결산월 조합은 더존 실측이 0건이고, 나머지 정률 테스트는
전부 core↔vcore 자기참조(assert got==core)라 둘이 함께 틀려도 못 잡는다.
이 파일은 법인세법 별표4 상각률로 사람이 직접 손계산한 값을 하드코딩해,
core·vcore 어느 쪽에도 의존하지 않는 제3의 기준을 고정한다.

케이스: 취득원가 1억, 내용연수 5년(별표4 정률율 0.451), 12월 결산, 2026-01 취득.
  연 상각 = int(기초장부가 × 0.451)  (12개월 풀이라 ×12//12=×1)
  종료해(5년차) = 기초장부가 − 비망가(1,000), 그해 12개월로 월할 균등 배분.

손계산 (단위 원):
  FY     기초장부가      상각액       누계         기말장부가
  2026  100,000,000   45,100,000   45,100,000   54,900,000
  2027   54,900,000   24,759,900   69,859,900   30,140,100
  2028   30,140,100   13,593,185   83,453,085   16,546,915
  2029   16,546,915    7,462,658   90,915,743    9,084,257
  2030    9,084,257    9,083,257   99,999,000        1,000   ← 종료해(잔액−비망가)
  종료해 월별 = [756,938]×11 + [756,939]  (= 9,083,257 균등배분)
"""
from vcore import declining_balance, capex, disposal
from vcore.monthly_schedule import monthly_schedule, monthly_events
from core.depreciation_engine import calculate_depreciation_enhanced
from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod


def _core_yearly_declining(fye=12, **kw):
    fin = AssetFinancials(cost=100_000_000, life_in_years=5, start_date="2026-01-15",
                          method=DepreciationMethod.DECLINING_BALANCE, **kw)
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=fye)
    return [(s.year, s.months_count, s.yearly_depreciation,
             s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]

# (fiscal_year, months, depreciation, accumulated, book_value) — 손계산 확정값
GOLDEN_YEARLY = [
    (2026, 12, 45_100_000, 45_100_000, 54_900_000),
    (2027, 12, 24_759_900, 69_859_900, 30_140_100),
    (2028, 12, 13_593_185, 83_453_085, 16_546_915),
    (2029, 12,  7_462_658, 90_915_743,  9_084_257),
    (2030, 12,  9_083_257, 99_999_000,      1_000),
]
GOLDEN_TERMINAL_MONTHS = [756_938] * 11 + [756_939]


def test_vcore_declining_yearly_matches_handcalc():
    rows = declining_balance.schedule(100_000_000, 5, 2026, 1, 12)
    got = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in rows]
    assert got == GOLDEN_YEARLY


def test_core_declining_yearly_matches_handcalc():
    fin = AssetFinancials(cost=100_000_000, life_in_years=5, start_date="2026-01-15",
                          method=DepreciationMethod.DECLINING_BALANCE)
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=12)
    got = [(s.year, s.months_count, s.yearly_depreciation,
            s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]
    assert got == GOLDEN_YEARLY


def test_vcore_declining_terminal_months_match_handcalc():
    """종료해 5% 잔재가 dump 아닌 월할 균등배분(손계산값)으로 분포한다."""
    cal = monthly_schedule(100_000_000, 5, 2026, 1, 12, declining=True)
    terminal = [m.amount for m in cal if m.year == 2030]
    assert terminal == GOLDEN_TERMINAL_MONTHS
    assert sum(terminal) == 9_083_257


# ── 임의 결산월(3월) 정률 — 첫해 부분월(3개월) + 종료해 부분월(9개월) ──────────
# 케이스: 1억/5년(0.451)/3월 결산/2026-01 취득.
# 3월 결산 회계연도 경계: FY2026=2026.01~03(3m), FY2027~2030=각 12m, FY2031=2030.04~12(9m).
#   비종료해 연 상각 = int(기초장부가 × 0.451 × 개월수 // 12)
#   종료해(FY2031) = 기초장부가 − 비망가, 그해 9개월로 월할 균등 배분.
#
# 손계산 (단위 원):
#   FY     개월  기초장부가      상각액       누계         기말장부가
#   2026    3   100,000,000   11,275,000   11,275,000   88,725,000
#   2027   12    88,725,000   40,014,975   51,289,975   48,710,025
#   2028   12    48,710,025   21,968,221   73,258,196   26,741,804
#   2029   12    26,741,804   12,060,553   85,318,749   14,681,251
#   2030   12    14,681,251    6,621,244   91,939,993    8,060,007
#   2031    9     8,060,007    8,059,007   99,999,000        1,000   ← 종료해
#   종료해 월별 = [895,445]×8 + [895,447]  (= 8,059,007 / 9 균등배분)
GOLDEN_YEARLY_FYE3 = [
    (2026,  3, 11_275_000, 11_275_000, 88_725_000),
    (2027, 12, 40_014_975, 51_289_975, 48_710_025),
    (2028, 12, 21_968_221, 73_258_196, 26_741_804),
    (2029, 12, 12_060_553, 85_318_749, 14_681_251),
    (2030, 12,  6_621_244, 91_939_993,  8_060_007),
    (2031,  9,  8_059_007, 99_999_000,      1_000),
]
GOLDEN_TERMINAL_MONTHS_FYE3 = [895_445] * 8 + [895_447]


def test_vcore_declining_yearly_fye3_matches_handcalc():
    rows = declining_balance.schedule(100_000_000, 5, 2026, 1, 3)
    got = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in rows]
    assert got == GOLDEN_YEARLY_FYE3


def test_core_declining_yearly_fye3_matches_handcalc():
    fin = AssetFinancials(cost=100_000_000, life_in_years=5, start_date="2026-01-15",
                          method=DepreciationMethod.DECLINING_BALANCE)
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=3)
    got = [(s.year, s.months_count, s.yearly_depreciation,
            s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]
    assert got == GOLDEN_YEARLY_FYE3


def test_vcore_declining_terminal_months_fye3_match_handcalc():
    """임의 결산월에서도 종료해(9개월) 잔재가 월할 균등배분된다."""
    cal = monthly_schedule(100_000_000, 5, 2026, 1, 3, declining=True)
    terminal = [m.amount for m in cal if (m.year, m.month) >= (2030, 4)]
    assert terminal == GOLDEN_TERMINAL_MONTHS_FYE3
    assert sum(terminal) == 8_059_007


# ── 정률 CAPEX(자본적지출) 단독 ────────────────────────────────────────────
# 케이스: 1억/5년(0.451)/12월결산/2026-01 취득, 2027-06 자본적지출 +3,000만.
# 컨벤션(레퍼런스 Vector 비율): 증가 직전월 장부가 B → ratio=(B+증가액)/B, 증가월부터
# base 월상각×ratio, 회계연도별 연말보정으로 연 목표 int(base연합×ratio) 달성. 종료해 균등배분.
# 손계산: 엔진 capex 모듈을 쓰지 않은 순수 산술 재현이 core·vcore와 1원 일치(검증 완료).
# 무결성: 누계+장부가 = 원가+증가액 = 130,000,000, 최종 장부가 = 비망가 1,000.
GOLDEN_CAPEX = [
    (2026, 12,  45_100_000,  45_100_000,  54_900_000),   # 증가 전 = 단순 정률 1년차
    (2027, 12,  34_478_730,  79_578_730,  50_421_270),   # 증가연도(ratio 적용)
    (2028, 12,  22_739_992, 102_318_722,  27_681_278),
    (2029, 12,  12_484_254, 114_802_976,  15_197_024),
    (2030, 12,  15_196_024, 129_999_000,       1_000),   # 종료해
]


def test_vcore_declining_capex_matches_handcalc():
    rows = capex.schedule_with_increase_declining(100_000_000, 5, 2026, 1, 30_000_000, 2027, 6, 12)
    got = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in rows]
    assert got == GOLDEN_CAPEX
    assert got[0][2] == 45_100_000                       # 증가 전 해는 단순 정률과 동일
    assert got[-1][3] + got[-1][4] == 130_000_000        # 누계+장부가 = 원가+증가액
    assert got[-1][4] == 1_000                           # 최종 장부가 = 비망가


def test_core_declining_capex_matches_handcalc():
    got = _core_yearly_declining(increase_date="2027-06-10", increase_amount=30_000_000)
    assert got == GOLDEN_CAPEX


# ── 정률 부분양도 단독 ─────────────────────────────────────────────────────
# 케이스: 1억/5년(0.451)/12월결산/2026-01 취득, 2027-06 부분양도 4,000만(더존식 양도월 포함).
# 컨벤션: remaining_ratio=1−양도액/원가=0.6. 양도월말 누계·장부가를 비율 분배(누계=round,
# 잔존=차감), 이후 회계연도 잔존상각=int(base연합×0.6) 연말보정. 종료해 균등배분.
# 손계산: 엔진 disposal 모듈 미사용 순수 산술 재현이 core·vcore와 1원 일치(검증 완료).
# 무결성: 누계+장부가 = 잔존원가 = 60,000,000, 최종 장부가 = 비망가 1,000.
GOLDEN_PARTIAL = [
    (2026, 12,  45_100_000,  45_100_000,  54_900_000),   # 양도 전 = 단순 정률 1년차
    (2027, 12,  19_807_920,  41_915_940,  18_084_060),   # 양도연도(누계 점프 하강)
    (2028, 12,   8_155_911,  50_071_851,   9_928_149),
    (2029, 12,   4_477_594,  54_549_445,   5_450_555),
    (2030, 12,   5_449_555,  59_999_000,       1_000),   # 종료해
]


def test_vcore_declining_partial_disposal_matches_handcalc():
    rows = disposal.schedule_partial_disposal_declining(100_000_000, 5, 2026, 1, 40_000_000, 2027, 6, 12)
    got = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in rows]
    assert got == GOLDEN_PARTIAL
    assert got[0][2] == 45_100_000                       # 양도 전 해는 단순 정률과 동일
    assert got[-1][3] + got[-1][4] == 60_000_000         # 누계+장부가 = 잔존원가(원가−양도액)
    assert got[-1][4] == 1_000                           # 최종 장부가 = 비망가


def test_core_declining_partial_disposal_matches_handcalc():
    got = _core_yearly_declining(disposal_date="2027-06-01", disposal_amount=40_000_000)
    assert got == GOLDEN_PARTIAL


# ── 정률 부분양도 단독 · 임의 결산월(3월) (TRUTH_MATRIX △임의월 해소) ─────────
# 12월 케이스(GOLDEN_PARTIAL)와 같은 사건(양도 2027-06, 4,000만)을 3월결산으로.
# 3월결산에서 양도 2027-06은 FY2028(2027.04~2028.03)에 발생.
# 사건 전 FY2026·FY2027 = 정률 단순 3월(GOLDEN_YEARLY_FYE3[:2])과 동일 = 외부 앵커.
# 손계산: db_monthly(외부검증 프리미티브) + disposal 로직 독립 재현이 core·vcore와 1원 일치.
# 무결성: 최종 누계+장부 = 잔존원가 = 60,000,000, 최종 장부가 = 비망가 1,000.
GOLDEN_PARTIAL_FYE3 = [
    (2026,  3, 11_275_000, 11_275_000, 88_725_000),   # 양도 전 = GOLDEN_YEARLY_FYE3[0]
    (2027, 12, 40_014_975, 51_289_975, 48_710_025),   # 양도 전 = GOLDEN_YEARLY_FYE3[1]
    (2028, 12, 15_377_754, 43_954_917, 16_045_083),   # 양도연도(누계 점프 하강)
    (2029, 12,  7_236_331, 51_191_248,  8_808_752),
    (2030, 12,  3_972_746, 55_163_994,  4_836_006),
    (2031,  9,  4_835_006, 59_999_000,      1_000),   # 종료해(9개월, 비망가)
]


def test_vcore_declining_partial_disposal_fye3_matches_handcalc():
    rows = disposal.schedule_partial_disposal_declining(100_000_000, 5, 2026, 1, 40_000_000, 2027, 6, 3)
    got = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in rows]
    assert got == GOLDEN_PARTIAL_FYE3
    assert got[:2] == GOLDEN_YEARLY_FYE3[:2]             # 양도 전 = 정률 단순 3월(외부 앵커)
    assert got[-1][3] + got[-1][4] == 60_000_000         # 누계+장부가 = 잔존원가(원가−양도액)
    assert got[-1][4] == 1_000                           # 최종 장부가 = 비망가


def test_core_declining_partial_disposal_fye3_matches_handcalc():
    got = _core_yearly_declining(fye=3, disposal_date="2027-06-01", disposal_amount=40_000_000)
    assert got == GOLDEN_PARTIAL_FYE3


# ── 정률 CAPEX + 부분양도 조합 (vcore 단독) ────────────────────────────────
# core는 이 경로에서 음수 월상각 버그가 있어 oracle 자격 없음(2026-06-12 확인) → 비교 제외.
# vcore 변환 합성: 증가(ratio) 적용 → 부분양도(잔존비율, 분모=통합 취득원가 basis) 적용 → 종료해 균등.
# 케이스: 1억/5년/12월결산/2026-01 취득, 2027-06 +3,000만, 2028-07 −4,000만(더존식 양도월 포함).
#   basis(통합 취득원가) = 1억+3,000만 = 130,000,000. remaining_ratio = 1−4,000만/basis.
# 손계산: 엔진 capex/disposal 모듈 미사용 순수 산술 재현이 vcore와 1원 일치(검증 완료).
# 무결성: 누계+장부가 = basis−양도액 = 90,000,000, 최종 비망가, 전 구간 음수 월상각 없음.
GOLDEN_CAPEX_PARTIAL = [
    (2026, 45_100_000, 45_100_000, 54_900_000),   # 사건 전 = 단순 정률 1년차
    (2027, 34_478_730, 79_578_730, 50_421_270),   # capex 연도(ratio)
    (2028, 19_824_605, 70_836_038, 19_163_962),   # 부분양도 연도(누계 점프 하강)
    (2029,  8_642_945, 79_478_983, 10_521_017),
    (2030, 10_520_017, 89_999_000,      1_000),   # 종료해
]


def _vcore_combo_yearly():
    cal = monthly_events(100_000_000, 5, 2026, 1, 12, declining=True,
                         inc=(30_000_000, 2027, 6), disp=(40_000_000, 2028, 7))
    rows, order = {}, []
    for c in cal:
        if c.year not in rows:
            rows[c.year] = [0, 0, 0]
            order.append(c.year)
        rows[c.year][0] += c.amount
        rows[c.year][1] = c.acc
        rows[c.year][2] = c.book
    return [(y, *rows[y]) for y in order], cal


def test_vcore_declining_capex_then_partial_matches_handcalc():
    """core 음수버그 경로 — vcore 단독 손계산 골든으로 회귀 고정."""
    got, cal = _vcore_combo_yearly()
    assert got == GOLDEN_CAPEX_PARTIAL
    assert all(c.amount >= 0 for c in cal)               # core 버그(음수 월상각) 없음
    assert got[-1][2] + got[-1][3] == 90_000_000         # 누계+장부가 = basis−양도액
    assert got[-1][3] == 1_000                           # 최종 장부가 = 비망가


def test_core_declining_capex_then_partial_matches_handcalc():
    """core 정률 capex+부분양도: 음수버그 수정 + vcore 위임으로 손계산 골든과 1원 일치."""
    got = _core_yearly_declining(increase_date="2027-06-10", increase_amount=30_000_000,
                                 disposal_date="2028-07-01", disposal_amount=40_000_000)
    expect = [(y, 12, dep, acc, book) for (y, dep, acc, book) in GOLDEN_CAPEX_PARTIAL]
    assert got == expect


# ── 정률 CAPEX + 전체양도 조합 ─────────────────────────────────────────────
# 케이스: 1억/5년/12월결산/2026-01 취득, 2027-06 +3,000만, 2028-07 전체양도(더존식 양도월 포함).
# 전체양도 = capex 적용 월벡터를 양도월(2028-07)까지 절단. 종료해 없음(미완료 구간, settle 미적용).
# 손계산: 엔진 capex/disposal 모듈 미사용 순수 산술 재현이 core·vcore와 1원 일치(검증 완료).
# 무결성: 양도월까지 누계+장부가 = basis(원가+증가) = 130,000,000.
GOLDEN_CAPEX_FULL = [
    (2026, 12, 45_100_000, 45_100_000, 54_900_000),   # capex 전 = 단순 정률 1년차
    (2027, 12, 34_478_730, 79_578_730, 50_421_270),   # capex 연도(ratio)
    (2028,  7, 13_264_986, 92_843_716, 37_156_284),   # 양도연도: 양도월(7월)까지 절단
]


def test_vcore_declining_capex_then_full_disposal_matches_handcalc():
    cal = monthly_events(100_000_000, 5, 2026, 1, 12, declining=True,
                         inc=(30_000_000, 2027, 6), disp=(None, 2028, 7))
    rows, order = {}, []
    for c in cal:
        if c.year not in rows:
            rows[c.year] = [0, 0, 0, 0]
            order.append(c.year)
        rows[c.year][0] += 1
        rows[c.year][1] += c.amount
        rows[c.year][2] = c.acc
        rows[c.year][3] = c.book
    got = [(y, *rows[y]) for y in order]
    assert got == GOLDEN_CAPEX_FULL
    assert (cal[-1].year, cal[-1].month) == (2028, 7)        # 양도월 포함(더존식)
    assert got[-1][3] + got[-1][4] == 130_000_000            # 양도월까지 누계+장부 = basis


def test_core_declining_capex_then_full_disposal_matches_handcalc():
    got = _core_yearly_declining(increase_date="2027-06-10", increase_amount=30_000_000,
                                 disposal_date="2028-07-01", disposal_amount=0)
    assert got == GOLDEN_CAPEX_FULL


# ── 정률 임의 결산월(3월) + CAPEX (부분월 × ratio 동시) ─────────────────────
# 케이스: 1억/5년/3월결산/2026-01 취득, 2027-06 +3,000만. 첫해 부분월(3개월)과 capex
# ratio가 동시에 작동하는 가장 복잡한 조합. 3월결산 회계연도 경계 + capex는 FY2028
# (2027.04~2028.03)에 발생. 종료해(FY2031, 9개월)는 균등배분.
# 손계산: 임의결산월 일반화 순수 산술 재현이 core·vcore와 1원 일치(검증 완료).
# 무결성: 누계+장부가 = basis = 130,000,000, 최종 비망가.
GOLDEN_CAPEX_FYE3 = [
    (2026,  3,  11_275_000,  11_275_000,  88_725_000),   # 부분월 3개월(capex 전)
    (2027, 12,  40_014_975,  51_289_975,  48_710_025),
    (2028, 12,  34_159_606,  85_449_581,  44_550_419),   # capex 연도(ratio)
    (2029, 12,  20_092_237, 105_541_818,  24_458_182),
    (2030, 12,  11_030_639, 116_572_457,  13_427_543),
    (2031,  9,  13_426_543, 129_999_000,       1_000),   # 종료해(9개월 균등)
]


def test_vcore_declining_capex_fye3_matches_handcalc():
    rows = capex.schedule_with_increase_declining(100_000_000, 5, 2026, 1, 30_000_000, 2027, 6, 3)
    got = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in rows]
    assert got == GOLDEN_CAPEX_FYE3
    assert got[-1][3] + got[-1][4] == 130_000_000        # 누계+장부가 = basis
    assert got[-1][4] == 1_000                           # 최종 비망가


def test_core_declining_capex_fye3_matches_handcalc():
    got = _core_yearly_declining(fye=3, increase_date="2027-06-10", increase_amount=30_000_000)
    assert got == GOLDEN_CAPEX_FYE3


# ── 정률 임의 결산월(3월) + CAPEX + 양도 조합 (△임의월 빈칸 해소) ────────────
# combo(capex+양도)는 schedule_* API가 없고 monthly_events(달력 월)만 있으므로, 회계연도
# 집계는 달력월→회계연도 라벨(3월결산: m≤3→당해연도, 그 외 →+1)로 수행한다. 12월결산은
# 달력=회계라 기존 c.year 집계와 동치.
def _events_yearly_fye(cal, fye):
    """monthly_events 달력월 → 회계연도별 집계 (임의 결산월). fy = y if month≤fye else y+1."""
    rows, order = {}, []
    for c in cal:
        fy = c.year if c.month <= fye else c.year + 1
        if fy not in rows:
            rows[fy] = [0, 0, 0, 0]
            order.append(fy)
        rows[fy][0] += 1
        rows[fy][1] += c.amount
        rows[fy][2] = c.acc
        rows[fy][3] = c.book
    return [(y, *rows[y]) for y in order]


# 케이스: 1억/5년/3월결산/2026-01 취득, 2027-06 +3,000만, 2028-07 양도(더존식 양도월 포함).
# 사건 전 FY2026~2028은 capex 단독 3월결산(GOLDEN_CAPEX_FYE3)과 동일 = 외부 앵커.
# 양도는 FY2029(2028.04~2029.03) 4번째 달(2028-07)에 발생.
# 손계산: db_monthly(외부검증 프리미티브) + capex/disposal 로직 독립 재현이 core·vcore와
#   1원 일치(검증 완료 — 3자 대조). 무결성: 부분양도 누계+장부 = basis−양도 = 90,000,000.
GOLDEN_CAPEX_PARTIAL_FYE3 = [
    (2026,  3, 11_275_000, 11_275_000, 88_725_000),   # capex 전 = GOLDEN_CAPEX_FYE3[0]
    (2027, 12, 40_014_975, 51_289_975, 48_710_025),   # = GOLDEN_CAPEX_FYE3[1]
    (2028, 12, 34_159_606, 85_449_581, 44_550_419),   # capex 연도 = GOLDEN_CAPEX_FYE3[2]
    (2029, 12, 15_970_751, 73_067_412, 16_932_588),   # 부분양도 연도(누계 점프 하강)
    (2030, 12,  7_636_596, 80_704_008,  9_295_992),
    (2031,  9,  9_294_992, 89_999_000,      1_000),   # 종료해(9개월, 비망가)
]


def test_vcore_declining_capex_then_partial_fye3_matches_handcalc():
    cal = monthly_events(100_000_000, 5, 2026, 1, 3, declining=True,
                         inc=(30_000_000, 2027, 6), disp=(40_000_000, 2028, 7))
    got = _events_yearly_fye(cal, 3)
    assert got == GOLDEN_CAPEX_PARTIAL_FYE3
    assert got[:3] == GOLDEN_CAPEX_FYE3[:3]              # 사건 전 = capex 단독 3월결산(외부 앵커)
    assert all(c.amount >= 0 for c in cal)               # 음수 월상각 없음
    assert got[-1][3] + got[-1][4] == 90_000_000         # 누계+장부 = basis−양도액
    assert got[-1][4] == 1_000                           # 최종 장부가 = 비망가


def test_core_declining_capex_then_partial_fye3_matches_handcalc():
    got = _core_yearly_declining(fye=3, increase_date="2027-06-10", increase_amount=30_000_000,
                                 disposal_date="2028-07-01", disposal_amount=40_000_000)
    assert got == GOLDEN_CAPEX_PARTIAL_FYE3


# 전체양도: 월벡터를 양도월(2028-07)까지 절단. 종료해 없음(미완료), 비망가 없음.
# FY2029(2028.04~2029.03)는 양도로 4개월(2028.04~07)만 남는다.
# 무결성(절단 항등): 양도월까지 누계+장부 = basis(원가+증가) = 130,000,000.
GOLDEN_CAPEX_FULL_FYE3 = [
    (2026,  3, 11_275_000, 11_275_000, 88_725_000),   # = GOLDEN_CAPEX_FYE3[0]
    (2027, 12, 40_014_975, 51_289_975, 48_710_025),   # = GOLDEN_CAPEX_FYE3[1]
    (2028, 12, 34_159_606, 85_449_581, 44_550_419),   # = GOLDEN_CAPEX_FYE3[2]
    (2029,  4,  6_697_408, 92_146_989, 37_853_011),   # 양도연도: 양도월(4번째달)까지 절단
]


def test_vcore_declining_capex_then_full_disposal_fye3_matches_handcalc():
    cal = monthly_events(100_000_000, 5, 2026, 1, 3, declining=True,
                         inc=(30_000_000, 2027, 6), disp=(None, 2028, 7))
    got = _events_yearly_fye(cal, 3)
    assert got == GOLDEN_CAPEX_FULL_FYE3
    assert got[:3] == GOLDEN_CAPEX_FYE3[:3]              # 사건 전 = capex 단독 3월결산(외부 앵커)
    assert (cal[-1].year, cal[-1].month) == (2028, 7)    # 양도월 포함(더존식)
    assert got[-1][1] == 4                               # FY2029 = 2028.04~07 4개월 절단
    assert got[-1][3] + got[-1][4] == 130_000_000        # 절단 항등: 누계+장부 = basis
    assert got[-1][4] != 1_000                           # 전체양도엔 비망가 없음


def test_core_declining_capex_then_full_disposal_fye3_matches_handcalc():
    got = _core_yearly_declining(fye=3, increase_date="2027-06-10", increase_amount=30_000_000,
                                 disposal_date="2028-07-01", disposal_amount=0)
    assert got == GOLDEN_CAPEX_FULL_FYE3


# ── 정률 전체양도 단독 (TRUTH_MATRIX ❗빈칸 해소) ─────────────────────────────
# 케이스: 1억/5년(0.451)/2026-01 취득, 2028-07 전체양도(더존식 양도월 포함), capex 없음.
# 전체양도 = 정률 월벡터를 양도월(2028-07)까지 절단. 종료해 없음(미완료, settle 미적용) → 비망가 없음.
# 손계산: db_monthly(외부검증 프리미티브) 절단 후 회계연도 집계가 core·vcore와 1원 일치(3자 대조 검증).
# 사건 전 연도 = 정률 단순 골든(GOLDEN_YEARLY / GOLDEN_YEARLY_FYE3)과 동일 = 외부 앵커.
# 무결성(절단 항등): 양도월까지 누계+장부 = 원가 100,000,000.
def _vy_decl(rows):
    return [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in rows]


GOLDEN_DECLINING_FULL = [
    (2026, 12, 45_100_000, 45_100_000, 54_900_000),   # = GOLDEN_YEARLY[0]
    (2027, 12, 24_759_900, 69_859_900, 30_140_100),   # = GOLDEN_YEARLY[1]
    (2028,  7,  7_929_355, 77_789_255, 22_210_745),   # 양도연도: 양도월(7월)까지 절단
]


def test_vcore_declining_full_disposal_matches_handcalc():
    got = _vy_decl(disposal.schedule_full_disposal_declining(100_000_000, 5, 2026, 1, 2028, 7, 12))
    assert got == GOLDEN_DECLINING_FULL
    assert got[:2] == GOLDEN_YEARLY[:2]                  # 사건 전 = 정률 단순(외부 앵커)
    assert got[-1][1] == 7                               # 양도월 포함(더존식): 7개월 절단
    assert got[-1][3] + got[-1][4] == 100_000_000        # 절단 항등: 누계+장부 = 원가
    assert got[-1][4] != 1_000                           # 전체양도엔 비망가 없음


def test_core_declining_full_disposal_matches_handcalc():
    got = _core_yearly_declining(disposal_date="2028-07-01", disposal_amount=0)
    assert got == GOLDEN_DECLINING_FULL


# 3월결산: 양도 2028-07은 FY2029(2028.04~2029.03) 4번째 달 → 4개월 절단.
GOLDEN_DECLINING_FULL_FYE3 = [
    (2026,  3, 11_275_000, 11_275_000, 88_725_000),   # = GOLDEN_YEARLY_FYE3[0]
    (2027, 12, 40_014_975, 51_289_975, 48_710_025),   # = GOLDEN_YEARLY_FYE3[1]
    (2028, 12, 21_968_221, 73_258_196, 26_741_804),   # = GOLDEN_YEARLY_FYE3[2]
    (2029,  4,  4_020_184, 77_278_380, 22_721_620),   # 양도연도: 양도월(4번째달)까지 절단
]


def test_vcore_declining_full_disposal_fye3_matches_handcalc():
    got = _vy_decl(disposal.schedule_full_disposal_declining(100_000_000, 5, 2026, 1, 2028, 7, 3))
    assert got == GOLDEN_DECLINING_FULL_FYE3
    assert got[:3] == GOLDEN_YEARLY_FYE3[:3]             # 사건 전 = 정률 단순 3월(외부 앵커)
    assert got[-1][1] == 4                               # 4개월 절단
    assert got[-1][3] + got[-1][4] == 100_000_000        # 절단 항등
    assert got[-1][4] != 1_000                           # 비망가 없음


def test_core_declining_full_disposal_fye3_matches_handcalc():
    got = _core_yearly_declining(fye=3, disposal_date="2028-07-01", disposal_amount=0)
    assert got == GOLDEN_DECLINING_FULL_FYE3


# ── 정률 단순 · 임의 결산월 6월·9월 (P-d: 3월 외 임의월 골든 부재 해소) ──────
#   정률은 기초장부가 의존이라 첫해 부분월 상각이 이후 모든 연도에 전파된다 —
#   프로젝션 다점 앵커의 가치가 정액보다 크다. 손계산(5년율 0.451):
#   각 연도 = int(기초장부가 × 0.451 × 개월 // 12), 종료해 = 직전 장부가 − 1,000.
#   6월: FY2026 = int(1억×0.451×6//12) = 22,550,000 → FY2027 = int(77,450,000×0.451) = 34,929,950 …
#   9월: FY2026 = int(1억×0.451×9//12) = 33,825,000 → FY2027 = int(66,175,000×0.451) = 29,844,925 …
GOLDEN_DECLINING_SIMPLE_FYE6 = [
    (2026,  6, 22_550_000, 22_550_000, 77_450_000),
    (2027, 12, 34_929_950, 57_479_950, 42_520_050),
    (2028, 12, 19_176_542, 76_656_492, 23_343_508),
    (2029, 12, 10_527_922, 87_184_414, 12_815_586),
    (2030, 12,  5_779_829, 92_964_243,  7_035_757),
    (2031,  6,  7_034_757, 99_999_000,      1_000),   # 종료해(잔재 정리, 비망가)
]
GOLDEN_DECLINING_SIMPLE_FYE9 = [
    (2026,  9, 33_825_000, 33_825_000, 66_175_000),
    (2027, 12, 29_844_925, 63_669_925, 36_330_075),
    (2028, 12, 16_384_863, 80_054_788, 19_945_212),
    (2029, 12,  8_995_290, 89_050_078, 10_949_922),
    (2030, 12,  4_938_414, 93_988_492,  6_011_508),
    (2031,  3,  6_010_508, 99_999_000,      1_000),   # 종료해(잔재 정리, 비망가)
]


def test_vcore_declining_simple_fye6_matches_handcalc():
    got = _vy_decl(declining_balance.schedule(100_000_000, 5, 2026, 1, 6))
    assert got == GOLDEN_DECLINING_SIMPLE_FYE6
    assert got[0][2] == int(100_000_000 * 0.451 * 6 // 12)   # 첫해 부분월(6개월)
    assert got[1][2] == int(77_450_000 * 0.451)              # 온전한 해 = 기초장부가 기준
    assert got[-1][3] == 99_999_000 and got[-1][4] == 1_000


def test_core_declining_simple_fye6_matches_handcalc():
    assert _core_yearly_declining(fye=6) == GOLDEN_DECLINING_SIMPLE_FYE6


def test_vcore_declining_simple_fye9_matches_handcalc():
    got = _vy_decl(declining_balance.schedule(100_000_000, 5, 2026, 1, 9))
    assert got == GOLDEN_DECLINING_SIMPLE_FYE9
    assert got[0][2] == int(100_000_000 * 0.451 * 9 // 12)   # 첫해 부분월(9개월)
    assert got[1][2] == int(66_175_000 * 0.451)              # 온전한 해 = 기초장부가 기준
    assert got[-1][3] == 99_999_000 and got[-1][4] == 1_000


def test_core_declining_simple_fye9_matches_handcalc():
    assert _core_yearly_declining(fye=9) == GOLDEN_DECLINING_SIMPLE_FYE9
