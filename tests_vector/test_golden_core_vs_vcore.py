"""골든 가드: 실행 경로(vcore monthly_events) 산출 == core 레퍼런스 월별 산출.

core는 동결된 oracle. 알려진 의도적 차이 2건만 예외로 다룬다:
  1. 양도월 규칙 — vcore는 더존식(양도월 포함). core(disposal_date 직전월 중단)와
     비교할 때 vcore 양도월 = core 월 - 1 매핑.
  2. 무형 종료연도 월 분배 — vcore는 유형 정액과 통일(균등 분배). 연총액은 동일하므로
     무형은 연 단위 합계로 비교.
"""
from collections import defaultdict

import pytest

from core.depreciation_engine import calculate_depreciation_enhanced
from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod
from vcore.monthly_schedule import monthly_events

COST, LIFE = 10_000_000, 5
_INFO = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")


def _core_monthly(menum, start, fye, disposal=None, disposal_amount=0, increase=None, inc_amount=0):
    fin = AssetFinancials(cost=COST, life_in_years=LIFE, start_date=start, method=menum,
                          disposal_date=disposal, disposal_amount=disposal_amount,
                          increase_date=increase, increase_amount=inc_amount)
    r = calculate_depreciation_enhanced(fin, _INFO, fiscal_year_end_month=fye)
    return [(m.year, m.month, m.numeric_depreciation, m.accumulated_depreciation, m.book_value)
            for m in r.schedule]


def _vcore_monthly(declining, acq, fye, inc=None, disp=None):
    cal = monthly_events(COST, LIFE, acq[0], acq[1], fye, declining, inc=inc, disp=disp)
    return [(m.year, m.month, m.amount, m.acc, m.book) for m in cal]


@pytest.mark.parametrize("declining", [False, True])
@pytest.mark.parametrize("fye", [12, 3])
@pytest.mark.parametrize("acq_month", [1, 4, 9])
def test_golden_simple(declining, fye, acq_month):
    menum = DepreciationMethod.DECLINING_BALANCE if declining else DepreciationMethod.STRAIGHT_LINE
    core = _core_monthly(menum, f"2026-{acq_month:02d}-15", fye)
    got = _vcore_monthly(declining, (2026, acq_month), fye)
    assert got == core


@pytest.mark.parametrize("declining", [False, True])
def test_golden_capex(declining):
    menum = DepreciationMethod.DECLINING_BALANCE if declining else DepreciationMethod.STRAIGHT_LINE
    core = _core_monthly(menum, "2026-04-15", 12, increase="2027-06-10", inc_amount=3_000_000)
    got = _vcore_monthly(declining, (2026, 4), 12, inc=(3_000_000, 2027, 6))
    assert got == core


@pytest.mark.parametrize("declining", [False, True])
def test_golden_full_disposal(declining):
    """core·vcore 모두 양도월 포함(더존식) — 동일 양도월 2028-07로 일치."""
    menum = DepreciationMethod.DECLINING_BALANCE if declining else DepreciationMethod.STRAIGHT_LINE
    core = _core_monthly(menum, "2026-04-15", 12, disposal="2028-07-01")
    got = _vcore_monthly(declining, (2026, 4), 12, disp=(None, 2028, 7))
    assert got == core


@pytest.mark.parametrize("declining", [False, True])
def test_golden_partial_disposal(declining):
    menum = DepreciationMethod.DECLINING_BALANCE if declining else DepreciationMethod.STRAIGHT_LINE
    core = _core_monthly(menum, "2026-04-15", 12, disposal="2028-07-01", disposal_amount=3_000_000)
    got = _vcore_monthly(declining, (2026, 4), 12, disp=(3_000_000, 2028, 7))
    assert got == core


@pytest.mark.parametrize("declining", [False, True])
def test_golden_partial_disposal_after_natural_end(declining):
    """자연종료(완전상각) 후 부분양도: core yearly_summary == vcore 연도별 (처분 조정행 포함).

    양도분 취득가액 안분 제거 + 잔존가액(비망가) 안분(30% 양도 → 잔류분 700). 월별 상각이
    없는 처분 이벤트라 연도별 표로 비교.
    """
    from vcore import disposal
    vfn = (disposal.schedule_partial_disposal_declining if declining
           else disposal.schedule_partial_disposal)
    # life=4 → 자연종료 2030-03, 양도 2031-06: 종료와 양도가 다른 회계연도(처분행 분리)
    vc = [(r.fiscal_year, r.depreciation, r.accumulated, r.book_value)
          for r in vfn(COST, 4, 2026, 4, 3_000_000, 2031, 6, 12)]
    menum = DepreciationMethod.DECLINING_BALANCE if declining else DepreciationMethod.STRAIGHT_LINE
    fin = AssetFinancials(cost=COST, life_in_years=4, start_date="2026-04-15", method=menum,
                          disposal_date="2031-06-01", disposal_amount=3_000_000)
    r = calculate_depreciation_enhanced(fin, _INFO, fiscal_year_end_month=12)
    cc = [(s.year, s.yearly_depreciation, s.accumulated_depreciation, s.ending_book_value)
          for s in r.yearly_summary]
    assert vc == cc
    assert cc[-1] == (2031, 0, 6_999_300, 700)          # 처분행: 잔류분 비망가 안분


def test_golden_capex_then_partial_disposal_straight():
    """capex+부분양도 동시 조합(정액) — core에서 한 번도 인증된 적 없는 경로.

    vcore는 변환 합성(증가→양도 스케일)로 처리. 연말보정 반올림에서 월 ±1원
    차이가 날 수 있으나 최종 누계·장부가는 완전 수렴해야 한다.
    """
    core = _core_monthly(DepreciationMethod.STRAIGHT_LINE, "2026-04-15", 12,
                         disposal="2028-07-01", disposal_amount=4_000_000,
                         increase="2027-06-10", inc_amount=3_000_000)
    got = _vcore_monthly(False, (2026, 4), 12, inc=(3_000_000, 2027, 6), disp=(4_000_000, 2028, 7))
    assert len(got) == len(core)
    assert got[-1][3:] == core[-1][3:]                       # 최종 누계·장부 완전 일치
    assert max(abs(a[2] - b[2]) for a, b in zip(core, got)) <= 1   # 월상각 ±1원


def test_capex_then_partial_disposal_declining_invariants():
    """capex+부분양도 동시 조합(정률) — core는 이 경로에서 음수 월상각을 산출하는
    버그가 있어 oracle 자격이 없음 (양도년 12월 -1,342,036원 확인, 2026-06-12).
    vcore 불변식으로 검증: 음수 월상각 없음 + 최종 누계·장부 수렴.
    """
    got = _vcore_monthly(True, (2026, 4), 12, inc=(3_000_000, 2027, 6), disp=(4_000_000, 2028, 7))
    assert all(r[2] >= 0 for r in got), "음수 월상각 발생"
    assert got[-1][3] == 10_000_000 + 3_000_000 - 4_000_000 - 1_000   # 최종 누계 = 잔존원가 - 비망
    assert got[-1][4] == 1_000                                        # 최종 장부 = 비망가


def test_golden_intangible_yearly():
    """무형: 월 분배는 의도적 차이(통일 분배) — 연 합계·최종값으로 비교."""
    core = _core_monthly(DepreciationMethod.INTANGIBLE, "2026-04-15", 12)
    got = _vcore_monthly(False, (2026, 4), 12)
    def yearly(rows):
        y = defaultdict(int)
        for r in rows:
            y[r[0]] += r[2]
        return dict(y)
    assert yearly(got) == yearly(core)
    assert got[-1][3:] == core[-1][3:]          # 최종 누계·장부가
    assert len(got) == len(core)


def test_golden_intangible_capex():
    """무형 capex: core가 vcore로 위임하므로 월별까지 1원 일치 (무형 = 별표4 정액 capex)."""
    core = _core_monthly(DepreciationMethod.INTANGIBLE, "2026-04-15", 12,
                         increase="2027-06-10", inc_amount=3_000_000)
    got = _vcore_monthly(False, (2026, 4), 12, inc=(3_000_000, 2027, 6))
    assert got == core


def test_golden_intangible_byeolpyo4_unified():
    """무형 전체(단순·부분양도)가 별표4 정액으로 통일 — 6년에서 1/n과 다름(별표4 0.166),
    core==vcore 연 단위 일치. core가 유형 정액 함수를 재사용하므로 별표4 적용."""
    from collections import defaultdict
    from vcore import intangible

    def core_yearly(**kw):
        fin = AssetFinancials(cost=12_000_000, life_in_years=6, start_date="2026-01-15",
                              method=DepreciationMethod.INTANGIBLE, **kw)
        r = calculate_depreciation_enhanced(fin, _INFO, fiscal_year_end_month=12)
        y = defaultdict(int)
        for m in r.schedule:
            y[m.year] += m.numeric_depreciation
        return sorted(y.items())

    # 단순: 1년차 별표4 1,992,000 (1/6=2,000,000 아님)
    cs = core_yearly()
    assert cs[0][1] == 1_992_000
    assert cs == [(r.fiscal_year, r.depreciation) for r in intangible.schedule(12_000_000, 6, 2026, 1, 12)]
    # 부분양도
    cp = core_yearly(disposal_date="2028-06-01", disposal_amount=3_000_000)
    assert cp == [(r.fiscal_year, r.depreciation)
                  for r in intangible.schedule_partial_disposal(12_000_000, 6, 2026, 1, 3_000_000, 2028, 6, 12)]
