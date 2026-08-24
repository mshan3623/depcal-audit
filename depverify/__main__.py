"""depverify CLI — python -m depverify <대장.xlsx> [--fy 2024] [--tolerance 0] [--out report.xlsx]

--fy 생략 시 파일명의 _YYYY1231 패턴에서 추정한다 (더존 결산 대장 관행).
종료코드: 0 = 전 자산 일치(허용차 포함), 1 = 차이 또는 검증불능 존재, 2 = 실행 오류.
"""
import argparse
import json
import re
import sys

from depverify.compliance import check_vehicles, summary_lines
from depverify.provenance import collect
from depverify.reader import read_ledger
from depverify.report import summary_text, write_xlsx
from depverify.verdict import verify_all


def _infer_fy(path: str):
    m = re.search(r"_(\d{4})1231", path)
    return int(m.group(1)) if m else None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="depverify",
                                description="더존 고정자산관리대장 감가상각 일괄 검증")
    p.add_argument("xlsx", help="고정자산관리대장 xlsx 경로")
    p.add_argument("--fy", type=int, help="검증 대상 회계연도 (생략 시 파일명 _YYYY1231에서 추정)")
    p.add_argument("--fye", type=int, default=12, help="결산월 (기본 12)")
    p.add_argument("--sheet", default=0, help="시트 이름 또는 인덱스 (기본 첫 시트)")
    p.add_argument("--mapping", help="컬럼 매핑 JSON 파일 (더존 표준 레이아웃이 아닐 때)")
    p.add_argument("--tolerance", type=int, default=0, metavar="원",
                   help="감사인 허용차(원, 기본 0=원단위 완전일치). "
                        "범위 내 차이는 '허용차'로 별도 표기 — 일치로 뭉개지 않음")
    p.add_argument("--out", help="Excel 보고서 출력 경로 (기본: <입력>_검증보고서.xlsx)")
    args = p.parse_args(argv)

    fy = args.fy or _infer_fy(args.xlsx)
    if fy is None:
        p.error("--fy를 지정하세요 (파일명에서 결산연도를 추정할 수 없음)")

    if args.tolerance < 0:
        p.error("--tolerance는 0 이상이어야 합니다")

    mapping = None
    if args.mapping:
        with open(args.mapping, encoding="utf-8") as f:
            mapping = json.load(f)

    try:
        assets, unreadable, structural = read_ledger(
            args.xlsx, fy, fye=args.fye, mapping=mapping, sheet=args.sheet)
    except (FileNotFoundError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2

    result = verify_all(assets, structural_skips=structural, unreadable=unreadable,
                        tolerance=args.tolerance)
    # 출처 정보는 판정 직후 수집한다 — 보고서와 stdout이 같은 값을 쓴다.
    meta = collect(args.xlsx, fy, args.fye, args.tolerance,
                   sheet=args.sheet, mapping_path=args.mapping)
    print(summary_text(result, fy, meta))

    # 적법성 점검 — 재계산 대조가 원리적으로 못 잡는 축(대장이 법령에 어긋난 방법을
    # 써도 그 방법대로 맞으면 '일치'가 난다). 판정이 아니라 검토 지원이다.
    findings = check_vehicles(assets)
    print()
    for line in summary_lines(findings):
        print(line)

    out = args.out or re.sub(r"\.xlsx$", "", args.xlsx) + "_검증보고서.xlsx"
    write_xlsx(result, fy, out, meta, findings)
    print(f"보고서: {out}")

    c = result.counts()
    return 1 if (c["차이"] or c["검증불능"]) else 0


if __name__ == "__main__":
    sys.exit(main())
