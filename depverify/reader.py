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
# 조용히 유형으로 잡혀 취득원가가 순장부가로 축소된다(B사 '무형B' 실측:
# 사전 제거 시 cost 100,000,000 → 51,666,667). 그래서 1순위는 사전이 아니라 항등식.
INTANGIBLE_ACCOUNTS = {
    "영업권", "산업재산권", "특허권", "실용신안권", "의장권", "디자인권", "상표권",
    "라이선스", "라이센스", "프랜차이즈", "개발비", "소프트웨어",
    "광업권", "어업권", "차지권", "임차권리금", "기타무형자산",
}

SUPPORTED_METHODS = {"정액법", "정률법"}

# 컬럼이 없을 때 **무엇이 불가능해지는지**. 기존에는 8개만 검사해서, 빠진 컬럼이
# `row.get` → 공백으로 흘러 판정을 조용히 왜곡했다(감사 G23): `capex`가 없으면 전 행이
# "필드결손"으로 사유가 오도되고, `category`·`disposal_date`가 없으면 **양도 자산이 전부
# '보유'로 재계산돼 '차이'로 뜬다**. 없는 채로 굴리지 않고 이유를 대며 멈춘다.
REQUIRED_COLUMNS = {
    "beginning": "기초가액 — 취득원가 재구성 불가",
    "prev_acc": "전기말상각누계액 — 취득원가 재구성·승계 대조 불가",
    "capex": "신규취득및증가 — 당기 신규취득 식별 불가(전 행이 '필드결손'으로 오도됨)",
    "life": "연수 — 별표4 상각률 결정 불가",
    "method": "상감법 — 정액/정률 구분 및 자산행/구조행 판별 불가",
    "acq_date": "취득일자 — 상각 개시월 결정 불가",
    "exp_dep": "당기상각비범위액 — 대조 대상 없음",
    "exp_acc": "당기말상각누계액 — 대조 대상 없음",
    "exp_bk": "당기말장부가액 — 대조 대상 없음",
    "category": "구분 — 양도/보유 판별 불가(양도 자산이 전부 '보유'로 재계산돼 거짓 '차이')",
    "disposal_date": "양도/폐기일 — 양도월 결정 불가(양도 자산이 전부 '보유'로 재계산됨)",
}

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


class AmbiguousDateCell(ValueError):
    """날짜 칸이 숫자다. pandas는 이를 epoch로 읽어 1970-01-01을 만든다."""


def _date_cell(v, label: str):
    """날짜 셀 해석 — 숫자 셀은 추정하지 않고 거부한다 (감사 G24).

    `pd.to_datetime(20220115)`는 나노초 epoch로 해석돼 **1970-01-01**이 된다. 판정은
    '차이'로 뜨니 조용한 통과는 아니지만, 보고서에 취득 1970-01이 찍혀 원인을 가린다.
    8자리 YYYYMMDD인지 엑셀 일련번호인지는 셀만 보고 확정할 수 없으므로 — 이 도구는
    조용한 추정을 하지 않는다 — 사유를 대며 멈추고 서식 수정을 요구한다.
    """
    if isinstance(v, bool) or (isinstance(v, (int, float)) and not pd.isna(v)):
        raise AmbiguousDateCell(
            f"{label}이 숫자 셀({v}) — 엑셀에서 날짜 서식으로 바꾼 뒤 다시 실행하세요")
    return pd.to_datetime(v)


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
    취득원가를 다르게 냈다(개발비 1,000 vs 37,000,000 / 무형B 51,666,667 vs 100,000,000).

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


_GRAND_TOTAL_LABELS = {"합계", "총계", "계"}


def _is_grand_total(label: str) -> bool:
    """대장 맨 아래 총계 행인가. 계정과목별 '소계'는 제외한다."""
    return (label in _GRAND_TOTAL_LABELS
            or (label.endswith(("합계", "총계")) and not label.endswith("소계")))


def _ledger_amounts(row, cols) -> Optional[dict]:
    """대장이 **표시한** (당기상각, 누계, 장부가). 판정 불능 행에도 통제합계 대사를 위해 읽는다."""
    out = {}
    for key, label in (("exp_dep", "당기상각비범위액"),
                       ("exp_acc", "당기말상각누계액"),
                       ("exp_bk", "당기말장부가액")):
        try:
            out[key] = _int_cell(row.get(cols[key]), label)
        except (ValueError, TypeError):
            return None
    return out


class ControlTotal:
    """대장 합계행 대사 결과 — 완전성의 유일한 독립 신호 (감사 G11).

    완전성은 방향이 반대다. 자산행을 아무리 뒤져도 '빠진 행'은 나오지 않는다. 리더가
    자산행을 구조행으로 오판해 버려도(예: 상감법 공백 + 자산명이 '…계'로 끝나는 행)
    지금까지는 검출 채널이 아예 없었다. 대장이 스스로 적어둔 합계와 맞춰보는 것이
    그 채널이다 — 실측 4개 대장이 맞았던 것은 드롭이 없었다는 뜻이지 검출기가
    있었다는 뜻이 아니다.

    합계행을 못 찾으면 `found=False`. 이때 '일치'라고 말하지 않는다 — 대사 불가다.
    """

    def __init__(self, control: Optional[dict], sums: dict, rows_summed: int,
                 rows_unsummed: int):
        self.found = control is not None
        self.label = control["label"] if control else ""
        self.ledger = {k: control[k] for k in ("exp_dep", "exp_acc", "exp_bk")} if control else {}
        self.summed = sums
        self.rows_summed = rows_summed
        self.rows_unsummed = rows_unsummed      # 금액을 못 읽어 합에서 빠진 데이터 행

    @property
    def deltas(self) -> dict:
        """합계행 − 자산행 합. 양수면 대장 합계가 더 크다 = 행이 빠졌을 수 있다."""
        return {k: self.ledger[k] - self.summed[k] for k in self.ledger} if self.found else {}

    @property
    def matched(self) -> bool:
        return self.found and not any(self.deltas.values())

    @property
    def reliable(self) -> bool:
        """대사 결과를 판정 근거로 쓸 수 있는가. 금액 못 읽은 행이 있으면 차이가 그 탓일 수 있다."""
        return self.found and self.rows_unsummed == 0

    def message(self) -> Optional[str]:
        if not self.found:
            return "대장 합계 대사 불가 — 합계행을 찾지 못했습니다(완전성 미검증)"
        if self.matched:
            return None
        d = self.deltas
        detail = (f"Δ당기상각 {d['exp_dep']:+,} · Δ누계 {d['exp_acc']:+,} · Δ장부가 {d['exp_bk']:+,}")
        tail = ("" if self.reliable
                else f" (금액을 읽지 못한 데이터 행 {self.rows_unsummed}건이 합에서 빠져 있음)")
        return (f"대장 합계 대사 불일치 — 합계행 '{self.label}' vs 자산행 "
                f"{self.rows_summed}건 합: {detail}{tail}")


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
        dt = _date_cell(row[cols["acq_date"]], "취득일자")
    except AmbiguousDateCell as e:
        return None, (ident, f"모호한날짜셀({e})")
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
            dp = _date_cell(row[cols["disposal_date"]], "양도/폐기일")
            a["disp_y"], a["disp_m"] = int(dp.year), int(dp.month)
        except AmbiguousDateCell as e:
            return None, (ident, f"모호한날짜셀({e})")
        except (KeyError, ValueError, TypeError) as e:
            return None, (ident, f"필드결손(양도일: {e})")
    return a, None


def read_ledger(path: str, fy: int, fye: int = 12,
                mapping: Optional[dict] = None,
                sheet=0) -> Tuple[List[dict], List[Tuple[dict, str]], int, "ControlTotal"]:
    """대장 xlsx → (자산 목록, 검증불능 (부분 dict, 사유) 목록, 구조행 수, 통제합계 대사).

    네 번째 값이 완전성 채널이다 — 자산행 합 vs 대장 합계행(감사 G11). 자세한 근거는
    `ControlTotal` docstring.
    """
    if mapping:
        # 오타 키는 조용히 무시되고 기본 컬럼명이 쓰인다 — 매핑을 줬는데 안 먹는 사고(G23)
        unknown = sorted(set(mapping) - set(DOUZONE_COLUMNS))
        if unknown:
            raise ValueError(
                f"--mapping에 알 수 없는 키: {unknown} — 사용 가능한 키: {sorted(DOUZONE_COLUMNS)}")
    cols = {**DOUZONE_COLUMNS, **(mapping or {})}
    df = pd.read_excel(path, sheet_name=sheet)

    missing = [f"{cols[k]}({why})" for k, why in REQUIRED_COLUMNS.items()
               if cols[k] not in df.columns]
    if missing:
        raise ValueError("대장에 필수 컬럼 없음 — 더존 표준 레이아웃이 아니면 --mapping 지정:\n  "
                         + "\n  ".join(missing))

    assets, unreadable, structural = [], [], 0
    sums = {"exp_dep": 0, "exp_acc": 0, "exp_bk": 0}
    rows_summed = rows_unsummed = 0
    control = None
    for _, row in df.iterrows():
        if _structural(row, cols):
            structural += 1                # 소계/합계 등 비자산 행
            name = row.get(cols["asset_name"])
            label = "" if _blank(name) else re.sub(r"\s", "", str(name))
            amounts = _ledger_amounts(row, cols)
            if amounts is not None and _is_grand_total(label):
                control = {"label": label, **amounts}   # 뒤에 오는 총계가 이긴다(맨 아래가 총계)
            continue
        # 판정 가능 여부와 무관하게 대장이 표시한 금액을 합산한다 — 검증불능 행을
        # 빼고 더하면 합계가 안 맞는 게 당연해져 대사가 무의미해진다.
        amounts = _ledger_amounts(row, cols)
        if amounts is None:
            rows_unsummed += 1
        else:
            rows_summed += 1
            for k in sums:
                sums[k] += amounts[k]
        a, bad = _row_to_asset(row, cols, fy, fye)
        if a is not None:
            assets.append(a)
        else:
            unreadable.append(bad)
    return assets, unreadable, structural, ControlTotal(control, sums, rows_summed, rows_unsummed)
