"""
dep_vector — 자본적지출(증가) 슬림 코어 (정액·정률)
==================================================

나침반(실증 완료): 자본적지출은 '취득 후 k개월' 상대시점 이벤트라 프로젝션과 호환된다.
취득·증가를 같은 calendar shift로 함께 옮기면 표준형(12월결산)으로 환원된다.
  → real(결산월 F) == standard(12월, 취득·증가 모두 δ시프트). 1원 단위 실증됨.

증가 처리(레퍼런스 "Vector 비율" 논리, core/dep_tang_engine.py:_calculate_with_increase):
  1. 증가 없는 base 월별 벡터 계산
  2. 증가 직전월 장부가 B → ratio = (B + 증가액) / B
  3. 증가월부터 base 월상각액 × ratio, 회계연도별 연말보정으로 연 목표 int(base연합 × ratio) 달성
  4. 내용연수·종료월 유지, 마지막 달 비망가 정리

정액·정률 증가 로직은 레퍼런스에서 바이트 동일 — base 월별 벡터만 다르다(monthly.sl/db).
"""

from typing import List

from vcore import monthly
from vcore.monthly import Month
from vcore.projection import (
    FiscalYearRow, standard_acq_month, first_fiscal_year, validate_asset_inputs,
)


def apply_increase(base: List[Month], cost: int, k: int, inc_amount: int) -> List[Month]:
    """증가월(상대 인덱스 k)부터 base 벡터에 ratio 적용 (레퍼런스 Vector 비율 논리).

    가드가 여기 있는 이유: monthly_schedule.monthly_events가 이 함수를 직접 호출하므로
    상위 진입점이 아닌 단일 관문에서 막아야 우회 경로가 없다.
    """
    if inc_amount <= 0:
        raise ValueError(f"자본적지출 금액은 양수여야 합니다 (inc_amount={inc_amount})")
    if k <= 0:              # k≤0은 base[k-1] 음수 인덱스로 직전월이 오염돼 폭주
        raise ValueError(f"자본적지출 시점은 취득월 이후여야 합니다 (취득 후 {k}개월)")
    if k >= len(base):      # 자연종료 이후 증가는 미지원 — 조용한 무시/IndexError 방지
        raise ValueError(f"자본적지출 시점(취득 후 {k}개월)이 내용연수 종료 이후입니다")
    prev = base[k - 1]                                   # 증가 직전월
    ratio = (prev.book + inc_amount) / prev.book
    # 증가 시 누계 불변 (book만 증가) — 스케일 루프는 부분양도와 공용 골격 사용
    return monthly.apply_ratio_from(base, k, ratio, prev.acc, prev.book + inc_amount)


def months_with_increase(monthly_fn, cost, life_years, acq_year, acq_month,
                          inc_amount, inc_year, inc_month, fiscal_end_month):
    """자본적지출 포함 월별 벡터 (인덱스 = 취득 후 경과월). k 범위 가드는 apply_increase(단일 관문)."""
    validate_asset_inputs(cost, acq_month, fiscal_end_month)
    m_std = standard_acq_month(fiscal_end_month, acq_month)
    k = (inc_year * 12 + inc_month) - (acq_year * 12 + acq_month)   # 취득→증가 개월 간격 (불변량)
    base = monthly_fn(cost, life_years, m_std)
    months = apply_increase(base, cost, k, inc_amount)
    return monthly.settle_terminal_evenly(months)   # 자연완료: 종료해 균등 재배분


def _schedule_with_increase(monthly_fn, cost, life_years, acq_year, acq_month,
                            inc_amount, inc_year, inc_month, fiscal_end_month):
    """자본적지출 포함 회계연도별 감가상각표. 표준형 + 프로젝션 (방법은 monthly_fn으로 주입)."""
    months = months_with_increase(monthly_fn, cost, life_years, acq_year, acq_month,
                                   inc_amount, inc_year, inc_month, fiscal_end_month)
    fy0 = first_fiscal_year(acq_year, acq_month, fiscal_end_month)
    return monthly.group(months, fy0)


def schedule_with_increase(cost: int, life_years: int, acq_year: int, acq_month: int,
                           inc_amount: int, inc_year: int, inc_month: int,
                           fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """자본적지출 포함 정액법 회계연도별 감가상각표 (임의 결산월)."""
    return _schedule_with_increase(monthly.sl_monthly, cost, life_years, acq_year,
                                   acq_month, inc_amount, inc_year, inc_month, fiscal_end_month)


def schedule_with_increase_declining(cost: int, life_years: int, acq_year: int, acq_month: int,
                                     inc_amount: int, inc_year: int, inc_month: int,
                                     fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """자본적지출 포함 정률법 회계연도별 감가상각표 (임의 결산월)."""
    return _schedule_with_increase(monthly.db_monthly, cost, life_years, acq_year,
                                   acq_month, inc_amount, inc_year, inc_month, fiscal_end_month)
