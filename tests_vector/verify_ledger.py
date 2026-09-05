"""A사 고정자산관리대장(더존 위하고) 실데이터 검증 — vcore vs 시스템 산출값.

FY 결산 대장(12월 결산) 기준으로 각 자산을:
  cost   = 기초가액(>0) 또는 신규취득및증가(당기 취득)
  vcore  = straight_line.schedule(cost, 연수, 취득연, 취득월).find(fiscal_year==FY)
대조:
  vcore.depreciation == 당기상각비범위액(col19)
  vcore.accumulated  == 당기말상각누계액(col22)
  vcore.book_value   == 당기말장부가액(col23)
교차검증:
  vcore FY-1.accumulated == 전기말상각누계액(col9)

pytest 통합: tests_vector/test_real_ledger_a.py (xlsx 부재 시 skip)
"""
import glob
import os
import sys

import pandas as pd

# 하네스 직접 실행(python sample_data/verify_ledger.py) 지원용 — 설치 사용 시 무해한 no-op
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from vcore.disposal import schedule_full_disposal
from vcore.straight_line import schedule

_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FY = 2022

INTANGIBLE = {"소프트웨어", "기타무형자산"}


def ledger_path(fy):
    """FY 결산 대장 파일 경로 (예: *_20221231.xlsx). 없으면 None."""
    hits = glob.glob(os.path.join(_DIR, f"*_{fy}1231.xlsx"))
    return hits[0] if hits else None


def _asset_from_row(r, fy):
    """xlsx 행 → 익명 자산 dict (비교에 필요한 수치·플래그만; 자산명·계정 식별정보 제외).

    이 dict가 골든 픽스처의 단위다 — xlsx 없이 compare()로 재현 가능(CI 상시화).
    """
    acct = str(r["계정과목"])
    intang = acct in INTANGIBLE
    base = int(r["기초가액"])
    acc_dep = int(r["전기말상각누계액"])
    capex = int(r["신규취득및증가"])
    # 취득원가 결정 (douzone_to_standard.py 규칙)
    if base == 0 and capex > 0:
        cost = capex                       # 당기 신규취득
    elif intang:
        cost = base + acc_dep              # 무형 이월: 기초가액=장부가, 취득원가=장부+누계
    else:
        cost = base                        # 유형 이월: 기초가액=취득원가
    dt = pd.to_datetime(r["취득일자"])
    disposed = str(r.get("구분", "")).strip() == "양도자산"
    a = {
        "fy": fy, "intang": intang, "cost": cost, "life": int(r["연수"]),
        "acq_y": int(dt.year), "acq_m": int(dt.month), "disposed": disposed,
        "exp_dep": int(r["당기상각비범위액"]),        # 더존 당기상각비범위액
        "exp_acc": int(r["당기말상각누계액"]),        # 더존 당기말상각누계액
        "exp_bk": int(r["당기말장부가액"]),           # 더존 당기말장부가액
        "prev_acc": acc_dep,                          # 전기말상각누계액(분할이월 예외용)
    }
    if disposed:
        dp = pd.to_datetime(r["양도/폐기일"])
        a["disp_y"], a["disp_m"] = int(dp.year), int(dp.month)
    return a


def compare(a):
    """익명 자산 dict를 vcore와 대조 → (ok, d_dep, d_acc, d_bk, note). xlsx 불필요.

    verify(xlsx 경로)와 골든 픽스처 검증이 공유하는 단일 비교 로직.
    """
    fy, cost, life, intang, disposed = a["fy"], a["cost"], a["life"], a["intang"], a["disposed"]
    if disposed:
        # vcore disposal은 더존식 — 양도월(포함)까지 상각
        sch = schedule_full_disposal(cost, life, a["acq_y"], a["acq_m"], a["disp_y"], a["disp_m"], 12)
    else:
        sch = schedule(cost, life, a["acq_y"], a["acq_m"], 12)
    cur = next((x for x in sch if x.fiscal_year == fy), None)

    exp_dep, exp_acc, exp_bk = a["exp_dep"], a["exp_acc"], a["exp_bk"]
    if cur is None:
        # 스케줄에 FY 행 없음 (상각 종료 후 등) — 시스템 값이 0이어야 일치
        d_dep, d_acc, d_bk = -exp_dep, -exp_acc, cost - exp_bk
    else:
        d_dep = cur.depreciation - exp_dep
        # 전액양도: 대장 장부가액은 0(자산 제거), vcore는 비망잔존 — 누계 기준으로 환산 대조
        d_bk = cur.book_value - ((cost - exp_acc) if disposed else exp_bk)
        # 직접상각(무형): col22 당기말누계 = 당기상각만 표시. 간접(유형): 실제 누계.
        d_acc = (cur.depreciation if intang else cur.accumulated) - exp_acc
    ok = (d_dep == 0 and d_acc == 0 and d_bk == 0)
    note = ""
    if not ok and cur is not None:
        # 전기말누계 승계차: 대장 전기말누계가 vcore 재계산과 다른 채로 넘어왔고,
        # 당기가 양쪽 다 종료년 정산행이라 그 차가 당기상각에만 전이된 행
        # (실측 원인: 자산 분할 시 누계 비례배분·자녀별 절사) — ±2원까지 인정.
        # depverify.verdict.verify_asset()과 동일 조건·동일 비고를 유지할 것.
        prev_acc = a["prev_acc"]
        carry_gap = prev_acc - (cur.accumulated - cur.depreciation)   # 대장 − vcore
        if (exp_dep == cost - 1000 - prev_acc and cur.accumulated == cost - 1000
                and abs(carry_gap) <= 2 and d_acc == 0 and d_bk == 0):
            ok = True
            note = (f"전기말누계 승계차({carry_gap:+d}원) — 전기 이전 발생, "
                    f"당기 종료년 정산에서 흡수(누계·장부 일치)")
    return ok, d_dep, d_acc, d_bk, note


def extract_assets(fy=DEFAULT_FY):
    """FY 대장의 정액법 자산을 익명 dict 리스트로 추출 (골든 픽스처 생성용)."""
    p = ledger_path(fy)
    if p is None:
        raise FileNotFoundError(f"{fy} 결산 대장 없음: {_DIR}/*_{fy}1231.xlsx")
    df = pd.read_excel(p, sheet_name=0)
    assets = df[df["상감법"] == "정액법"]   # 소계/합계(NaN) 제외
    return [_asset_from_row(r, fy) for _, r in assets.iterrows()]


def verify_assets(fixtures):
    """익명 자산 dict 리스트를 vcore와 대조. (DataFrame, 불일치건수) 반환. xlsx 불필요."""
    rows, mism = [], 0
    for a in fixtures:
        ok, d_dep, d_acc, d_bk, note = compare(a)
        if not ok:
            mism += 1
        rows.append({
            "fy": a["fy"], "intang": a["intang"], "cost": a["cost"],
            "취득": f"{a['acq_y']}-{a['acq_m']:02d}",
            "양도": f"{a.get('disp_y')}-{a.get('disp_m', 0):02d}" if a["disposed"] else "",
            "Δ당기상각": d_dep, "Δ누계": d_acc, "Δ장부": d_bk, "OK": ok, "비고": note,
        })
    return pd.DataFrame(rows), mism


def verify(fy=DEFAULT_FY):
    """FY 대장의 정액법 자산을 vcore와 대조. (DataFrame, 불일치건수) 반환. xlsx 필요."""
    return verify_assets(extract_assets(fy))


if __name__ == "__main__":
    fy = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FY
    out, mism = verify(fy)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 240)
    print(out.to_string())
    print(f"\n자산 {len(out)}건 / 불일치 {mism}건")
    print("당기상각 합계 차이 (vcore-시스템):", int(out["Δ당기상각"].sum()))
