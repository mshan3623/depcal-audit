"""검증 결과 보고서 — 요약 텍스트(stdout) + Excel(자산별/요약 2시트).

보고서 원칙: 검증불능·차이를 앞세워 감사인이 예외부터 보게 한다.
숫자는 원단위 그대로(반올림·축약 없음).
"""
from typing import Optional

from openpyxl import Workbook
from openpyxl.styles import Font

from depverify.verdict import RunResult

#: 산출물에 반드시 동행해야 하는 용도·한계 고지.
#: 이 표는 감사조서에 붙을 수 있다 — 읽는 사람이 도구의 지위를 오해하면 그 자체가 위험이다.
DISCLAIMER = [
    "이 보고서는 감사인의 판단과 감사절차를 보조하는 참고자료이며, 그것을 대체하지 않습니다.",
    "'검증불능'은 문제없음이 아니라 '이 도구가 확인하지 못함'입니다 — 반드시 개별 확인하십시오.",
    "'허용차'는 일치가 아닙니다. 감사인이 설정한 범위 내라는 뜻이며 개별 확인 대상입니다.",
    "검증 범위는 법인세법 [별표 4] 준용 상각(정액·정률·무형 직접상각)과 더존 대장 레이아웃에 한정됩니다.",
    "범위 밖(별도 검토 필요): 세무조정(상각부인액·시인부족액), 감가상각의제, 업무용승용차 특례,",
    "  중고자산 수정내용연수, 상각방법 변경 신고, 사업연도 월수 12개월 미만, K-IFRS 회계상각.",
    "본 소프트웨어는 Apache-2.0 라이선스로 어떠한 보증도 없이 제공됩니다.",
]

_STATUS_ORDER = {"검증불능": 0, "차이": 1, "허용차": 2, "일치": 3}

_HEADERS = ["판정", "사유/비고", "자산코드", "자산명", "취득", "양도",
            "상각방법", "무형", "취득원가", "내용연수",
            "Δ당기상각", "Δ누계", "Δ장부가",
            "시스템 당기상각", "시스템 누계", "시스템 장부가"]


def _rows(result: RunResult):
    items = sorted(result.items,
                   key=lambda it: _STATUS_ORDER.get(it[1].status, 9))
    for a, v in items:
        yield [
            v.status, v.reason or v.note,
            a.get("asset_code", ""), a.get("asset_name", ""),
            f"{a['acq_y']}-{a['acq_m']:02d}" if "acq_y" in a else "",
            f"{a['disp_y']}-{a['disp_m']:02d}" if a.get("disposed") else "",
            a.get("method", ""), "무형" if a.get("intang") else "",
            a.get("cost", ""), a.get("life", ""),
            v.d_dep, v.d_acc, v.d_bk,
            a.get("exp_dep", ""), a.get("exp_acc", ""), a.get("exp_bk", ""),
        ]


def summary_text(result: RunResult, fy: int, meta: Optional[dict] = None) -> str:
    c = result.counts()
    total = sum(c.values())
    basis = (f"±{result.tolerance:,}원 (감사인 설정)" if result.tolerance
             else "원단위 완전일치")
    lines = [
        f"FY{fy} 검증 결과: 자산 {total}건 (구조행 {result.structural_skips}건 제외)",
        f"  허용차 기준: {basis}",
        f"  일치 {c['일치']}건 / 허용차 {c['허용차']}건 / 차이 {c['차이']}건 / 검증불능 {c['검증불능']}건",
    ]
    if c["차이"] or c["검증불능"]:
        lines.append("  ⚠ 예외 자산 — 보고서의 상단 행 확인:")
        for a, v in result.items:
            if v.status in ("차이", "검증불능"):
                who = a.get("asset_name") or a.get("asset_code") or "(식별정보 없음)"
                detail = v.reason if v.status == "검증불능" else \
                    f"Δ당기상각 {v.d_dep:+,} / Δ누계 {v.d_acc:+,} / Δ장부 {v.d_bk:+,}"
                lines.append(f"    [{v.status}] {who}: {detail}")
    elif c["허용차"] == 0:
        lines.append("  예외 없음 — 전 자산 시스템 산출값과 일치")
    # 허용차는 일치로 뭉개지 않고 항상 별도 열거한다 (V1-3)
    if c["허용차"]:
        lines.append("  허용차 내 차이 — 일치가 아님, 개별 확인 필요:")
        for a, v in result.items:
            if v.status == "허용차":
                who = a.get("asset_name") or a.get("asset_code") or "(식별정보 없음)"
                lines.append(
                    f"    [허용차] {who}: {v.note} "
                    f"(Δ당기상각 {v.d_dep:+,} / Δ누계 {v.d_acc:+,} / Δ장부 {v.d_bk:+,})")
    if meta:
        lines.append("")
        lines.append(f"  엔진 {meta['엔진 버전']} (rev {meta['소스 리비전']}) / 실행 {meta['실행 일시']}")
        lines.append(f"  대장 {meta['대장 파일']}  SHA-256 {meta['대장 SHA-256'][:16]}…")
    lines.append("")
    lines.append("  ※ 이 결과는 감사인의 판단을 대체하지 않습니다. '검증불능'은 문제없음이 아니라")
    lines.append("     확인하지 못했다는 뜻입니다. 상세 고지는 보고서 '고지' 시트를 보십시오.")
    return "\n".join(lines)


def write_xlsx(result: RunResult, fy: int, out_path: str,
               meta: Optional[dict] = None, findings: Optional[list] = None) -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = "자산별"
    ws.append(_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in _rows(result):
        ws.append(row)

    c = result.counts()
    ws2 = wb.create_sheet("요약")
    ws2.append(["FY", fy])
    for k in ("일치", "허용차", "차이", "검증불능"):
        ws2.append([k, c[k]])
    ws2.append(["구조행 스킵", result.structural_skips])
    ws2.append([])
    ws2.append(["검증 기준", "vcore 재계산 vs 시스템 산출값 원단위 대조"])
    ws2.append(["허용차 기준",
                f"±{result.tolerance:,}원 (감사인 설정) — 일치 아님, 별도 분류"
                if result.tolerance else "원단위 완전일치 (허용차 설정 없음)"])
    ws2.append(["스코프", "법인세법 준용 상각(별표4)·더존 대장 — K-IFRS 자체 추정 상각 제외"])

    # 출처(provenance) — 이 표가 어느 엔진·어느 파일에서 나왔는지. 재현성의 근거다.
    if meta:
        ws2.append([])
        ws2.append(["── 실행 출처 (재현성) ──"])
        ws2.cell(row=ws2.max_row, column=1).font = Font(bold=True)
        for k, v in meta.items():
            ws2.append([k, v])

    # 적법성 점검 — 재계산 '일치'와 별개 축이므로 시트를 나눠 오해를 막는다
    ws4 = wb.create_sheet("적법성점검")
    ws4.append(["점검 항목", "자산명", "계정과목", "관측된 값", "법령 근거"])
    for cell in ws4[1]:
        cell.font = Font(bold=True)
    if findings:
        for f in findings:
            ws4.append([f.issue, f.asset_name, f.account, f.detail, f.basis])
    else:
        ws4.append(["업무용승용차 상각 요건", "-", "-", "요건 불일치 후보 없음", "법인세법 시행령 §50조의2 ③"])
    ws4.append([])
    ws4.append(["※ 이 시트는 판정이 아니라 검토 지원입니다. 업무용승용차 해당 여부는 "
                "「개별소비세법」 §1②3호 승용자동차 여부(화물·승합 9인승↑·경차 제외)와 "
                "운수업 등 영업용·연구개발용 제외 요건(시행령 §50조의2 ①)으로 감사인이 확정합니다."])
    for w, c in (("A", 26), ("B", 34), ("C", 16), ("D", 60), ("E", 40)):
        ws4.column_dimensions[w].width = c

    ws3 = wb.create_sheet("고지")
    ws3.append(["용도 및 한계 고지"])
    ws3.cell(row=1, column=1).font = Font(bold=True)
    ws3.append([])
    for line in DISCLAIMER:
        ws3.append([line])
    ws3.column_dimensions["A"].width = 110

    wb.save(out_path)
    return out_path
