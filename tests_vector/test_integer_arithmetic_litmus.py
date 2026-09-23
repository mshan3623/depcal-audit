"""정수 산술 리트머스 — float 상각률 곱셈이 원단위를 조용히 떨어뜨리던 결함의 회귀 가드.

배경(docs/audit_lattice_2026-09-03.md G1·G2): 별표4 상각률은 1000분율 정수인데 계산은
`cost × (s/1000)` float로 했다. 0.284·0.142·0.071 같은 값은 이진 표현이 참값보다 작아
  - 정률: 정확한 정수 결과(10,000,000 × 0.284 = 2,840,000)가 2,839,999.99…로 나와 `//`가 내리고,
  - 정액: 정확히 x.5(10,000,500 × 0.071 = 710,035.5)가 x.4999…로 나와 4사5입이 내린다.
실무 금액대(100만~10억) 표본에서 정률 9·41년 71%, 정액 7·14년 71%가 1원 하향이었다. 더존
실측 105건·손계산 골든이 전부 5·6년(float가 정확한 연수)이라 어느 채널도 못 잡았고, core는
같은 float 산식이라 거울도 눈이 멀어 있었다. 2026-07-25 D8의 "10¹¹부터·실무 영향 없음"은
스캔 범위 부족으로 오판이었다.

오라클 = `rate_table.STATUTORY_PERMILLE` 정수만 쓰는 순수 정수 산술(float 개입 0):
    정액 연상각          = (cost × s + 500) // 1000     (4사5입)
    정률 연(월수 안분)상각 = book × d × months // 12000   (절사)
이 파일은 (1) 감사에서 실측한 핀 케이스, (2) 연수 2~60 전수 × 취득원가 표본의 오라클 대조,
(3) 월별·분리자산 경로가 같은 산식을 쓰는지, (4) core 오라클 동반 수정의 거울 일치를 고정한다.
수정 전 코드에서 (1)·(2)가 실제로 실패함을 확인하고 봉인했다(공허 테스트 아님).
"""
import pytest

from vcore import declining_balance, monthly, separate_asset, straight_line
from vcore.monthly_schedule import monthly_events
from vcore.rate_table import LIFE_YEARS_RANGE, STATUTORY_PERMILLE

from core.dep_common import AssetFinancials, AssetInfo, DepreciationMethod
from core.depreciation_engine import calculate_depreciation_enhanced

LIVES = range(LIFE_YEARS_RANGE[0], LIFE_YEARS_RANGE[1] + 1)


def _sl_exact(cost: int, life: int) -> int:
    s, _ = STATUTORY_PERMILLE[life]
    return (cost * s + 500) // 1000


def _db_exact(book: int, life: int, months: int) -> int:
    _, d = STATUTORY_PERMILLE[life]
    return book * d * months // 12000


# ── (1) 핀 케이스 — 감사 실측값 ─────────────────────────────────────────────
# (취득원가, 내용연수, 첫해(1월 취득·12개월) 상각액). 수정 전 float 값은 각각 1원 작았다.
SL_PINS = [
    (3_000_250, 7, 426_036),      # 3,000,250 × 0.142 = 426,035.5  → float 426,035
    (10_000_500, 14, 710_036),    # 10,000,500 × 0.071 = 710,035.5 → float 710,035
    (3_000_125, 28, 108_005),     # 3,000,125 × 0.036 = 108,004.5  → float 108,004
    (23_000_250, 46, 506_006),    # 23,000,250 × 0.022 = 506,005.5 → float 506,005
]
DB_PINS = [
    (10_000_000, 9, 2_840_000),   # 10,000,000 × 0.284 = 2,840,000 → float 2,839,999
    (3_000_000, 7, 1_047_000),    # 3,000,000 × 0.349 = 1,047,000  → float 1,046,999
    (1_333_000, 41, 94_643),      # 1,333,000 × 0.071 = 94,643     → float 94,642
    (5_000_000, 28, 510_000),     # 5,000,000 × 0.102 = 510,000    → float 509,999
]


@pytest.mark.parametrize("cost,life,expected", SL_PINS)
def test_straight_line_rounds_half_up_at_exact_half(cost, life, expected):
    assert (cost * STATUTORY_PERMILLE[life][0]) % 1000 == 500        # 정확히 x.5 성립
    assert straight_line.schedule(cost, life, 2026, 1)[0].depreciation == expected


@pytest.mark.parametrize("cost,life,expected", DB_PINS)
def test_declining_keeps_exact_integer_result(cost, life, expected):
    assert (cost * STATUTORY_PERMILLE[life][1]) % 1000 == 0          # 정확한 정수 결과 성립
    assert declining_balance.schedule(cost, life, 2026, 1)[0].depreciation == expected


# ── (2) 연수 2~60 전수 × 취득원가 표본 — 순수 정수 오라클 대조 ──────────────
def _half_boundary_costs(life: int):
    """cost × s ≡ 500 (mod 1000)인 취득원가(4사5입 경계) — 100만~10억 표본. 경계가 없는 연수는 []."""
    s, _ = STATUTORY_PERMILLE[life]
    residues = [c for c in range(1000) if (c * s) % 1000 == 500]
    return [base + r for base in range(1_000_000, 1_000_000_000, 37_000_000) for r in residues]


@pytest.mark.parametrize("life", LIVES)
def test_straight_line_annual_matches_integer_oracle(life):
    """정액 연상각: 4사5입 경계 + 1000원 단위 일반 표본 전부 정수 오라클과 일치."""
    costs = _half_boundary_costs(life) + list(range(1_000_000, 1_000_000_000, 11_111_000))
    for cost in costs:
        assert straight_line.annual_depreciation(cost, life) == _sl_exact(cost, life), \
            f"정액 cost={cost:,} life={life}"


@pytest.mark.parametrize("life", LIVES)
@pytest.mark.parametrize("acq_month", [1, 6, 12])
def test_declining_first_year_matches_integer_oracle(life, acq_month):
    """정률 첫해(12·7·1개월): 1000원 단위 표본 전부 정수 오라클(절사)과 일치."""
    months = 13 - acq_month
    for cost in range(1_000_000, 1_000_000_000, 7_919_000):
        got = declining_balance.schedule(cost, life, 2026, acq_month)[0].depreciation
        assert got == min(_db_exact(cost, life, months), cost - 1000), \
            f"정률 cost={cost:,} life={life} months={months}"


# ── (3) 월별·분리자산 경로가 같은 산식을 쓰는가 ────────────────────────────
@pytest.mark.parametrize("cost,life,expected", SL_PINS)
def test_straight_line_monthly_and_separate_paths_agree(cost, life, expected):
    assert sum(m.amount for m in monthly.sl_monthly(cost, life, 1)[:12]) == expected
    assert separate_asset.schedule_separate_asset(cost, life, 2026, 1, 0, 2026)[0].depreciation == expected


@pytest.mark.parametrize("cost,life,expected", DB_PINS)
def test_declining_monthly_and_separate_paths_agree(cost, life, expected):
    assert sum(m.amount for m in monthly.db_monthly(cost, life, 1)[:12]) == expected
    assert separate_asset.schedule_separate_asset(cost, life, 2026, 1, 0, 2026,
                                                  declining=True)[0].depreciation == expected


# ── (4) core 오라클 동반 수정 — 거울 일치(해당 연수) ────────────────────────
_INFO = AssetInfo(asset_id="A", asset_name="자산", asset_category="비품")


def _core_monthly(cost, life, menum, start):
    fin = AssetFinancials(cost=cost, life_in_years=life, start_date=start, method=menum)
    r = calculate_depreciation_enhanced(fin, _INFO, fiscal_year_end_month=12)
    return [(m.year, m.month, m.numeric_depreciation, m.accumulated_depreciation, m.book_value)
            for m in r.schedule]


def _yearly_totals(rows):
    out = {}
    for year, _month, dep, _acc, _book in rows:
        out[year] = out.get(year, 0) + dep
    return out


@pytest.mark.parametrize("cost,life,expected", SL_PINS + DB_PINS)
@pytest.mark.parametrize("acq_month", [1, 4])
def test_core_mirror_agrees_on_affected_lives(cost, life, expected, acq_month):
    """core도 같은 정수 산술로 고쳤다(FREEZE 예외 사유 2번, P2·A-1 선례). 거울이 갈리면 한쪽만 고친 것.

    종료해 월배분도 함께 고정한다(G28): 정액 7·14년처럼 별표4율 × n < 1인 연수(0.142 × 7
    = 0.994)는 종료해에 6‰ 잔재가 남는데, core는 이를 12월에 몰아넣고 vcore는 균등 배분해
    갈려 있었다. 2026-09-03에 core 단순 경로에도 균등 재배분을 적용해(2026-06-13 "정액·정률
    동일 원칙"의 정액 미적용분 완결) 72개월 전체가 1원까지 일치한다.
    """
    declining = (cost, life, expected) in DB_PINS
    menum = DepreciationMethod.DECLINING_BALANCE if declining else DepreciationMethod.STRAIGHT_LINE
    core = _core_monthly(cost, life, menum, f"2026-{acq_month:02d}-15")
    got = [(m.year, m.month, m.amount, m.acc, m.book)
           for m in monthly_events(cost, life, 2026, acq_month, 12, declining)]
    assert got == core                                       # 월별 전 구간 완전 일치
    assert _yearly_totals(got) == _yearly_totals(core)
    assert got[-1][3:] == core[-1][3:]                       # 종료월 누계·장부가(비망 1,000)
    assert _yearly_totals(got)[2026] == (expected if acq_month == 1 else
                                         min(_db_exact(cost, life, 13 - acq_month), cost - 1000)
                                         if declining else (expected * (13 - acq_month)) // 12)


@pytest.mark.parametrize("cost,life,expected", DB_PINS)
def test_core_separate_asset_mirror_agrees_on_affected_lives(cost, life, expected):
    """core 정률 분리자산 산식(dep_tang_engine 분리자산 분기)도 동반 수정 — 2차연도 prior로 대조."""
    prior = expected                                           # 첫해(12개월) 누계
    v = [(r.fiscal_year, r.months, r.depreciation, r.accumulated, r.book_value)
         for r in separate_asset.schedule_separate_asset(cost, life, 2026, 1, prior, 2027, 12, True)]
    r = calculate_depreciation_enhanced(
        AssetFinancials(cost=cost, life_in_years=life, start_date="2026-01-15",
                        method=DepreciationMethod.DECLINING_BALANCE,
                        prior_accumulated=prior, target_year=2027),
        _INFO, fiscal_year_end_month=12)
    c = [(s.year, s.months_count, s.yearly_depreciation,
          s.accumulated_depreciation, s.ending_book_value) for s in r.yearly_summary]
    assert v == c
    assert v[0][2] == min(_db_exact(cost - prior, life, 12), cost - prior - 1000)


# ── (5) 부분양도 잔존비율 — 비율 산술도 정수로 (감사 2026-09-23 A2, INC-13) ──────
# `remaining_ratio = 1.0 - D/cost`가 float라, 양도 후 연 목표 `int(base연합 × ratio)`가
# 정확한 정수 결과를 1원 내렸다. 55% 양도면 2,000,000 × 0.45 = 900,000이 899,999가 됐다.
# 5년 자산에서도 발화한다 — 상각률 정수 관문(INC-04)은 **상각률**에만 섰고 비율은 밖에 있었다.
# 오라클: 양도 이후 온전한 회계연도의 상각 = base연상각 × (cost − D) // cost (float 개입 0).
from vcore import disposal  # noqa: E402

PARTIAL_PINS = [
    # (취득원가, 연수, 양도액, 정률여부, FY, 기대 상각) — 수정 전 값은 각각 1원 작았다
    (10_000_000, 5, 5_500_000, False, 2021, 900_000),     # float 899,999
    (10_000_000, 5, 8_000_000, False, 2021, 400_000),     # float 399,999
    (10_000_000, 5, 8_000_000, True, 2021, 495_198),      # 2,475,990 × 0.2 → float 495,197
]


def _partial(cost, life, amount, declining, disp_month=6):
    fn = (disposal.schedule_partial_disposal_declining if declining
          else disposal.schedule_partial_disposal)
    return fn(cost, life, 2020, 1, amount, 2020, disp_month)


def _base(cost, life, declining):
    return (declining_balance.schedule if declining else straight_line.schedule)(cost, life, 2020, 1)


@pytest.mark.parametrize("cost,life,amount,declining,fy,expected", PARTIAL_PINS)
def test_partial_disposal_keeps_exact_integer_result(cost, life, amount, declining, fy, expected):
    row = next(r for r in _partial(cost, life, amount, declining) if r.fiscal_year == fy)
    assert row.depreciation == expected


@pytest.mark.parametrize("declining", [False, True])
@pytest.mark.parametrize("life", [3, 5, 7, 9, 10, 14, 20])
def test_partial_disposal_full_years_match_integer_oracle(life, declining):
    """퍼센트 양도(1~99%) × 원가 표본에서 양도 이후 온전한 회계연도를 정수 오라클과 대조."""
    bad = []
    for cost in (1_000_000, 3_000_000, 10_000_000, 12_345_000, 250_000_000):
        base = {r.fiscal_year: r.depreciation for r in _base(cost, life, declining)}
        for pct in range(1, 100):
            amount = cost * pct // 100
            rows = _partial(cost, life, amount, declining)
            for r in rows[1:-1]:                     # 양도연도·종료해 제외 = 온전한 연도
                want = base[r.fiscal_year] * (cost - amount) // cost
                if r.depreciation != want:
                    bad.append((cost, pct, r.fiscal_year, r.depreciation, want))
    assert not bad, f"{len(bad)}건 불일치, 예: {bad[:5]}"


@pytest.mark.parametrize("cost,life,amount,declining,fy,expected", PARTIAL_PINS)
def test_partial_disposal_monthly_events_path_agrees(cost, life, amount, declining, fy, expected):
    """운영 경로(monthly_events)도 같은 관문을 지난다."""
    months = monthly_events(cost, life, 2020, 1, declining=declining, disp=(amount, 2020, 6))
    assert sum(m.amount for m in months if m.year == fy) == expected
