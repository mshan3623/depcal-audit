"""
dep_vector — 분리자산 슬림 코어 (정액·정률)
=============================================

분리자산 = prior_accumulated(전기말 누계)만 알고 당기(target_year)만 계산하는 경로.
기중 인수·시스템 이전처럼 취득 이력 없이 전기말 누계만 주어질 때 쓴다.

나침반: 전기말 누계가 외부 확정값이므로 전체 스케줄을 재생성하지 않고, 그 누계를 기초로
당기 1개 회계연도만 계산한다(정률은 기초장부가=cost−prior 기준). 종료해(내용연수 종료
회계연도)는 잔액 전액(비망가 제외)을 상각한다.

제약: 12월 결산만 지원(core 분리자산과 동등 — 비-12월은 ValueError).
정확성: core(_calculate_korean_*_enhanced의 분리자산 분기)와 회계연도 1원 일치.
"""

from typing import List

from vcore.straight_line import annual_depreciation
from vcore.rate_table import declining_rate
from vcore.projection import FiscalYearRow, MEMORANDUM, validate_asset_inputs


def schedule_separate_asset(cost: int, life_years: int, acq_year: int, acq_month: int,
                            prior_accumulated: int, target_year: int,
                            fiscal_end_month: int = 12,
                            declining: bool = False) -> List[FiscalYearRow]:
    """분리자산 당기 회계연도 감가상각. prior_accumulated 기초 → target_year 1개 연도 반환."""
    if fiscal_end_month != 12:
        raise ValueError(
            f"분리자산 경로는 12월 결산만 지원 (fiscal_end_month={fiscal_end_month}).")
    validate_asset_inputs(cost, acq_month, fiscal_end_month)
    if prior_accumulated < 0:
        raise ValueError(f"전기말 누계는 음수일 수 없습니다 (prior_accumulated={prior_accumulated})")
    if target_year < acq_year:
        raise ValueError(f"당기연도({target_year})는 취득연도({acq_year}) 이전일 수 없습니다")

    # 내용연수 종료 회계연도(취득 후 life년) 산정
    dep_complete_year = acq_year + life_years
    dep_complete_month = acq_month - 1
    if dep_complete_month == 0:
        dep_complete_year -= 1
        dep_complete_month = 12

    if target_year > dep_complete_year:   # 내용연수 종료 후: 추가 상각 없음 (remaining≤0의 [] 관행과 동일)
        return []

    is_terminal = (target_year == dep_complete_year)
    months = 12
    if dep_complete_month < 12 and is_terminal:
        months = dep_complete_month                      # 종료해 부분월(취득월에 따라)

    if declining:
        rate = declining_rate(life_years)
        book = cost - prior_accumulated                  # 정률 기초장부가
        remaining = book - MEMORANDUM
        if remaining <= 0:
            return []
        yearly = int(book * rate * months // 12)
        dep = remaining if is_terminal else min(yearly, remaining)
    else:
        annual = annual_depreciation(cost, life_years)  # 별표4 정액 연상각(cost 기준)
        remaining = cost - prior_accumulated - MEMORANDUM
        if remaining <= 0:
            return []
        yearly = (annual * months) // 12
        dep = min(yearly, remaining)                     # 종료해는 remaining<yearly라 잔액 전액

    acc = prior_accumulated + dep
    return [FiscalYearRow(target_year, months, dep, acc, cost - acc)]
