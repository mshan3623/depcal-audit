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
고정자산 감가상각비 계산 엔진 - Phase3 (최소 수정 버전)
===========================================================

■ 핵심 원칙 (2026-02-01 확립)
  결산 마감 → 감가상각비·감가상각누계액 확정 → 다음 해 기초 장부가
  - 매 회계연도 말 감가상각 누적액은 보정된 금액으로 확정된다
  - 다음 해는 확정된 누적에서 출발한다
  - 전기말 장부가액은 결산 확정 상수값이다 (엔진도 동일값 산출)
  - 분리자산: 쪼개도 합계는 확정 누적과 일치해야 한다 (엔진의 자기 일관성)
  - 감가상각은 비망가(1,000원)까지만 상각한다
  - 모든 계산은 반드시 이 엔진으로만 수행한다 (수동계산 금지)

✅ 기존 코드 유지 + 최소한의 개선만 적용
✅ 더존 상수 원칙 준수
✅ 무형자산 전용 논리 적용
✅ 파일간 인터페이스 100% 호환성 유지
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union
from enum import Enum
from datetime import datetime, date, timedelta
import logging
import calendar
import math
from decimal import Decimal, ROUND_HALF_UP
import traceback

# utils.py에서 공통 유틸리티 함수 import (중복 제거)
from .utils import safe_int_conversion

# ================================
# 로깅 설정
# ================================

logger = logging.getLogger(__name__)

# ================================
# 상수 정의
# ================================

# 정액법 상각률 테이블 (한국 법인세법기준)
# 출처: 법인세법 [별표 4] 감가상각자산의 상각률표 (제15조제2항관련)
# 파일: C:\python-study\dep_api\fixed_asset\정률법정액법상각률.pdf
# 단위: 할분리(1/1000) -> 소수 변환
# 업데이트: 2025-08-07 (법인세법 공식 상각률표 기준 수정)
STRAIGHT_LINE_RATES = {
    2: 0.500,   # 500/1000
    3: 0.333,   # 333/1000
    4: 0.250,   # 250/1000
    5: 0.200,   # 200/1000
    6: 0.166,   # 166/1000
    7: 0.142,   # 142/1000
    8: 0.125,   # 125/1000
    9: 0.111,   # 111/1000
    10: 0.100,  # 100/1000
    11: 0.090,  # 090/1000
    12: 0.083,  # 083/1000
    13: 0.076,  # 076/1000
    14: 0.071,  # 071/1000
    15: 0.066,  # 066/1000
    16: 0.062,  # 062/1000
    17: 0.058,  # 058/1000
    18: 0.055,  # 055/1000
    19: 0.052,  # 052/1000
    20: 0.050,  # 050/1000
    21: 0.048,  # 048/1000
    22: 0.046,  # 046/1000
    23: 0.044,  # 044/1000
    24: 0.042,  # 042/1000
    25: 0.040,  # 040/1000
    26: 0.039,  # 039/1000
    27: 0.037,  # 037/1000
    28: 0.036,  # 036/1000
    29: 0.035,  # 035/1000
    30: 0.034,  # 034/1000
    31: 0.033,  # 033/1000
    32: 0.032,  # 032/1000
    33: 0.031,  # 031/1000
    34: 0.030,  # 030/1000
    35: 0.029,  # 029/1000
    36: 0.028,  # 028/1000
    37: 0.027,  # 027/1000
    38: 0.027,  # 027/1000 (동일)
    39: 0.026,  # 026/1000
    40: 0.025,  # 025/1000
    41: 0.025,  # 025/1000 (동일)
    42: 0.024,  # 024/1000
    43: 0.024,  # 024/1000 (동일)
    44: 0.023,  # 023/1000
    45: 0.023,  # 023/1000 (동일)
    46: 0.022,  # 022/1000
    47: 0.022,  # 022/1000 (동일)
    48: 0.021,  # 021/1000
    49: 0.021,  # 021/1000 (동일)
    50: 0.020,  # 020/1000
    51: 0.020,  # 020/1000 (동일)
    52: 0.020,  # 020/1000 (동일)
    53: 0.019,  # 019/1000
    54: 0.019,  # 019/1000 (동일)
    55: 0.019,  # 019/1000 (동일)
    56: 0.018,  # 018/1000
    57: 0.018,  # 018/1000 (동일)
    58: 0.018,  # 018/1000 (동일)
    59: 0.017,  # 017/1000
    60: 0.017   # 017/1000 (동일)
}

# 정률법 상각률 테이블 (한국 법인세법기준)
# 출처: 법인세법 [별표 4] 감가상각자산의 상각률표 (제15조제2항관련)
# 파일: C:\python-study\dep_api\fixed_asset\정률법정액법상각률.pdf
# 단위: 할분리(1/1000) -> 소수 변환
# 업데이트: 2025-08-07 (법인세법 공식 상각률표 기준 수정)
DECLINING_BALANCE_RATES = {
    2: 0.777,   # 777/1000 
    3: 0.632,   # 632/1000
    4: 0.528,   # 528/1000
    5: 0.451,   # 451/1000
    6: 0.394,   # 394/1000
    7: 0.349,   # 349/1000
    8: 0.313,   # 313/1000
    9: 0.284,   # 284/1000
    10: 0.259,  # 259/1000
    11: 0.239,  # 239/1000
    12: 0.221,  # 221/1000
    13: 0.206,  # 206/1000
    14: 0.193,  # 193/1000
    15: 0.182,  # 182/1000
    16: 0.171,  # 171/1000
    17: 0.162,  # 162/1000
    18: 0.154,  # 154/1000
    19: 0.146,  # 146/1000
    20: 0.140,  # 140/1000
    21: 0.133,  # 133/1000
    22: 0.128,  # 128/1000
    23: 0.123,  # 123/1000
    24: 0.118,  # 118/1000
    25: 0.113,  # 113/1000
    26: 0.109,  # 109/1000
    27: 0.106,  # 106/1000
    28: 0.102,  # 102/1000
    29: 0.099,  # 099/1000
    30: 0.096,  # 096/1000
    31: 0.093,  # 093/1000
    32: 0.090,  # 090/1000
    33: 0.087,  # 087/1000
    34: 0.085,  # 085/1000
    35: 0.083,  # 083/1000
    36: 0.080,  # 080/1000
    37: 0.078,  # 078/1000
    38: 0.076,  # 076/1000
    39: 0.074,  # 074/1000
    40: 0.073,  # 073/1000
    41: 0.071,  # 071/1000
    42: 0.069,  # 069/1000
    43: 0.068,  # 068/1000
    44: 0.066,  # 066/1000
    45: 0.065,  # 065/1000
    46: 0.064,  # 064/1000
    47: 0.062,  # 062/1000
    48: 0.061,  # 061/1000
    49: 0.060,  # 060/1000
    50: 0.059,  # 059/1000
    51: 0.058,  # 058/1000
    52: 0.056,  # 056/1000
    53: 0.055,  # 055/1000
    54: 0.054,  # 054/1000
    55: 0.054,  # 054/1000 (동일)
    56: 0.053,  # 053/1000
    57: 0.052,  # 052/1000
    58: 0.051,  # 051/1000
    59: 0.050,  # 050/1000
    60: 0.049   # 049/1000
}

# 기본 정률법 상각률 (10년 초과시)
DEFAULT_DECLINING_RATE = 0.100

# 최소 비망가액 (한국 세법 기준: 1,000원)
# 법령은 min(취득가액×5%, 1,000원)이나 자산계상 하한 관행(100만원 초과만 자산계상)
# 아래에서는 항상 1,000원으로 확정된다 — 근거 전문은 vcore/projection.py MEMORANDUM 참조.
MIN_MEMORANDUM_VALUE = 1000

# 기본 내용연수
DEFAULT_USEFUL_LIFE = 5

# ================================
# 데이터클래스 정의
# ================================
# Note: safe_int_conversion은 utils.py에서 import (중복 제거)

class DepreciationMethod(Enum):
    """감가상각 방법 열거형"""
    STRAIGHT_LINE = "정액법"
    DECLINING_BALANCE = "정률법"
    INTANGIBLE = "무형자산"

class AssetStatus(Enum):
    """자산 상태"""
    ACTIVE = "사용중"
    DISPOSED = "처분완료"
    SCRAPPED = "폐기완료"

@dataclass
class AssetFinancials:
    """자산 재무 정보"""
    cost: int                           # 취득원가
    life_in_years: int                   # 내용연수 (년)
    start_date: str                      # 취득일자 (YYYY-MM-DD)
    method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE
    salvage_value: int = 0             # 잔존가액
    memorandum_value: int = 1000       # 비망가액

    # 양도/폐기 처리 관련
    disposal_date: str = None          # 양도일자/폐기일자 (YYYY-MM-DD, 전부양도/폐기인 경우)
    disposal_amount: int = 0           # 당기감소액 (부분양도용, 취득원가 기준)

    # 증가 처리 관련 (유형자산 전용)
    increase_amount: int = 0           # 증가액 (기중 증가분)
    increase_date: str = None          # 증가일자 (YYYY-MM-DD)

    # 분리자산 처리 (전기말 기초값 사용)
    prior_accumulated: int = None      # 전기말상각누계액 (외부 기초값, 분리자산 등)
    target_year: int = None            # 당기 연도 (분리자산 계산 시 사용)

    def __post_init__(self):
        """데이터 검증 및 초기화"""
        if self.cost < 0:
            raise ValueError("취득원가는 0 이상이어야 합니다.")
        if self.life_in_years <= 0:
            raise ValueError("내용연수는 1년 이상이어야 합니다.")
        if self.salvage_value < 0:
            raise ValueError("잔존가액은 0 이상이어야 합니다.")
        if self.salvage_value >= self.cost:
            raise ValueError("잔존가액은 취득원가보다 작아야 합니다.")
        if self.memorandum_value < MIN_MEMORANDUM_VALUE and self.method != DepreciationMethod.INTANGIBLE:
            self.memorandum_value = MIN_MEMORANDUM_VALUE
        # 자본적지출은 자산 취득 이후에만 가능 (회계 원칙: 취득 전 자본적지출 발생 불가)
        if self.increase_date and self.increase_date < self.start_date:
            raise ValueError(f"자본적지출 일자({self.increase_date})는 취득일({self.start_date}) 이후여야 합니다.")
    
    @property
    def depreciable_amount(self) -> int:
        """감가상각 대상 금액 (정수 반환으로 개선)"""
        return int(self.cost - self.salvage_value)

@dataclass
class AssetInfo:
    """자산 기본 정보"""
    asset_id: str                        # 자산코드
    asset_name: str                      # 자산명
    asset_category: str = ""             # 자산분류
    status: AssetStatus = AssetStatus.ACTIVE
    
    def __post_init__(self):
        """데이터 검증"""
        if not self.asset_id.strip():
            raise ValueError("자산코드는 필수입니다.")
        if not self.asset_name.strip():
            raise ValueError("자산명은 필수입니다.")

@dataclass
class MonthlyDepreciation:
    """월별 감가상각 정보"""
    year: int                           # 연도
    month: int                          # 월
    monthly_depreciation: Union[int, str]  # 월 감가상각비 (또는 '-')
    accumulated_depreciation: int     # 누적 감가상각비
    book_value: int                   # 장부가액
    calculation_method: str = ""        # 계산 방법
    is_partial_month: bool = False      # 부분월 여부
    is_last_month: bool = False        # 최종월 여부
    
    def __post_init__(self):
        """데이터 검증 및 조정"""
        if self.year < 1900 or self.year > 2100:
            raise ValueError("연도가 유효하지 않습니다.")
        if self.month < 1 or self.month > 12:
            raise ValueError("월이 유효하지 않습니다.")
        if self.accumulated_depreciation < 0:
            raise ValueError("누적 감가상각비는 0 이상이어야 합니다.")
        if self.book_value < 0:
            logger.warning(f"{self.year}년 {self.month}월 장부가액이 음수입니다: {self.book_value}")
    
    @property
    def is_zero_depreciation(self) -> bool:
        """감가상각비가 0인지 확인"""
        return self.monthly_depreciation == 0 or self.monthly_depreciation == '-'
    
    @property
    def numeric_depreciation(self) -> int:
        """숫자형 감가상각비 반환 (정수 반환으로 개선)"""
        if isinstance(self.monthly_depreciation, (int, float)):
            return int(self.monthly_depreciation)
        else:
            return 0

@dataclass
class YearlySummary:
    """회계기간(fiscal year) 감가상각 요약. year 필드는 결산일이 속한 회계연도."""
    year: int                           # 회계연도 (결산일 속한 연도)
    yearly_depreciation: int          # 회계기간 감가상각비
    accumulated_depreciation: int     # 회계기간 말 누적 감가상각비
    ending_book_value: int           # 회계기간 말 장부가액
    months_count: int = 0              # 회계기간 내 감가상각 발생 개월수
    average_monthly: int = 0       # 월평균 감가상각비

    def __post_init__(self):
        """통계 계산 (정수 나눗셈으로 개선)"""
        if self.months_count > 0:
            self.average_monthly = self.yearly_depreciation // self.months_count

@dataclass
class FiscalPeriodSummary:
    """단일 회계기간 요약 (당기 요약). dep_verify의 company_* 어휘와 1:1 매칭."""
    fiscal_year: int                   # 회계연도 (결산일 속한 연도)
    fiscal_year_end_month: int         # 결산월 (1~12)
    period_start_date: str             # 회계기간 시작일 (YYYY-MM-DD)
    period_end_date: str               # 회계기간 종료일 (YYYY-MM-DD)
    period_depreciation: int           # 당기 감가상각비
    period_end_accumulated: int        # 당기말 감가상각누계액
    period_end_book_value: int         # 당기말 장부가액
    months_in_period: int              # 회계기간 내 감가상각 발생 개월수

@dataclass
class DepreciationResult:
    """감가상각 계산 결과. fiscal_year_end_month는 계산 컨텍스트 보존 (필수)."""
    asset_info: AssetInfo
    fiscal_year_end_month: int           # 결산월 (1~12, 필수, 계산 컨텍스트 보존)
    schedule: List[MonthlyDepreciation] = field(default_factory=list)
    yearly_summary: List[YearlySummary] = field(default_factory=list)
    total_depreciation: int = 0
    final_book_value: int = 0
    calculation_method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE
    calculation_time_ms: float = 0

# ================================
# 날짜 유틸리티 함수들
# ================================

def parse_date_safe(date_str: str) -> Tuple[int, int, int]:
    """날짜 파싱 — 해석할 수 없으면 ValueError. 기본값으로 대체하지 않는다.

    이름의 'safe'는 예외를 삼킨다는 뜻이 **아니다**(감사 G18-①·②). 종전에는 어떤 오류든
    2020-01-01을 돌려줘서, `'2020-13-99'`나 `'날짜아님'`이 무예외로 통과하고
    `calculation_success=True`에 그럴듯한 상각액까지 나왔다. 상위의 날짜 가드
    (`depreciation_engine.py`)도 이 함수가 절대 raise하지 않아 죽은 코드였다.

    core는 vcore의 거울(오라클)이다. 오라클이 오타 입력에 그럴듯한 값을 내면 거울
    스윕이 vcore의 결함을 가릴 수 있다 — 틀린 입력에는 틀렸다고 말해야 한다.
    """
    try:
        if not date_str or not isinstance(date_str, str):
            raise ValueError(f"날짜가 비었거나 문자열이 아닙니다: {date_str!r}")

        date_str = date_str.strip()
        
        # YYYY-MM-DD 형식
        if '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 3:
                year, month, day = map(int, parts)
            else:
                raise ValueError("날짜 형식 오류")
        elif len(date_str) == 8 and date_str.isdigit():
            year = int(date_str[:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
        elif '/' in date_str:
            parts = date_str.split('/')
            year, month, day = map(int, parts)
        else:
            raise ValueError("지원하지 않는 날짜 형식")
        
        # 날짜 유효성 검증
        if year < 1900 or year > 2100:
            raise ValueError(f"연도 범위 오류: {year}")
        if month < 1 or month > 12:
            raise ValueError(f"월 범위 오류: {month}")
        if day < 1 or day > 31:
            raise ValueError(f"일 범위 오류: {day}")
        
        # 해당 월의 실제 일수 확인
        max_day = calendar.monthrange(year, month)[1]
        if day > max_day:
            logger.warning(f"{year}년 {month}월에는 {day}일이 없습니다. {max_day}일로 조정")
            day = max_day
        
        return year, month, day

    except ValueError as e:
        # 삼키지 않고 올린다. 사유를 붙여 어느 값이 문제인지 호출부에 남긴다.
        raise ValueError(f"날짜 파싱 실패: {date_str!r} — {e}") from e

def get_days_in_month(year: int, month: int) -> int:
    """해당 월의 일수 반환 (윤년 고려)"""
    try:
        return calendar.monthrange(year, month)[1]
    except Exception as e:
        logger.error(f"월 일수 계산 오류: {year}년 {month}월, 오류: {str(e)}")
        return 30

def calculate_remaining_days(year: int, month: int, day: int) -> int:
    """해당 월에서 남은 일수 계산 (해당일 포함)"""
    try:
        days_in_month = get_days_in_month(year, month)
        return days_in_month - day + 1
    except Exception as e:
        logger.error(f"남은 일수 계산 오류: {year}-{month}-{day}, 오류: {str(e)}")
        return 1

def add_months_safe(year: int, month: int, months_to_add: int) -> Tuple[int, int]:
    """월 수를 안전하게 더해서 새로운 년월 반환"""
    try:
        total_months = year * 12 + month - 1 + months_to_add
        new_year = total_months // 12
        new_month = total_months % 12 + 1
        
        if new_year < 1900 or new_year > 2100:
            logger.warning(f"연도 범위 초과: {new_year}")
        
        return new_year, new_month
        
    except Exception as e:
        logger.error(f"월 더하기 오류: {year}-{month} + {months_to_add}, 오류: {str(e)}")
        return year, month

def to_int(amount) -> int:
    """금액을 안전하게 정수로 변환 (절사). 예외 시 0 반환."""
    try:
        return int(amount)
    except Exception as e:
        logger.error(f"정수 변환 오류: {amount}, 오류: {str(e)}")
        return 0


def round_half_up(x: float) -> int:
    """상용 4사5입(x.5 → 항상 올림). 내장 round()는 banker's rounding(x.5 → 짝수)이라
    원단위 반올림 사이트에서 명시적으로 이 함수를 대신 쓴다. (vcore/projection.py와 동일 정의)"""
    return math.floor(x + 0.5)


def annual_straight_line(cost: int, rate: float) -> int:
    """정액 연 상각액 = 4사5입(cost × rate) — **정수 산술** (2026-09-03, FREEZE 예외 사유 2번).

    rate는 이 모듈의 별표4 float 리터럴(소수 3자리)이므로 round(rate × 1000)으로 1000분율
    정수를 정확히 복원한다. 종전 `round_half_up(cost * rate)`는 0.142·0.071처럼 이진 표현이
    참값보다 작은 연수에서 정확히 x.5인 곱을 x.4999…로 만들어 4사5입을 내렸다
    (10,000,500 × 14년 → 710,035, 정답 710,036). vcore/rate_table.straight_line_annual과
    같은 산식 — oracle이 같은 결함을 가진 채 남으면 거울 스윕의 의미가 깨지므로 동반 수정.
    """
    permille = round(rate * 1000)
    return (cost * permille + 500) // 1000


def yearly_declining(book: int, rate: float, months: int) -> int:
    """정률 상각액 = 절사(book × rate × months / 12) — **정수 산술** (2026-09-03).

    종전 `int(book * rate * months // 12)`는 정확한 정수 결과(10,000,000 × 0.284 = 2,840,000)를
    2,839,999.99…로 만들어 1원 내렸다. vcore/rate_table.declining_balance_amount와 같은 산식.
    """
    permille = round(rate * 1000)
    return book * permille * months // 12000


def get_fiscal_year(year: int, month: int, fiscal_year_end_month: int) -> int:
    """(year, month)가 속한 fiscal_year (한국 관행: 결산일이 속한 연도)."""
    if month <= fiscal_year_end_month:
        return year
    return year + 1


def get_fiscal_period_dates(fiscal_year: int, fiscal_year_end_month: int) -> Tuple[str, str]:
    """(period_start_date, period_end_date) YYYY-MM-DD 반환."""
    end_year = fiscal_year
    end_mo = fiscal_year_end_month
    end_day = calendar.monthrange(end_year, end_mo)[1]
    start_year, start_month = add_months_safe(end_year, end_mo, -11)
    return (
        f"{start_year:04d}-{start_month:02d}-01",
        f"{end_year:04d}-{end_mo:02d}-{end_day:02d}",
    )


def get_fiscal_year_period(fiscal_year: int, fiscal_year_end_month: int) -> Tuple[int, int, int, int]:
    """fiscal_year의 calendar 좌표 (start_year, start_month, end_year, end_month) 반환.

    한국 관행 — fiscal_year = 결산일이 속한 연도.
    예: end_mo=3, fy=2025 → (2024, 4, 2025, 3)
    """
    end_year, end_mo = fiscal_year, fiscal_year_end_month
    start_year, start_month = add_months_safe(end_year, end_mo, -11)
    return start_year, start_month, end_year, end_mo


def get_fiscal_year_dep_window(
    fiscal_year: int,
    fiscal_year_end_month: int,
    asset_start_year: int,
    asset_start_month: int,
    asset_dep_end_year: int,
    asset_dep_end_month: int,
) -> Tuple[int, int, int, int, int]:
    """fiscal_year 안에서 자산이 상각되는 calendar window 반환.

    (months_count, first_year, first_month, last_year, last_month)
    상각 안 되면 (0, 0, 0, 0, 0) 반환.
    """
    fy_start_y, fy_start_m, fy_end_y, fy_end_m = get_fiscal_year_period(
        fiscal_year, fiscal_year_end_month
    )

    # 자산 상각 가능 범위와 fiscal_year의 교집합
    first_y, first_m = max((fy_start_y, fy_start_m), (asset_start_year, asset_start_month))
    last_y, last_m = min((fy_end_y, fy_end_m), (asset_dep_end_year, asset_dep_end_month))

    if (first_y, first_m) > (last_y, last_m):
        return 0, 0, 0, 0, 0

    months = (last_y - first_y) * 12 + (last_m - first_m) + 1
    return months, first_y, first_m, last_y, last_m

def calculate_proration(full_amount: int, numerator: int, denominator: int) -> int:
    """비례 계산 (정수 반환으로 개선)"""
    try:
        if denominator == 0:
            logger.error("분모가 0입니다.")
            return 0
        
        result = (full_amount * numerator) // denominator
        return result
        
    except Exception as e:
        logger.error(f"비례 계산 오류: {full_amount} * {numerator} / {denominator}, 오류: {str(e)}")
        return 0

# ================================
