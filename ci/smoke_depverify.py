"""depverify CLI 엔드투엔드 스모크 — 합성 대장 xlsx로 종료코드 계약을 확인한다.

pytest는 read_ledger/verify_all을 직접 호출하므로 CLI 경로(인자 파싱·xlsx 읽기·
보고서 쓰기·종료코드)는 회귀 그물 밖에 있다. 실대장 xlsx는 고객 데이터라 git에
없으므로(.gitignore) 여기서 손계산 자산 2건을 openpyxl로 합성해 CLI를 실제로 돌린다.

검사 항목:
  1) 전건 일치 대장  → 종료코드 0, 보고서 xlsx 생성
  2) 상각비 1원 훼손 → 종료코드 1 (차이 검출)

손계산 근거(정액법·유형·간접법, FY2024):
  취득원가 12,000,000 / 연수 5 / 2022-01 취득 → 연 상각 2,400,000
  기초가액 12,000,000, 전기말누계 4,800,000(2022·2023),
  당기상각비 2,400,000, 당기말누계 7,200,000, 당기말장부가 4,800,000
"""
import os
import subprocess
import sys
import tempfile

from openpyxl import Workbook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FY = 2024

HEADER = ["계정과목", "Code.1", "자산명", "취득일자", "기초가액", "전기말상각누계액",
          "신규취득및증가", "연수", "상감법", "당기상각비범위액", "당기말상각누계액",
          "당기말장부가액", "구분", "양도/폐기일"]

# 손계산 자산: 정액법 이월분 + 당기 신규취득분(2024-07 취득, 6/12개월 = 600,000)
ROWS = [
    ["비품", "A-001", "책상", "2022-01-01", 12000000, 4800000, 0, 5, "정액법",
     2400000, 7200000, 4800000, "미상각분", None],
    ["비품", "A-002", "의자", "2024-07-01", 0, 0, 2400000, 2, "정액법",
     600000, 600000, 1800000, "미상각분", None],
]


def _build(path, tamper=False):
    wb = Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in ROWS:
        row = list(r)
        if tamper and r[1] == "A-001":
            row[9] = row[9] + 1          # 당기상각비범위액 1원 훼손
        ws.append(row)
    ws.append([None, None, "소  계", None, 12000000, 4800000, 2400000, None, None,
               3000000, 7800000, 6600000, None, None])   # 구조행(스킵 대상)
    wb.save(path)


def _run(xlsx, out):
    p = subprocess.run([sys.executable, "-m", "depverify", xlsx, "--fy", str(FY),
                        "--out", out],
                       cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    return p.returncode


def main() -> int:
    fails = []
    with tempfile.TemporaryDirectory() as d:
        clean = os.path.join(d, f"smoke_ledger_{FY}1231.xlsx")
        report = os.path.join(d, "report.xlsx")
        _build(clean)
        rc = _run(clean, report)
        if rc != 0:
            fails.append(f"[1] 전건 일치 대장인데 종료코드 {rc} (기대 0)")
        if not os.path.exists(report):
            fails.append("[1] 보고서 xlsx가 생성되지 않음")

        bad = os.path.join(d, f"smoke_tampered_{FY}1231.xlsx")
        _build(bad, tamper=True)
        rc = _run(bad, os.path.join(d, "report_bad.xlsx"))
        if rc != 1:
            fails.append(f"[2] 1원 훼손을 검출 못함 — 종료코드 {rc} (기대 1)")

    if fails:
        print("\n=== SMOKE FAIL ===")
        for f in fails:
            print(" -", f)
        return 1
    print("\n=== SMOKE OK === (일치→0, 차이→1, 보고서 생성 확인)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
