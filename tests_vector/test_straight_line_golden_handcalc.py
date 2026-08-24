"""정액법 CAPEX·전체양도 손계산 절대 골든값 — core·vcore 독립 외부 기준.

배경(docs/TRUTH_MATRIX.md): 정액 CAPEX·전체양도 경로는 외부기준이 없어 그동안
core↔vcore 자기참조(둘이 함께 틀려도 통과)뿐이었다(❗❗빈칸). 이 파일은 법인세법
[별표 4] 정액율(내용연수 5년 = 0.200)로 사람이 직접 손계산한 값을 하드코딩해,
core·vcore 어느 쪽에도 의존하지 않는 제3의 기준을 고정한다.

주의: 이건 '컨벤션 손계산' 앵커다(더존식 양도월 포함·비망가 1,000·Vector 비율 capex).
정액 '실측(더존 위하고)'은 test_real_ledger_a.py가 별도 커버(단 xlsx 부재 시 skip).

공통 케이스: 취득원가 1억, 내용연수 5년, 2026-01 취득.
  연 상각(별표4 정액) = round(1억 × 0.200) = 20,000,000
  월 base = 20,000,000 // 12 = 1,666,666  (연말 잔재 8원은 결산월에 가산)
  종료해 = 직전 장부가 − 비망가(1,000) 강제 → 최종 장부가 = 1,000
"""
from vcore import straight_line, capex, disposal
from vcore.monthly_schedule import monthly_events
from core.depreciation_engine import calculate_depreciation_enhanced
from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod

SL_MONTHLY = 1_666_666   # 20,000,000 // 12 — 월 base(독립 손계산용)


def _vy(rows):
    return [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value) for r in rows]


def _events_yearly(cal):
    """monthly_events 월벡터 → (연, 개월수, 연상각, 누계, 장부가) 회계연도별 집계(12월결산)."""
    return _events_yearly_fye(cal, 12)


def _events_yearly_fye(cal, fye):
    """monthly_events 달력월 → 회계연도별 집계 (임의 결산월). fy = y if month≤fye else y+1."""
    rows, order = {}, []
    for c in cal:
        f = c.year if c.month <= fye else c.year + 1
        if f not in rows:
            rows[f] = [0, 0, 0, 0]
            order.append(f)
        rows[f][0] += 1
        rows[f][1] += c.amount
        rows[f][2] = c.acc
        rows[f][3] = c.book
    return [(y, *rows[y]) for y in order]


def _core_yearly(fye=12, **kw):
    fin = AssetFinancials(cost=100_000_000, life_in_years=5, start_date="2026-01-15",
                          method=DepreciationMethod.STRAIGHT_LINE, **kw)
    info = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")
    r = calculate_depreciation_enhanced(fin, info, fiscal_year_end_month=fye)
    return [(s.year, s.months_count, s.yearly_depreciation,
             s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]


# ── 정액 단순 · 12월 / 임의 결산월(3월) (TRUTH_MATRIX ❗임의월 해소) ──────────
# 케이스: 1억/5년(0.200)/2026-01 취득, 이벤트 없음. 정액 단순은 더존 실측이 커버하나
# xlsx-gated skip 위험(CI 커버리지 0). 손계산 골든으로 비-skip CI 앵커를 고정한다.
#   연 상각 = round(1억×0.200) = 20,000,000. 종료해 = 직전 장부가 − 비망가(1,000).
#   3월결산: FY2026=2026.01~03(3m)=20,000,000×3/12=5,000,000, FY2031=2030.04~12(9m) 종료해.
GOLDEN_SL_SIMPLE = [
    (2026, 12, 20_000_000, 20_000_000, 80_000_000),
    (2027, 12, 20_000_000, 40_000_000, 60_000_000),
    (2028, 12, 20_000_000, 60_000_000, 40_000_000),
    (2029, 12, 20_000_000, 80_000_000, 20_000_000),
    (2030, 12, 19_999_000, 99_999_000,      1_000),   # 종료해(비망가 강제)
]
GOLDEN_SL_SIMPLE_FYE3 = [
    (2026,  3,  5_000_000,  5_000_000, 95_000_000),   # 부분월 3개월 = 연 20M × 3/12
    (2027, 12, 20_000_000, 25_000_000, 75_000_000),
    (2028, 12, 20_000_000, 45_000_000, 55_000_000),
    (2029, 12, 20_000_000, 65_000_000, 35_000_000),
    (2030, 12, 20_000_000, 85_000_000, 15_000_000),
    (2031,  9, 14_999_000, 99_999_000,      1_000),   # 종료해(9개월, 비망가)
]


def test_vcore_sl_simple_matches_handcalc():
    got = _vy(straight_line.schedule(100_000_000, 5, 2026, 1, 12))
    assert got == GOLDEN_SL_SIMPLE
    assert all(r[2] == 20_000_000 for r in got[:4])      # 온전한 해 = 연 2천만(별표4 정액)
    assert got[-1][3] == 99_999_000 and got[-1][4] == 1_000


def test_core_sl_simple_matches_handcalc():
    assert _core_yearly() == GOLDEN_SL_SIMPLE


def test_vcore_sl_simple_fye3_matches_handcalc():
    got = _vy(straight_line.schedule(100_000_000, 5, 2026, 1, 3))
    assert got == GOLDEN_SL_SIMPLE_FYE3
    assert got[0][2] == 20_000_000 * 3 // 12             # 부분월 = 연 상각 × 3/12
    assert got[1][2] == 20_000_000                        # 온전한 해 = 연 2천만
    assert got[-1][3] == 99_999_000 and got[-1][4] == 1_000


def test_core_sl_simple_fye3_matches_handcalc():
    assert _core_yearly(fye=3) == GOLDEN_SL_SIMPLE_FYE3


# ── 정액 CAPEX(자본적지출) 단독 · 12월 결산 ────────────────────────────────
# 케이스: 1억/5년(0.200)/12월결산/2026-01 취득, 2027-06 자본적지출 +3,000만.
# 컨벤션(Vector 비율, capex.py:apply_increase): 증가 직전월(2027-05) 장부가 B=71,666,670,
# ratio=(B+3천만)/B=101,666,670/71,666,670. 증가월부터 base 월상각×ratio, 회계연도별
# 연말보정으로 연목표 int(base연합×ratio) 달성. 종료해 균등, 비망가 강제.
# 손계산 검증(FY2027): 미적용 2027.01~05 = 5×1,666,666 = 8,333,330;
#   적용 2027.06~12 base합 = 6×1,666,666 + 1,666,674(결산월) = 11,666,670;
#   int(11,666,670 × 101,666,670/71,666,670) = 16,550,392 → 합 24,883,722. (엔진 일치)
#   FY2028 = int(20,000,000 × ratio) = 28,372,092.
# 무결성: 누계+장부 = basis = 원가+증가 = 130,000,000, 최종 장부가 = 비망가 1,000.
GOLDEN_SL_CAPEX = [
    (2026, 12, 20_000_000,  20_000_000,  80_000_000),   # 증가 전 = 단순 정액 1년차
    (2027, 12, 24_883_722,  44_883_722,  85_116_278),   # 증가연도(부분월×ratio, 장부 점프 상승)
    (2028, 12, 28_372_092,  73_255_814,  56_744_186),
    (2029, 12, 28_372_092, 101_627_906,  28_372_094),
    (2030, 12, 28_371_094, 129_999_000,       1_000),   # 종료해
]


def test_vcore_sl_capex_matches_handcalc():
    got = _vy(capex.schedule_with_increase(100_000_000, 5, 2026, 1, 30_000_000, 2027, 6, 12))
    assert got == GOLDEN_SL_CAPEX
    assert got[0][2] == 20_000_000                       # 증가 전 해 = 단순 정액
    assert got[-1][3] + got[-1][4] == 130_000_000        # 누계+장부 = basis(원가+증가)
    assert got[-1][4] == 1_000                            # 최종 장부가 = 비망가
    assert sum(r[2] for r in got) == 129_999_000          # 총상각 = basis − 비망가


def test_core_sl_capex_matches_handcalc():
    got = _core_yearly(increase_date="2027-06-10", increase_amount=30_000_000)
    assert got == GOLDEN_SL_CAPEX


# ── 정액 CAPEX · 임의 결산월(3월) ─────────────────────────────────────────
# 3월결산: FY2026=2026.01~03(3m), FY2027~2030=12m, FY2031=2030.04~12(9m).
# 자본적지출 2027-06은 FY2028(2027.04~2028.03)에 발생 → 장부 점프가 FY2028에.
# 무결성: 누계+장부 = 130,000,000, 최종 비망가.
GOLDEN_SL_CAPEX_FYE3 = [
    (2026,  3,  5_000_000,   5_000_000,  95_000_000),   # 부분월 3개월(증가 전)
    (2027, 12, 20_000_000,  25_000_000,  75_000_000),
    (2028, 12, 26_976_744,  51_976_744,  78_023_256),   # 증가연도(장부 점프 상승)
    (2029, 12, 28_372_092,  80_348_836,  49_651_164),
    (2030, 12, 28_372_092, 108_720_928,  21_279_072),
    (2031,  9, 21_278_072, 129_999_000,       1_000),   # 종료해(9개월)
]


def test_vcore_sl_capex_fye3_matches_handcalc():
    got = _vy(capex.schedule_with_increase(100_000_000, 5, 2026, 1, 30_000_000, 2027, 6, 3))
    assert got == GOLDEN_SL_CAPEX_FYE3
    assert got[-1][3] + got[-1][4] == 130_000_000
    assert got[-1][4] == 1_000


def test_core_sl_capex_fye3_matches_handcalc():
    got = _core_yearly(fye=3, increase_date="2027-06-10", increase_amount=30_000_000)
    assert got == GOLDEN_SL_CAPEX_FYE3


# ── 정액 전체양도 · 12월 결산 ─────────────────────────────────────────────
# 케이스: 1억/5년/12월결산/2026-01 취득, 2028-07 전체양도(더존식 양도월 포함).
# 전체양도 = 월벡터를 양도월(2028-07)까지 절단. 종료해 없음(미완료 구간) → 비망가 없음.
# 손계산: 양도연도(2028) = 2028.01~07 = 7개월 × 1,666,666 = 11,666,662.
# 무결성(절단 항등): 모든 시점에서 누계 + 장부가 = 원가 100,000,000.
GOLDEN_SL_FULL = [
    (2026, 12, 20_000_000, 20_000_000, 80_000_000),
    (2027, 12, 20_000_000, 40_000_000, 60_000_000),
    (2028,  7, 11_666_662, 51_666_662, 48_333_338),   # 양도연도: 양도월(7월)까지 절단
]


def test_vcore_sl_full_disposal_matches_handcalc():
    got = _vy(disposal.schedule_full_disposal(100_000_000, 5, 2026, 1, 2028, 7, 12))
    assert got == GOLDEN_SL_FULL
    assert got[-1][1] == 7                                # 양도월 포함(더존식): 7개월
    assert got[-1][2] == 7 * SL_MONTHLY                   # 독립 손계산: 7 × 월base
    assert got[-1][3] + got[-1][4] == 100_000_000         # 절단 항등: 누계+장부 = 원가
    assert got[-1][4] != 1_000                            # 전체양도엔 비망가 없음


def test_core_sl_full_disposal_matches_handcalc():
    got = _core_yearly(disposal_date="2028-07-01", disposal_amount=0)
    assert got == GOLDEN_SL_FULL


# ── 정액 전체양도 · 임의 결산월(3월) ──────────────────────────────────────
# 3월결산에서 양도 2028-07은 FY2029(2028.04~2029.03) 중 4번째 달 → 4개월 절단.
# 손계산: FY2029 = 2028.04~07 = 4개월 × 1,666,666 = 6,666,664.
GOLDEN_SL_FULL_FYE3 = [
    (2026,  3,  5_000_000,  5_000_000, 95_000_000),
    (2027, 12, 20_000_000, 25_000_000, 75_000_000),
    (2028, 12, 20_000_000, 45_000_000, 55_000_000),
    (2029,  4,  6_666_664, 51_666_664, 48_333_336),   # 양도연도: 양도월(4번째달)까지 절단
]


def test_vcore_sl_full_disposal_fye3_matches_handcalc():
    got = _vy(disposal.schedule_full_disposal(100_000_000, 5, 2026, 1, 2028, 7, 3))
    assert got == GOLDEN_SL_FULL_FYE3
    assert got[-1][1] == 4                                # 4개월 절단
    assert got[-1][2] == 4 * SL_MONTHLY                   # 독립 손계산: 4 × 월base
    assert got[-1][3] + got[-1][4] == 100_000_000         # 절단 항등


def test_core_sl_full_disposal_fye3_matches_handcalc():
    got = _core_yearly(fye=3, disposal_date="2028-07-01", disposal_amount=0)
    assert got == GOLDEN_SL_FULL_FYE3


# ── 정액 부분양도 단독 · 12월 결산 (TRUTH_MATRIX ❗빈칸 해소) ─────────────────
# 케이스: 1억/5년(0.200)/12월결산/2026-01 취득, 2028-07 부분양도 4,000만(capex 없음).
#   부분양도 잔존비율 분모 = 취득원가 cost = 100,000,000. 잔존비율 = 1 − 40/100 = 0.6.
#   양도월(2028-07)까지 전체기준 상각 후 누계·장부 안분 차감(더존식 양도월 포함).
# 손계산 앵커(disposal 모듈 미사용 순수 산술 재현이 core·vcore와 1원 일치, 검증 완료):
#   - 사건 전 FY2026·FY2027 = 단순 정액(연 20,000,000)과 동일 = 외부 앵커.
#   - 양도월말 전체기준 누계 = 51,666,662(31개월). disposed 누계 = round(51,666,662×0.4)
#     = 20,666,665 제거 → FY2028 누계 점프 하강(FY2027말 40,000,000 → FY2028말 35,999,999).
# 무결성: 최종 누계+장부 = cost−양도액 = 60,000,000, 최종 장부가 = 비망가 1,000.
GOLDEN_SL_PARTIAL = [
    (2026, 12, 20_000_000, 20_000_000, 80_000_000),   # 사건 전 = 단순 정액 1년차
    (2027, 12, 20_000_000, 40_000_000, 60_000_000),   # 사건 전 = 단순 정액 2년차
    (2028, 12, 16_666_664, 35_999_999, 24_000_001),   # 부분양도 연도(누계 점프 하강)
    (2029, 12, 12_000_000, 47_999_999, 12_000_001),
    (2030, 12, 11_999_001, 59_999_000,      1_000),   # 종료해(비망가 강제)
]


def test_vcore_sl_partial_disposal_matches_handcalc():
    got = _vy(disposal.schedule_partial_disposal(100_000_000, 5, 2026, 1, 40_000_000, 2028, 7, 12))
    assert got == GOLDEN_SL_PARTIAL
    assert got[0][2] == 20_000_000 and got[1][2] == 20_000_000   # 사건 전 = 단순 정액 연 2천만(외부 앵커)
    assert got[-1][3] + got[-1][4] == 60_000_000          # 누계+장부 = cost−양도액
    assert got[-1][4] == 1_000                            # 최종 장부가 = 비망가


def test_core_sl_partial_disposal_matches_handcalc():
    got = _core_yearly(disposal_date="2028-07-01", disposal_amount=40_000_000)
    assert got == GOLDEN_SL_PARTIAL


# ── 정액 CAPEX + 부분양도 조합 (TRUTH_MATRIX ❗❗빈칸 해소) ────────────────────
# 케이스: 1억/5년(0.200)/12월결산/2026-01 취득, 2027-06 +3,000만, 2028-07 부분양도 4,000만.
# 합성(monthly_schedule.monthly_events): 증가 적용(basis=1.3억) 후 부분양도 안분.
#   부분양도 잔존비율 분모 = 통합 취득원가 basis = 130,000,000 (원가+증가, monthly_schedule:84).
#   잔존비율 = 1 − 40,000,000/130,000,000 = 90/130. 양도월(2028-07)에 누계·장부 안분 차감.
# 손계산 앵커(엔진 capex/disposal 모듈 미사용 순수 산술 재현이 core·vcore와 1원 일치, 검증 완료):
#   - 사건 전 FY2026·FY2027 = 단독 정액 CAPEX 골든(GOLDEN_SL_CAPEX)과 동일 = 외부 앵커.
#   - FY2028 양도연도: 양도월에 누계 점프 하강(disposed 누계 제거), 이후 잔존비율 상각.
# 무결성: 최종 누계+장부 = basis−양도액 = 90,000,000, 최종 장부가 = 비망가 1,000, 음수 월상각 없음.
GOLDEN_SL_CAPEX_PARTIAL = [
    (2026, 12, 20_000_000, 20_000_000, 80_000_000),   # 사건 전 = 단순 정액 1년차
    (2027, 12, 24_883_722, 44_883_722, 85_116_278),   # capex 연도(GOLDEN_SL_CAPEX와 동일)
    (2028, 12, 24_734_642, 50_715_563, 39_284_437),   # 부분양도 연도(누계 점프 하강)
    (2029, 12, 19_642_217, 70_357_780, 19_642_220),
    (2030, 12, 19_641_220, 89_999_000,      1_000),   # 종료해(비망가 강제)
]


def test_vcore_sl_capex_then_partial_matches_handcalc():
    cal = monthly_events(100_000_000, 5, 2026, 1, 12,
                         inc=(30_000_000, 2027, 6), disp=(40_000_000, 2028, 7))
    got = _events_yearly(cal)
    assert got == GOLDEN_SL_CAPEX_PARTIAL
    assert got[:2] == GOLDEN_SL_CAPEX[:2]                 # 사건 전 = 단독 CAPEX 골든(외부 앵커)
    assert all(c.amount >= 0 for c in cal)                # 음수 월상각 없음
    assert got[-1][3] + got[-1][4] == 90_000_000          # 누계+장부 = basis−양도액
    assert got[-1][4] == 1_000                            # 최종 장부가 = 비망가


def test_core_sl_capex_then_partial_matches_handcalc():
    got = _core_yearly(increase_date="2027-06-10", increase_amount=30_000_000,
                       disposal_date="2028-07-01", disposal_amount=40_000_000)
    assert got == GOLDEN_SL_CAPEX_PARTIAL


# ── 정액 CAPEX + 전체양도 조합 (TRUTH_MATRIX ❗❗빈칸 해소) ────────────────────
# 케이스: 1억/5년/12월결산/2026-01 취득, 2027-06 +3,000만, 2028-07 전체양도(더존식 양도월 포함).
# 합성: 증가 적용(basis=1.3억) 후 월벡터를 양도월(2028-07)까지 절단. 종료해 없음(미완료, settle 미적용).
# 손계산 앵커: 사건 전 FY2026·FY2027 = GOLDEN_SL_CAPEX와 동일. FY2028 = 양도월까지 7개월 절단.
# 무결성(절단 항등): 양도월까지 누계+장부 = basis(원가+증가) = 130,000,000, 비망가 없음.
GOLDEN_SL_CAPEX_FULL = [
    (2026, 12, 20_000_000, 20_000_000, 80_000_000),   # capex 전 = 단순 정액 1년차
    (2027, 12, 24_883_722, 44_883_722, 85_116_278),   # capex 연도(GOLDEN_SL_CAPEX와 동일)
    (2028,  7, 16_550_380, 61_434_102, 68_565_898),   # 양도연도: 양도월(7월)까지 절단
]


def test_vcore_sl_capex_then_full_disposal_matches_handcalc():
    cal = monthly_events(100_000_000, 5, 2026, 1, 12,
                         inc=(30_000_000, 2027, 6), disp=(None, 2028, 7))
    got = _events_yearly(cal)
    assert got == GOLDEN_SL_CAPEX_FULL
    assert got[:2] == GOLDEN_SL_CAPEX[:2]                 # 사건 전 = 단독 CAPEX 골든(외부 앵커)
    assert (cal[-1].year, cal[-1].month) == (2028, 7)     # 양도월 포함(더존식)
    assert got[-1][1] == 7                                # 양도연도 7개월 절단
    assert got[-1][3] + got[-1][4] == 130_000_000         # 절단 항등: 누계+장부 = basis
    assert got[-1][4] != 1_000                            # 전체양도엔 비망가 없음


def test_core_sl_capex_then_full_disposal_matches_handcalc():
    got = _core_yearly(increase_date="2027-06-10", increase_amount=30_000_000,
                       disposal_date="2028-07-01", disposal_amount=0)
    assert got == GOLDEN_SL_CAPEX_FULL


# ── 정액 부분양도 단독 · 임의 결산월(3월) (TRUTH_MATRIX △임의월 해소) ─────────
# 12월 케이스(GOLDEN_SL_PARTIAL)와 같은 사건(양도 2028-07, 4,000만)을 3월결산으로.
# 사건 전 FY2026~2028 = 정액 단순 3월(GOLDEN_SL_SIMPLE_FYE3[:3])과 동일 = 외부 앵커.
# 무결성: 최종 누계+장부 = cost−양도액 = 60,000,000, 최종 장부가 = 비망가 1,000.
GOLDEN_SL_PARTIAL_FYE3 = [
    (2026,  3,  5_000_000,  5_000_000, 95_000_000),   # 양도 전 = 정액 단순 3월
    (2027, 12, 20_000_000, 25_000_000, 75_000_000),
    (2028, 12, 20_000_000, 45_000_000, 55_000_000),
    (2029, 12, 14_666_665, 38_999_999, 21_000_001),   # 양도연도(누계 점프 하강)
    (2030, 12, 12_000_000, 50_999_999,  9_000_001),
    (2031,  9,  8_999_001, 59_999_000,      1_000),   # 종료해(9개월, 비망가)
]


def test_vcore_sl_partial_disposal_fye3_matches_handcalc():
    got = _vy(disposal.schedule_partial_disposal(100_000_000, 5, 2026, 1, 40_000_000, 2028, 7, 3))
    assert got == GOLDEN_SL_PARTIAL_FYE3
    assert got[:3] == GOLDEN_SL_SIMPLE_FYE3[:3]          # 양도 전 = 정액 단순 3월(외부 앵커)
    assert got[-1][3] + got[-1][4] == 60_000_000         # 누계+장부 = cost−양도액
    assert got[-1][4] == 1_000


def test_core_sl_partial_disposal_fye3_matches_handcalc():
    got = _core_yearly(fye=3, disposal_date="2028-07-01", disposal_amount=40_000_000)
    assert got == GOLDEN_SL_PARTIAL_FYE3


# ── 정액 CAPEX + 전체양도 · 임의 결산월(3월) (TRUTH_MATRIX 해소) ──────────────
# 12월 케이스(GOLDEN_SL_CAPEX_FULL)의 3월결산 변형. capex +3천만@2027-06, 전체양도@2028-07.
# 사건 전 FY2026·FY2027 = 정액 단순 3월, FY2028(capex 연도) = 정액 CAPEX 3월(GOLDEN_SL_CAPEX_FYE3[2]).
# 무결성(절단 항등): 양도월까지 누계+장부 = basis(원가+증가) = 130,000,000, 비망가 없음.
GOLDEN_SL_CAPEX_FULL_FYE3 = [
    (2026,  3,  5_000_000,  5_000_000, 95_000_000),
    (2027, 12, 20_000_000, 25_000_000, 75_000_000),
    (2028, 12, 26_976_744, 51_976_744, 78_023_256),   # capex 연도 = GOLDEN_SL_CAPEX_FYE3[2]
    (2029,  4,  9_457_360, 61_434_104, 68_565_896),   # 양도연도: 양도월(4번째달)까지 절단
]


def test_vcore_sl_capex_then_full_disposal_fye3_matches_handcalc():
    cal = monthly_events(100_000_000, 5, 2026, 1, 3,
                         inc=(30_000_000, 2027, 6), disp=(None, 2028, 7))
    got = _events_yearly_fye(cal, 3)
    assert got == GOLDEN_SL_CAPEX_FULL_FYE3
    assert got[2] == GOLDEN_SL_CAPEX_FYE3[2]             # capex 연도 = 정액 CAPEX 3월(외부 앵커)
    assert got[-1][1] == 4                               # FY2029 = 2028.04~07 4개월 절단
    assert got[-1][3] + got[-1][4] == 130_000_000        # 절단 항등: 누계+장부 = basis
    assert got[-1][4] != 1_000


def test_core_sl_capex_then_full_disposal_fye3_matches_handcalc():
    got = _core_yearly(fye=3, increase_date="2027-06-10", increase_amount=30_000_000,
                       disposal_date="2028-07-01", disposal_amount=0)
    assert got == GOLDEN_SL_CAPEX_FULL_FYE3


# ── 정액 CAPEX + 부분양도 · 임의 결산월(3월) (vcore 위임으로 해소) ─────────────
# 12월은 core==vcore 1원 일치였으나, 3월결산에서 core 자체 2단계 루프가 종료해 부근 1원
# 이탈했다(2026-07-02 발견). core는 진실이 아니므로 depreciation_engine에서 이 경로를
# vcore로 위임 처리(정률 capex+부분양도와 대칭) → core==vcore==손계산 1원 일치로 해소.
# vcore가 진실: db 미사용 순수 산술 재현(sl_monthly + capex/disposal 자체 재구현)이 vcore와 일치.
# 무결성: 최종 누계+장부 = basis−양도액 = 90,000,000, 최종 장부가 = 비망가 1,000.
GOLDEN_SL_CAPEX_PARTIAL_FYE3 = [               # vcore = core(위임) = 손계산 진실
    (2026,  3,  5_000_000,  5_000_000, 95_000_000),
    (2027, 12, 20_000_000, 25_000_000, 75_000_000),
    (2028, 12, 26_976_744, 51_976_744, 78_023_256),   # capex 연도
    (2029, 12, 22_552_174, 55_626_117, 34_373_883),   # 부분양도 연도(누계 점프 하강)
    (2030, 12, 19_642_217, 75_268_334, 14_731_666),
    (2031,  9, 14_730_666, 89_999_000,      1_000),   # 종료해(9개월, 비망가)
]


def test_vcore_sl_capex_then_partial_fye3_matches_handcalc():
    cal = monthly_events(100_000_000, 5, 2026, 1, 3,
                         inc=(30_000_000, 2027, 6), disp=(40_000_000, 2028, 7))
    got = _events_yearly_fye(cal, 3)
    assert got == GOLDEN_SL_CAPEX_PARTIAL_FYE3
    assert all(c.amount >= 0 for c in cal)               # 음수 월상각 없음
    assert got[-1][3] + got[-1][4] == 90_000_000         # 누계+장부 = basis−양도액
    assert got[-1][4] == 1_000


def test_core_sl_capex_then_partial_fye3_matches_handcalc():
    """core는 이 경로를 vcore로 위임 → 손계산 골든과 1원 일치(3월 이탈 해소)."""
    got = _core_yearly(fye=3, increase_date="2027-06-10", increase_amount=30_000_000,
                       disposal_date="2028-07-01", disposal_amount=40_000_000)
    assert got == GOLDEN_SL_CAPEX_PARTIAL_FYE3


# ── 정액 단순 · 임의 결산월 6월·9월 (P-d: 3월 외 임의월 골든 부재 해소) ──────
#   프로젝션의 외부 앵커가 3월 하나뿐이면 shift 불변성 검증이 단일점이다. 6월(δ=6)·
#   9월(δ=9)을 추가해 다점 앵커로 만든다. 산식은 3월과 동일 컨벤션:
#   첫해 부분월 = 연 20,000,000 × 개월/12, 종료해 = 직전 장부가 − 비망가(1,000).
GOLDEN_SL_SIMPLE_FYE6 = [
    (2026,  6, 10_000_000, 10_000_000, 90_000_000),   # 부분월 6개월 = 연 20M × 6/12
    (2027, 12, 20_000_000, 30_000_000, 70_000_000),
    (2028, 12, 20_000_000, 50_000_000, 50_000_000),
    (2029, 12, 20_000_000, 70_000_000, 30_000_000),
    (2030, 12, 20_000_000, 90_000_000, 10_000_000),
    (2031,  6,  9_999_000, 99_999_000,      1_000),   # 종료해(6개월, 비망가)
]
GOLDEN_SL_SIMPLE_FYE9 = [
    (2026,  9, 15_000_000, 15_000_000, 85_000_000),   # 부분월 9개월 = 연 20M × 9/12
    (2027, 12, 20_000_000, 35_000_000, 65_000_000),
    (2028, 12, 20_000_000, 55_000_000, 45_000_000),
    (2029, 12, 20_000_000, 75_000_000, 25_000_000),
    (2030, 12, 20_000_000, 95_000_000,  5_000_000),
    (2031,  3,  4_999_000, 99_999_000,      1_000),   # 종료해(3개월, 비망가)
]


def test_vcore_sl_simple_fye6_matches_handcalc():
    got = _vy(straight_line.schedule(100_000_000, 5, 2026, 1, 6))
    assert got == GOLDEN_SL_SIMPLE_FYE6
    assert got[0][2] == 20_000_000 * 6 // 12
    assert got[-1][3] == 99_999_000 and got[-1][4] == 1_000


def test_core_sl_simple_fye6_matches_handcalc():
    assert _core_yearly(fye=6) == GOLDEN_SL_SIMPLE_FYE6


def test_vcore_sl_simple_fye9_matches_handcalc():
    got = _vy(straight_line.schedule(100_000_000, 5, 2026, 1, 9))
    assert got == GOLDEN_SL_SIMPLE_FYE9
    assert got[0][2] == 20_000_000 * 9 // 12
    assert got[-1][3] == 99_999_000 and got[-1][4] == 1_000


def test_core_sl_simple_fye9_matches_handcalc():
    assert _core_yearly(fye=9) == GOLDEN_SL_SIMPLE_FYE9


# ── 정액 종료월(내용연수 마지막 달) 부분양도 (P-d: MED-4 조용한 무시 해소) ────
#   케이스: 1,000만/5년/2026-01 취득, 2030-12(취득 후 59개월 = 종료월) 400만 부분양도.
#   종료월 양도는 그 달까지 상각(자연완료와 동일: 총상각 9,999,000, 비망가 1,000) 후
#   분배만 남는다 → 자연종료 후 양도와 같은 처분 조정행 경로.
#   조정행 손계산: 양도 누계 = 4사5입(9,999,000 × 400만/1,000만) = 3,999,600,
#   양도 장부가 = 4,000,000 − 3,999,600 = 400. 잔존 누계 = 9,999,000 − 3,999,600
#   = 5,999,400, 잔존 비망가 = 1,000 − 400 = 600 (비율 안분: 40% 양도 → 400).
#   조정행 연도 = 양도월(2030-12)이 속한 FY2030 (더존식 양도월 포함 — core는
#   disposal_date=양도월+1 컨벤션이라 조정행을 FY2031에 붙여 라벨만 1년 차이,
#   상각액·분배 수치는 동일. 더존식 기준 정답은 2030이므로 vcore를 고정한다).
GOLDEN_SL_TERMINAL_MONTH_PARTIAL = [
    (2026, 12, 2_000_000, 2_000_000, 8_000_000),
    (2027, 12, 2_000_000, 4_000_000, 6_000_000),
    (2028, 12, 2_000_000, 6_000_000, 4_000_000),
    (2029, 12, 2_000_000, 8_000_000, 2_000_000),
    (2030, 12, 1_999_000, 9_999_000,     1_000),      # 종료해(자연완료와 동일)
    (2030,  0,         0, 5_999_400,       600),      # 처분 조정행(양도분 안분 제거)
]


def test_vcore_sl_terminal_month_partial_disposal_adjusts():
    """종료월 부분양도가 무흔적으로 사라지지 않고(과거 조용한 무시) 조정행이 붙는다."""
    got = _vy(disposal.schedule_partial_disposal(10_000_000, 5, 2026, 1, 4_000_000, 2030, 12))
    assert got == GOLDEN_SL_TERMINAL_MONTH_PARTIAL
    natural = _vy(straight_line.schedule(10_000_000, 5, 2026, 1, 12))
    assert got[:-1] == natural                        # 상각 스케줄은 자연완료와 동일
    assert got != natural                             # 그러나 양도 흔적(조정행)은 남아야 함
    assert got[-1][3] + got[-1][4] == 6_000_000       # 잔존 누계+비망가 = 원가−양도액
