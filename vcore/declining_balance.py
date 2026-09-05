"""
dep_vector — 정률법 슬림 코어
==============================

정액법과 동일한 표준형+프로젝션 골격. 연 상각액 산식만 다르다(매년 기초장부가 기준).

정확성 규칙(레퍼런스 core/dep_tang_engine.py와 회계연도 단위 1원 일치):
  - 상각률 = 별표4 정률 1000분율 정수 (rate_table.STATUTORY_PERMILLE)
  - 회계연도 상각 = 절사(기초장부가 × 상각률 × 그해개월수 / 12), 비망가 한도 캡
    — 정수 산술 `rate_table.declining_balance_amount` (float 곱셈 금지, 2026-09-03)
  - 내용연수 종료해는 (직전 장부가 - 비망가)로 강제 → 최종 장부가 = 비망가
    (정률법 특성상 종료해 잔재 ≈ 5%가 마지막 해에 일괄 정리되어 폭증 — 회계적 정상)
"""

from typing import List

from vcore.rate_table import check_life_years, declining_balance_amount
from vcore.projection import (
    FiscalYearRow, MEMORANDUM, capped_yearly, standard_month_counts,
    standard_acq_month, project, validate_asset_inputs,
)


def standard_vector(cost: int, life_years: int, acq_month: int) -> List[FiscalYearRow]:
    """12월 결산 표준형 정률법 벡터 (상대 인덱스 라벨). 정확성의 단일 진실원."""
    check_life_years(life_years)                       # 범위 가드 = rate_table 단일 관문(상단 발화)
    counts = standard_month_counts(acq_month, life_years)
    rows: List[FiscalYearRow] = []
    acc = 0
    last = len(counts) - 1
    for i, months in enumerate(counts):
        book = cost - acc                              # 회계연도 기초 장부가
        if i == last:
            yearly = book - MEMORANDUM                 # 종료해: 비망가 강제
        else:                                          # 정수 산술 단일 관문
            yearly = capped_yearly(book, months,
                                   lambda b, m: declining_balance_amount(b, life_years, m))
        acc += yearly
        rows.append(FiscalYearRow(i, months, yearly, acc, cost - acc))
    return rows


def schedule(cost: int, life_years: int, acq_year: int, acq_month: int,
             fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """정률법 회계연도별 감가상각표 (임의 결산월). 표준형 + 프로젝션."""
    validate_asset_inputs(cost, acq_month, fiscal_end_month)
    m_std = standard_acq_month(fiscal_end_month, acq_month)
    base = standard_vector(cost, life_years, m_std)
    return project(base, acq_year, acq_month, fiscal_end_month)
