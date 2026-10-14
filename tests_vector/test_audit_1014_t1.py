"""감사 2026-10-14 T1 — 운영 경로에서 숫자가 틀리던 소비자 계층 결함 (G2·G4).

G1(정률 이벤트의 5% 교차 기준)은 `test_event_five_percent_basis.py`.
"""
import openpyxl
import pytest

from asset_schedule_generator import generate_depreciation_schedule


# ── G2 / INC-19: CLI 처분비율(%) → 금액 변환의 float (원단위 산술 4회차) ────────
# `int(cost * ratio / 100)` — 1,000,000원 × 2.01% → 20,099(정답 20,100). 소수 비율 입력의 1.06%.
# 사용자가 입력한 십진수 그대로의 비율로, 금액 × 비율은 정수 곱셈·나눗셈 한 번(절사).

COSTS = [1_000_000, 3_333_333, 10_000_000, 99_999_999, 123_456_789]


@pytest.mark.parametrize("cost", COSTS)
def test_cli_ratio_amount_is_exact_floor_for_every_hundredth_percent(cost):
    from depcal import partial_disposal_amount_from_ratio
    wrong = []
    for hundredths in range(1, 10_000):                     # 0.01% ~ 99.99%
        ratio = float(f"{hundredths // 100}.{hundredths % 100:02d}")   # CLI가 넘기는 값(float)
        expected = cost * hundredths // 10_000
        if expected < 1:
            continue
        got = partial_disposal_amount_from_ratio(cost, ratio)
        if got != expected:
            wrong.append((ratio, got, expected))
    assert wrong == []


def test_cli_ratio_known_case():
    from depcal import partial_disposal_amount_from_ratio
    assert partial_disposal_amount_from_ratio(1_000_000, 2.01) == 20_100


# ── G4 / INC-22: 상각완료 후 전부 처분이 엑셀에서 증발 ──────────────────────
# 처분월이 월별 스케줄 밖(상각 종료 후)이면 시트1 처분 정보가 `return None`으로 버려졌다.
# 상각완료 자산의 폐기·매각은 실무에서 흔하다 — 처분 사실과 제거액이 시트1에 남아야 한다.

def _sheet1(path):
    ws = openpyxl.load_workbook(path).worksheets[0]
    return {r[1]: r[2] for r in ws.iter_rows(values_only=True) if r[1]}     # (항목, 내용)


def test_full_disposal_after_depreciation_complete_is_reported(tmp_path):
    path = generate_depreciation_schedule('A', '2015-01-01', 10_000_000, 5, '유형자산', '정액법',
                                          '2024-06-30', None, output_path=str(tmp_path / "x.xlsx"))
    s1 = _sheet1(path)
    assert s1.get("처분유형") == "전체처분"
    assert s1.get("취득원가 (전체)") == 10_000_000
    assert (s1.get("감가상각누계액 (전체)"), s1.get("장부가액 (전체)")) == (9_999_000, 1_000)


def test_partial_disposal_after_depreciation_complete_is_rejected_not_dropped(tmp_path):
    """같은 조건의 부분양도는 월별 스케줄로 표현할 수 없다 — 조용히 버리지 않고 거부."""
    with pytest.raises(ValueError):
        generate_depreciation_schedule('A', '2015-01-01', 10_000_000, 5, '유형자산', '정액법',
                                       '2024-06-30', 4_000_000, output_path=str(tmp_path / "y.xlsx"))
