"""상각률표 3자 대조 — 법령 PDF ↔ vcore ↔ core (봉인된 오라클)

상각률표는 이 엔진에서 유일하게 '외부에서 주어진 사실'이다. 계산 로직은 골든 손계산과
실데이터 대조가 지키지만, 표 자체는 지금까지 아무 테스트도 지키지 않았다 — 숫자 한 자리
오타가 전 스위트를 통과한 채 실무 산출물에 들어갈 수 있었다(2026-08-22 감사 지적).

3자 대조인 이유: vcore와 core는 같은 표를 **각자의 리터럴로** 들고 있다. 오라클이 검증
대상과 데이터를 공유하면 오라클이 아니므로 일부러 합치지 않았다. 셋 중 어느 하나에
오타가 들어가면 반드시 어긋난다.

  법령 PDF ──(전사)──> fixtures/byeolpyo4_rates.tsv ──> vcore.rate_table  (정본)
                                                  └──> core.dep_common    (독립 증인)
"""
import os
import shutil
import subprocess
import re

import pytest

from core.dep_common import (
    STRAIGHT_LINE_RATES as CORE_SL,
    DECLINING_BALANCE_RATES as CORE_DB,
)
from vcore.rate_table import (
    STATUTORY_PERMILLE,
    STRAIGHT_LINE_RATES as VCORE_SL,
    DECLINING_BALANCE_RATES as VCORE_DB,
    LIFE_YEARS_RANGE,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_FIXTURE = os.path.join(_HERE, "fixtures", "byeolpyo4_rates.tsv")
_PDF = os.path.join(os.path.dirname(_HERE), "legal", "정률법정액법상각률.pdf")


def _law_table():
    """법령측 기준점(픽스처) → {내용연수: (정액 1000분율, 정률 1000분율)}."""
    table = {}
    with open(_FIXTURE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("내용연수"):
                continue
            n, sl, db = line.split("\t")
            table[int(n)] = (int(sl), int(db))
    return table


LAW = _law_table()


def test_law_fixture_is_complete():
    """별표4는 내용연수 2~60년을 빠짐없이 수록한다 — 결손이 있으면 대조가 무의미하다."""
    assert sorted(LAW) == list(range(2, 61))


@pytest.mark.parametrize("life", sorted(LAW))
def test_vcore_table_matches_law(life):
    """정본(vcore)이 법령 표와 1000분율 정수 단위로 일치한다."""
    assert STATUTORY_PERMILLE[life] == LAW[life], f"내용연수 {life}년 표 이탈"


@pytest.mark.parametrize("life", sorted(LAW))
def test_core_oracle_table_matches_law(life):
    """독립 증인(봉인된 core)도 법령 표와 일치한다. vcore와 별개 리터럴이라 교차 검증이 된다."""
    sl_permille, db_permille = LAW[life]
    assert CORE_SL[life] == sl_permille / 1000, f"core 정액 {life}년 이탈"
    assert CORE_DB[life] == db_permille / 1000, f"core 정률 {life}년 이탈"


def test_vcore_and_core_agree_bitwise():
    """두 벌이 float 비트 단위로 동일하다 — vcore가 정수에서 유도해도 core 리터럴과 같다.

    이 등식이 깨지면 core를 오라클로 쓴 기존 1원 일치 회귀 전부가 의미를 잃는다.
    """
    assert VCORE_SL == CORE_SL
    assert VCORE_DB == CORE_DB


def test_life_years_range_matches_guards():
    """엔진 가드가 알리는 범위(2~60년)와 표의 실제 범위가 어긋나지 않는다."""
    assert LIFE_YEARS_RANGE == (2, 60)


@pytest.mark.skipif(shutil.which("pdftotext") is None,
                    reason="pdftotext(poppler) 미설치 — 픽스처 대조는 위 테스트가 수행")
def test_fixture_matches_source_pdf():
    """픽스처가 법령 PDF 원문과 일치한다 — 전사본이 원본에서 표류하지 않았음을 닫는다.

    poppler가 있는 환경에서만 실행된다. 없으면 픽스처가 법령측 기준점 역할을 계속한다.
    """
    assert os.path.exists(_PDF), f"법령 원문 PDF 없음: {_PDF}"
    out = subprocess.run(["pdftotext", "-layout", _PDF, "-"],
                         capture_output=True, text=True, check=True).stdout
    extracted = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(\d{3})\s+(\d{3})\s*$", line)
        if m:
            n = int(m.group(1))
            if 2 <= n <= 60:
                extracted[n] = (int(m.group(2)), int(m.group(3)))
    assert extracted == LAW, "픽스처가 법령 PDF와 어긋남 — 픽스처를 PDF에서 재생성할 것"
