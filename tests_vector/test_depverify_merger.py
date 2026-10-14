"""depverify 합병 승계자산 판정 — `--merger-registration YYYY-MM --merger-prefix 접두` (INC-23).

종전엔 승계자산도 대장에 적힌 월수(12)를 그대로 믿어, 등기월 다음 달부터 상각해야 할 자산의
1~2월 이중상각을 '일치'로 판정했다(표본 법인 2026 대장 5건). 대장만으로는 승계자산이 존속법인
자산과 구별되지 않으므로(둘 다 이월자산 모양, '변동' 칸 공란) 사용자가 등기월과 자산명 접두를
지정한다(사용자 결정 2026-10-14) — 도구가 추측하지 않는다.

합병연도 기대값: 전기말누계(소멸법인의 직전 사업연도 말) + 소멸법인 최종 의제사업연도분
(1월~등기월, §26⑧ 짧은 사업연도 — `schedule_extinction`) = 등기월 말 승계 누계. 존속법인은
등기월 다음 달부터 상각한다(`schedule_merger_succession`, 사용자 결정 2026-08-27).
"""
import pytest

from depverify.__main__ import main
from depverify.reader import read_ledger, tag_merger_succession
from depverify.verdict import verify_asset

from tests_vector.test_depverify_completeness import _asset_row, _write

PREFIX = "(소멸법인)"

# 손계산 골든 — 정률 5년(451‰), 12,035,000원, 2025-06 취득, 2026-02 합병등기
#   FY2025(7개월) 누계 = 12,035,000 × 451 × 7 // 12000            = 3,166,207 (대장 전기말누계)
#   소멸 최종기(1~2월) = 8,868,793 × 451 × 2 // 12000              =   666,637
#   등기월 말 승계 누계 = 3,832,844 → 장부 8,202,156
#   존속(3~12월, 10개월) = 8,202,156 × 451 × 10 // 12000           = 3,082,643
#   당기말 누계 = 6,915,487, 장부 = 5,119,513
COST, PREV = 12_035_000, 3_166_207
SUCC_DEP, SUCC_ACC, SUCC_BK = 3_082_643, 6_915_487, 5_119_513
TWELVE = 8_868_793 * 451 // 1000                       # 대장이 적은 12개월치 3,999,825


def _row(name, dep, acc, bk, **over):
    return _asset_row(name, COST, PREV, dep, acc, bk, 취득일자="2025-06-12", 상감법="정률법",
                      **over)


def _assets(tmp_path, rows, fy=2026):
    assets, unreadable, _, _ = read_ledger(_write(tmp_path, rows), fy)
    return assets


def test_succession_golden_matches_when_ledger_starts_month_after_registration(tmp_path):
    assets = _assets(tmp_path, [_row(PREFIX + "서버", SUCC_DEP, SUCC_ACC, SUCC_BK)])
    assert tag_merger_succession(assets, PREFIX, 2026, 2) == 1
    v = verify_asset(assets[0])
    assert v.status == "일치", v


def test_twelve_month_ledger_is_a_difference_once_registration_is_given(tmp_path):
    """표본 대장의 실제 모양 — 승계자산을 12개월 상각(1~2월 이중상각)."""
    rows = [_row(PREFIX + "서버", TWELVE, PREV + TWELVE, COST - PREV - TWELVE)]
    assets = _assets(tmp_path, rows)
    assert verify_asset(assets[0]).status == "일치"            # 등기월을 모르면 못 잡는다(종전)
    tag_merger_succession(assets, PREFIX, 2026, 2)
    v = verify_asset(assets[0])
    assert v.status == "차이" and v.d_dep == SUCC_DEP - TWELVE


def test_only_prefixed_assets_are_tagged(tmp_path):
    rows = [_row(PREFIX + "서버", SUCC_DEP, SUCC_ACC, SUCC_BK),
            _row("자체자산", TWELVE, PREV + TWELVE, COST - PREV - TWELVE)]
    assets = _assets(tmp_path, rows)
    assert tag_merger_succession(assets, PREFIX, 2026, 2) == 1
    assert [verify_asset(a).status for a in assets] == ["일치", "일치"]


def test_year_after_merger_continues_from_ledger_prior(tmp_path):
    """합병 다음 해 — 전기말누계(존속법인 장부)에서 12개월. 소멸 최종기 가산은 합병연도만."""
    prev = SUCC_ACC
    dep = (COST - prev) * 451 // 1000
    rows = [_asset_row(PREFIX + "서버", COST, prev, dep, prev + dep, COST - prev - dep,
                       취득일자="2025-06-12", 상감법="정률법")]
    assets = _assets(tmp_path, rows, fy=2027)
    tag_merger_succession(assets, PREFIX, 2026, 2)
    assert verify_asset(assets[0]).status == "일치"


def test_disposed_succeeded_asset_is_unverifiable(tmp_path):
    rows = [_row(PREFIX + "서버", 0, 0, 0, 구분="양도자산", **{"양도/폐기일": "2026-08-31"})]
    assets = _assets(tmp_path, rows)
    tag_merger_succession(assets, PREFIX, 2026, 2)
    assert verify_asset(assets[0]).status == "검증불능"


# ── CLI ───────────────────────────────────────────────────────────────────

def test_cli_flags_twelve_month_succession_as_difference(tmp_path):
    path = _write(tmp_path, [_row(PREFIX + "서버", TWELVE, PREV + TWELVE, COST - PREV - TWELVE)])
    out = str(tmp_path / "r.xlsx")
    assert main([path, "--fy", "2026", "--out", out]) == 0
    assert main([path, "--fy", "2026", "--out", out,
                 "--merger-registration", "2026-02", "--merger-prefix", PREFIX]) == 1


@pytest.mark.parametrize("args", [["--merger-registration", "2026-02"],
                                  ["--merger-prefix", PREFIX],
                                  ["--merger-registration", "2026-13", "--merger-prefix", PREFIX]])
def test_cli_merger_options_must_come_together_and_be_valid(tmp_path, args):
    path = _write(tmp_path, [_row(PREFIX + "서버", SUCC_DEP, SUCC_ACC, SUCC_BK)])
    with pytest.raises(SystemExit) as e:
        main([path, "--fy", "2026", "--out", str(tmp_path / "r.xlsx"), *args])
    assert e.value.code == 2


def test_cli_prefix_matching_nothing_stops(tmp_path):
    """접두가 아무 행에도 안 맞으면 오타일 수 있다 — 조용히 무시하지 않고 멈춘다."""
    path = _write(tmp_path, [_row("자체자산", TWELVE, PREV + TWELVE, COST - PREV - TWELVE)])
    assert main([path, "--fy", "2026", "--out", str(tmp_path / "r.xlsx"),
                 "--merger-registration", "2026-02", "--merger-prefix", PREFIX]) == 2
