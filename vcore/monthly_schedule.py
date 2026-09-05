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
from vcore.projection import first_fiscal_year, standard_acq_month, validate_asset_inputs


@dataclass
class CalendarMonth:
    year: int          # 실제 연도
    month: int         # 실제 월 (1~12)
    amount: int        # 월 감가상각비
    acc: int           # 월말 감가상각누계액
    book: int          # 월말 장부가액
    fiscal_year: int   # 이 달이 속한 회계연도 라벨 (결산월 반영, schedule_* 행과 동일)


def _to_calendar(months: List[Month], acq_year: int, acq_month: int,
                 fiscal_end_month: int = 12) -> List[CalendarMonth]:
    """달력(연·월)과 **회계연도 라벨**을 함께 부착한다.

    회계연도는 달력연도가 아니다(결산월 ≠ 12면 갈린다). 소비자가 `year`로 다시 묶으면
    연도별 표와 어긋나므로(감사 G3) 라벨을 벡터가 직접 싣는다 — 출처는 연도별 표와
    같은 `Month.fy_index`다.
    """
    base = acq_year * 12 + (acq_month - 1)
    fy0 = first_fiscal_year(acq_year, acq_month, fiscal_end_month)
    return [CalendarMonth((base + i) // 12, (base + i) % 12 + 1, m.amount, m.acc, m.book,
                          fy0 + m.fy_index)
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
    return _to_calendar(months, acq_year, acq_month, fiscal_end_month)


def monthly_with_increase(cost: int, life_years: int, acq_year: int, acq_month: int,
                          inc_amount: int, inc_year: int, inc_month: int,
                          fiscal_end_month: int = 12, declining: bool = False) -> List[CalendarMonth]:
    """자본적지출 포함 월별 상각 스케줄."""
    months = capex.months_with_increase(_monthly_fn(declining), cost, life_years,
                                         acq_year, acq_month, inc_amount, inc_year,
                                         inc_month, fiscal_end_month)
    return _to_calendar(months, acq_year, acq_month, fiscal_end_month)


def monthly_full_disposal(cost: int, life_years: int, acq_year: int, acq_month: int,
                          disp_year: int, disp_month: int,
                          fiscal_end_month: int = 12, declining: bool = False) -> List[CalendarMonth]:
    """전체양도 월별 상각 스케줄. disp_month = 양도월(그 달까지 상각, 더존식)."""
    months = disposal.months_full_disposal(_monthly_fn(declining), cost, life_years,
                                            acq_year, acq_month, disp_year, disp_month,
                                            fiscal_end_month)
    return _to_calendar(months, acq_year, acq_month, fiscal_end_month)


def monthly_partial_disposal(cost: int, life_years: int, acq_year: int, acq_month: int,
                             disposal_amount: int, disp_year: int, disp_month: int,
                             fiscal_end_month: int = 12, declining: bool = False) -> List[CalendarMonth]:
    """부분양도 월별 상각 스케줄 (잔류분 관점). disp_month = 양도월(포함, 더존식)."""
    months = disposal.months_partial_disposal(_monthly_fn(declining), cost, life_years,
                                               acq_year, acq_month, disposal_amount,
                                               disp_year, disp_month, fiscal_end_month)
    return _to_calendar(months, acq_year, acq_month, fiscal_end_month)


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
        months = capex.apply_increase(months, k, inc_amount)
        basis = cost + inc_amount
    if disp is not None:
        disp_amount, disp_year, disp_month = disp
        d = disposal.months_to_disposal(acq_year, acq_month, disp_year, disp_month)
        if disposal.is_full_disposal(basis, disp_amount):  # 전부양도/폐기
            # 자연종료 **이후**의 전부양도는 자를 것이 없다. 그때도 truncated를 세우면
            # 종료해 균등 재배분을 건너뛰어, 같은 자산의 월별 배분이 보유일 때와 양도일 때
            # 달라진다(감사 G9: 정률 종료해가 dump vs 균등). 실제로 잘렸을 때만 세운다.
            truncated = d + 1 < len(months)
            months = months[:d + 1]
        else:                                             # 부분양도
            if d + 1 >= len(months):
                # 상각이 끝난(또는 끝나는) 달의 부분양도. 월벡터에는 분배를 실을 칸이
                # 없어 `apply_ratio_from`이 조용히 사본을 돌려주고 양도가 **무흔적으로
                # 사라진다**(감사 G8 — 엑셀 월별 명세서에서 양도가 보이지 않았다).
                # 연도별 API(`disposal.schedule_partial_disposal`)는 같은 사건에 조정행을
                # 붙인다. 같은 사건이 API마다 다르게 보이지 않도록, 표현할 수 없으면
                # 조용히 넘기지 않고 그렇다고 말한다.
                raise ValueError(
                    f"자연종료 시점 이후의 부분양도는 월별 스케줄로 표현할 수 없습니다 "
                    f"(양도 {disp_year}-{disp_month:02d}, 상각 종료 {len(months)}개월째). "
                    f"연도별 API(schedule_partial_disposal)를 쓰면 조정행으로 표시됩니다")
            months = disposal.apply_partial_disposal(months, basis, d + 1, disp_amount)
    if not truncated:                                     # 자연완료: 종료해 균등 재배분
        months = monthly.settle_terminal_evenly(months)
    return _to_calendar(months, acq_year, acq_month, fiscal_end_month)
