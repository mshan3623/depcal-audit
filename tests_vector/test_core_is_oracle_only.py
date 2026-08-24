"""core는 테스트 전용 오라클이다 — 실행 경로가 core를 import하지 않음을 고정한다.

배경(2026-08-22 분석): core는 오래도록 "봉인된 레퍼런스"였지만 실제 지위가 모호했다.
asset_schedule_generator가 core 타입 3개를 import하고 있었고, 그것을 쓰던
`to_engine_format()`은 호출자가 0인 데드코드였다 — 즉 실행 경로는 이미 core 없이
돌고 있었는데 import 한 줄이 그 사실을 가리고 있었다.

그 줄을 걷어내 **실행 경로의 core 의존을 0으로 확정**했고, 이 파일이 그 경계를 지킨다.
core의 지위는 이제 명확하다:

    실행 경로 (vcore·depverify·asset_schedule_generator·웹·CLI) — core 없이 동작
    테스트     (동등성 회귀·상각률표 독립 증인)                  — core 필요

이 검사가 깨지면 둘 중 하나다. (a) 실행 경로가 다시 core에 의존하기 시작했다 —
장기 목표(core 박제)에서 멀어지는 변경이니 의도를 먼저 확인할 것. (b) 새 실행 경로
모듈이 생겼는데 _RUNTIME_MODULES에 등록되지 않았다 — 목록을 갱신할 것.

주의: 이 검사는 **core를 지워도 된다는 뜻이 아니다.** core를 치우면 동등성 회귀
432건과 상각률표의 독립 증인이 함께 사라진다(test_rate_table_statutory 참조).
"""
import ast
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 실행 경로 — 고객이 실제로 돌리는 코드. 여기서 core를 부르면 안 된다.
_RUNTIME_MODULES = [
    "asset_schedule_generator.py",
    "depcal.py",
    "dep_cal_web.py",
    "vcore/rate_table.py", "vcore/projection.py", "vcore/straight_line.py",
    "vcore/declining_balance.py", "vcore/monthly.py", "vcore/monthly_schedule.py",
    "vcore/capex.py", "vcore/disposal.py", "vcore/intangible.py",
    "vcore/separate_asset.py", "vcore/__init__.py",
    "depverify/__init__.py", "depverify/__main__.py", "depverify/reader.py",
    "depverify/report.py", "depverify/verdict.py", "depverify/provenance.py",
    "depverify/compliance.py",
]


def _imported_roots(path: str):
    """모듈이 import하는 최상위 패키지 이름 (함수 내부 지연 import 포함)."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_runtime_module_list_is_current():
    """목록이 실제 파일과 어긋나면(이름 변경·삭제) 검사가 조용히 무력해진다."""
    missing = [m for m in _RUNTIME_MODULES if not os.path.exists(os.path.join(_ROOT, m))]
    assert not missing, f"_RUNTIME_MODULES에 없는 파일이 있음: {missing}"


def test_every_runtime_package_module_is_listed():
    """vcore·depverify에 새 모듈이 생기면 목록에 등록되도록 강제한다."""
    for pkg in ("vcore", "depverify"):
        on_disk = {f"{pkg}/{f}" for f in os.listdir(os.path.join(_ROOT, pkg))
                   if f.endswith(".py")}
        assert on_disk <= set(_RUNTIME_MODULES), (
            f"{pkg}의 신규 모듈이 _RUNTIME_MODULES에 없음: "
            f"{sorted(on_disk - set(_RUNTIME_MODULES))}")


@pytest.mark.parametrize("module", _RUNTIME_MODULES)
def test_runtime_module_does_not_import_core(module):
    roots = _imported_roots(os.path.join(_ROOT, module))
    assert "core" not in roots, (
        f"{module}이 core를 import한다 — 실행 경로는 core 없이 동작해야 한다. "
        "의도한 변경이라면 이 테스트와 README의 엔진 레이어 설명을 함께 갱신할 것.")
