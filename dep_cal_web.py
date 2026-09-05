# Copyright 2026 Han Myeong Su
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
감가상각비 계산기 - Web Version
================================

Flask 기반 웹 인터페이스

Author: CPA Sean Han
Version: 1.0.0 (Web)
Date: 2025-12-05
"""

import os
from pathlib import Path
from datetime import datetime
import uuid
import threading
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException, NotFound

# 감가상각 계산 모듈 임포트
from asset_schedule_generator import generate_depreciation_schedule

import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

# 이 엔드포인트가 받는 JSON은 자산 1건의 스칼라 필드뿐이라 수십 바이트면 충분하다.
# 상한이 없으면 거대 본문이 파싱 단계에서 메모리를 먹는다 — Flask가 413으로 거절한다.
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024

# 프로젝트 루트 경로 (절대 경로 사용)
PROJECT_ROOT = Path(__file__).parent.absolute()

# 출력 폴더 설정
OUTPUT_FOLDER = PROJECT_ROOT / 'output'
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

# 파일 정리를 위한 딕셔너리 (파일경로: 생성시간)
generated_files = {}

# 10분 후 파일 자동 삭제
FILE_EXPIRY_SECONDS = 600


def cleanup_old_files():
    """오래된 파일 자동 삭제 (백그라운드 스레드).

    ⚠️ 단일 프로세스 전제: 만료 대상을 프로세스 메모리(generated_files)에만 들고 있어,
    다중 워커(gunicorn -w N 등)로 띄우면 워커마다 자기가 만든 파일만 지운다 — 남의
    워커가 만든 산출물은 output/에 무기한 남는다. 다중 워커로 운영하려면 만료 관리를
    프로세스 밖(파일 mtime 스캔 또는 외부 스토어)으로 옮겨야 한다 (2026-08-22 감사).
    """
    while True:
        time.sleep(60)  # 1분마다 체크
        current_time = time.time()
        files_to_remove = []

        for filepath, created_time in list(generated_files.items()):
            if current_time - created_time > FILE_EXPIRY_SECONDS:
                try:
                    if Path(filepath).exists():
                        Path(filepath).unlink()
                        print(f"[Cleanup] Deleted: {filepath}")
                except Exception as e:
                    print(f"[Cleanup Error] {filepath}: {e}")
                files_to_remove.append(filepath)

        for filepath in files_to_remove:
            generated_files.pop(filepath, None)


# 백그라운드 정리 스레드 시작
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()


#: 파일명에 허용하지 않는 문자 — 경로 분리자, 윈도우 예약문자, 상위 디렉터리 참조
_FORBIDDEN_IN_NAME = set('<>:"/\\|?*')
_MAX_NAME_LEN = 80


def _sanitize_asset_name(raw) -> str:
    """자산명을 파일명 조각으로 안전하게 만든다 (한글 보존).

    제거: 경로 분리자·윈도우 예약문자·제어문자(널바이트, 개행, RTL 오버라이드 등).
    치환: '..'(상위 디렉터리 참조)와 선행 점. 길이는 _MAX_NAME_LEN로 자른다.
    전부 걸러져 빈 문자열이 되면 'asset'으로 대체한다 — 파일명이 구분자로만 남는 것을 막는다.
    """
    text = str(raw)
    cleaned = "".join(
        c for c in text
        if c not in _FORBIDDEN_IN_NAME and c.isprintable() and not c.isspace()
    )
    cleaned = cleaned.replace("..", "").lstrip(".")
    cleaned = cleaned[:_MAX_NAME_LEN]
    return cleaned or "asset"


@app.route('/')
def index():
    """메인 페이지"""
    return render_template('calculator.html')


@app.route('/calculate', methods=['POST'])
def calculate():
    """감가상각 계산 처리"""
    try:
        data = request.get_json()

        # 필수 파라미터 검증
        required_fields = ['asset_name', 'acquisition_date', 'acquisition_cost',
                          'useful_life', 'asset_type', 'depreciation_method']

        for field in required_fields:
            if field not in data or data[field] is None:
                return jsonify({
                    'success': False,
                    'error': f'필수 항목이 누락되었습니다: {field}'
                }), 400

        # 고유 파일명 생성. 자산명이 파일명에 들어가므로 살균은 필수다 —
        # secure_filename은 비ASCII를 통째로 버려 한글 자산명을 파괴하므로 쓰지 않고,
        # 경로 분리자·제어문자·길이만 직접 막는다(다운로드 경로 이탈은 아래 참조).
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = _sanitize_asset_name(data['asset_name'])
        safe_filename = f"depreciation_{safe_name}_{timestamp}_{unique_id}.xlsx"
        output_path = OUTPUT_FOLDER / safe_filename

        # 감가상각 계산 실행
        result_path = generate_depreciation_schedule(
            asset_name=data['asset_name'],
            acquisition_date=data['acquisition_date'],
            acquisition_cost=int(data['acquisition_cost']),
            useful_life=int(data['useful_life']),
            asset_type=data['asset_type'],
            depreciation_method=data['depreciation_method'],
            disposal_date=data.get('disposal_date'),
            disposal_amount=int(data['disposal_amount']) if data.get('disposal_amount') else None,
            increase_date=data.get('increase_date'),
            increase_amount=int(data['increase_amount']) if data.get('increase_amount') else None,
            # 결산월 — 없으면 12월 결산. 종전에는 폼에 필드 자체가 없어 3월 결산법인이
            # 12월 결산 표를 받았고, 그 사실이 산출물 어디에도 적히지 않았다.
            fiscal_year_end_month=int(data.get('fiscal_year_end_month') or 12),
            output_path=str(output_path)
        )

        # 파일 생성 시간 기록 (자동 삭제용)
        generated_files[result_path] = time.time()

        return jsonify({
            'success': True,
            'message': f'감가상각 스케줄이 생성되었습니다.',
            'filename': safe_filename
        })

    except HTTPException:
        # 413(본문 초과) 등 Flask가 정한 응답은 그대로 내보낸다. 아래 광범위한
        # except Exception이 이걸 먼저 삼키면 413이 500으로 뭉개진다(테스트가 잡음).
        raise
    except (ValueError, TypeError) as e:
        return jsonify({
            'success': False,
            'error': f'입력값 오류: {str(e)}'
        }), 400
    except Exception as e:
        # 내부 오류 상세는 서버 로그에만 남기고 응답에는 노출하지 않음
        app.logger.exception('계산 중 오류 발생')
        return jsonify({
            'success': False,
            'error': '계산 중 오류가 발생했습니다. 입력값을 확인 후 다시 시도해주세요.'
        }), 500


@app.route('/download/<filename>')
def download(filename):
    """결과 파일 다운로드"""
    try:
        # send_from_directory가 경로 이탈(../ 등)을 차단하고 폴더 밖 접근은 404 처리
        return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)
    except NotFound:
        return jsonify({'error': '파일을 찾을 수 없습니다. 다시 계산해주세요.'}), 404
    except HTTPException:
        raise
    except Exception:
        app.logger.exception('파일 다운로드 중 오류 발생')
        return jsonify({'error': '파일 다운로드 중 오류가 발생했습니다.'}), 500


if __name__ == '__main__':
    # 이 앱에는 인증·권한·감사로그가 없다. 고객 자산대장 수치를 다루므로 기본은
    # 루프백 바인딩이고, 외부 노출은 환경변수로 **명시적으로 선택**해야 한다
    # (과거 기본값 0.0.0.0은 실행하는 순간 사내망 전체에 무인증 공개였다).
    # 외부 제공이 필요하면 리버스 프록시 뒤에서 인증을 붙이고 HOST를 넘길 것.
    HOST = os.environ.get('DEP_CAL_HOST', '127.0.0.1')
    PORT = int(os.environ.get('DEP_CAL_PORT', '5002'))

    print("=" * 70)
    print("감가상각비 계산기 - Web Version")
    print("Depreciation Calculator (Korean Tax Law)")
    print("=" * 70)
    print()
    print(f"Starting Flask server on port {PORT}...")
    print()
    print("Access URLs:")
    print(f"  Local:    http://localhost:{PORT}")
    if HOST not in ('127.0.0.1', 'localhost', '::1'):
        print(f"  Network:  http://<server-ip>:{PORT}")
        print()
        print("  ⚠️ 경고: 루프백 밖({}) 바인딩입니다. 이 앱은 인증이 없습니다 —".format(HOST))
        print("     신뢰할 수 없는 망에 노출하지 마세요.")
    else:
        print("  (외부 노출하려면 DEP_CAL_HOST=0.0.0.0 — 인증 없음에 유의)")
    print()
    print("Port assignments:")
    print("  GLKR:     5000")
    print("  PCBL:     5001")
    print("  Dep_Cal:  5002")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 70)

    # debug=True는 Werkzeug 대화형 디버거가 네트워크에 노출되어 원격 코드 실행이 가능하므로 금지
    app.run(debug=False, host=HOST, port=PORT)
