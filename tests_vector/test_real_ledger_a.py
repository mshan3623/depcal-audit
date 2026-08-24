"""A사 실데이터 회귀 가드 — 더존(위하고) 실측 vs vcore.

익명 골든 픽스처(fixtures/douzone_golden_a.json, 99건)로 **xlsx 없이 CI 상시 검증**.
픽스처는 자산명·계정 등 식별정보를 뺀 수치·플래그만 담아 vcore가 더존 시스템 산출값과
1원 일치함을 재현한다. 실고객 대장(xlsx)이 있는 로컬에서는 라이브 대조 + 픽스처 최신성
교차검증도 수행한다.

픽스처 재생성(대장 변경 시): sample_data에서
    python -c "import json,verify_ledger as v; \
        json.dump(sum([v.extract_assets(fy) for fy in (2022,2024,2025)],[]), \
        open('../tests_vector/fixtures/douzone_golden_a.json','w'),ensure_ascii=False,indent=0)"
"""
import json
import os

import pytest

import verify_ledger

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures", "douzone_golden_a.json")


def _load_fixtures():
    with open(_FIXTURES, encoding="utf-8") as f:
        return json.load(f)


def test_vcore_matches_douzone_fixtures():
    """익명 골든 픽스처(99건)로 vcore가 더존 실측과 1원 일치 — xlsx 불필요(CI 상시)."""
    fixtures = _load_fixtures()
    assert len(fixtures) >= 99
    df, mism = verify_ledger.verify_assets(fixtures)
    assert mism == 0, f"더존 실측 불일치 {mism}건:\n{df[~df['OK']].to_string()}"


@pytest.mark.parametrize("fy", [2022, 2024, 2025])
def test_fixtures_match_live_ledger(fy):
    """xlsx 있으면: 라이브 대장 재추출이 저장된 픽스처와 동일한지(픽스처 최신성 가드)."""
    if verify_ledger.ledger_path(fy) is None:
        pytest.skip(f"{fy} 결산 대장 xlsx 없음 (로컬 전용 데이터)")
    live = verify_ledger.extract_assets(fy)
    stored = [a for a in _load_fixtures() if a["fy"] == fy]
    assert live == stored, f"FY{fy} 픽스처가 라이브 대장과 다름 — 재생성 필요"
    _, mism = verify_ledger.verify(fy)
    assert mism == 0, f"FY{fy} 라이브 대조 불일치 {mism}건"
