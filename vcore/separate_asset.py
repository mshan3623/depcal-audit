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
from vcore.rate_table import declining_balance_amount
from vcore.projection import FiscalYearRow, MEMORANDUM, validate_asset_inputs


def schedule_separate_asset(cost: int, life_years: int, acq_year: int, acq_month: int,
                            prior_accumulated: int, target_year: int,
                            fiscal_end_month: int = 12,
                            declining: bool = False,
                            start_month: int = 1) -> List[FiscalYearRow]:
    """분리자산 당기 회계연도 감가상각. prior_accumulated 기초 → target_year 1개 연도 반환.

    start_month: 그 회계연도에 상각을 개시하는 월(연도 중 진입). 기본 1 = 연초부터.
    합병 승계는 `schedule_merger_succession`을 쓸 것 — 등기월 다음 달이라는 규칙을
    호출부가 매번 기억하지 않도록 그쪽에 묶어 두었다.
    """
    if fiscal_end_month != 12:
        raise ValueError(
            f"분리자산 경로는 12월 결산만 지원 (fiscal_end_month={fiscal_end_month}).")
    if not 1 <= start_month <= 12:
        raise ValueError(f"상각 개시월은 1~12여야 합니다 (start_month={start_month})")
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
    if start_month > 1:                                  # 연도 중 진입: 개시월 앞부분을 뺀다
        months -= start_month - 1
        if months <= 0:                                  # 진입 전에 이미 상각 종료
            return []

    if declining:
        book = cost - prior_accumulated                  # 정률 기초장부가
        yearly = declining_balance_amount(book, life_years, months)   # 정수 산술 단일 관문(범위 가드 포함)
        remaining = book - MEMORANDUM
        if remaining <= 0:
            return []
        dep = remaining if is_terminal else min(yearly, remaining)
    else:
        annual = annual_depreciation(cost, life_years)  # 별표4 정액 연상각(cost 기준)
        remaining = cost - prior_accumulated - MEMORANDUM
        if remaining <= 0:
            return []
        yearly = (annual * months) // 12
        # 종료해는 정률과 같이 잔액 전액을 강제한다. "종료해는 remaining<yearly라 자연히
        # 잔액 전액"은 prior_accumulated가 스케줄과 정합할 때만 참인데, 이 경로의
        # prior_accumulated는 **외부 확정값**이라 어긋난 채로 들어올 수 있다(감사 G6).
        # 강제하지 않으면 같은 입력에서 정률은 비망가로 끝나고 정액만 잔액이 남는다
        # (12,000,000/5년/prior 9,000,000 → 정액 장부 600,000, 이후 연도는 [] = 영구 미상각).
        dep = remaining if is_terminal else min(yearly, remaining)

    acc = prior_accumulated + dep
    return [FiscalYearRow(target_year, months, dep, acc, cost - acc)]


def schedule_merger_succession(cost: int, life_years: int, acq_year: int, acq_month: int,
                               prior_accumulated: int, merger_year: int, merger_month: int,
                               target_year: int, fiscal_end_month: int = 12,
                               declining: bool = False) -> List[FiscalYearRow]:
    """합병 존속법인이 승계한 자산의 회계연도 감가상각 — **합병등기월 다음 달부터**.

    소멸법인은 합병등기월까지 상각한다(`disposal.schedule_full_disposal`의 양도월 포함
    규칙과 동일). 존속법인이 등기월 다음 달부터 이어받으면 두 법인의 월수 합이 그해
    12개월로 딱 맞는다.

    시행령 문언(§26⑧⑨)을 그대로 적용하면 "1월 미만의 일수는 1월로 한다"가 양쪽에
    각각 걸려 등기월이 소멸·존속 두 법인에 중복 계산된다(등기 5/15 → 소멸 5개월 +
    존속 8개월 = 13개월). 금액이 이중상각되지는 않지만(§29의2② — 존속법인의 미상각
    잔액은 양도 당시 장부가액에서 출발) 그해 합산 상각범위액이 12개월치를 넘는다.
    이 함수는 그 중복을 배제하는 쪽을 택한다(사용자 결정, 2026-08-27).

    cost·acq_year·acq_month·life_years는 **양도법인 기준**이다(§29의2② 1호 — 적격합병
    승계 시 취득가액·상각방법·내용연수를 승계하는 방법). prior_accumulated는 승계받은
    상각누계(양도법인이 합병등기월까지 상각한 결과).
    """
    if target_year < merger_year:
        raise ValueError(
            f"당기연도({target_year})는 합병연도({merger_year}) 이전일 수 없습니다")
    if not 1 <= merger_month <= 12:
        raise ValueError(f"합병등기월은 1~12여야 합니다 (merger_month={merger_month})")
    if target_year == merger_year and merger_month == 12:
        return []                                        # 그해는 소멸법인이 전부 상각
    start = merger_month + 1 if target_year == merger_year else 1
    return schedule_separate_asset(cost, life_years, acq_year, acq_month,
                                   prior_accumulated, target_year, fiscal_end_month,
                                   declining, start_month=start)
