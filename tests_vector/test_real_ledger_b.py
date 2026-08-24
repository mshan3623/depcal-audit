"""B사 FY2025 실데이터 회귀 가드 — 더존(위하고) 실측 vs vcore (정률 앵커).

익명 골든 픽스처(fixtures/douzone_golden_b.json, 6건)로 **xlsx 없이 CI 상시 검증**.
2026-07 검증 기록의 FY2026 대장과 다른 FY2025 대장이며, 정률 실측
앵커를 넓힌다:
  - 정률 계산 진행 중 2건 (455,000/2021-06 취득, 1,088,728/**2022-12 취득 = 첫해 1개월**)
  - 정률·정액 상각완료 보유 2건 (비망 1,000 유지 패턴)
  - 무형 직접상각 2건 (진행 중 1건 + **상각완료 비망 유지 1건**)

무형 2건이 이 픽스처의 핵심이다. '개발비'는 원래 INTANGIBLE_ACCOUNTS에 없어 유형으로
오분류됐고, 취득원가가 1,000(실제 37,000,000)으로 복원됐는데도 상각완료 자산이라
비망 규칙 세 조건이 우연히 맞아 '일치'로 통과했다(2026-07-25 발견). 오분류 재발 시
이 픽스처의 cost 값이 어긋나 즉시 실패한다.

픽스처 재생성(대장 변경 시): 원본 xlsx는 저장소 밖(고객 데이터)이므로 리더로 재추출 후
식별정보(asset_code/asset_name)를 제거해 저장한다.
"""
import json
import os

from depverify.verdict import verify_all, verify_asset

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures", "douzone_golden_b.json")


def _fixtures():
    with open(_FIXTURES, encoding="utf-8") as f:
        return json.load(f)


def test_all_assets_match_douzone():
    """6건 전건이 vcore 재계산과 1원 일치 (더존 실측 앵커)."""
    result = verify_all(_fixtures())
    c = result.counts()
    diffs = [(a, v) for a, v in result.items if v.status != "일치"]
    assert c["일치"] == 6, f"불일치 {diffs}"


def test_declining_in_progress_anchors():
    """정률 계산 진행 중 2건 — 표준형 벡터가 더존 산출값과 1원 일치.

    사무용가구(2022-12 취득)는 첫해 1개월 월할 케이스라 정률 프로젝션의 경계 앵커.
    """
    anchors = [a for a in _fixtures()
               if a["method"] == "정률법" and a["exp_dep"] > 0]
    assert len(anchors) == 2
    assert {a["acq_m"] for a in anchors} == {6, 12}     # 6월·12월 취득
    for a in anchors:
        assert verify_asset(a).status == "일치"


def test_intangible_cost_reconstruction_anchor():
    """무형 취득원가 복원(기초가액+전기말누계)이 실측과 정합.

    개발비: 기초 1,000 + 전기말누계 36,999,000 = 37,000,000.
    소프트웨어: 기초 71,666,667 + 전기말누계 28,333,333 = 100,000,000.
    유형으로 오분류되면 cost가 각각 1,000 / 71,666,667이 되어 이 값과 어긋난다.
    """
    intang = [a for a in _fixtures() if a["intang"]]
    assert {a["cost"] for a in intang} == {37_000_000, 100_000_000}
    for a in intang:
        assert a["cost"] == a["prev_acc"] + a["exp_bk"] or a["exp_dep"] > 0
        assert verify_asset(a).status == "일치"


def test_intangible_fully_amortized_held_at_memo():
    """무형 직접상각 완료 후 계속 보유 — 당기 0 / 누계열 0 / 장부 1,000 (B사 실측).

    유형의 비망 유지 규칙(누계열=취득가-1,000)과 열 의미가 달라 별도 분기가 필요하다.
    """
    a = next(x for x in _fixtures()
             if x["intang"] and x["exp_dep"] == 0)
    assert (a["exp_acc"], a["exp_bk"]) == (0, 1000)
    assert a["prev_acc"] == a["cost"] - 1000
    assert verify_asset(a).status == "일치"
