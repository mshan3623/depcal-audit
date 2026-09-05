"""
dep_vector — 양도 슬림 코어 (전체양도, 정액·정률)
=================================================

나침반: 양도는 '취득 후 d개월' 상대시점 이벤트. disp_year/disp_month는
**양도월(포함)** — 더존 공식: 양도월까지 월할 상각 후 익월부터 중단.
전체양도 = base 월별 벡터를 양도월(인덱스 d)까지 절단한 것.
취득·양도를 같은 δ로 함께 시프트하면 표준형으로 환원된다.

core와의 관계: **양도월 컨벤션이 통일돼 있다**(core 2026-06-13 변경). 둘 다 양도월까지
상각하므로 대조 시 같은 양도월을 넣는다 — 매핑이 필요 없다
(tests_vector/test_slim_vs_reference.py 참고).
"""

from typing import List

from vcore import monthly
from vcore.monthly import Month
from vcore.projection import (
    FiscalYearRow, standard_acq_month, first_fiscal_year, round_half_up,
    validate_asset_inputs,
)


def months_to_disposal(acq_year: int, acq_month: int, disp_year: int, disp_month: int) -> int:
    """취득→양도 개월 간격(불변량). 음수(양도월 < 취득월)는 base[:d+1]이 파이썬 음수
    슬라이스로 뒤에서 절단돼 그럴듯한 오답 표가 나오므로 여기서 막는다."""
    d = (disp_year * 12 + disp_month) - (acq_year * 12 + acq_month)
    if d < 0:
        raise ValueError(
            f"양도 시점({disp_year}-{disp_month})은 취득월({acq_year}-{acq_month}) 이후여야 합니다")
    return d


def months_full_disposal(monthly_fn, cost, life_years, acq_year, acq_month,
                          disp_year, disp_month, fiscal_end_month):
    """전체양도 월별 벡터 — base를 양도월(인덱스 d, 포함)까지 절단. 더존 공식."""
    validate_asset_inputs(cost, acq_month, fiscal_end_month)
    m_std = standard_acq_month(fiscal_end_month, acq_month)
    d = months_to_disposal(acq_year, acq_month, disp_year, disp_month)
    base = monthly_fn(cost, life_years, m_std)
    return base[:d + 1]


def _schedule_full_disposal(monthly_fn, cost, life_years, acq_year, acq_month,
                            disp_year, disp_month, fiscal_end_month):
    """전체양도 회계연도별 감가상각표. 표준형 base를 양도월(포함)까지 절단 + 프로젝션."""
    truncated = months_full_disposal(monthly_fn, cost, life_years, acq_year, acq_month,
                                      disp_year, disp_month, fiscal_end_month)
    fy0 = first_fiscal_year(acq_year, acq_month, fiscal_end_month)
    return monthly.group(truncated, fy0)


def schedule_full_disposal(cost: int, life_years: int, acq_year: int, acq_month: int,
                           disp_year: int, disp_month: int,
                           fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """전체양도 정액법 (임의 결산월). disp_month = 양도월(그 달까지 상각, 더존식)."""
    return _schedule_full_disposal(monthly.sl_monthly, cost, life_years, acq_year,
                                   acq_month, disp_year, disp_month, fiscal_end_month)


def schedule_full_disposal_declining(cost: int, life_years: int, acq_year: int, acq_month: int,
                                     disp_year: int, disp_month: int,
                                     fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """전체양도 정률법 (임의 결산월). disp_month = 양도월(그 달까지 상각, 더존식)."""
    return _schedule_full_disposal(monthly.db_monthly, cost, life_years, acq_year,
                                   acq_month, disp_year, disp_month, fiscal_end_month)


# ── 양도 판정·분배 단일 관문 ────────────────────────────────────────────
def is_full_disposal(basis: int, disposal_amount) -> bool:
    """전부양도(폐기 포함) 판정. basis = 이벤트 시점 통합 취득원가(원가 + 자본적지출).

    None = 금액 미지정(전부), basis 이상 = 남는 지분 없음. 이 판정이 두 곳에 있으면
    스케줄과 명세서가 갈린다(감사 G4) — 소비자는 전부 이 함수를 부른다.
    """
    return disposal_amount is None or disposal_amount >= basis


def disposal_split(basis: int, acc: int, book: int, disposal_amount) -> tuple:
    """양도로 제거되는 (취득원가, 감가상각누계액, 장부가액, 부분양도여부).

    acc·book은 **양도월말**(그 달까지 상각한 뒤) 값이다 — 직전월이 아니다(감사 G5).
    양도 누계는 4사5입, 장부가는 차감으로 등식(제거원가 = 제거누계 + 제거장부)을 보장한다.
    """
    if is_full_disposal(basis, disposal_amount):
        return basis, acc, book, False
    disp_acc = round_half_up(acc * disposal_amount / basis)
    return disposal_amount, disp_acc, disposal_amount - disp_acc, True


# ── 부분양도 = 역(逆) 자본적지출 + 누계 분배 ────────────────────────────
def apply_partial_disposal(base: List[Month], cost: int, d: int, disposal_amount: int) -> List[Month]:
    """이벤트월(상대 인덱스 d)부터 base 벡터에 잔존비율 적용. 이벤트 시점에 누계·장부가 분배.

    d = 양도월 + 1 (상각중단 시작월). 더존 공식: 양도월까지 전체 기준 상각 후 분배.
    capex `apply_increase`의 거울: factor=잔존비율(<1), 이벤트 시점에 book·acc 둘 다 차감.
    가드가 여기 있는 이유: monthly_schedule.monthly_events가 직접 호출하는 단일 관문.
    """
    if not 0 < disposal_amount < cost:   # ≥cost는 호출부가 전부양도(절단)로 위임, ≤0은 도메인 밖
        raise ValueError(f"부분양도 금액은 0 < 금액 < 취득원가여야 합니다 (disposal_amount={disposal_amount}, cost={cost})")
    remaining_ratio = 1.0 - disposal_amount / cost
    prev = base[d - 1]                                   # 양도월 (마지막 전체기준 상각월)
    # 양도월말 분배: 양도 누계 = 4사5입, 잔존 = 차감으로 무결성 보장
    _, disposal_accumulated, disposal_book, _ = disposal_split(cost, prev.acc, prev.book,
                                                               disposal_amount)
    # 잔존 누계·장부가로 진입 — 스케일 루프는 capex와 공용 골격 사용
    return monthly.apply_ratio_from(base, d, remaining_ratio,
                                    prev.acc - disposal_accumulated, prev.book - disposal_book)


def months_partial_disposal(monthly_fn, cost, life_years, acq_year, acq_month,
                             disposal_amount, disp_year, disp_month, fiscal_end_month):
    """부분양도 월별 벡터. 양도가 자연상각 종료 이후면 분배만 남고 월 영향 없음 — 절단 없이 base 그대로."""
    validate_asset_inputs(cost, acq_month, fiscal_end_month)
    m_std = standard_acq_month(fiscal_end_month, acq_month)
    d = months_to_disposal(acq_year, acq_month, disp_year, disp_month)
    base = monthly_fn(cost, life_years, m_std)
    if disposal_amount >= cost:           # 가드: 양도액≥원가는 전부양도(절단)로 위임 — 음수 상각 방지
        return base[:d + 1]
    ev = min(d + 1, len(base))            # 양도월 포함(더존 공식), 종료 후 양도는 경계로 클램프
    months = apply_partial_disposal(base, cost, ev, disposal_amount)
    return monthly.settle_terminal_evenly(months)   # 자연완료: 종료해 균등 재배분


def _schedule_partial_disposal(monthly_fn, cost, life_years, acq_year, acq_month,
                               disposal_amount, disp_year, disp_month, fiscal_end_month):
    """부분양도 회계연도별 감가상각표. 표준형 base + 잔존비율 스케일 + 프로젝션.

    자연종료(완전상각) 후 부분양도는 추가 상각이 없으므로(상각 0), 감가상각 스케줄 대신
    양도 연도에 처분 조정행을 더한다. 양도분의 취득원가·누계·비망가를 취득가액 비율로
    안분 제거(비망가는 가치가 아닌 자산 단위 메모라 잔류분도 비율 안분 — 60% 양도 → 400).
    """
    months = months_partial_disposal(monthly_fn, cost, life_years, acq_year, acq_month,
                                      disposal_amount, disp_year, disp_month, fiscal_end_month)
    fy0 = first_fiscal_year(acq_year, acq_month, fiscal_end_month)
    rows = monthly.group(months, fy0)
    d = (disp_year * 12 + disp_month) - (acq_year * 12 + acq_month)
    # 종료월(d=n-1) 포함: 종료월 양도는 그 달까지 상각(자연완료와 동일) 후 분배만 남으므로
    # 자연종료 후 양도와 같은 조정행 경로 — 미포함 시 양도가 무흔적으로 사라짐(조용한 무시)
    if disposal_amount < cost and d >= life_years * 12 - 1:    # 자연종료(종료월 포함) 후 부분양도
        m_std = standard_acq_month(fiscal_end_month, acq_month)
        last = rows[-1]                                        # 자연종료 시점(완전상각)
        _, disp_acc, disp_book, _ = disposal_split(cost, last.accumulated, last.book_value,
                                                    disposal_amount)
        res_acc = last.accumulated - disp_acc                  # 잔류분 누계
        res_book = last.book_value - disp_book                 # 잔류분 비망가(안분)
        disp_fy = fy0 + ((m_std - 1) + d) // 12                # 양도 연도 라벨
        if disp_fy == last.fiscal_year:
            # 종료월 양도: 조정행의 FY가 종료해와 같다. 따로 붙이면 한 회계연도에 행이 둘이
            # 되어 `fiscal_year`가 비유일해지고, `next(r for r in sch if r.fiscal_year == fy)`
            # 류 소비자가 **첫 행만 보고 양도를 놓친다**(감사 G10). 같은 해의 사건이므로
            # 종료해 행에 병합한다 — 그 해 상각액은 그대로고 기말 잔액만 잔류분이 된다.
            last.accumulated, last.book_value = res_acc, res_book
        else:
            rows.append(FiscalYearRow(disp_fy, 0, 0, res_acc, res_book))
    return rows


def schedule_partial_disposal(cost: int, life_years: int, acq_year: int, acq_month: int,
                              disposal_amount: int, disp_year: int, disp_month: int,
                              fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """부분양도 정액법 (임의 결산월). disp_month = 양도월(그 달까지 전체기준 상각, 더존식)."""
    return _schedule_partial_disposal(monthly.sl_monthly, cost, life_years, acq_year,
                                      acq_month, disposal_amount, disp_year, disp_month, fiscal_end_month)


def schedule_partial_disposal_declining(cost: int, life_years: int, acq_year: int, acq_month: int,
                                        disposal_amount: int, disp_year: int, disp_month: int,
                                        fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """부분양도 정률법 (임의 결산월). disp_month = 양도월(그 달까지 전체기준 상각, 더존식)."""
    return _schedule_partial_disposal(monthly.db_monthly, cost, life_years, acq_year,
                                      acq_month, disposal_amount, disp_year, disp_month, fiscal_end_month)
