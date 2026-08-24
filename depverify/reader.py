"""더존(위하고) 고정자산관리대장 xlsx 리더 — 자산행 → 익명 자산 dict.

기본 매핑은 더존 표준 레이아웃(A사 대장으로 실측). 고객사 대장의 컬럼명이
다르면 JSON 매핑 파일로 재정의한다(--mapping). 취득원가 재구성 규칙은
sample_data/verify_ledger.py(실측 99건 검증)와 동일:
  - 기초가액=0 & 신규취득>0  → 당기 신규취득 (cost = 신규취득및증가)
  - 무형 이월                → 기초가액=장부가, cost = 기초가액+전기말누계 (직접상각 복원)
  - 유형 이월                → cost = 기초가액 (간접법: 기초가액=취득원가)

읽기 불능 행은 조용히 버리지 않고 (부분 dict, 사유) 로 분류해 반환한다:
  - 스코프외-상각방법: 정액법·정률법 외
  - 스코프외-처분구분: 보유/양도 외 라벨(폐기 등) — 재계산 규칙 미확립
  - 스코프외-당기증가조합: 이월자산+당기증가 동시 (증가월이 대장에 없어 V2 과제)
  - 비정수셀: 원 단위 셀에 소수 — 입력측 절사 금지
  - 필드결손: 필수 필드 누락/해석 불능
소계·합계 등 비자산 행(상각방법 공백 + 자산명이 공백이거나 소계/합계 라벨)만
구조행으로 스킵 카운트한다 — 더존 대장은 소계 행의 자산명 칸에 '소  계' 등을 쓴다.
"""
import re
from typing import List, Optional, Tuple

import pandas as pd

# 내부 키 → 더존 표준 컬럼명 (A사 대장 실측 레이아웃)
DOUZONE_COLUMNS = {
    "account": "계정과목",
    "asset_code": "Code.1",
    "asset_name": "자산명",
    "acq_date": "취득일자",
    "beginning": "기초가액",
    "prev_acc": "전기말상각누계액",
    "capex": "신규취득및증가",
    "life": "연수",
    "method": "상감법",
    "exp_dep": "당기상각비범위액",
    "exp_acc": "당기말상각누계액",
    "exp_bk": "당기말장부가액",
    "category": "구분",              # 양도자산 | 미상각분 …
    "disposal_date": "양도/폐기일",
    "prev_book": "전기말장부가액",     # 항등식 판별용 (없으면 계정과목명 사전으로 폴백)
}

# 무형자산 계정과목 — 항등식(classify_asset) 미가용 시 폴백 + 상시 교차검증용.
# 사전은 그 자체로 안전장치가 아니다: 미등재 이름이 오면 반쯤 상각된 무형자산이
# 조용히 유형으로 잡혀 취득원가가 순장부가로 축소된다(B사 미등재 무형계정 실측:
# 사전 제거 시 cost 100,000,000 → 51,666,667). 그래서 1순위는 사전이 아니라 항등식.
INTANGIBLE_ACCOUNTS = {
    "영업권", "산업재산권", "특허권", "실용신안권", "의장권", "디자인권", "상표권",
    "라이선스", "라이센스", "프랜차이즈", "개발비", "소프트웨어",
    "광업권", "어업권", "차지권", "임차권리금", "기타무형자산",
}

SUPPORTED_METHODS = {"정액법", "정률법"}

# 구분(category) 라벨. 어느 쪽에도 없는 라벨(폐기·감액 등)을 조용히 '계속 보유'로
# 재계산하면 처분 자산이 **차이**로 잘못 뜬다(B사 대장 폐기 2건 실측). 재계산
# 규칙이 확립되지 않은 라벨은 검증불능-스코프외로 정직 분류한다. 공백은 보유로 본다.
HELD_LABELS = {"미상각분"}
DISPOSED_LABELS = {"양도자산"}


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "nan", "NaT")


class NonIntegerCell(ValueError):
    """원 단위 셀에 소수가 들어옴. 절사하면 판정이 왜곡되므로 검증불능으로 올린다."""


def _int_cell(v, label: str) -> int:
    """원 단위 정수 셀 해석 — 소수는 조용히 절사하지 않고 NonIntegerCell."""
    if _blank(v):
        raise ValueError(f"{label} 공백")
    f = float(v)
    if not f.is_integer():
        raise NonIntegerCell(f"{label} {v}")
    return int(f)


def _opt_int_cell(v, label: str) -> Optional[int]:
    """공백/컬럼부재는 None(=판별 폴백), 소수는 _int_cell과 동일하게 거부."""
    if _blank(v):
        return None
    return _int_cell(v, label)


def _carryover_cost(base: int, prev_acc: int, prev_book: Optional[int],
                    account: str) -> Tuple[Optional[bool], Optional[int], Optional[str]]:
    """이월자산의 (무형여부, 취득원가) 판정 → 불능이면 (None, None, 사유).

    1순위는 계정과목명 사전이 아니라 **대장 자체의 항등식**이다. 더존은 유형을
    간접법(취득원가·누계 병기), 무형을 직접법(순액)으로 싣기 때문에 전기말장부가액이
    어느 쪽 식을 만족하는지가 곧 표시방법이다:

        간접법(유형): 전기말장부가액 = 기초가액 − 전기말상각누계액   → cost = 기초가액
        직접법(무형): 전기말장부가액 = 기초가액                     → cost = 기초가액 + 누계

    전기말누계=0이면 두 식이 동시에 성립하나 그 행은 base==0 & capex>0(당기신규)라
    호출 전에 걸러진다. 실측(A사 3개년 + B사, 자산 142행): 유형 95 · 무형 8 ·
    양쪽성립 39(전부 당기신규) · 둘다불성립 0 · 사전과 충돌 0.

    사전은 폐기하지 않고 교차검증에 쓴다. 항등식과 사전이 어긋나면 한쪽을 조용히
    고르지 않고 검증불능으로 올린다 — 둘 중 무엇이 틀렸든 사람이 봐야 하는 행이다.
    """
    by_name = account in INTANGIBLE_ACCOUNTS
    if prev_book is None:
        # 항등식 불가(컬럼 부재/공백) → 사전 폴백 + 간접법 불변식 방어
        if by_name:
            return True, base + prev_acc, None
        if prev_acc > 0 and base <= prev_acc:
            return None, None, (f"해석모순(기초가액 {base:,} ≤ 전기말누계 {prev_acc:,}"
                                f" — 무형 직접상각 계정 '{account}' 미등록 의심"
                                f", 전기말장부가액 없어 항등식 판별 불가)")
        return False, base, None

    indirect = prev_book == base - prev_acc
    direct = prev_book == base
    if indirect and direct:
        by_id = by_name                     # 누계 0 — 어느 쪽이든 cost 동일
    elif indirect:
        by_id = False
    elif direct:
        by_id = True
    else:
        return None, None, (f"항등식불성립(기초 {base:,} − 누계 {prev_acc:,} ≠ 장부 {prev_book:,}"
                            f" 이고 장부 ≠ 기초 — 유형 간접법도 무형 직접법도 아님)")
    if by_id != by_name:
        return None, None, (f"판별충돌(항등식={'무형' if by_id else '유형'} vs "
                            f"계정과목명 '{account}'={'무형' if by_name else '유형'}"
                            f" — 기초 {base:,} / 누계 {prev_acc:,} / 장부 {prev_book:,})")
    return by_id, (base + prev_acc) if by_id else base, None


def classify_asset(base: int, prev_acc: int, prev_book: Optional[int], capex: int,
                   account: str) -> Tuple[Optional[bool], Optional[int], Optional[str]]:
    """더존 대장 1행의 (무형여부, 취득원가) 판정 — **두 저장소가 공유하는 단일 기준**.

    dep_verify/parsers/douzone_to_standard.py 가 이 함수를 import 해서 쓴다. 사본을
    만들지 말 것: 판별 로직이 두 벌이던 동안 같은 B사 대장에서 두 도구가 무형 2건의
    취득원가를 다르게 냈다(무형A 1,000 vs 37,000,000 / 무형B 51,666,667 vs 100,000,000).

    당기신규(기초0 & 신규취득>0)는 취득원가가 표시방법과 무관하게 신규취득액이고,
    항등식은 전기말누계 0이라 축퇴한다. 이 해에는 계정과목명 사전이 유일한 신호지만
    판정 결과에 영향이 없다 — 취득 1차연도는 당기말상각누계액 = 당기상각비라 verdict가
    비교하는 두 축(무형=당기상각비 / 유형=누계)이 수치로 일치하기 때문이다. 이월된
    2차연도부터는 항등식이 판별을 넘겨받는다.
    """
    if base == 0 and capex > 0:
        return account in INTANGIBLE_ACCOUNTS, capex, None
    return _carryover_cost(base, prev_acc, prev_book, account)


_TOTAL_LABELS = {"소계", "합계", "총계", "계"}


def _structural(row, cols) -> bool:
    """소계/합계 등 비자산 행 — 상감법 공백이고 자산명이 공백 또는 집계 라벨.

    집계 라벨은 정확 일치 또는 소계/합계/총계 접미사('계정과목총계' 등 더존 변형).
    상감법이 채워진 행은 자산명이 무엇이든 자산행으로 취급하므로 '온도계' 같은
    자산명과 충돌하지 않는다.
    """
    if not _blank(row.get(cols["method"])):
        return False
    name = row.get(cols["asset_name"])
    if _blank(name):
        return True
    label = re.sub(r"\s", "", str(name))
    return label in _TOTAL_LABELS or label.endswith(("소계", "합계", "총계"))


def _ident(row, cols) -> dict:
    """판정 불능 행에도 붙이는 식별 정보 (보고서용)."""
    return {
        "asset_code": None if _blank(row.get(cols["asset_code"])) else str(row.get(cols["asset_code"])).strip(),
        "asset_name": None if _blank(row.get(cols["asset_name"])) else str(row.get(cols["asset_name"])).strip(),
    }


def _row_to_asset(row, cols, fy: int, fye: int) -> Tuple[Optional[dict], Optional[Tuple[dict, str]]]:
    """자산행 1개 해석 → (자산 dict, None) 또는 (None, (부분 dict, 검증불능 사유))."""
    ident = _ident(row, cols)

    method = str(row.get(cols["method"], "")).strip()
    if method not in SUPPORTED_METHODS:
        return None, (ident, f"스코프외-상각방법({method})")

    label = "" if _blank(row.get(cols["category"])) else str(row.get(cols["category"])).strip()
    if label and label not in HELD_LABELS and label not in DISPOSED_LABELS:
        return None, (ident, f"스코프외-처분구분({label} — 재계산 규칙 미확립)")
    disposed = label in DISPOSED_LABELS

    try:
        base = _int_cell(row[cols["beginning"]], "기초가액")
        prev_acc = _int_cell(row[cols["prev_acc"]], "전기말상각누계액")
        capex = _int_cell(row[cols["capex"]], "신규취득및증가")
        life = _int_cell(row[cols["life"]], "연수")
        exp_dep = _int_cell(row[cols["exp_dep"]], "당기상각비범위액")
        exp_acc = _int_cell(row[cols["exp_acc"]], "당기말상각누계액")
        exp_bk = _int_cell(row[cols["exp_bk"]], "당기말장부가액")
        prev_book = _opt_int_cell(row.get(cols["prev_book"]), "전기말장부가액")
        dt = pd.to_datetime(row[cols["acq_date"]])
    except NonIntegerCell as e:
        return None, (ident, f"비정수셀({e} — 원 단위 절사 금지)")
    except (KeyError, ValueError, TypeError) as e:
        return None, (ident, f"필드결손({e})")

    if base > 0 and capex > 0:
        # 이월자산 + 당기 자본적지출: 대장에 증가월이 없어 재계산 불가 (V2 과제)
        return None, (ident, "스코프외-당기증가조합(증가월 미상)")

    account = str(row.get(cols["account"], "")).strip()
    intang, cost, why = classify_asset(base, prev_acc, prev_book, capex, account)
    if why is not None:
        return None, (ident, why)

    a = {
        "fy": fy, "fye": fye, "intang": intang, "cost": cost, "life": life,
        "acq_y": int(dt.year), "acq_m": int(dt.month), "disposed": disposed,
        "method": method, "prev_acc": prev_acc,
        "exp_dep": exp_dep, "exp_acc": exp_acc, "exp_bk": exp_bk,
        "account": account,          # 적법성 점검(업무용승용차 식별)에 쓰인다
        **ident,
    }
    if disposed:
        try:
            dp = pd.to_datetime(row[cols["disposal_date"]])
            a["disp_y"], a["disp_m"] = int(dp.year), int(dp.month)
        except (KeyError, ValueError, TypeError) as e:
            return None, (ident, f"필드결손(양도일: {e})")
    return a, None


def read_ledger(path: str, fy: int, fye: int = 12,
                mapping: Optional[dict] = None,
                sheet=0) -> Tuple[List[dict], List[Tuple[dict, str]], int]:
    """대장 xlsx → (자산 dict 목록, 검증불능 (부분 dict, 사유) 목록, 구조행 스킵 수)."""
    cols = {**DOUZONE_COLUMNS, **(mapping or {})}
    df = pd.read_excel(path, sheet_name=sheet)

    missing = [c for k, c in cols.items()
               if k in ("beginning", "prev_acc", "life", "method", "acq_date",
                        "exp_dep", "exp_acc", "exp_bk") and c not in df.columns]
    if missing:
        raise ValueError(f"대장에 필수 컬럼 없음: {missing} — 더존 표준 레이아웃이 아니면 --mapping 지정")

    assets, unreadable, structural = [], [], 0
    for _, row in df.iterrows():
        if _structural(row, cols):
            structural += 1                # 소계/합계 등 비자산 행
            continue
        a, bad = _row_to_asset(row, cols, fy, fye)
        if a is not None:
            assets.append(a)
        else:
            unreadable.append(bad)
    return assets, unreadable, structural
