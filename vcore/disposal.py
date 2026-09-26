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
    FiscalYearRow, capped_yearly, standard_acq_month, first_fiscal_year,
    validate_asset_inputs,
)
from vcore.rate_table import declining_balance_amount
from vcore.straight_line import annual_depreciation


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


def months_extinction(monthly_fn, yearly_fn, cost, life_years, acq_year, acq_month,
                      end_year, end_month, fiscal_end_month):
    """법인 소멸(합병·해산)로 사업연도가 end_month에 끝나는 경우의 월별 벡터.

    자산 양도와 다르다. 양도는 12개월 사업연도 **중간**에 자산이 빠지는 것이라 월 base ×
    양도월수로 끊지만(결산월 끝수 보정 미도달), 소멸법인의 마지막 의제사업연도(법 §8)는 그
    자체가 **짧은 사업연도**다 — 상각범위액 = 연 상각액 × 그 월수 ÷ 12(시행령 §26⑧), 끝수는
    그 사업연도의 마지막 달(등기월)이 흡수한다. 더존 실측(합병소멸 법인 2026-01~02, 정률 5건)이
    5건 모두 이 값이고, 양도 경로(`schedule_full_disposal`)는 4건에서 1원 적었다.
    월수는 역에 따라, 1월 미만은 1월(§26⑧) — end_month = 등기월(포함).
    """
    validate_asset_inputs(cost, acq_month, fiscal_end_month)
    m_std = standard_acq_month(fiscal_end_month, acq_month)
    d = months_to_disposal(acq_year, acq_month, end_year, end_month)
    base = monthly_fn(cost, life_years, m_std)
    if d >= len(base) - 1:                     # 그 전에 상각이 끝났다 — 짧은 사업연도 영향 없음
        return base[:d + 1]
    fy = base[d].fy_index
    start = next(i for i, m in enumerate(base) if m.fy_index == fy)
    n = d - start + 1                          # 마지막 사업연도 중 상각 월수
    acc = base[start - 1].acc if start else 0
    yearly = capped_yearly(cost - acc, n, yearly_fn)
    per = yearly // n
    out = list(base[:start])
    for j in range(n):
        amt = per + (yearly - per * n if j == n - 1 else 0)
        acc += amt
        out.append(Month(fy, amt, acc, cost - acc))
    return out


def schedule_extinction(cost: int, life_years: int, acq_year: int, acq_month: int,
                        end_year: int, end_month: int,
                        fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """합병·해산 소멸법인의 정액법 상각표 — 마지막 행이 등기월에 끝나는 짧은 의제사업연도."""
    annual = annual_depreciation(cost, life_years)
    months = months_extinction(monthly.sl_monthly, lambda b, m: (annual * m) // 12,
                               cost, life_years, acq_year, acq_month, end_year, end_month,
                               fiscal_end_month)
    return monthly.group(months, first_fiscal_year(acq_year, acq_month, fiscal_end_month))


def schedule_extinction_declining(cost: int, life_years: int, acq_year: int, acq_month: int,
                                  end_year: int, end_month: int,
                                  fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """합병·해산 소멸법인의 정률법 상각표 — 마지막 행이 등기월에 끝나는 짧은 의제사업연도."""
    months = months_extinction(monthly.db_monthly,
                               lambda b, m: declining_balance_amount(b, life_years, m),
                               cost, life_years, acq_year, acq_month, end_year, end_month,
                               fiscal_end_month)
    return monthly.group(months, first_fiscal_year(acq_year, acq_month, fiscal_end_month))


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
    disp_acc = (2 * acc * disposal_amount + basis) // (2 * basis)   # 4사5입, 정수 산술(INC-13)
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
    prev = base[d - 1]                                   # 양도월 (마지막 전체기준 상각월)
    # 양도월말 분배: 양도 누계 = 4사5입, 잔존 = 차감으로 무결성 보장
    _, disposal_accumulated, disposal_book, _ = disposal_split(cost, prev.acc, prev.book,
                                                               disposal_amount)
    # 잔존 누계·장부가로 진입 — 스케일 루프는 capex와 공용 골격 사용
    return monthly.apply_ratio_from(base, d, cost - disposal_amount, cost,   # 잔존비율(정수)
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
    return monthly.settle_terminal_evenly(months, ev)   # 자연완료: 종료해 균등(양도 이후 구간)


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
    # 자연종료월 = base 마지막 인덱스. `life_years * 12 - 1`이 아니다 — 정률은 5% 교차 해에서
    # 내용연수보다 먼저 끝날 수 있다(§26⑥). months 길이는 양도 시점과 무관하게 base 길이다.
    if disposal_amount < cost and d >= len(months) - 1:        # 자연종료(종료월 포함) 후 부분양도
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
