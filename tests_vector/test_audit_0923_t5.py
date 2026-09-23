"""감사 2026-09-23 트랜치 T5 — 하위 결함 중 운영 경로에서 실제로 도달하는 것들의 회귀 가드."""
import json

import openpyxl
import pytest

from depverify.__main__ import main
from test_depverify_completeness import _COLUMNS, _matching_asset, _write


def _run(argv, capsys):
    code = main(argv)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


# ── depverify: 예상 밖 오류는 exit 2(실행 오류)지 1(차이)이 아니다 ─────────────
# 종전: 잘못된 --mapping JSON·출력 파일 잠김(엑셀로 열어둔 보고서)이 traceback + exit 1 —
# 계약(0 일치 / 1 차이·검증불능 / 2 실행 오류)상 '차이'와 구별되지 않았다.

def test_bad_mapping_json_is_exit_2(tmp_path, capsys):
    bad = tmp_path / "m.json"
    bad.write_text("{not json", encoding="utf-8")
    code, _, err = _run([_write(tmp_path, [_matching_asset()]), "--fy", "2025",
                         "--mapping", str(bad), "--out", str(tmp_path / "r.xlsx")], capsys)
    assert code == 2 and "오류" in err


def test_unwritable_report_path_is_exit_2(tmp_path, capsys):
    code, _, err = _run([_write(tmp_path, [_matching_asset()]), "--fy", "2025",
                         "--out", str(tmp_path / "없는폴더" / "r.xlsx")], capsys)
    assert code == 2 and "오류" in err


# ── depverify: 결산연도는 파일명에서만 추정한다 ─────────────────────────────
# 종전: 경로 전체를 검색해 상위 폴더명(audit_20231231/)이 이겼다 → 전 자산 '차이'.

def test_fiscal_year_is_inferred_from_file_name_not_directory(tmp_path, capsys):
    d = tmp_path / "audit_20231231"
    d.mkdir()
    ledger = _write(d, [_matching_asset()], name="대장_20251231.xlsx")
    code, out, _ = _run([ledger, "--out", str(tmp_path / "r.xlsx")], capsys)
    assert "FY2025" in out and code == 0


# ── depverify: 중복 헤더는 추정하지 않고 멈춘다 ─────────────────────────────
# 종전: pandas가 두 번째를 '기초가액.1'로 바꾸고 리더는 첫 번째를 조용히 썼다.

def test_duplicate_required_header_stops_with_reason(tmp_path, capsys):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["기초가액"] + _COLUMNS)
    row = _matching_asset()
    ws.append([999] + [row.get(c) for c in _COLUMNS])
    path = str(tmp_path / "dup.xlsx")
    wb.save(path)
    code, _, err = _run([path, "--fy", "2025", "--out", str(tmp_path / "r.xlsx")], capsys)
    assert code == 2 and "중복" in err and "기초가액" in err


# ── depverify: 구분 공란인데 양도일이 있으면 검증불능 ───────────────────────
# 종전: 구분 공란 = 보유로 보고 재계산 → 양도 자산이 '차이 Δ장부 +1,000'처럼 오도적 사유로 떴다.

def test_blank_category_with_disposal_date_is_unverifiable(tmp_path):
    from depverify.reader import read_ledger
    row = _matching_asset()
    row.update({"구분": None, "양도/폐기일": "2025-06-30"})
    assets, unreadable, _, _ = read_ledger(_write(tmp_path, [row]), 2025)
    assert assets == [] and len(unreadable) == 1
    assert "구분" in unreadable[0][1] and "양도" in unreadable[0][1]


# ── depverify: 차량 점검은 검증불능 행을 못 본다 — 그렇다고 말한다 ────────────

def test_vehicle_summary_discloses_unchecked_rows():
    from depverify.compliance import summary_lines
    text = "\n".join(summary_lines([], unchecked=3))
    assert "검증불능 3건" in text
    assert "후보 없음" in text
    assert "검증불능" not in "\n".join(summary_lines([], unchecked=0))


# ── vcore monthly_events(운영 단일 진입점) 이벤트 입력 가드 ──────────────────
# cost만 타입을 봤다(G21). 이벤트 금액·월은 안 봐서 소수 금액·13월이 그럴듯한 표로 흘렀다.
from vcore.monthly_schedule import monthly_events  # noqa: E402

_BASE = (10_000_000, 5, 2020, 1)


@pytest.mark.parametrize("kw", [
    {"disp": (6_000_000.5, 2022, 6)},        # 소수 양도액 → 소수 장부가
    {"inc": (3_000_000.5, 2022, 6)},
    {"disp": (6_000_000, 2022, 13)},         # 13월 → 조용히 다음 해 1월
    {"disp": (6_000_000, 2022, 0)},
    {"inc": (3_000_000, 2022, 0)},
    {"declining": "no"},                     # 참 문자열 → 정률로 계산됐다
])
def test_monthly_events_rejects_malformed_event_inputs(kw):
    with pytest.raises(ValueError):
        monthly_events(*_BASE, **kw)


def test_monthly_events_rejects_disposal_before_capex():
    """양도가 증가보다 먼저면 기준원가(원가+증가액)가 틀어진다 — 엑셀 경로만 막고 있었다."""
    with pytest.raises(ValueError, match="증가"):
        monthly_events(*_BASE, inc=(5_000_000, 2022, 1), disp=(4_000_000, 2021, 1))


def test_monthly_events_valid_events_still_work():
    rows = monthly_events(*_BASE, inc=(3_000_000, 2021, 6), disp=(None, 2023, 6))
    assert rows[-1].year == 2023 and rows[-1].month == 6


# ── CLI(depcal.py) ────────────────────────────────────────────────────────
# 날짜: strptime은 '2023-3-5'를 받지만 원문을 그대로 돌려줘, 뒤의 **문자열** 비교에서
# '2023-3-5' > '2023-12-01'이 참이 됐다(증가일이 취득일보다 앞선다고 오판·오거부).

def test_cli_date_input_is_normalized_to_zero_padded(monkeypatch):
    import depcal
    monkeypatch.setattr("builtins.input", lambda _="": "2023-3-5")
    assert depcal.get_date_input("날짜: ") == "2023-03-05"


def test_cli_ctrl_c_is_not_success_exit(monkeypatch):
    """Ctrl-C 중단이 exit 0(성공)이면 스크립트·배치가 완료로 오인한다 — 관례대로 130."""
    import depcal

    def interrupt(_=""):
        raise KeyboardInterrupt
    monkeypatch.setattr("builtins.input", interrupt)
    with pytest.raises(SystemExit) as e:
        depcal.main()
    assert e.value.code == 130
