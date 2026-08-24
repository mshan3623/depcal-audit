"""
dep_vector — 표준형 월별 빌더 (공유)
=====================================

12월 결산 표준형의 월별 감가상각 벡터. 이벤트(자본적지출·양도)는 월 단위로 발화하므로
회계연도 집계 전에 월별 벡터가 필요하다. 정액·정률은 연 상각액 함수만 다르다.

레퍼런스 월별과 1원 일치: 회계연도 base_monthly=연상각//개월, 잔재는 마지막 달,
종료해는 비망가 강제.
"""

from dataclasses import dataclass
from typing import Callable, List

from vcore.straight_line import annual_depreciation
from vcore.rate_table import declining_rate
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
                     yearly_nonfinal: Callable[[int, int], int]) -> List[Month]:
    """12월 결산 표준형 월별 벡터 (이벤트 없음). yearly_nonfinal(기초장부가, 개월)로 방법 주입."""
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


def settle_terminal_evenly(months: List[Month]) -> List[Month]:
    """자연완료 스케줄의 종료해(마지막 회계연도) 잔재 정리를 그해 월수로 균등 재배분한다.

    원칙: 종료해 연간상각액(=벡터의 그해 월상각 총합, 불변)을 먼저 확정 → 월할 균등 + 마지막
    달 보정. 정률법 5% 잔재의 '마지막 달 dump'를 제거하고 연간상각액의 일부로 균등 안분한다
    (법인세법 시행령 제26조⑥ '상각범위액에 가산'의 월 단위 적용). 정액법은 잔재가 없어 항상
    무변(no-op). basis-free: 종료해 총액·직전 장부가를 벡터에서 도출하므로 취득가 변동(capex
    증가·부분양도 감소) 잔여표에도 안전. 단 절단 경로(전체양도, 미완료 구간)에는 적용하지 않는다.
    """
    if not months:
        return months
    last_fy = months[-1].fy_index
    idxs = [i for i, m in enumerate(months) if m.fy_index == last_fy]
    yearly = sum(months[i].amount for i in idxs)             # 종료해 연간상각액(총합, 불변)
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


def apply_ratio_from(base: List[Month], start: int, ratio: float, acc: int, book: int) -> List[Month]:
    """이벤트월(상대 인덱스 start)부터 base 월상각을 ratio로 스케일하는 공용 골격.

    capex 증가(ratio>1, 이벤트 시점 book만 증가)와 부분양도(ratio<1, 이벤트 시점
    acc·book 분배 차감)의 거울 루프 단일화 — 이벤트 진입 acc/book은 호출자가 확정해
    넘긴다. 연도별 연말보정으로 연 목표 int(base연합×ratio) 달성, 마지막 달은 비망가
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
            year_target = int(year_base_sum * ratio)
            amount = year_target - year_acc[fy]
        else:
            amount = int(base[idx].amount * ratio)
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
    """정률법 표준형 월별."""
    rate = declining_rate(life_years)
    return standard_monthly(cost, life_years, acq_month,
                            lambda book, miy: int(book * rate * miy // 12))


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
