"""
dep_vector — 표준형 월별 빌더 (공유)
=====================================

12월 결산 표준형의 월별 감가상각 벡터. 이벤트(자본적지출·양도)는 월 단위로 발화하므로
회계연도 집계 전에 월별 벡터가 필요하다. 정액·정률은 연 상각액 함수만 다르다.

레퍼런스 월별과 1원 일치: 회계연도 base_monthly=연상각//개월, 잔재는 마지막 달,
종료해는 비망가 강제.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

from vcore.straight_line import annual_depreciation
from vcore.declining_balance import month_counts as db_month_counts
from vcore.rate_table import declining_balance_amount
from vcore.projection import (
    FiscalYearRow, MEMORANDUM, capped_yearly, standard_month_counts, first_fiscal_year,
)


@dataclass
class Month:
    fy_index: int      # 표준형 회계연도 상대 인덱스 (0,1,2,…)
    amount: int        # 월 감가상각비
    acc: int           # 월말 감가상각누계액 (부분양도 시 점프 하강 반영)
    book: int          # 월말 장부가액 (이벤트 후 원가기준 반영)


def standard_monthly(cost: int, life_years: int, acq_month: int,
                     yearly_nonfinal: Callable[[int, int], int],
                     counts: Optional[List[int]] = None) -> List[Month]:
    """12월 결산 표준형 월별 벡터 (이벤트 없음). yearly_nonfinal(기초장부가, 개월)로 방법 주입.

    counts = 회계연도별 개월수. 기본은 내용연수 전체, 정률은 5% 교차 해에서 끊은 것을 넘긴다.
    """
    if counts is None:
        counts = standard_month_counts(acq_month, life_years)
    months: List[Month] = []
    acc = 0
    last_fy = len(counts) - 1
    for fy_i, miy in enumerate(counts):
        book = cost - acc                               # 회계연도 기초 장부가
        yearly = capped_yearly(book, miy, yearly_nonfinal)
        base_m = yearly // miy
        rem = yearly - base_m * miy                     # 연말 잔재
        for j in range(miy):
            if fy_i == last_fy and j == miy - 1:
                amt = (cost - acc) - MEMORANDUM         # 자연종료 마지막 달: 비망가 정리(잔재 폭증)
            elif j == miy - 1:
                amt = base_m + rem                      # 결산월 잔재 보정
            else:
                amt = base_m                            # 일반월: 정상 base_monthly
            acc += amt
            months.append(Month(fy_i, amt, acc, cost - acc))
    return months


def settle_terminal_evenly(months: List[Month], start: int = 0) -> List[Month]:
    """자연완료 스케줄의 종료해(마지막 회계연도) 잔재 정리를 그해 월수로 균등 재배분한다.

    원칙: 종료해 연간상각액(=벡터의 그해 월상각 총합, 불변)을 먼저 확정 → 월할 균등 + 마지막
    달 보정. 정률법 5% 잔재의 '마지막 달 dump'를 제거하고 연간상각액의 일부로 균등 안분한다
    (법인세법 시행령 제26조⑥ '상각범위액에 가산'의 월 단위 적용). 정액법도 별표4율 × n ≠ 1인
    연수(6년 0.166×6=0.996, 7년 0.142×7=0.994, 14년 등)에는 종료해 잔재가 남으므로 같은
    원칙으로 균등 배분한다 — 무변(no-op)인 것은 잔재가 0인 연수뿐이다. 단 절단 경로(전체양도,
    미완료 구간)에는 적용하지 않는다.

    주의: §26⑥의 '가산'은 **정률법** 잔존가액 규정이다. 정액법은 같은 항 본문대로 잔존가액이
    0이고 매년 상각범위액은 취득가액 × 상각률이라, 종료해에 잔재를 흡수하는 것 자체는 §26⑥이
    근거가 아닌 엔진 규약이다(문언상 잔재는 다음 해 몫 — 외부 평가 2026-09-26 ②, 결정 대기).

    `start` = 마지막 이벤트(capex 증가월·부분양도 익월)의 상대 인덱스. 균등화는 종료해 중
    **start 이후 구간**에만 한다 — 미래의 사건은 지나간 달을 바꾸지 않는다. 종전에는 종료해
    12개월 전체를 균등화해, 종료해 안의 이벤트 이전 달이 이벤트 이후 기준 금액으로 바뀌었다
    (capex 7월 → 1~6월 장부가 음수, 부분양도 6월 → 엑셀 시트1 처분 누계 ≠ 시트3 누계 하락
    180,090원. 연간 합계는 맞아 연도별 대조로는 안 보였다 — 감사 2026-09-23 A3, INC-14).
    """
    if not months:
        return months
    last_fy = months[-1].fy_index
    idxs = [i for i, m in enumerate(months) if m.fy_index == last_fy and i >= start]
    if not idxs:
        return months
    yearly = sum(months[i].amount for i in idxs)             # 종료해 (이벤트 후) 상각액 총합, 불변
    miy = len(idxs)
    base_m = yearly // miy
    rem = yearly - base_m * miy
    # 금액만 균등 재배분하고, acc/book은 '누적 재배분 차이(delta)'를 기존 값에 가산.
    # 이렇게 하면 종료해 안의 이벤트 점프(부분양도 누계 하강·capex 장부 상승)가 기존 acc/book에
    # 이미 반영돼 있으므로 그대로 보존되고, 마지막 달 delta=0이라 연말 acc/book도 정확히 불변.
    cum_old = cum_new = 0
    for k, i in enumerate(idxs):
        new_amt = base_m + rem if k == miy - 1 else base_m
        cum_old += months[i].amount
        cum_new += new_amt
        delta = cum_new - cum_old
        m = months[i]
        months[i] = Month(last_fy, new_amt, m.acc + delta, m.book - delta)
    return months


def apply_ratio_from(base: List[Month], start: int, num: int, den: int,
                     acc: int, book: int) -> List[Month]:
    """이벤트월(상대 인덱스 start)부터 base 월상각을 비율 num/den으로 스케일하는 공용 골격.

    비율은 **정수 분자·분모**로 받는다 — float 비율(`1.0 - D/cost`)은 정확한 정수 결과를
    1원 내렸다(55% 양도: 2,000,000 × 0.45 → 899,999. 감사 2026-09-23 A2, INC-13).
    금액 × 비율은 `x * num // den` 하나로만 계산한다(INC-01·04와 같은 원단위 산술 계열).

    capex 증가(ratio>1, 이벤트 시점 book만 증가)와 부분양도(ratio<1, 이벤트 시점
    acc·book 분배 차감)의 거울 루프 단일화 — 이벤트 진입 acc/book은 호출자가 확정해
    넘긴다. 연도별 연말보정으로 연 목표 base연합×num//den 달성, 마지막 달은 비망가
    정리, book 음수 방지(레퍼런스 동일: acc는 보정 전 금액 유지).
    """
    n = len(base)
    out = list(base[:start])
    year_acc: dict = {}
    for idx in range(start, n):
        fy = base[idx].fy_index
        year_acc.setdefault(fy, 0)
        is_final = (idx == n - 1)
        is_last_of_fy = is_final or base[idx + 1].fy_index != fy
        if is_final:
            amount = max(0, book - MEMORANDUM)
        elif is_last_of_fy:
            year_base_sum = sum(base[j].amount for j in range(start, n) if base[j].fy_index == fy)
            year_target = year_base_sum * num // den
            amount = year_target - year_acc[fy]
        else:
            amount = base[idx].amount * num // den
        year_acc[fy] += amount
        acc += amount
        book -= amount
        if book < 0:                                     # 음수 방지 (레퍼런스 동일)
            amount += book
            book = 0
        out.append(Month(fy, amount, acc, book))
    return out


def sl_monthly(cost: int, life_years: int, acq_month: int) -> List[Month]:
    """정액법 표준형 월별."""
    annual = annual_depreciation(cost, life_years)
    return standard_monthly(cost, life_years, acq_month,
                            lambda book, miy: (annual * miy) // 12)


def db_monthly(cost: int, life_years: int, acq_month: int) -> List[Month]:
    """정률법 표준형 월별. 연 산식은 rate_table.declining_balance_amount(정수 산술) 하나."""
    return standard_monthly(cost, life_years, acq_month,
                            lambda book, miy: declining_balance_amount(book, life_years, miy),
                            db_month_counts(cost, life_years, acq_month))   # 범위 가드 포함


def group(months: List[Month], fy0: int) -> List[FiscalYearRow]:
    """월별 벡터를 회계연도로 묶고 실제 연도 라벨(fy0 + 상대인덱스) 부착."""
    rows: dict = {}
    order: List[int] = []
    for mo in months:
        fy = fy0 + mo.fy_index
        if fy not in rows:
            rows[fy] = FiscalYearRow(fy, 0, 0, mo.acc, mo.book)
            order.append(fy)
        r = rows[fy]
        r.months += 1
        r.depreciation += mo.amount
        r.accumulated = mo.acc          # 회계연도 마지막 월의 누계 (carry)
        r.book_value = mo.book          # 회계연도 마지막 월의 장부가
    return [rows[fy] for fy in order]
