"""검증 산출물의 출처(provenance) — 감사조서 재현성용.

감사증거로 쓰이는 표는 "누가·언제·무엇을·어떤 기준으로" 계산했는지가 표 자체에 남아야
한다. 6개월 뒤 같은 대장을 같은 엔진으로 다시 돌렸을 때 같은 숫자가 나온다는 것을
증명할 수 없으면 그 표는 증거로서 약하다(2026-08-22 감사 지적 — 기존 보고서에는
FY·판정건수·기준만 있고 엔진 버전도 대상 파일의 동일성 근거도 없었다).

여기서 수집하는 것:
  - 엔진 버전      : vcore.__version__ (패키지 버전의 단일 진실원)
  - 소스 리비전    : git 커밋 해시 (최선 노력 — 설치본·git 부재 시 '미상')
  - 대장 파일 지문 : SHA-256. **어느 파일을 검증했는지의 유일한 확정 근거**다.
                     파일명은 바뀌고 수정본은 같은 이름으로 덮어써진다.
  - 실행 일시      : 로컬 타임존 포함 ISO 8601
"""
import hashlib
import os
import subprocess
from datetime import datetime, timezone

from vcore import __version__ as ENGINE_VERSION

_UNKNOWN = "미상"


def run_timestamp() -> str:
    """실행 일시 (로컬 타임존 오프셋 포함 ISO 8601)."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def source_revision() -> str:
    """git 커밋 해시 — 최선 노력.

    저장소에서 실행하면 짧은 해시를, 커밋되지 않은 변경이 있으면 '-dirty'를 붙인다.
    설치본(wheel)이나 git 부재 환경에서는 '미상(설치본)'을 반환한다 — 없는 정보를
    지어내지 않는다. dirty 표시는 "이 산출물은 커밋된 코드로 재현되지 않는다"는 경고다.

    **추적 파일만 본다**(`--untracked-files=no`). 미추적 디렉터리는 계산에 쓰이는 코드가
    아니므로, 그것 때문에 dirty가 붙으면 모든 보고서에 상시 경고가 찍혀 진짜 경고를
    가린다(감사 G17 — 실제로 `inbox/`·`projects/` 때문에 발화 중이었다).
    """
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        rev = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        if not rev:
            return f"{_UNKNOWN}(설치본)"
        dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain",
                                "--untracked-files=no"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return f"{rev}-dirty" if dirty else rev
    except (OSError, subprocess.SubprocessError):
        return f"{_UNKNOWN}(설치본)"


def file_digest(path: str) -> str:
    """대장 파일의 SHA-256 (검증 대상의 동일성 확정 근거)."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return _UNKNOWN
    return h.hexdigest()


def collect(ledger_path: str, fy: int, fye: int, tolerance: int,
            sheet=0, mapping_path: str = None) -> dict:
    """보고서에 기록할 출처 정보 일체."""
    return {
        "실행 일시": run_timestamp(),
        "엔진 버전": f"dep_vector {ENGINE_VERSION}",
        "소스 리비전": source_revision(),
        "대장 파일": os.path.basename(ledger_path),
        "대장 SHA-256": file_digest(ledger_path),
        "검증 회계연도": f"FY{fy}",
        "결산월": f"{fye}월",
        "시트": str(sheet),
        "컬럼 매핑": os.path.basename(mapping_path) if mapping_path else "더존 표준 레이아웃",
        "상각률 근거": "법인세법 시행령 [별표 4] (vcore/rate_table.py — 법령 PDF 대조 고정)",
        "허용차 설정": (f"±{tolerance:,}원 (감사인 설정)" if tolerance
                        else "0원 — 원단위 완전일치"),
    }
