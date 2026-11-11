"""
dep_vector — 정액법 슬림 코어
==============================

12월 결산 표준형 벡터 1개만 구현하고, 임의 결산월은 projection.py로 프로젝션한다.

정확성 규칙(레퍼런스 core/dep_tang_engine.py와 회계연도 단위 1원 일치):
  - 연 상각액 = 4사5입(취득원가 × 상각률테이블[내용연수])   (법인세법 [별표 4])
    — 정수 산술 `rate_table.straight_line_annual` (float 곱셈 금지, 2026-09-03)
  - 회계연도 상각 = (연상각액 × 그해개월수) // 12, 비망가 한도 캡
  - 내용연수 종료해는 (직전 장부가 - 비망가)로 강제 → 최종 장부가 = 비망가
"""

from typing import List

from vcore.rate_table import straight_line_annual
from vcore.projection import (
    FiscalYearRow, MEMORANDUM, capped_yearly, standard_month_counts,
    standard_acq_month, project, validate_asset_inputs,
)


def annual_depreciation(cost: int, life_years: int) -> int:
    """법인세법 [별표 4] 정액법 연 상각액 = 4사5입(취득원가 × 상각률).

    공개 API다 — monthly·separate_asset이 방법 주입을 위해 소비한다(밑줄 이름을
    모듈 밖에서 부르던 캡슐화 누수 해소, 2026-08-22). 산식·범위 가드는 rate_table 단일 관문.
    """
    return straight_line_annual(cost, life_years)


def month_counts(cost: int, life_years: int, acq_month: int) -> List[int]:
    """정액법 회계연도별 상각 개월수 — 상각이 끝나는 해에서 끊은 standard_month_counts.

    별표4 정액률은 소수 셋째 자리라 상각률 × 내용연수 > 1인 연수가 35개 있다(30년: 0.034 × 30 =
    1.02). 이런 연수는 내용연수가 끝나기 전에 장부가가 비망가에 닿는다. 그 해에서 스케줄을 끝낸다 —
    정률이 5% 교차 해에서 끝나는 것(`declining_balance.month_counts`), 분리자산 경로가 같은
    상황에서 `[]`를 돌려주는 것과 같은 규칙이다. 종전에는 내용연수 끝까지 상각액 0인 행을 붙였고
    (INC-11), 그 0원 구간의 자본적지출이 한 해 동안 상각되지 않다가 다음 해에 몰렸다
    (52년·1억, 2076-03 +1천만 → FY2076 0원, FY2077 1천만). 연도별 상각액·누계·장부가는 같다.
    """
    annual = annual_depreciation(cost, life_years)     # 범위 가드 = rate_table 단일 관문
    counts = standard_month_counts(acq_month, life_years)
    book = cost
    for i, months in enumerate(counts[:-1]):
        book -= capped_yearly(book, months, lambda b, m: (annual * m) // 12)
        if book <= MEMORANDUM:                         # 상각 완료 — 이후 해는 없다
            return counts[:i + 1]
    return counts


def standard_vector(cost: int, life_years: int, acq_month: int) -> List[FiscalYearRow]:
    """12월 결산 표준형 정액법 벡터 (상대 인덱스 라벨). 정확성의 단일 진실원."""
    annual = annual_depreciation(cost, life_years)
    counts = month_counts(cost, life_years, acq_month)
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
