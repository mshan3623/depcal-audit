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
Core 감가상각 엔진

프로덕션 레벨 - 코드 동결 상태
Enterprise Grade Quality ⭐⭐⭐⭐⭐

유지보수 정책:
- 현재 코드 변경 금지
- 세법 변경 시에만 업데이트
- 신규 기능은 별도 모듈로 추가
"""

from .depreciation_engine import calculate_depreciation_enhanced
from .dep_common import (
    DepreciationMethod,
    AssetFinancials,
    AssetInfo,
    MonthlyDepreciation
)

__all__ = [
    'calculate_depreciation_enhanced',
    'DepreciationMethod',
    'AssetFinancials',
    'AssetInfo',
    'MonthlyDepreciation'
]

__version__ = '2.0.0'
__status__ = 'Production'
