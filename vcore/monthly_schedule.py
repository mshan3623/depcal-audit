"""
dep_vector — 달력 매핑 월별 스케줄 (실행 경로용 공개 API)
==========================================================

내부 표준형 월벡터(인덱스 = 취득 후 경과월)에 실제 달력(연·월)을 부착한다.
연도별 표(schedule_*)와 같은 벡터에서 나오므로 월별↔연도별 정합이 구조적으로
보장된다 — 상각명세서(엑셀)의 월별 상세표가 이 API를 소비한다.
"""

from dataclasses import dataclass
from typing import List

from vcore import capex, disposal, monthly
from vcore.monthly import Month
from vcore.projection import standard_acq_month, validate_asset_inputs


@dataclass
class CalendarMonth:
    year: int          # 실제 연도
    month: int         # 실제 월 (1~12)
    amount: int        # 월 감가상각비
    acc: int           # 월말 감가상각누계액
    book: int          # 월말 장부가액


def _to_calendar(months: List[Month], acq_year: int, acq_month: int) -> List[CalendarMonth]:
    base = acq_year * 12 + (acq_month - 1)
    return [CalendarMonth((base + i) // 12, (base + i) % 12 + 1, m.amount, m.acc, m.book)
            for i, m in enumerate(months)]


def _monthly_fn(declining: bool):
    return monthly.db_monthly if declining else monthly.sl_monthly


def monthly_schedule(cost: int, life_years: int, acq_year: int, acq_month: int,
                     fiscal_end_month: int = 12, declining: bool = False) -> List[CalendarMonth]:
    """단순(이벤트 없음) 월별 상각 스케줄."""
    validate_asset_inputs(cost, acq_month, fiscal_end_month)
    m_std = standard_acq_month(fiscal_end_month, acq_month)
    months = _monthly_fn(declining)(cost, life_years, m_std)
    months = monthly.settle_terminal_evenly(months)   # 자연완료: 종료해 균등 재배분
    return _to_calendar(months, acq_year, acq_month)


def monthly_with_increase(cost: int, life_years: int, acq_year: int, acq_month: int,
                          inc_amount: int, inc_year: int, inc_month: int,
                          fiscal_end_month: int = 12, declining: bool = False) -> List[CalendarMonth]:
    """자본적지출 포함 월별 상각 스케줄."""
    months = capex.months_with_increase(_monthly_fn(declining), cost, life_years,
                                         acq_year, acq_month, inc_amount, inc_year,
                                         inc_month, fiscal_end_month)
    return _to_calendar(months, acq_year, acq_month)


def monthly_full_disposal(cost: int, life_years: int, acq_year: int, acq_month: int,
                          disp_year: int, disp_month: int,
                          fiscal_end_month: int = 12, declining: bool = False) -> List[CalendarMonth]:
    """전체양도 월별 상각 스케줄. disp_month = 양도월(그 달까지 상각, 더존식)."""
    months = disposal.months_full_disposal(_monthly_fn(declining), cost, life_years,
                                            acq_year, acq_month, disp_year, disp_month,
                                            fiscal_end_month)
    return _to_calendar(months, acq_year, acq_month)


def monthly_partial_disposal(cost: int, life_years: int, acq_year: int, acq_month: int,
                             disposal_amount: int, disp_year: int, disp_month: int,
                             fiscal_end_month: int = 12, declining: bool = False) -> List[CalendarMonth]:
    """부분양도 월별 상각 스케줄 (잔류분 관점). disp_month = 양도월(포함, 더존식)."""
    months = disposal.months_partial_disposal(_monthly_fn(declining), cost, life_years,
                                               acq_year, acq_month, disposal_amount,
                                               disp_year, disp_month, fiscal_end_month)
    return _to_calendar(months, acq_year, acq_month)


def monthly_events(cost: int, life_years: int, acq_year: int, acq_month: int,
                   fiscal_end_month: int = 12, declining: bool = False,
                   inc: tuple = None, disp: tuple = None) -> List[CalendarMonth]:
    """이벤트 일반 디스패치 — 실행 경로(상각명세서)의 단일 진입점.

    inc  = (증가액, 연, 월) 또는 None
    disp = (양도액 or None=전부, 연, 월) 또는 None. 양도월 포함(더존식).
    capex+양도 동시 조합은 변환 합성: 증가 적용 후 양도 적용(절단/스케일).
    부분양도 잔존비율 분모는 이벤트 시점 통합 취득원가(원가+증가액).
    이벤트 시점 가드는 단일 관문(capex.apply_increase, disposal.months_to_disposal,
    disposal.apply_partial_disposal)에서 발화한다.
    """
    validate_asset_inputs(cost, acq_month, fiscal_end_month)
    m_std = standard_acq_month(fiscal_end_month, acq_month)
    months = _monthly_fn(declining)(cost, life_years, m_std)
    truncated = False
    basis = cost
    if inc is not None:
        inc_amount, inc_year, inc_month = inc
        k = (inc_year * 12 + inc_month) - (acq_year * 12 + acq_month)
        months = capex.apply_increase(months, cost, k, inc_amount)
        basis = cost + inc_amount
    if disp is not None:
        disp_amount, disp_year, disp_month = disp
        d = disposal.months_to_disposal(acq_year, acq_month, disp_year, disp_month)
        if disp_amount is None or disp_amount >= basis:   # 전부양도/폐기
            months = months[:d + 1]
            truncated = True
        else:                                             # 부분양도
            ev = min(d + 1, len(months))
            months = disposal.apply_partial_disposal(months, basis, ev, disp_amount)
    if not truncated:                                     # 자연완료: 종료해 균등 재배분
        months = monthly.settle_terminal_evenly(months)
    return _to_calendar(months, acq_year, acq_month)
