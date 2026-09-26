"""
dep_vector — 무형자산 슬림 코어 (직접상각법, 별표4 상각률)
========================================================

무형자산은 정액법으로 상각하되, 감가상각누계액 계정을 쓰지 않고 취득원가에서 직접
차감하는 직접상각법을 쓴다. 직접상각은 **표시(재무제표) 차이일 뿐 상각액·장부가는
정액법과 동일** — 엔진 수치에는 영향이 없다.

상각률은 법인세법 [별표4] 정액법 상각률을 사용한다 (= round(cost × 별표4율)).
  - 4·5·8·10년: 별표4율 = 1/내용연수 → 1/n 직접 나눗셈과 동일(과거 실무가 4·5년이라 무차이)
  - 3·6·7·9·11·12…년: 별표4율은 1/n을 소수 3자리 절사 → 1/n과 다름. **별표4가 정답.**
    (사용자 도메인 판단 2026-06-02: 무형도 별표4 상각률을 쓴다.)

따라서 무형자산 = 유형 정액법과 회계연도 수치 동일. 단 **개발비**(시행령 §26①6)는
별표4가 아닌 1/n 경과월수 비례라 따로 둔다(아래 `schedule_development_cost`). 단순취득·자본적지출·양도 모두
유형 정액법 슬림을 그대로 재사용한다.

주의: 무형 검증의 oracle은 별표4(=유형 정액 슬림)다. 과거 core/dep_intang_engine.py 의
무형 함수는 base_annual = int(cost // life) 로 1/n 직접 나눗셈이라 3·6·7·9년 등에서
별표4와 어긋났으나, 2026-06-16부터 core(depreciation_engine)의 무형 경로 전체가 유형
정액 함수를 재사용해 별표4로 통일됐다(core==vcore 1원 일치). dep_intang_engine 의 1/n
함수는 단위 테스트가 직접 호출하므로 잔존하나 실행 경로에서는 더 이상 쓰이지 않는다.
"""

from typing import List

from vcore import straight_line, capex, disposal, monthly
from vcore.monthly import Month
from vcore.projection import (
    FiscalYearRow, first_fiscal_year, standard_acq_month, validate_asset_inputs,
)

# 무형자산 = 별표4 정액법. 직접상각은 표시 차이일 뿐 수치 동일 → 유형 정액 슬림 재사용.
schedule = straight_line.schedule
schedule_with_increase = capex.schedule_with_increase
schedule_full_disposal = disposal.schedule_full_disposal
schedule_partial_disposal = disposal.schedule_partial_disposal


# ── 개발비 (시행령 §26①6) ─────────────────────────────────────────────────
# 개발비는 별표4가 아니다: "20년의 범위에서 연단위로 신고한 내용연수에 따라 매 사업연도별
# 경과월수에 비례하여 상각". 즉 연 상각액 = 취득가액 ÷ 내용연수(1/n). 별표4율과 1/n은
# 4·5·8·10·20년에서만 같고 3·6·7·9년 등에서 갈린다(1억·3년: 별표4 33,300,000 vs
# 1/n 33,333,333 — 외부 평가 2026-09-26 ④). 일반 무형(영업권·특허권·소프트웨어 등)은
# 계속 별표4 정액이다(§26①1 정액법 + 시행규칙 [별표 4] 상각률).
# 끝수·월할·종료해·비망 1,000원은 정액법 골격을 그대로 따른다(연 상각액 산식만 다르다).
DEVELOPMENT_COST_MAX_LIFE = 20


def development_cost_annual(cost: int, life_years: int) -> int:
    """개발비 연 상각액 = 4사5입(취득가액 ÷ 신고내용연수), 정수 산술."""
    if isinstance(life_years, bool) or not isinstance(life_years, int) \
            or not 1 <= life_years <= DEVELOPMENT_COST_MAX_LIFE:
        raise ValueError(f"개발비 내용연수는 1~{DEVELOPMENT_COST_MAX_LIFE}년입니다 "
                         f"(시행령 §26①6, life_years={life_years!r})")
    return (2 * cost + life_years) // (2 * life_years)


def dev_monthly(cost: int, life_years: int, acq_month: int) -> List[Month]:
    """개발비 표준형 월별 — 정액 골격에 연 상각액만 1/n."""
    annual = development_cost_annual(cost, life_years)
    return monthly.standard_monthly(cost, life_years, acq_month,
                                    lambda book, miy: (annual * miy) // 12)


def schedule_development_cost(cost: int, life_years: int, acq_year: int, acq_month: int,
                              fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """개발비 회계연도별 상각표 (임의 결산월)."""
    validate_asset_inputs(cost, acq_month, fiscal_end_month)
    m_std = standard_acq_month(fiscal_end_month, acq_month)
    months = monthly.settle_terminal_evenly(dev_monthly(cost, life_years, m_std))
    return monthly.group(months, first_fiscal_year(acq_year, acq_month, fiscal_end_month))


def schedule_full_disposal_development_cost(cost: int, life_years: int, acq_year: int,
                                            acq_month: int, disp_year: int, disp_month: int,
                                            fiscal_end_month: int = 12) -> List[FiscalYearRow]:
    """개발비 전체양도(폐기) — 양도월까지 상각(더존식)."""
    return disposal._schedule_full_disposal(dev_monthly, cost, life_years, acq_year, acq_month,
                                            disp_year, disp_month, fiscal_end_month)
