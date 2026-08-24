"""웹 앱(dep_cal_web) 경계 검사 — 입력 살균·경로 이탈·본문 상한.

이 앱은 지금까지 테스트가 전혀 없었다(2026-08-22 감사). 계산 정확성은 엔진 쪽 스위트가
지키므로 여기서는 **웹 경계만** 고정한다: 사용자 입력이 파일명·파일경로로 흘러가는 길과,
거절해야 할 요청이 실제로 거절되는지.
"""
import json

import pytest

pytest.importorskip("flask", reason="Flask 미설치 — 웹 extras(pip install -e '.[web]') 필요")

import dep_cal_web
from dep_cal_web import _sanitize_asset_name


@pytest.fixture
def client(tmp_path, monkeypatch):
    """산출물이 저장소 output/을 오염시키지 않도록 임시 폴더로 돌린다."""
    monkeypatch.setattr(dep_cal_web, "OUTPUT_FOLDER", tmp_path)
    dep_cal_web.app.config["TESTING"] = True
    return dep_cal_web.app.test_client()


VALID = {
    "asset_name": "기계장치",
    "acquisition_date": "2025-03-01",
    "acquisition_cost": 100_000_000,
    "useful_life": 5,
    "asset_type": "유형자산",
    "depreciation_method": "정액법",
}


# ── 파일명 살균 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw, forbidden", [
    ("../../etc/passwd", "/"),
    ("..\\..\\windows", "\\"),
    ("a:b*c?d|e", ":"),
    ('quote"name', '"'),
    ("<script>", "<"),
])
def test_sanitize_strips_path_and_reserved_chars(raw, forbidden):
    out = _sanitize_asset_name(raw)
    assert forbidden not in out
    assert ".." not in out
    assert not out.startswith(".")


def test_sanitize_strips_control_characters():
    """널바이트·개행·RTL 오버라이드가 파일명에 남으면 안 된다."""
    out = _sanitize_asset_name("자산\x00\n\r‮gnp.exe")
    assert "\x00" not in out and "\n" not in out and "‮" not in out


def test_sanitize_preserves_korean():
    """한글 자산명은 보존한다 — secure_filename을 쓰지 않는 이유."""
    assert _sanitize_asset_name("기계장치") == "기계장치"


def test_sanitize_caps_length():
    assert len(_sanitize_asset_name("가" * 500)) <= 80


def test_sanitize_falls_back_when_everything_stripped():
    """전부 걸러져도 빈 파일명 조각이 되지 않는다."""
    assert _sanitize_asset_name("///") == "asset"
    assert _sanitize_asset_name("") == "asset"


# ── /calculate ────────────────────────────────────────────────────────────
def test_calculate_happy_path_writes_into_output_folder(client, tmp_path):
    res = client.post("/calculate", json=VALID)
    assert res.status_code == 200, res.data
    body = res.get_json()
    assert body["success"] is True
    produced = list(tmp_path.iterdir())
    assert [p.name for p in produced] == [body["filename"]]


def test_calculate_missing_field_is_400(client):
    payload = {k: v for k, v in VALID.items() if k != "useful_life"}
    res = client.post("/calculate", json=payload)
    assert res.status_code == 400
    assert "useful_life" in res.get_json()["error"]


def test_calculate_engine_guard_surfaces_as_400(client):
    """엔진 입력 가드(ValueError)가 500이 아니라 400으로 나온다 — 사용자 입력 오류다."""
    res = client.post("/calculate", json={**VALID, "useful_life": 200})
    assert res.status_code == 400


def test_calculate_hostile_asset_name_stays_inside_output_folder(client, tmp_path):
    res = client.post("/calculate", json={**VALID, "asset_name": "../../../evil"})
    assert res.status_code == 200, res.data
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert written[0].parent == tmp_path      # 폴더 밖으로 새지 않았다


def test_oversized_body_is_rejected(client):
    """MAX_CONTENT_LENGTH 상한이 실제로 발동한다."""
    fat = {**VALID, "asset_name": "가" * 200_000}
    res = client.post("/calculate", data=json.dumps(fat),
                      content_type="application/json")
    assert res.status_code == 413


# ── /download ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("attack", [
    "../conftest.py",
    "....//....//etc/passwd",
    "%2e%2e%2fconftest.py",
])
def test_download_rejects_path_traversal(client, attack):
    res = client.get(f"/download/{attack}")
    assert res.status_code == 404


def test_download_returns_generated_file(client):
    filename = client.post("/calculate", json=VALID).get_json()["filename"]
    res = client.get(f"/download/{filename}")
    assert res.status_code == 200
    assert res.data[:2] == b"PK"          # xlsx = zip 컨테이너
