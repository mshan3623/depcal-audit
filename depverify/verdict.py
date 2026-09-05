"""자산별 판정 엔진 — verify_ledger.compare()의 비교 의미론을 판정 4분류로 일반화.

입력 단위는 익명 자산 dict(ledger_a 골든 픽스처와 동일 스키마 + 선택 필드):
  필수: fy, intang, cost, life, acq_y, acq_m, disposed, exp_dep, exp_acc, exp_bk, prev_acc
  선택: disp_y/disp_m(양도 시), method("정액법"|"정률법", 기본 정액법),
        asset_id/asset_name(보고서 식별용), fye(결산월, 기본 12)

판정:
  일치     — 당기상각·누계·장부가 1원 일치
  허용차   — 전기말누계 승계차 ±2원 (대장의 전기말누계가 독립재계산과 다른 채로
             넘어왔고 당기 종료년 정산에서 흡수된 행 — 비고에 근거 명시),
             또는 감사인이 tolerance를 설정한 경우 그 범위 내 차이 (일치로 뭉개지 않음)
  차이     — 불일치 (Δ당기상각/Δ누계/Δ장부 부호·금액 보고)
  검증불능 — 재계산 자체가 불가. 사유 코드:
             가드발동(엔진 입력 가드 ValueError 원문), 스코프외-상각방법,
             필드결손(리더에서 분류), 스코프외-당기증가조합(리더에서 분류)

비교 의미론(더존 대장 특성, verify_ledger에서 실측 검증됨):
  - 무형(직접상각): 당기말상각누계액 열은 당기상각만 표시 → 당기상각과 대조
  - 전액양도: 대장 장부가액=0(자산 제거) → 누계 기준으로 환산 대조
  - 스케줄에 FY 행 없음(상각 종료 후 등): 계속 보유 자산은 비망 1,000 유지
    (당기 0/누계 취득가-1,000/장부 1,000, B사 대장 실측), 그 외는 0이어야 일치
"""
from dataclasses import dataclass, field
from typing import List, Optional

from vcore.declining_balance import schedule as db_schedule
from vcore.disposal import schedule_full_disposal, schedule_full_disposal_declining
from vcore.straight_line import schedule as sl_schedule


@dataclass
class Verdict:
    status: str                     # 일치 | 허용차 | 차이 | 검증불능
    d_dep: int = 0                  # Δ당기상각 (vcore − 시스템)
    d_acc: int = 0                  # Δ누계
    d_bk: int = 0                   # Δ장부가
    reason: str = ""                # 검증불능 사유 코드
    note: str = ""                  # 허용차 등 비고


def verify_asset(a: dict, tolerance: int = 0) -> Verdict:
    """익명 자산 dict 1건을 vcore 재계산과 대조해 판정한다.

    tolerance: 감사인이 설정한 허용 오차(원, 기본 0 = 원단위 완전일치).
               0 초과 시 Δ 전부가 이 범위 안이면 '허용차'로 분류한다 — '일치'가 아니다.
    """
    method = a.get("method", "정액법")
    if method not in ("정액법", "정률법"):
        return Verdict("검증불능", reason=f"스코프외-상각방법({method})")

    fy, cost, life = a["fy"], a["cost"], a["life"]
    intang, disposed = a["intang"], a["disposed"]
    fye = a.get("fye", 12)
    declining = (method == "정률법") and not intang    # 무형은 항상 별표4 정액

    try:
        if disposed:
            fn = schedule_full_disposal_declining if declining else schedule_full_disposal
            sch = fn(cost, life, a["acq_y"], a["acq_m"], a["disp_y"], a["disp_m"], fye)
        else:
            fn = db_schedule if declining else sl_schedule
            sch = fn(cost, life, a["acq_y"], a["acq_m"], fye)
    except ValueError as e:
        return Verdict("검증불능", reason=f"가드발동: {e}")

    cur = next((x for x in sch if x.fiscal_year == fy), None)
    exp_dep, exp_acc, exp_bk = a["exp_dep"], a["exp_acc"], a["exp_bk"]
    if cur is None:
        # 상각 종료 후 계속 보유: 더존은 비망 1,000 유지 표시 (B사 대장 실측,
        # 정액·정률 동일) — 당기 0 / 누계 취득가-1,000 / 장부 1,000
        if (not disposed and not intang
                and exp_dep == 0 and exp_acc == cost - 1000 and exp_bk == 1000):
            return Verdict("일치")
        # 무형(직접상각)의 같은 패턴: 누계 열은 당기분만 표시하므로 0, 장부는 비망 1,000,
        # 전기말누계가 취득원가-1,000 (B사 대장 '개발비' 실측 — 기초가액 1,000이
        # 비망가임을 확인하는 조건). [[douzone-column-semantics]]
        if (not disposed and intang and exp_dep == 0 and exp_acc == 0
                and exp_bk == 1000 and a["prev_acc"] == cost - 1000):
            return Verdict("일치")
        if disposed:
            # 상각완료(또는 전기) 후 양도. 아래 식 `d_bk = cost - exp_bk`는 "장부가액이
            # 취득원가여야 일치"라는 뜻이라, 자산이 제거돼 장부 0인 대장은 **무엇을 적든
            # 항상 '차이'**가 된다(감사 G7: Δ장부 +취득원가). 더존이 이 상황을 어떻게
            # 표시하는지에 대한 실측 앵커가 0건이므로 비교식을 세울 수 없다 — 틀린 사유의
            # 경보로 감사인 시간을 태우느니 모른다고 말한다.
            return Verdict("검증불능",
                           reason="비교식미확립(상각완료·전기 양도 — 대장 표시 규약 실측 앵커 0건)")
        # 스케줄에 FY 행 없음 (상각 종료 후 제거 등) — 시스템 값이 0이어야 일치
        d_dep, d_acc, d_bk = -exp_dep, -exp_acc, cost - exp_bk
    else:
        if disposed and intang:
            # 무형 양도. 아래 양도 환산식 `cost - exp_acc`는 누계열이 **실제 누계**인
            # 간접법(유형) 전제다. 무형은 직접상각이라 누계열이 당기분만 표시하므로
            # 2차연도 이후 무형 양도는 항상 '차이'가 된다(감사 G7 재현: 소프트웨어
            # 12,000,000/5년/2022-01, 2024-06 양도 → Δ장부 −4,800,000. 같은 수치가
            # 유형이면 '일치'). 무형 양도 실측 앵커는 0건이다.
            return Verdict("검증불능",
                           reason="비교식미확립(무형 양도 — 직접상각 누계열 × 양도 환산식, 실측 앵커 0건)")
        d_dep = cur.depreciation - exp_dep
        # 전액양도: 대장 장부가액은 0(자산 제거), vcore는 비망잔존 — 누계 기준 환산 대조
        d_bk = cur.book_value - ((cost - exp_acc) if disposed else exp_bk)
        # 직접상각(무형): 누계열 = 당기상각만 표시. 간접(유형): 실제 누계
        d_acc = (cur.depreciation if intang else cur.accumulated) - exp_acc

    if d_dep == 0 and d_acc == 0 and d_bk == 0:
        return Verdict("일치")

    if cur is not None:
        # 전기말누계 승계차: 대장의 전기말누계가 vcore 독립재계산과 다른 채로 넘어왔는데,
        # 당기가 양쪽 다 상각 종료년(정산행 = 취득가-비망-전기말누계)이라 그 승계차가
        # 당기상각에 1:1 전이되고 누계·장부가는 정산에서 흡수돼 일치하는 행.
        # 실측 원인(A사 FY2025 자산②): 더존이 자산을 분할하며 원자산 누계를
        # 취득가 비례로 배분 — 총액은 보존되나 자녀별 절사 반복으로 자녀수-1원까지 벌어짐.
        # 상한 2는 실물(2분할)에서 관측된 범위이며 근거 있는 일반값이 아니다.
        #
        # ★ 재검증 조건(감사 G15 — 만료 없는 허용목록 금지): 이 상한은 **분할 자녀수−1**이
        #   경험적 상한이라는 관찰에서 나왔고 표본은 1개사(TI) 1건뿐이다. 대장 표본이
        #   3개사 이상이 되면 그 시점에 상한을 재실측한다 — 3분할 자산이 하나라도 나오면
        #   2로는 부족하다(자녀수−1 = 2가 아니라 그 이상). 표본 확대 전까지 이 값을
        #   올리지 말 것: 근거 없이 넓힌 허용목록은 차이를 통과시키는 구멍이 된다.
        #   추적: docs/IMPROVEMENT_PLAN_2026-09-05.md 트랙 B2(실대장 표본 5~10개사).
        # d_dep == carry_gap 은 두 정산식에서 따라오는 항등식(원인은 전기, 당기 아님).
        prev_acc = a["prev_acc"]
        carry_gap = prev_acc - (cur.accumulated - cur.depreciation)   # 대장 − vcore
        if (exp_dep == cost - 1000 - prev_acc          # 대장 당기 = 종료년 정산행
                and cur.accumulated == cost - 1000     # vcore도 당기가 종료년
                and abs(carry_gap) <= 2 and d_acc == 0 and d_bk == 0):
            return Verdict("허용차", d_dep=d_dep,
                           note=f"전기말누계 승계차({carry_gap:+d}원) — 전기 이전 발생, "
                                f"당기 종료년 정산에서 흡수(누계·장부 일치)")

    # 감사인 설정 threshold — 범위 내 차이는 '허용차'로 별도 표기(일치로 뭉개지 않음)
    if tolerance > 0 and max(abs(d_dep), abs(d_acc), abs(d_bk)) <= tolerance:
        return Verdict("허용차", d_dep=d_dep, d_acc=d_acc, d_bk=d_bk,
                       note=f"허용차 내 차이(설정 ±{tolerance:,}원)")

    return Verdict("차이", d_dep=d_dep, d_acc=d_acc, d_bk=d_bk)


@dataclass
class RunResult:
    """대장 1건 실행 결과 — 자산별 (dict, Verdict) 쌍과 구조행 스킵 수."""
    items: List[tuple] = field(default_factory=list)   # (asset dict, Verdict)
    structural_skips: int = 0                          # 소계/합계 등 비자산 행
    tolerance: int = 0                                 # 적용된 허용차 설정(원)

    def counts(self) -> dict:
        c = {"일치": 0, "허용차": 0, "차이": 0, "검증불능": 0}
        for _, v in self.items:
            c[v.status] += 1
        return c


def verify_all(assets: List[dict], structural_skips: int = 0,
               unreadable: Optional[List[tuple]] = None,
               tolerance: int = 0) -> RunResult:
    """자산 dict 리스트 일괄 판정. unreadable = 리더가 분류한 (부분 dict, 사유) 목록."""
    r = RunResult(structural_skips=structural_skips, tolerance=tolerance)
    for a in assets:
        r.items.append((a, verify_asset(a, tolerance=tolerance)))
    for partial, reason in (unreadable or []):
        r.items.append((partial, Verdict("검증불능", reason=reason)))
    return r
