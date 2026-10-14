"""공개판 반입 스크립트의 fail-closed 배선 (감사 2026-10-14 M7·M9).

- M9: 반입이 공개판에 먼저 쓰고 게이트를 돌렸다 — 실패해도 누출 파일이 작업트리에 남았다.
  이제 임시 사본에서 반입·게이트를 하고, 통과했을 때만 공개판에 쓴다.
- M7: 동작 변경이 [Unreleased]에 쌓인 채 확정 버전 라벨로 공개판에 나간 것이 두 번(09-23·10-14).
  릴리스가 확정되지 않았으면 반입 자체를 막는다.
"""
import importlib.util
import os

import pytest

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "ci", "port_to_public.py")
if not os.path.exists(_PATH):                     # 공개판에는 이 스크립트가 없다(치환표 = 실명 대응표)
    pytest.skip("port_to_public.py 없음(공개판)", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("port_to_public", _PATH)
port = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(port)


CL = """# Changelog

## [Unreleased]
{unreleased}
## [3.8.0] - 2026-10-14

### Fixed
- 무언가
"""


def test_release_gate_passes_when_unreleased_is_empty_and_version_matches():
    assert port.release_problems(CL.format(unreleased="\n"), "3.8.0") == []


def test_release_gate_blocks_unreleased_entries():
    text = CL.format(unreleased="\n### Fixed\n- 동작 변경\n  이어지는 줄\n- 또 하나\n")
    fails = port.release_problems(text, "3.8.0")
    assert len(fails) == 1 and "[Unreleased]에 항목 2개" in fails[0]


def test_release_gate_blocks_version_label_mismatch():
    fails = port.release_problems(CL.format(unreleased="\n"), "3.7.0")
    assert len(fails) == 1 and "3.7.0" in fails[0] and "3.8.0" in fails[0]


def _snapshot(base):
    out = {}
    for root, _, files in os.walk(base):
        for f in files:
            p = os.path.join(root, f)
            out[os.path.relpath(p, base)] = open(p, "rb").read()
    return out


@pytest.fixture
def fake_public(tmp_path, monkeypatch):
    dst = tmp_path / "public"
    dst.mkdir()
    (dst / "LICENSE").write_text("공개판 전용 파일\n", encoding="utf-8")
    monkeypatch.setattr(port, "_src_release_problems", lambda: [])
    return str(dst)


def test_gate_failure_writes_nothing_to_public(fake_public):
    before = _snapshot(fake_public)
    fails = port.run(fake_public, dry_run=False, gate_fn=lambda base: ["누출 가짜"])
    assert fails == ["누출 가짜"]
    assert _snapshot(fake_public) == before


def test_gates_run_on_staged_copy_with_ported_files(fake_public):
    seen = {}

    def gate(base):
        seen["base"] = base
        seen["has_engine"] = os.path.exists(os.path.join(base, "vcore", "monthly.py"))
        seen["has_public_only"] = os.path.exists(os.path.join(base, "LICENSE"))
        return []

    port.run(fake_public, dry_run=True, gate_fn=gate)
    assert seen["base"] != fake_public                      # 공개판이 아니라 임시 사본에서
    assert seen["has_engine"] and seen["has_public_only"]   # 반입분 + 공개판 전용 파일 모두 검사 대상
    assert _snapshot(fake_public) == {"LICENSE": "공개판 전용 파일\n".encode()}   # dry-run은 쓰지 않음


def test_gate_pass_applies_to_public(fake_public):
    assert port.run(fake_public, dry_run=False, gate_fn=lambda base: []) == []
    assert os.path.exists(os.path.join(fake_public, "vcore", "monthly.py"))
    assert not os.path.exists(os.path.join(fake_public, "ci", "port_to_public.py"))   # 금지목록
