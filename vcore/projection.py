"""
dep_vector — vector projection 공유 골격
=========================================

정액법·정률법이 공유하는 좌표 변환 machinery.

설계: 정확성은 12월 결산 '표준형 벡터' 하나에만 존재하고(각 방법 모듈의
standard_vector), 임의 결산월은 (취득월 환산 + 연도 라벨 재부착)으로 프로젝션한다.
shift 불변성(정액·정률 실증 완료)이 이 분리를 정당화한다.
"""

import math
from dataclasses import dataclass
from typing import Callable, List

# 비망가액 — 고정 1,000원 (레퍼런스 core와 동일값). **비망기록은 1천원으로 고정한다.**
#
# 법령 문언(시행령 제26조⑦)은 min(취득가액 × 5%, 1,000원)이라 취득원가 20,000원 미만
# 구간에서는 법정 비망가가 1,000원보다 작다(5,000원 → 250원). 그럼에도 고정값을 쓰는
# 근거는 **그 구간의 자산이 애초에 이 엔진에 도달하지 않는다**는 것이다 (즉시상각의 의제,
# 시행령 제31조 — 2026-08-22 법령 원문 대조 확인):
#
#   ④ 거래단위별 취득가액 100만원 이하 감가상각자산은 사용한 날이 속하는 사업연도에
#     손비계상하면 전액 손금. → 자산계상되는 자산은 100만원 초과이고,
#     100만원 × 5% = 50,000원 > 1,000원이므로 전부 min(…)=1,000원 구간이다.
#   ⑥4호 전화기(휴대용 포함)·개인용 컴퓨터(주변기기 포함)는 "④에도 불구하고"
#     **금액 한도 없이** 사용연도 손비계상분 전액 손금. 같은 항 2호(공구·가구·전기기구·
#     가스기기·가정용 기구/비품·시계·시험기기·측정기기·간판)도 금액 제한이 없다.
#     → 수백만원대 IT 장비가 대장에 오르지 않고 당기 비용으로 빠지는 실무의 근거.
#
# 나아가 제31조⑦(생산설비 일부 폐기·임차사업장 원상회복 철거)은 금액 조건 없이
# "장부가액에서 1천원을 공제한 금액"을 손금으로 규정한다 — 법령이 비망 1,000원을
# 고정 상수로 쓰는 자리다.
#
# 결론: 20,000원 미만 구간의 이탈은 **엔진 밖 입력**이며 결함이 아니다(션 결정 2026-08-22).
# min(cost * 0.05, 1000) 승격은 자산계상 하한 관행이 깨지는 대장이 실제로 나올 때만 검토한다.
MEMORANDUM = 1000


def capped_yearly(book: int, months: int,
                  yearly_fn: Callable[[int, int], int]) -> int:
    """평소년(종료해 아닌 해) 연 상각액 — 비망가 캡의 단일 관문.

    정액·정률·월별 3경로가 각각 재구현하던 "연 상각액 산출 + 비망가 한도 캡"을 하나로
    모은다. 방법 차이는 yearly_fn(기초장부가, 개월수)으로만 주입된다.

    캡 규칙: 상각 후 장부가는 비망가액 아래로 내려갈 수 없다. 이미 비망가에 도달했으면
    (remaining ≤ 0) 추가 상각은 0이다 — 과거 `if 0 < remaining < yearly` 조건은 이
    경우 캡을 통째로 건너뛰어 계속 상각했고, 그 초과분이 종료해에 음수 상각으로
    되돌아왔다(2026-07-25 발견, 소액 취득원가에서만 발화).
    """
    remaining = book - MEMORANDUM
    if remaining <= 0:
        return 0
    return min(yearly_fn(book, months), remaining)


def round_half_up(x: float) -> int:
    """상용 4사5입(x.5 → 항상 올림). 내장 round()는 banker's rounding(x.5 → 짝수)이라
    원단위 처리 사이트(연 상각액·양도 누계 분배)에서 명시적으로 이 함수를 대신 쓴다."""
    return math.floor(x + 0.5)


@dataclass
class FiscalYearRow:
    """회계연도 1줄. 표준형에선 fiscal_year=상대인덱스(0,1,…), 프로젝션 후엔 실제 연도."""
    fiscal_year: int
    months: int               # 당기 감가상각 발생 개월수
    depreciation: int         # 당기 감가상각비
    accumulated: int          # 당기말 감가상각누계액
    book_value: int           # 당기말 장부가액


def standard_month_counts(acq_month: int, life_years: int) -> List[int]:
    """12월 결산 표준형의 회계연도별 자산활성 개월수. 첫해=13-취득월, 이후 12, 마지막=나머지."""
    total = life_years * 12
    first = 13 - acq_month
    counts = [first]
    rem = total - first
    while rem >= 12:
        counts.append(12)
        rem -= 12
    if rem > 0:
        counts.append(rem)
    return counts                     # sum == total


def standard_acq_month(fiscal_end_month: int, acq_month: int) -> int:
    """임의 (결산월 F, 취득월 M)을 12월 결산 표준형의 등가 취득월로 환산.

    불변량 = '취득월과 결산일 사이의 거리'. 같으면 결산월이 달라도 동일 벡터.
    """
    return 12 - ((fiscal_end_month - acq_month) % 12)


def first_fiscal_year(acq_year: int, acq_month: int, fiscal_end_month: int) -> int:
    """취득시점이 속한 첫 회계연도(결산일 기준 연도, 한국 관행)."""
    return acq_year if acq_month <= fiscal_end_month else acq_year + 1


def validate_asset_inputs(cost: int, acq_month: int, fiscal_end_month: int) -> None:
    """vcore 공개 진입점 공통 입력 가드.

    core 경계(depreciation_engine)를 거치지 않는 직접 호출 경로에서 도메인 밖 입력이
    예외 대신 '그럴듯한 오답 표'로 흘러나오는 것을 막는다(내용연수는 상각률 조회
    rate_table의 상각률 조회에서 검증 — 단일 관문).
    """
    # 타입을 먼저 본다. 종전에는 값 범위만 봐서 `cost=12_000_000.5`가 그대로 흘러
    # 장부가액 9,600,000.5 같은 소수 금액이 나왔다(감사 G21) — 원 단위 대조 도구에서
    # 소수 금액은 그 자체로 오답이다. bool은 int의 하위형이라 따로 막는다.
    for name, value in (("cost", cost), ("acq_month", acq_month),
                        ("fiscal_end_month", fiscal_end_month)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name}는 정수여야 합니다 ({name}={value!r}, {type(value).__name__})")
    if cost <= MEMORANDUM:
        # 비망가액 이하 자산은 상각할 금액 자체가 없다(취득원가 − 비망가 ≤ 0). 미가드 시
        # 캡 경로가 전부 0을 내다가 종료해에 음수 상각으로 마감된다.
        raise ValueError(
            f"취득원가는 비망가액({MEMORANDUM})을 초과해야 합니다 (cost={cost})")
    if not 1 <= acq_month <= 12:
        raise ValueError(f"취득월은 1~12여야 합니다 (acq_month={acq_month})")
    if not 1 <= fiscal_end_month <= 12:
        raise ValueError(f"결산월은 1~12여야 합니다 (fiscal_end_month={fiscal_end_month})")


def project(standard_vector: List[FiscalYearRow], acq_year: int,
            acq_month: int, fiscal_end_month: int) -> List[FiscalYearRow]:
    """표준형 벡터(상대 인덱스)에 실제 회계연도 라벨만 재부착."""
    fy0 = first_fiscal_year(acq_year, acq_month, fiscal_end_month)
    return [FiscalYearRow(fy0 + r.fiscal_year, r.months, r.depreciation,
                          r.accumulated, r.book_value) for r in standard_vector]
