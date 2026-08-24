"""depverify V1 게이트 — 판정 엔진이 verify_ledger.compare()와 동일 판정 + 분류 정확성.

게이트(개선계획 V1): TI 익명 골든 픽스처 99건을 새 파이프라인에 투입했을 때
기존 하네스와 판정·Δ가 완전히 같아야 한다. 추가로 검증불능 분류(사유 코드)와
리더의 정직 분류(조용한 스킵 금지)를 고정한다.
"""
import json
import os

import pytest

import verify_ledger
from depverify.verdict import Verdict, verify_all, verify_asset

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures", "douzone_golden_a.json")


def _fixtures():
    with open(_FIXTURES, encoding="utf-8") as f:
        return json.load(f)


# ── 게이트: 기존 하네스와 동일 판정 ─────────────────────────────────────────

def test_gate_same_verdict_as_verify_ledger():
    """99건 전건: verify_ledger.compare()의 (ok, Δ)와 depverify 판정이 일치."""
    fixtures = _fixtures()
    assert len(fixtures) >= 99
    for a in fixtures:
        ok, d_dep, d_acc, d_bk, note = verify_ledger.compare(a)
        v = verify_asset(a)
        assert (v.status in ("일치", "허용차")) == ok, f"판정 불일치: {a}"
        if v.status == "차이":
            assert (v.d_dep, v.d_acc, v.d_bk) == (d_dep, d_acc, d_bk)
        if v.status == "허용차":
            assert note and v.note == note        # 분할이월 반올림 비고 동일


def test_gate_all_fixtures_pass():
    """99건 전건이 일치/허용차 (더존 실측 1원 일치의 파이프라인 재현)."""
    result = verify_all(_fixtures())
    c = result.counts()
    assert c["차이"] == 0 and c["검증불능"] == 0
    assert c["일치"] + c["허용차"] == len(result.items)


# ── 검증불능 분류 ────────────────────────────────────────────────────────────

def _asset(**over):
    base = {"fy": 2024, "intang": False, "cost": 12_000_000, "life": 5,
            "acq_y": 2022, "acq_m": 4, "disposed": False,
            "exp_dep": 2_400_000, "exp_acc": 6_600_000, "exp_bk": 5_400_000,
            "prev_acc": 4_200_000}
    base.update(over)
    return base


def test_unsupported_method_is_unverifiable():
    v = verify_asset(_asset(method="생산량비례법"))
    assert v.status == "검증불능" and "스코프외-상각방법" in v.reason


def test_engine_guard_is_unverifiable_not_crash():
    """엔진 입력 가드(P-b) 발동 → 검증불능(사유 원문), 예외 전파 없음."""
    v = verify_asset(_asset(cost=0))
    assert v.status == "검증불능" and "가드발동" in v.reason
    v = verify_asset(_asset(life=1))
    assert v.status == "검증불능" and "가드발동" in v.reason


def test_difference_reports_deltas():
    """시스템 값이 틀린 자산은 Δ 부호·금액이 보고된다 (정액 2,400,000이 정답)."""
    v = verify_asset(_asset(exp_dep=2_500_000))
    assert v.status == "차이" and v.d_dep == -100_000    # vcore − 시스템


# ── 전기말누계 승계차 허용차 (구 '분할이월 반올림' 오귀속 정정) ──────────────
# 실측(TI FY2025 내부인테리어): 부분양도가 아니라 자산 분할 시 원자산 누계를
# 취득가 비례로 배분한 결과 — 총액은 보존되나 자녀별 절사로 ±N원이 승계된다.

def _final_year(**over):
    """정액 12,000,000 / 5년 / 2022-04 취득 → FY2027이 종료년 정산행.
    vcore: 전기말누계 11,400,000 / 당기 599,000 / 누계 11,999,000 / 장부 1,000."""
    base = {"fy": 2027, "intang": False, "cost": 12_000_000, "life": 5,
            "acq_y": 2022, "acq_m": 4, "disposed": False,
            "prev_acc": 11_400_000, "exp_dep": 599_000,
            "exp_acc": 11_999_000, "exp_bk": 1_000}
    base.update(over)
    return base


def test_carry_gap_within_2_is_허용차_with_honest_note():
    """승계차 +2원: 허용차로 통과하되 비고가 실제 원인(전기 발생)을 말한다."""
    v = verify_asset(_final_year(prev_acc=11_400_002, exp_dep=598_998))
    assert v.status == "허용차" and v.d_dep == 2
    assert "전기말누계 승계차(+2원)" in v.note
    assert "부분양도" not in v.note and "분할이월" not in v.note   # 오귀속 재발 금지


def test_carry_gap_beyond_2_is_차이():
    """상한 2 유지(가안) — 3원 승계차는 묵인하지 않는다."""
    v = verify_asset(_final_year(prev_acc=11_400_003, exp_dep=598_997))
    assert v.status == "차이" and v.d_dep == 3


def test_current_year_only_error_is_not_absorbed():
    """전기말누계가 일치하는데 당기상각만 2원 틀린 행은 허용차가 아니다.
    이 분기가 묵인하는 것은 '전기에서 넘어온 차'뿐임을 고정한다."""
    v = verify_asset(_final_year(exp_dep=598_998))    # prev_acc은 vcore와 동일
    assert v.status == "차이" and v.d_dep == 2


def test_carry_gap_requires_accumulated_and_book_to_agree():
    """누계·장부가가 정산에서 흡수되지 않으면(Δ≠0) 승계차 분기로 빠지지 않는다."""
    v = verify_asset(_final_year(prev_acc=11_400_002, exp_dep=598_998,
                                 exp_acc=11_998_998))
    assert v.status == "차이"


# ── B-4 허용차 threshold 설정화 (계획서 V1-3) ────────────────────────────────

def test_tolerance_default_is_exact_match():
    """기본값은 원단위 완전일치 — 1원 차이도 '차이'다."""
    v = verify_asset(_asset(exp_dep=2_400_001))
    assert v.status == "차이" and v.d_dep == -1


def test_tolerance_within_is_not_match_but_허용차():
    """설정 범위 내 차이는 '허용차' — '일치'로 뭉개지 않고 Δ를 그대로 보고한다."""
    v = verify_asset(_asset(exp_dep=2_400_500), tolerance=1000)
    assert v.status == "허용차"
    assert v.d_dep == -500                       # Δ 은폐 금지
    assert "±1,000원" in v.note


def test_tolerance_boundary_inclusive():
    """경계값은 포함, 1원만 넘어도 차이."""
    assert verify_asset(_asset(exp_dep=2_400_500), tolerance=500).status == "허용차"
    assert verify_asset(_asset(exp_dep=2_400_500), tolerance=499).status == "차이"


def test_tolerance_does_not_mask_unverifiable():
    """검증불능은 허용차로 승격되지 않는다 (재계산 자체가 불가)."""
    v = verify_asset(_asset(method="생산량비례법"), tolerance=1_000_000)
    assert v.status == "검증불능"


def test_tolerance_recorded_in_result_and_counted_separately():
    """RunResult가 적용 threshold를 보존하고, 허용차는 일치와 별도 집계된다."""
    result = verify_all([_asset(exp_dep=2_400_500)], tolerance=1000)
    assert result.tolerance == 1000
    c = result.counts()
    assert c["허용차"] == 1 and c["일치"] == 0 and c["차이"] == 0


def test_summary_never_claims_all_match_when_허용차_exists():
    """보고서 요약이 허용차를 일치로 뭉개지 않는다 (V1-3 핵심 게이트)."""
    from depverify.report import summary_text
    result = verify_all([_asset(exp_dep=2_400_500)], tolerance=1000)
    text = summary_text(result, 2024)
    assert "전 자산 시스템 산출값과 일치" not in text
    assert "허용차 내 차이" in text
    assert "±1,000원" in text                    # 적용 기준 명시
    assert "-500" in text or "−500" in text      # Δ 노출


def test_summary_states_basis_when_no_tolerance():
    """threshold 미설정 시에도 기준을 명시한다."""
    from depverify.report import summary_text
    text = summary_text(verify_all([_asset()]), 2024)
    assert "허용차 기준: 원단위 완전일치" in text


def test_declining_method_supported():
    """정률법 자산도 판정 경로가 열려 있다 (실측 앵커는 V3 과제 — 손계산 골든만)."""
    from vcore.declining_balance import schedule
    sch = schedule(10_000_000, 5, 2023, 1, 12)
    r = next(x for x in sch if x.fiscal_year == 2024)
    v = verify_asset(_asset(method="정률법", cost=10_000_000, acq_y=2023, acq_m=1,
                            exp_dep=r.depreciation, exp_acc=r.accumulated,
                            exp_bk=r.book_value, prev_acc=0))
    assert v.status == "일치"


def test_ended_asset_held_at_memo_value_matches():
    """상각 종료 후 계속 보유 자산 — 더존은 비망 1,000 유지 (B사 대장 실측 2건).

    정률(기계장치 네트웍서버)·정액(쏘나타DN8) 실측 값 그대로 앵커.
    """
    v = verify_asset(_asset(method="정률법", fy=2026, cost=42_371_219, life=5,
                            acq_y=2018, acq_m=4, exp_dep=0,
                            exp_acc=42_370_219, exp_bk=1_000, prev_acc=42_370_219))
    assert v.status == "일치"
    v = verify_asset(_asset(method="정액법", fy=2026, cost=28_281_000, life=5,
                            acq_y=2019, acq_m=8, exp_dep=0,
                            exp_acc=28_280_000, exp_bk=1_000, prev_acc=28_280_000))
    assert v.status == "일치"


def test_unreadable_rows_are_reported_not_dropped():
    """리더가 분류한 읽기 불능 행이 결과에 검증불능으로 포함된다 (조용한 스킵 금지)."""
    result = verify_all([_asset()], structural_skips=2,
                        unreadable=[({"asset_name": "불명자산"}, "필드결손(취득일자)")])
    c = result.counts()
    assert c["검증불능"] == 1 and c["일치"] == 1
    assert result.structural_skips == 2
    bad = [it for it in result.items if it[1].status == "검증불능"][0]
    assert bad[0]["asset_name"] == "불명자산" and "필드결손" in bad[1].reason


# ── 리더: 취득원가 복원 가드 ────────────────────────────────────────────────

def _row(**over):
    """더존 표준 레이아웃 1행 (리더가 row.get/row[]만 쓰므로 dict로 충분)."""
    base = {"계정과목": "비품", "Code.1": "1", "자산명": "테스트자산",
            "취득일자": "2022-04-01", "기초가액": 12_000_000, "전기말상각누계액": 4_200_000,
            "신규취득및증가": 0, "연수": 5, "상감법": "정액법",
            "당기상각비범위액": 2_400_000, "당기말상각누계액": 6_600_000,
            "당기말장부가액": 5_400_000, "구분": "미상각분", "양도/폐기일": None}
    base.update(over)
    return base


def _read_row(**over):
    from depverify.reader import DOUZONE_COLUMNS, _row_to_asset
    return _row_to_asset(_row(**over), DOUZONE_COLUMNS, 2025, 12)


def test_intangible_accounts_cover_development_cost():
    """개발비 등 무형 계정이 직접상각으로 복원된다 (B사 대장 실측 오분류 회귀 가드).

    미등록 시 취득원가가 기초가액(=비망 1,000)으로 복원돼 37,000배 틀린다.
    """
    a, bad = _read_row(계정과목="개발비", 취득일자="2019-12-31", 기초가액=1000,
                       전기말상각누계액=36_999_000, 당기상각비범위액=0,
                       당기말상각누계액=0, 당기말장부가액=1000)
    assert bad is None and a["intang"] is True
    assert a["cost"] == 37_000_000            # 기초 1,000 + 전기말누계 36,999,000


def test_indirect_method_invariant_violation_is_unverifiable():
    """유형 간접법 불변식(기초가액 > 전기말누계) 위반 → 검증불능(조용한 오복원 금지).

    누계는 비망가 때문에 취득원가에 도달할 수 없다. 위반 = 미등록 무형 계정 의심.
    """
    a, bad = _read_row(계정과목="미등록무형계정", 기초가액=1000,
                       전기말상각누계액=36_999_000)
    assert a is None
    ident, reason = bad
    assert "해석모순" in reason and "미등록무형계정" in reason
    assert ident["asset_name"] == "테스트자산"      # 식별정보는 보고서에 남는다


def test_indirect_method_invariant_allows_fully_depreciated():
    """비망가만 남은 정상 자산(기초 = 누계 + 1,000)은 불변식을 통과한다."""
    a, bad = _read_row(기초가액=42_371_219, 전기말상각누계액=42_370_219,
                       당기상각비범위액=0, 당기말상각누계액=42_370_219,
                       당기말장부가액=1000)
    assert bad is None and a["cost"] == 42_371_219


# ── 리더: 항등식 기반 유형/무형 판별 (사전 비의존) ──────────────────────────
#
# 위 두 테스트의 _row()에는 '전기말장부가액'이 없다 = 항등식 불가 → 계정과목명 사전
# 폴백 경로를 고정한 것이다. 아래는 더존 실제 레이아웃(장부가액 존재)의 1순위 경로:
#     간접법(유형): 전기말장부가액 = 기초가액 − 전기말상각누계액
#     직접법(무형): 전기말장부가액 = 기초가액
# 실측(A사 3개년 + B사, 자산 142행): 유형 95 · 무형 8 · 양쪽성립 39(전부
# 당기신규) · 둘다불성립 0 · 사전과 충돌 0.

def _intangible_b(**over):
    """B사 미등재 무형계정 실측 — 반쯤 상각된 직접법 무형자산."""
    row = {"기초가액": 51_666_667, "전기말상각누계액": 48_333_333,
           "전기말장부가액": 51_666_667, "연수": 5, "취득일자": "2023-07-01",
           "당기상각비범위액": 20_000_000, "당기말상각누계액": 68_333_333,
           "당기말장부가액": 31_666_667}
    row.update(over)
    return _read_row(**row)


def test_identity_restores_intangible_cost():
    """직접법 항등식(장부=기초) → 취득원가 = 기초 + 누계 복원."""
    a, bad = _intangible_b(계정과목="소프트웨어")
    assert bad is None and a["intang"] is True
    assert a["cost"] == 100_000_000            # 51,666,667 + 48,333,333


def test_unregistered_intangible_account_is_not_silently_tangible():
    """사전 미등재 무형계정이 조용히 유형으로 잡히지 않는다 (핵심 회귀 가드).

    간접법 불변식(기초 > 누계)은 반쯤 상각된 무형을 못 잡는다 — 해당 무형자산은 기초
    51,666,667 > 누계 48,333,333이라 불변식을 통과해버린다. 사전에만 의존하면
    취득원가가 순장부가로 축소돼(100,000,000 → 51,666,667) 상각비가 절반으로
    나오고, 감사 조서에는 '차이'로 잘못 귀속된다. 항등식이 이를 잡아낸다.
    """
    a, bad = _intangible_b(계정과목="미등록무형계정")
    assert a is None, "미등재 무형계정이 유형으로 조용히 통과했다"
    _, reason = bad
    assert "판별충돌" in reason and "미등록무형계정" in reason


def test_identity_conflict_when_name_says_intangible_but_form_is_indirect():
    """이름=무형인데 대장이 간접법 형식 → 어느 쪽도 조용히 고르지 않고 검증불능."""
    a, bad = _read_row(계정과목="소프트웨어", 기초가액=12_000_000,
                       전기말상각누계액=4_200_000, 전기말장부가액=7_800_000)
    assert a is None
    _, reason = bad
    assert "판별충돌" in reason


def test_identity_neither_form_is_unverifiable():
    """간접법도 직접법도 아닌 장부가액 → 항등식불성립(대장 자체 모순)."""
    a, bad = _read_row(전기말장부가액=9_999_999)
    assert a is None
    _, reason = bad
    assert "항등식불성립" in reason


def test_identity_agrees_with_tangible_indirect_form():
    """정상 유형 이월(장부 = 기초 − 누계) → 취득원가 = 기초가액."""
    a, bad = _read_row(전기말장부가액=7_800_000)     # 12,000,000 − 4,200,000
    assert bad is None and a["intang"] is False and a["cost"] == 12_000_000


def test_new_acquisition_needs_no_discrimination():
    """당기신규(기초 0 & 신규취득>0)는 표시방법과 무관하게 cost = 신규취득액."""
    a, bad = _read_row(계정과목="미등록계정", 기초가액=0, 신규취득및증가=2_650_000,
                       전기말상각누계액=0, 전기말장부가액=0)
    assert bad is None and a["cost"] == 2_650_000


# ── 리더: 처분 구분 라벨 (B-2) ─────────────────────────────────────────────

def test_unknown_disposal_label_is_unverifiable():
    """폐기 등 미인식 구분 → 검증불능(조용히 '계속 보유'로 재계산 금지).

    B사 대장 폐기 2건 실측 경로: 보유로 재계산돼 **차이**로 잘못 떴다.
    """
    a, bad = _read_row(구분="폐기")
    assert a is None
    ident, reason = bad
    assert "스코프외-처분구분" in reason and "폐기" in reason
    assert ident["asset_name"] == "테스트자산"      # 식별정보는 보고서에 남는다


def test_held_and_disposed_labels_are_read():
    """인식 라벨 3종(미상각분 · 공백 · 양도자산)은 종전대로 해석된다."""
    held, bad = _read_row(구분="미상각분")
    assert bad is None and held["disposed"] is False
    blank, bad = _read_row(구분=None)
    assert bad is None and blank["disposed"] is False
    sold, bad = _read_row(구분="양도자산", **{"양도/폐기일": "2025-06-30"})
    assert bad is None and sold["disposed"] is True
    assert (sold["disp_y"], sold["disp_m"]) == (2025, 6)


# ── 리더: 비정수 셀 (B-3) ──────────────────────────────────────────────────

@pytest.mark.parametrize("col,val", [
    ("기초가액", 12_000_000.5),
    ("전기말상각누계액", 4_200_000.7),
    ("신규취득및증가", 0.4),
    ("연수", 5.5),
    ("당기상각비범위액", 2_400_000.4),      # 종전에는 try 밖이라 예외가 read_ledger를 뚫었다
    ("당기말상각누계액", 6_600_000.9),
    ("당기말장부가액", 5_400_000.1),
])
def test_non_integer_cell_is_unverifiable_not_truncated(col, val):
    """소수 셀 7곳 전부 검증불능 — 원단위 대조 도구가 입력을 절사하면 판정이 왜곡된다."""
    a, bad = _read_row(**{col: val})
    assert a is None, f"{col}={val} 가 조용히 절사됐다"
    _, reason = bad
    assert "비정수셀" in reason and col in reason


def test_integral_float_cells_are_accepted():
    """pandas가 정수 셀을 float로 읽어도(12000000.0) 정상 해석된다."""
    a, bad = _read_row(기초가액=12_000_000.0, 연수=5.0, 당기말장부가액=5_400_000.0)
    assert bad is None and a["cost"] == 12_000_000 and a["life"] == 5
    assert isinstance(a["cost"], int) and isinstance(a["exp_bk"], int)


# ── 리더 (xlsx 있는 로컬 전용 — CI에서는 skip) ──────────────────────────────

@pytest.mark.parametrize("fy", [2022, 2024, 2025])
def test_reader_matches_verify_ledger_extraction(fy):
    """리더의 자산 추출이 기존 하네스 추출과 동일 (비교 필드 기준)."""
    from depverify.reader import read_ledger
    path = verify_ledger.ledger_path(fy)
    if path is None:
        pytest.skip(f"{fy} 결산 대장 xlsx 없음 (로컬 전용 데이터)")
    assets, unreadable, structural = read_ledger(path, fy)
    old = verify_ledger.extract_assets(fy)
    assert len(assets) == len(old)
    assert unreadable == []                       # TI 대장은 전 행 해석 가능
    keys = ("fy", "intang", "cost", "life", "acq_y", "acq_m", "disposed",
            "exp_dep", "exp_acc", "exp_bk", "prev_acc")
    for new_a, old_a in zip(assets, old):
        assert {k: new_a[k] for k in keys} == {k: old_a[k] for k in keys}
