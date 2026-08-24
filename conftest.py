"""pytest 공통 설정.

core·vcore·depverify는 정규 패키지이므로 경로 조작이 필요 없다(`pip install -e .`
또는 pytest의 rootdir 자동 등록으로 해결). sample_data/는 패키지가 아닌 실데이터
하네스 디렉터리라, `import verify_ledger`를 위해 여기만 등록한다.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_ROOT, "sample_data"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
