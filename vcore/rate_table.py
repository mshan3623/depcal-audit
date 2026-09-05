"""
dep_vector — 법인세법 시행령 [별표 4] 감가상각자산의 상각률표 (제15조제2항 관련)
================================================================================

**이 모듈이 상각률표의 정본이다.** 정액법·정률법의 구분보다 이 표가 계산의 본질이고
(계산 뼈대는 동일하고 표 엔트리만 다르다), 따라서 표를 방법 모듈 밖 한 곳에 둔다.

표기: 법 원문은 "할·분·리" 즉 **1000분율 정수**로 고시한다(내용연수 5년 → 정액 200,
정률 451). 여기서도 정수로 전사하고 float은 `/1000`으로 유도한다 — 소수 리터럴을 손으로
옮기다 생기는 전사 오류를 없애기 위함이며, 유도값은 `core/dep_common.py`의 float 리터럴과
**비트 단위로 동일**하다(테스트가 고정).

독립 증인 2벌: `core/dep_common.py`도 같은 표를 자체 리터럴로 들고 있다. 오라클이 검증
대상과 데이터를 공유하면 오라클이 아니므로 일부러 합치지 않는다. 대신
`tests_vector/test_rate_table_statutory.py`가 **법령 PDF ↔ vcore ↔ core** 3자를 매 실행
대조한다 — 어느 한 벌에 오타가 들어가면 즉시 깨진다.

출처: legal/정률법정액법상각률.pdf (법제처 원문). 세법 개정 시 이 표와 core의 표를
**둘 다** 갱신해야 한다 — 한쪽만 고치면 3자 대조가 막는다.

**계산도 이 표의 정수로 한다 (2026-09-03).** float 상각률(`s/1000`)을 곱하면 0.284·0.142·
0.071처럼 이진 표현이 참값보다 작은 연수에서 정확한 정수 결과가 x.999…로, 정확히 x.5가
x.4999…로 나와 절사·4사5입이 1원을 내린다(실무 금액대에서 정률 9·41년 71%, 정액 7·14년
71% 발화 — docs/audit_lattice_2026-09-03.md G1·G2). 그래서 연 상각액 산식은
`straight_line_annual`·`declining_balance_amount` 두 정수 함수에만 있고, 정액·정률·월별·
분리자산 경로가 전부 이 둘을 부른다. float 표(`STRAIGHT_LINE_RATES` 등)는 3자 대조와
표시용으로만 남는다.
"""

from typing import Dict, Tuple

# 내용연수 → (정액법 상각률, 정률법 상각률), 단위 1000분율 정수 (법 원문 "할분리" 표기)
STATUTORY_PERMILLE: Dict[int, Tuple[int, int]] = {
     2: (500, 777),
     3: (333, 632),
     4: (250, 528),
     5: (200, 451),
     6: (166, 394),
     7: (142, 349),
     8: (125, 313),
     9: (111, 284),
    10: (100, 259),
    11: ( 90, 239),
    12: ( 83, 221),
    13: ( 76, 206),
    14: ( 71, 193),
    15: ( 66, 182),
    16: ( 62, 171),
    17: ( 58, 162),
    18: ( 55, 154),
    19: ( 52, 146),
    20: ( 50, 140),
    21: ( 48, 133),
    22: ( 46, 128),
    23: ( 44, 123),
    24: ( 42, 118),
    25: ( 40, 113),
    26: ( 39, 109),
    27: ( 37, 106),
    28: ( 36, 102),
    29: ( 35,  99),
    30: ( 34,  96),
    31: ( 33,  93),
    32: ( 32,  90),
    33: ( 31,  87),
    34: ( 30,  85),
    35: ( 29,  83),
    36: ( 28,  80),
    37: ( 27,  78),
    38: ( 27,  76),
    39: ( 26,  74),
    40: ( 25,  73),
    41: ( 25,  71),
    42: ( 24,  69),
    43: ( 24,  68),
    44: ( 23,  66),
    45: ( 23,  65),
    46: ( 22,  64),
    47: ( 22,  62),
    48: ( 21,  61),
    49: ( 21,  60),
    50: ( 20,  59),
    51: ( 20,  58),
    52: ( 20,  56),
    53: ( 19,  55),
    54: ( 19,  54),
    55: ( 19,  54),
    56: ( 18,  53),
    57: ( 18,  52),
    58: ( 18,  51),
    59: ( 17,  50),
    60: ( 17,  49),
}

#: 내용연수 → 정액법 상각률 (법인세법 시행령 [별표 4])
STRAIGHT_LINE_RATES: Dict[int, float] = {n: s / 1000 for n, (s, _) in STATUTORY_PERMILLE.items()}

#: 내용연수 → 정률법 상각률 (법인세법 시행령 [별표 4])
DECLINING_BALANCE_RATES: Dict[int, float] = {n: d / 1000 for n, (_, d) in STATUTORY_PERMILLE.items()}

#: 표가 수록한 내용연수 범위 (2~60년).
LIFE_YEARS_RANGE = (min(STATUTORY_PERMILLE), max(STATUTORY_PERMILLE))


def check_life_years(life_years: int) -> None:
    """내용연수 범위 가드의 단일 관문 — 표 밖 내용연수는 명시 실패한다.

    표가 2~60년을 빠짐없이 수록하므로 "가장 가까운 작은 연수로 폴백" 같은 분기는
    이 구간에서 죽은 코드였고, 살아 있는 효과는 **범위 밖 입력의 조용한 클램프**뿐이었다
    (life=100 → 60년율로 예외 없이 그럴듯한 표 산출). 도메인 밖은 막는다 (2026-07-25).

    가드가 표 옆에 있는 이유: 정액·정률 두 모듈이 각자 같은 검사를 재구현하면 한쪽만
    고쳐질 수 있다. 범위의 진실원은 표이므로 검사도 표와 함께 둔다 (2026-08-22).
    """
    if life_years not in STATUTORY_PERMILLE:
        lo, hi = LIFE_YEARS_RANGE
        raise ValueError(
            f"내용연수는 별표4 상각률표 범위({lo}~{hi}년)여야 합니다 (life_years={life_years})")


def _lookup(table: Dict[int, float], life_years: int, method: str) -> float:
    check_life_years(life_years)
    return table[life_years]


def straight_line_rate(life_years: int) -> float:
    """법인세법 [별표 4] 정액법 상각률 (float — 표시·대조용. 계산은 straight_line_annual)."""
    return _lookup(STRAIGHT_LINE_RATES, life_years, "정액법")


def declining_rate(life_years: int) -> float:
    """법인세법 [별표 4] 정률법 상각률 (float — 표시·대조용. 계산은 declining_balance_amount)."""
    return _lookup(DECLINING_BALANCE_RATES, life_years, "정률법")


# ── 정수 산술 관문 — 연 상각액 산식은 아래 두 함수에만 있다 ──────────────────

def straight_line_annual(cost: int, life_years: int) -> int:
    """정액법 연 상각액 = 4사5입(취득원가 × 별표4 정액률), 정수 산술.

    `(cost × s + 500) // 1000` — s는 1000분율 정수. float `round_half_up(cost × s/1000)`은
    정확히 x.5인 곱(10,000,500 × 14년 = 710,035.5)을 x.4999…로 만들어 710,035로 내렸다
    (2026-09-03 감사 G2). 정액·월별(sl_monthly)·분리자산 세 경로가 전부 이 함수를 부른다.
    """
    check_life_years(life_years)
    s, _ = STATUTORY_PERMILLE[life_years]
    return (cost * s + 500) // 1000


def declining_balance_amount(book: int, life_years: int, months: int) -> int:
    """정률법 상각액 = 절사(기초장부가 × 별표4 정률 × 개월수 / 12), 정수 산술.

    `book × d × months // 12000` — d는 1000분율 정수. float `int(book × d/1000 × months // 12)`는
    정확한 정수 결과(10,000,000 × 9년 = 2,840,000)를 2,839,999.99…로 만들어 1원 내렸다
    (2026-09-03 감사 G1 — 실무 금액대 표본에서 9·41년 71%, 7년 25% 발화). 절사 규칙(B사 더존
    실측)은 그대로이고 float만 제거한다. 연도별·월별(db_monthly)·분리자산 세 경로가 전부
    이 함수를 부른다.
    """
    check_life_years(life_years)
    _, d = STATUTORY_PERMILLE[life_years]
    return book * d * months // 12000
