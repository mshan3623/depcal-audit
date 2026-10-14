"""감사 2026-10-14 T2 — depverify가 exit 0으로 새던 경로를 fail-closed로 (INC-21·M2·M3).

완전성 게이트는 '합계행을 못 찾음 = 대사 불가 = exit 0' 정책이라, 합계행을 **찾았는데 못 읽은** 것과
**정말 없는** 것이 구별되지 않으면 게이트가 조용히 꺼진다. 더존 총계행은 합이 0인 열을 `''`로 쓴다
(실대장 3개 실측) — 상각완료 자산만 남은 대장에서 행을 지워도 exit 0이었다.
"""
import openpyxl
import pytest

from depverify.__main__ import main
from depverify.reader import read_ledger
from depverify.verdict import verify_asset

from tests_vector.test_depverify_completeness import _COLUMNS, _asset_row, _total_row, _write


def _done(name):
    """상각완료 자산 — 당기상각 0 (5년, 2018 취득, 비망가 1,000)."""
    return _asset_row(name, 5_000_000, 4_999_000, 0, 4_999_000, 1_000, 취득일자="2018-01-01")


# ── M1 / INC-21: 합계행의 0원 칸 `''` ──────────────────────────────────────

def test_blank_zero_cell_in_grand_total_is_read_as_zero(tmp_path):
    rows = [_done("자산A"), _done("자산B"), _total_row("계정과목총계", "", "9,998,000", "2,000")]
    _, _, _, control = read_ledger(_write(tmp_path, rows), 2025)
    assert control.found and control.matched


def test_blank_zero_cell_grand_total_still_detects_dropped_row(tmp_path):
    """음성 대조 — 같은 대장에서 자산행 하나가 구조행으로 오판돼 빠지면 드러나야 한다."""
    rows = [_done("자산A"), {**_done("자산B"), "상감법": None, "자산명": None},
            _total_row("계정과목총계", "", "9,998,000", "2,000")]
    _, _, _, control = read_ledger(_write(tmp_path, rows), 2025)
    assert control.found and not control.matched
    assert control.deltas == {"exp_dep": 0, "exp_acc": 4_999_000, "exp_bk": 1_000}


def test_grand_total_found_but_unreadable_fails_closed(tmp_path):
    """합계행은 있는데 금액을 못 읽으면 '대사 불가'(exit 0)가 아니라 '해석 불가'(exit 1)."""
    rows = [_done("자산A"), _total_row("계정과목총계", "", "4,999,000원", "1,000원")]
    path = _write(tmp_path, rows)
    _, _, _, control = read_ledger(path, 2025)
    assert control.status == "해석 불가"
    assert "계정과목총계" in control.line()
    assert main([path, "--fy", "2025", "--out", str(tmp_path / "r.xlsx")]) == 1


def test_no_grand_total_row_is_still_unverified_not_failed(tmp_path):
    """정책 유지 — 합계행 자체가 없으면 대사 불가(미검증)이고 실패로 보지 않는다."""
    path = _write(tmp_path, [_done("자산A")])
    _, _, _, control = read_ledger(path, 2025)
    assert control.status == "대사 불가"
    assert main([path, "--fy", "2025", "--out", str(tmp_path / "r.xlsx")]) == 0


# ── M2: 합계 라벨이 자산명 열 밖에 있을 때 ────────────────────────────────

def test_grand_total_label_in_account_column_is_found(tmp_path):
    rows = [_asset_row("자산A", 12_000_000, 4_200_000, 2_400_000, 6_600_000, 5_400_000),
            {**_total_row(None, 3_600_000, 8_800_000, 9_200_000), "계정과목": "합  계"}]
    _, _, _, control = read_ledger(_write(tmp_path, rows), 2025)
    assert control.found and not control.matched           # 자산B가 빠진 대장


def test_grand_total_found_without_asset_name_column(tmp_path):
    """자산명 열이 없는(헤더가 다른) 대장 — 합계 라벨을 다른 칸에서 찾는다."""
    cols = [("자산" if c == "자산명" else c) for c in _COLUMNS]
    rows = [_asset_row("자산A", 12_000_000, 4_200_000, 2_400_000, 6_600_000, 5_400_000),
            _total_row("합  계", 3_600_000, 8_800_000, 9_200_000)]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(cols)
    for r in rows:
        ws.append([r.get(c) for c in _COLUMNS])
    path = tmp_path / "noname.xlsx"
    wb.save(path)
    _, _, _, control = read_ledger(str(path), 2025)
    assert control.found and not control.matched


# ── M3: 개발비 판정 1벌 ──────────────────────────────────────────────────

def _new_dev(account):
    """당기신규 3년 3천만, 대장은 별표4 정액(0.333)으로 9,990,000 — 개발비라면 1/n은 10,000,000."""
    return _asset_row("개발", 0, 0, 9_990_000, 9_990_000, 20_010_000, 계정과목=account,
                      신규취득및증가=30_000_000, 연수=3, 취득일자="2025-01-01", 전기말장부가액=0)


@pytest.mark.parametrize("account", ["개발비", "개발비(무형)", " 개발 비 "])
def test_development_cost_variants_route_to_one_over_n(tmp_path, account):
    assets, unreadable, _, _ = read_ledger(_write(tmp_path, [_new_dev(account)]), 2025)
    assert unreadable == [] and len(assets) == 1
    v = verify_asset(assets[0])
    assert v.status == "차이"                               # 1/n 10,000,000 ≠ 대장 9,990,000


@pytest.mark.parametrize("account", ["", "연구개발비"])
def test_ambiguous_account_for_new_asset_is_unverifiable(tmp_path, account):
    """당기신규는 계정과목이 무형·개발비의 유일한 신호 — 비었거나 '개발비'가 섞인 미등록 계정이면 판정하지 않는다."""
    assets, unreadable, _, _ = read_ledger(_write(tmp_path, [_new_dev(account)]), 2025)
    assert assets == [] and len(unreadable) == 1
