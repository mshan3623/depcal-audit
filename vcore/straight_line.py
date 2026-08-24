"""
dep_vector — 정액법 슬림 코어
==============================

12월 결산 표준형 벡터 1개만 구현하고, 임의 결산월은 projection.py로 프로젝션한다.

정확성 규칙(레퍼런스 core/dep_tang_engine.py와 회계연도 단위 1원 일치):
  - 연 상각액 = 4사5입(취득원가 × 상각률테이블[내용연수])   (법인세법 [별표 4])
  - 회계연도 상각 = (연상각액 × 그해개월수) // 12, 비망가 한도 캡
  - 내용연수 종료해는 (직전 장부가 - 비망가)로 강제 → 최종 장부가 = 비망가
"""

from typing import List

from vcore.rate_table import straight_line_rate
from vcore.projection import (
    FiscalYearRow, MEMORANDUM, capped_yearly, standard_month_counts,
    standard_acq_month, project, round_half_up, validate_asset_inputs,
)


def annual_depreciation(cost: int, life_years: int) -> int:
    """법인세법 [별표 4] 정액법 연 상각액 = 4사5입(취득원가 × 상각률).

    공개 API다 — monthly·separate_asset이 방법 주입을 위해 소비한다(밑줄 이름을
    모듈 밖에서 부르던 캡슐화 누수 해소, 2026-08-22). 범위 가드는 rate_table 단일 관문.
    """
    return round_half_up(cost * straight_line_rate(life_years))


def standard_vector(cost: int, life_years: int, acq_month: int) -> List[FiscalYearRow]:
    """12월 결산 표준형 정액법 벡터 (상대 인덱스 라벨). 정확성의 단일 진실원."""
    annual = annual_depreciation(cost, life_years)
    counts = standard_month_counts(acq_month, life_years)
    rows: List[FiscalYearRow] = []
    acc = 0
    last = len(counts) - 1
    for i, months in enumerate(counts):
        book = cost - acc                             # 회계연도 기초 장부가
        if i == last:
            yearly = book - MEMORANDUM                # 종료해: 비망가 강제
        else:
            yearly = capped_yearly(book, months, lambda b, m: (annual * m) // 12)
        acc += yearly
        rows.append(FiscalYearRow(i, months, yearly, acc, cost - acc))
    return rows


def schedule(cost: int, life_years: int, acq_year: int, acq_month: int,
             fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """정액법 회계연도별 감가상각표 (임의 결산월). 표준형 + 프로젝션."""
    validate_asset_inputs(cost, acq_month, fiscal_end_month)
    m_std = standard_acq_month(fiscal_end_month, acq_month)
    base = standard_vector(cost, life_years, m_std)
    return project(base, acq_year, acq_month, fiscal_end_month)
