"""depverify CLI — python -m depverify <대장.xlsx> [--fy 2024] [--tolerance 0] [--out report.xlsx]

--fy 생략 시 파일명의 _YYYY1231 패턴에서 추정한다 (더존 결산 대장 관행).
종료코드: 0 = 전 자산 일치(허용차 포함), 1 = 차이 또는 검증불능 존재, 2 = 실행 오류.
"""
import argparse
import json
import os
import re
import sys

from depverify.compliance import check_vehicles, summary_lines
from depverify.provenance import collect
from depverify.reader import other_ledger_sheets, read_ledger, tag_merger_succession
from depverify.report import summary_text, write_xlsx
from depverify.verdict import verify_all


def _infer_fy(path: str):
    # 파일명에서만 찾는다 — 경로 전체를 보면 상위 폴더명(audit_20231231/)이 이겨 전 자산이
    # '차이'로 뜬다(감사 2026-09-23).
    m = re.search(r"_(\d{4})1231", os.path.basename(path))
    return int(m.group(1)) if m else None


def main(argv=None) -> int:
    """종료코드 계약: 0 일치 / 1 차이·검증불능 / 2 실행 오류.

    예상 밖 예외(출력 파일 잠김 — 보고서를 엑셀로 열어둔 경우 등)가 traceback과 함께 exit 1로
    나가 '차이'와 구별되지 않았다(감사 2026-09-23). 실행 오류는 전부 2로 모은다.
    """
    try:
        return _main(argv)
    except Exception as e:                  # argparse의 SystemExit(2)는 Exception이 아니라 그대로 통과
        print(f"오류: 실행 중 예외 — {type(e).__name__}: {e}", file=sys.stderr)
        return 2


def _main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="depverify",
                                description="더존 고정자산관리대장 감가상각 일괄 검증")
    p.add_argument("xlsx", help="고정자산관리대장 xlsx 경로")
    p.add_argument("--fy", type=int, help="검증 대상 회계연도 (생략 시 파일명 _YYYY1231에서 추정)")
    p.add_argument("--fye", type=int, default=12, help="결산월 (기본 12)")
    p.add_argument("--sheet", help="시트 이름 또는 인덱스 (기본 첫 시트 — 대장 시트가 여럿이면 필수)")
    p.add_argument("--mapping", help="컬럼 매핑 JSON 파일 (더존 표준 레이아웃이 아닐 때)")
    p.add_argument("--tolerance", type=int, default=0, metavar="원",
                   help="감사인 허용차(원, 기본 0=원단위 완전일치). "
                        "범위 내 차이는 '허용차'로 별도 표기 — 일치로 뭉개지 않음")
    p.add_argument("--out", help="Excel 보고서 출력 경로 (기본: <입력>_검증보고서.xlsx)")
    p.add_argument("--merger-registration", metavar="YYYY-MM",
                   help="합병 등기월 — 승계자산을 등기월 다음 달부터 상각 기준으로 대조(--merger-prefix와 함께)")
    p.add_argument("--merger-prefix", metavar="접두",
                   help="승계자산 자산명 접두(예: \"(소멸법인)\") — 이 접두로 시작하는 행만 승계자산")
    args = p.parse_args(argv)

    merger = None
    if bool(args.merger_registration) != bool(args.merger_prefix):
        p.error("--merger-registration과 --merger-prefix는 함께 지정하세요")
    if args.merger_registration:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})", args.merger_registration.strip())
        if not m or not 1 <= int(m.group(2)) <= 12:
            p.error(f"--merger-registration은 YYYY-MM 형식이어야 합니다 ({args.merger_registration})")
        merger = (int(m.group(1)), int(m.group(2)))

    fy = args.fy or _infer_fy(args.xlsx)
    if fy is None:
        p.error("--fy를 지정하세요 (파일명에서 결산연도를 추정할 수 없음)")

    if args.tolerance < 0:
        p.error("--tolerance는 0 이상이어야 합니다")

    mapping = None
    if args.mapping:
        try:
            with open(args.mapping, encoding="utf-8") as f:
                mapping = json.load(f)
        except (OSError, ValueError) as e:
            print(f"오류: --mapping 파일을 읽을 수 없습니다 — {e}", file=sys.stderr)
            return 2

    # "1"은 시트 **이름**이 아니라 인덱스로 해석돼야 한다 — 문자열로 흘리면 pandas가
    # 이름으로 찾다가 실패한다(감사 G19). 이름이 숫자인 시트는 없다고 본다.
    sheet = 0 if args.sheet is None else (
        int(args.sheet) if str(args.sheet).lstrip("-").isdigit() else args.sheet)

    out = args.out or re.sub(r"\.xlsx$", "", args.xlsx) + "_검증보고서.xlsx"
    if os.path.abspath(out) == os.path.abspath(args.xlsx):
        # 보고서가 원본 대장을 덮어쓰면 보고서에 찍힌 SHA-256이 사라진 파일을 가리킨다
        print("오류: --out이 입력 대장과 같은 파일입니다 — 대장을 덮어쓰지 않습니다", file=sys.stderr)
        return 2

    try:
        assets, unreadable, structural, control = read_ledger(
            args.xlsx, fy, fye=args.fye, mapping=mapping, sheet=sheet)
    except (FileNotFoundError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2

    # 한 실행은 한 시트만 검증한다. 대장 시트가 더 있는데 말없이 첫 시트만 보고 "전 자산 일치"라고
    # 하면 나머지 시트가 흔적 없이 빠진다 — 고르게 하고, 고른 뒤에도 남은 시트를 적는다.
    others = other_ledger_sheets(args.xlsx, sheet, mapping)
    if others and args.sheet is None:
        print(f"오류: 통합문서에 대장 시트가 더 있습니다: {others} — 한 번에 한 시트만 검증합니다. "
              f"--sheet로 시트를 지정해 시트마다 따로 실행하세요", file=sys.stderr)
        return 2
    if others:
        print(f"[완전성] 이 실행이 검증하지 않은 대장 시트: {others}\n")

    if merger:
        n = tag_merger_succession(assets, args.merger_prefix, *merger)
        if n == 0:
            # 접두 오타일 수 있다 — 조용히 무시하면 승계 판정이 꺼진 채 '일치'가 나온다
            print(f"오류: 자산명이 '{args.merger_prefix}'로 시작하는 행이 없습니다 "
                  f"(--merger-prefix 확인)", file=sys.stderr)
            return 2
        print(f"[합병 승계] 등기 {merger[0]}-{merger[1]:02d} · 접두 '{args.merger_prefix}' {n}건 — "
              f"등기월 다음 달부터 상각 기준으로 대조\n")

    result = verify_all(assets, structural_skips=structural, unreadable=unreadable,
                        tolerance=args.tolerance)
    # 출처 정보는 판정 직후 수집한다 — 보고서와 stdout이 같은 값을 쓴다.
    meta = collect(args.xlsx, fy, args.fye, args.tolerance,
                   sheet=sheet, mapping_path=args.mapping)
    if others:
        meta["검증하지 않은 시트"] = ", ".join(others)
    if merger:                             # 재현성 — 같은 대장도 이 설정에 따라 판정이 달라진다
        meta["합병 승계"] = (f"등기 {merger[0]}-{merger[1]:02d}, 접두 '{args.merger_prefix}' "
                         f"— 등기월 다음 달부터 상각")

    # 완전성 대사를 요약 맨 위에 올린다 — 자산행이 통째로 빠졌다면 아래의 '일치 N건'은
    # 빠진 행을 세지 않은 숫자다. 판정 건수보다 먼저 읽혀야 한다(감사 G11).
    print(f"[완전성] {control.line()}\n")
    print(summary_text(result, fy, meta, control))

    # 적법성 점검 — 재계산 대조가 원리적으로 못 잡는 축(대장이 법령에 어긋난 방법을
    # 써도 그 방법대로 맞으면 '일치'가 난다). 판정이 아니라 검토 지원이다.
    findings = check_vehicles(assets)
    print()
    for line in summary_lines(findings, unchecked=len(unreadable)):
        print(line)

    write_xlsx(result, fy, out, meta, findings, control, unchecked=len(unreadable))
    print(f"보고서: {out}")

    c = result.counts()
    # 합계 대사 불일치는 '차이'와 같은 무게다 — 대장에 있는 행을 못 읽었다는 뜻이라
    # 판정 결과 자체가 불완전하다. 합계행이 없어 대사 불가인 경우는 실패로 보지 않는다
    # (미검증이지 불일치가 아니다 — 보고서 첫 줄에 그렇게 적힌다). 합계행을 찾았는데 금액을
    # 못 읽은 것은 실패다 — 이것까지 '없음'으로 보면 게이트가 조용히 꺼진다(INC-21).
    # 읽은 자산이 0건이면 검증한 것이 없다 — exit 0만 보는 배치가 빈 대장을 통과로 읽지 않게 한다.
    return 1 if (c["차이"] or c["검증불능"] or control.failed or not result.items) else 0


if __name__ == "__main__":
    sys.exit(main())
