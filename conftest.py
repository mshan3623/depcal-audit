"""pytest 공통 설정.

core·vcore·depverify는 정규 패키지이므로 경로 조작이 필요 없다(`pip install -e .`
또는 pytest의 rootdir 자동 등록으로 해결). sample_data/는 패키지가 아닌 실데이터
하네스 디렉터리라, `import verify_ledger`를 위해 여기만 등록한다.

실행 인터프리터 (감사 G25 — 어디에도 적혀 있지 않아 로컬 skip을 결함으로 오인하기 쉽다):
  · 시스템 python3 → Flask가 없어 웹 테스트가 skip된다. 계산·검증 로직에는 영향 없음.
  · `~/Python_envs/main/bin/python` → Flask·pytest-cov 포함, 웹 테스트까지 전부 실행된다.
    커버리지를 재려면 이 인터프리터를 쓴다. CI는 Flask를 설치하므로 skip이 없다.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_ROOT, "sample_data"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
