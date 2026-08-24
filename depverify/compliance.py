"""적법성 점검 — 재계산 대조가 원리적으로 잡지 못하는 축.

`verdict.py`는 "대장에 적힌 방법·연수대로 다시 계산하면 회사 값이 나오는가"를 본다.
그래서 **대장이 법령에 어긋난 방법을 쓰고 있어도, 그 방법대로 계산이 맞으면 '일치'가
나온다.** 계산은 맞고 적법성은 틀린 거짓 일치다.

현재 다루는 항목은 업무용승용차 하나다 (법인세법 §27조의2, 시행령 §50조의2).

  시행령 §50조의2 ③
    "업무용승용차는 제26조제1항제2호 및 제28조제1항제2호에도 **불구하고** 정액법을
     상각방법으로 하고 내용연수를 5년으로 하여 계산한 금액을 감가상각비로 하여 손금에
     산입**하여야 한다**."

  → 정률법을 신고한 법인이라도, 신고 내용연수와 무관하게 승용차는 5년 정액이 **강제**다.
    상각범위액 계산 자체를 규율하므로 이 엔진의 스코프 안이다(800만원 한도·이월 추인은
    세무조정 영역이라 범위 밖 — 아래 참고 안내만 한다).

**판정이 아니라 검토 지원이다.** 대장만으로는 업무용승용차 해당 여부를 확정할 수 없다:
  - 대상은 「개별소비세법」 §1②3호 승용자동차 — 화물차·승합차(9인승 이상)·경차는 제외
  - 운수업·자동차판매업 등에서 직접 사용하는 영업용, 연구개발용은 제외 (시행령 §50조의2 ①)
  - 계정과목·자산명은 회사가 붙인 이름일 뿐 차종을 확정하지 않는다
따라서 후보를 **뽑아 보여주고 근거를 제시**하며, 해당 여부와 결론은 감사인이 판단한다.
"""
from dataclasses import dataclass
from typing import List

#: 업무용승용차 후보를 뽑는 계정과목·자산명 힌트. 넓게 잡아 후보를 놓치지 않고,
#: 해당 여부 판단은 감사인에게 맡긴다(좁게 잡아 놓치는 쪽이 감사에서 더 위험하다).
VEHICLE_HINTS = ("차량운반구", "차량", "승용차", "승용자동차", "자동차")

#: 시행령 §50조의2 ③이 강제하는 상각 요건
REQUIRED_METHOD = "정액법"
REQUIRED_LIFE = 5

#: 법 §27조의2 ③ 감가상각비 손금 한도(업무사용금액 기준). 부동산임대업 주업 등은 400만원(⑤).
ANNUAL_DEDUCTION_CAP = 8_000_000


@dataclass
class Finding:
    asset_name: str
    account: str
    issue: str          # 점검 항목
    detail: str         # 관측된 값
    basis: str          # 법령 근거


def _is_vehicle_candidate(a: dict) -> bool:
    text = f"{a.get('account') or ''} {a.get('asset_name') or ''}"
    return any(h in text for h in VEHICLE_HINTS)


def check_vehicles(assets: List[dict]) -> List[Finding]:
    """업무용승용차 후보 중 상각방법·내용연수가 법정 요건과 다른 자산을 뽑는다.

    무형자산은 대상이 아니므로 제외한다.
    """
    out: List[Finding] = []
    for a in assets:
        if a.get("intang") or not _is_vehicle_candidate(a):
            continue
        name = a.get("asset_name") or a.get("asset_code") or "(식별정보 없음)"
        account = a.get("account") or ""
        method, life = a.get("method"), a.get("life")

        wrong = []
        if method and method != REQUIRED_METHOD:
            wrong.append(f"상각방법 {method}")
        if life is not None and life != REQUIRED_LIFE:
            wrong.append(f"내용연수 {life}년")
        if wrong:
            out.append(Finding(
                name, account, "업무용승용차 상각 요건 불일치",
                f"{' · '.join(wrong)} (법정: {REQUIRED_METHOD} {REQUIRED_LIFE}년, "
                f"취득 {a.get('acq_y')}-{a.get('acq_m'):02d})",
                "법인세법 시행령 §50조의2 ③"))

        dep = a.get("exp_dep") or 0
        if dep > ANNUAL_DEDUCTION_CAP:
            out.append(Finding(
                name, account, "감가상각비 손금 한도 초과 가능",
                f"당기상각 {dep:,}원 > {ANNUAL_DEDUCTION_CAP:,}원. "
                f"업무사용비율을 곱한 금액 기준으로 판단하며 초과분은 이월 손금산입 대상",
                "법인세법 §27조의2 ③ (부동산임대업 주업 등은 400만원 — 같은 조 ⑤)"))
    return out


def summary_lines(findings: List[Finding]) -> List[str]:
    """stdout·보고서 공용 요약. 점검 항목이 없어도 '검사했다'는 사실을 남긴다."""
    if not findings:
        return ["  업무용승용차 점검: 요건 불일치 후보 없음 "
                "(해당 여부는 개별소비세법 §1②3호·영업용 제외 요건으로 감사인이 확정)"]
    lines = [f"  ⚠ 업무용승용차 점검: {len(findings)}건 — 재계산 '일치'와 별개로 적법성 확인 필요"]
    for f in findings:
        lines.append(f"    [{f.issue}] {f.asset_name} ({f.account})")
        lines.append(f"       {f.detail}")
        lines.append(f"       근거: {f.basis}")
    return lines
