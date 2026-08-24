"""매트릭스 프로젝션 통찰 검증 (연구용 스크립트, pytest 회귀 아님)

작성: 2026-05-22 (v2.2 머지 후속 검증)
관련 메모리: feedback_fiscal_period_matrix_projection.md

가설
----
임의 `fiscal_year_end_month=M` 호출은 다음 두 단계와 등가:
  1. 자산의 모든 calendar 일자를 `shift = -((M-12) mod 12)` 개월 시프트
  2. v2.2 엔진을 `fiscal_year_end_month=12`로 호출

(두 결과의 monthly_dep / accumulated / book_value 는 1대1 동일, year/month는 shift 차이)

회계 도메인 전제 (가설의 등가성 보장 근거)
- 월할 상각 (한국 법인세법 [별표 4])
- 결산일=월말 상수 (한국 회계 도메인 상수)
- 자산 변동 사건은 직전월末 장부가액을 고정값으로 받아 처리 (v2.1 매각 대원칙의 일반화)

검증 결과 (2026-05-22)
- 8개 시나리오 × 5개 결산월(1·3·6·9·12월) = **40/40 PASS**
- 자본적지출 Vector 비율, 부분양도 분배, 결산월 잔재 보정 발화 모두 1원 단위 일치

함의
----
v2.2의 `yearly_info` fiscal year화 + 14곳 month==12 일반화 + DepreciationResult.fiscal_year_end_month
필드 = calendar shift 어댑터와 본질적으로 등가. v2.2 코드가 매트릭스 프로젝션을 7곳에서
"내장 분산 구현"한 셈. 단일 어댑터 ~50~100 lines로 환원 가능했던 over-engineering임을
40개 시나리오로 코드 실증.

향후 회계기간/결산월 일반화 문제를 만나면 먼저 "calendar shift만으로 등가 변환 가능한가?"
를 묻는다 (메모리 feedback-fiscal-period-matrix-projection 의 How to apply).

실행
----
$ python3 dep_cal/tests/research/verify_matrix_projection.py
"""
import sys
import os

_RESEARCH_DIR = os.path.dirname(os.path.abspath(__file__))
_TESTS_DIR = os.path.dirname(_RESEARCH_DIR)
_DEP_CAL_DIR = os.path.dirname(_TESTS_DIR)
if _DEP_CAL_DIR not in sys.path:
    sys.path.insert(0, _DEP_CAL_DIR)

from core.dep_tang_engine import (
    _calculate_korean_straight_line_enhanced as sl,
    _calculate_korean_declining_balance_enhanced as dec,
    _calculate_with_increase as sl_inc,
    _calculate_with_increase_declining as dec_inc,
    _calculate_with_partial_disposal as sl_p,
    _calculate_with_partial_disposal_declining as dec_p,
)
from core.dep_intang_engine import (
    _calculate_intangible_asset_enhanced as intang,
    _calculate_intangible_with_partial_disposal as intang_p,
)
from core.dep_common import add_months_safe
from calendar import monthrange


def shift_months_str(date_str, months):
    """date_str을 months 만큼 시프트 (월말 자동 처리)."""
    if date_str is None:
        return None
    y, m, d = map(int, date_str.split('-'))
    new_y, new_m = add_months_safe(y, m, months)
    max_d = monthrange(new_y, new_m)[1]
    return f"{new_y:04d}-{new_m:02d}-{min(d, max_d):02d}"


def calc_shift(M):
    """fiscal_year_end_month=M 호출을 12월 결산으로 환원하는 calendar shift."""
    return -((M - 12) % 12) if M != 12 else 0


def compare_schedules(schedule_A, schedule_B, shift, label):
    """schedule_A[i] (원본 end_month=M) 와 schedule_B[i] (shift 적용 후 end_month=12) 비교.

    year/month는 shift만큼 차이나야 하며, monthly_dep/accumulated/book_value는 동일해야 함.
    """
    if len(schedule_A) != len(schedule_B):
        return (False, f"{label}: 길이 불일치 A={len(schedule_A)} B={len(schedule_B)}")

    for i, (a, b) in enumerate(zip(schedule_A, schedule_B)):
        a_shifted_y, a_shifted_m = add_months_safe(a.year, a.month, shift)
        if (a_shifted_y, a_shifted_m) != (b.year, b.month):
            return (False, f"{label}[{i}]: year/month shift 실패 A=({a.year},{a.month}) "
                           f"shifted=({a_shifted_y},{a_shifted_m}) B=({b.year},{b.month})")
        if a.monthly_depreciation != b.monthly_depreciation:
            return (False, f"{label}[{i}] {a.year}-{a.month:02d}: "
                           f"dep A={a.monthly_depreciation:,} B={b.monthly_depreciation:,}")
        if a.accumulated_depreciation != b.accumulated_depreciation:
            return (False, f"{label}[{i}] {a.year}-{a.month:02d}: "
                           f"acc A={a.accumulated_depreciation:,} B={b.accumulated_depreciation:,}")
        if a.book_value != b.book_value:
            return (False, f"{label}[{i}] {a.year}-{a.month:02d}: "
                           f"bv A={a.book_value:,} B={b.book_value:,}")
    return (True, f"{label}: {len(schedule_A)}개월 완전 일치")


def run_scenario(scenario_name, end_month, run_fn):
    """A: 원본 (end_month=M). B: shift 적용 후 end_month=12. 비교 결과 반환."""
    shift = calc_shift(end_month)
    sched_A = run_fn(end_month, shift=0)
    sched_B = run_fn(12, shift=shift)
    return compare_schedules(sched_A, sched_B, shift, f"{scenario_name} M={end_month} shift={shift}")


# ============================================================
# 시나리오 정의 (8개)
# ============================================================
scenarios = []

def scen_sl_normal(end_month, shift):
    return sl(cost=10_000_000, life_years=5,
              start_date=shift_months_str('2025-11-15', shift),
              fiscal_year_end_month=end_month)
scenarios.append(("정액법 정상", scen_sl_normal))

def scen_dec_normal(end_month, shift):
    return dec(cost=10_000_000, life_years=5,
               start_date=shift_months_str('2025-11-15', shift),
               fiscal_year_end_month=end_month)
scenarios.append(("정률법 정상", scen_dec_normal))

def scen_sl_inc(end_month, shift):
    return sl_inc(cost=10_000_000, life_years=5,
                  start_date=shift_months_str('2025-11-15', shift),
                  increase_amount=5_000_000,
                  increase_date=shift_months_str('2027-06-10', shift),
                  fiscal_year_end_month=end_month)
scenarios.append(("정액법 자본적지출", scen_sl_inc))

def scen_dec_inc(end_month, shift):
    return dec_inc(cost=10_000_000, life_years=5,
                   start_date=shift_months_str('2025-11-15', shift),
                   increase_amount=5_000_000,
                   increase_date=shift_months_str('2027-06-10', shift),
                   fiscal_year_end_month=end_month)
scenarios.append(("정률법 자본적지출", scen_dec_inc))

def scen_sl_p(end_month, shift):
    return sl_p(cost=10_000_000, life_years=5,
                start_date=shift_months_str('2025-11-15', shift),
                disposal_amount=3_000_000,
                disposal_date=shift_months_str('2028-04-20', shift),
                fiscal_year_end_month=end_month)
scenarios.append(("정액법 부분양도", scen_sl_p))

def scen_dec_p(end_month, shift):
    return dec_p(cost=10_000_000, life_years=5,
                 start_date=shift_months_str('2025-11-15', shift),
                 disposal_amount=3_000_000,
                 disposal_date=shift_months_str('2028-04-20', shift),
                 fiscal_year_end_month=end_month)
scenarios.append(("정률법 부분양도", scen_dec_p))

def scen_intang(end_month, shift):
    return intang(cost=12_000_000, life_years=10,
                  start_date=shift_months_str('2025-11-15', shift),
                  fiscal_year_end_month=end_month)
scenarios.append(("무형자산 정상", scen_intang))

def scen_intang_p(end_month, shift):
    return intang_p(cost=12_000_000, life_years=10,
                    start_date=shift_months_str('2025-11-15', shift),
                    disposal_amount=4_000_000,
                    disposal_date=shift_months_str('2029-07-10', shift),
                    fiscal_year_end_month=end_month)
scenarios.append(("무형자산 부분양도", scen_intang_p))


# ============================================================
# 실행
# ============================================================
def main():
    end_months = [1, 3, 6, 9, 12]
    total = 0
    passed = 0
    failures = []

    for scenario_name, run_fn in scenarios:
        for M in end_months:
            total += 1
            ok, msg = run_scenario(scenario_name, M, run_fn)
            if ok:
                passed += 1
                print(f"✓ {msg}")
            else:
                print(f"✗ {msg}")
                failures.append(msg)

    print(f"\n{'='*60}")
    print(f"매트릭스 프로젝션 검증: {passed}/{total} PASS")
    print(f"{'='*60}")

    if failures:
        print(f"\n실패 사례 ({len(failures)}):")
        for f in failures[:10]:
            print(f"  {f}")
        sys.exit(1)
    else:
        print("\n매트릭스 프로젝션 통찰 완전 입증 — 모든 시나리오 × 결산월 조합에서")
        print("calendar shift 변환과 fiscal_year_end_month 직접 호출이 1대1 동등.")


if __name__ == "__main__":
    main()
