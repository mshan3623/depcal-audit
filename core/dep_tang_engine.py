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
유형자산 감가상각 계산 엔진
==========================

■ 핵심 원칙 (2026-02-01 확립)
  결산 마감 → 감가상각비·감가상각누계액 확정 → 다음 해 기초 장부가
  - 매 회계연도 말 감가상각 누적액은 보정된 금액으로 확정된다
  - 다음 해는 확정된 누적에서 출발한다
  - 전기말 장부가액은 결산 확정 상수값이다 (엔진도 동일값 산출)
  - 분리자산: 쪼개도 합계는 확정 누적과 일치해야 한다 (엔진의 자기 일관성)
  - 감가상각은 비망가(1,000원)까지만 상각한다
  - 모든 계산은 반드시 이 엔진으로만 수행한다 (수동계산 금지)

유형자산 전용 감가상각 계산:
- 정액법 (Straight Line)
- 정률법 (Declining Balance)
- 간접상각법: 취득원가 불변, 감가상각누계액 별도 관리
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import logging
import traceback
from .dep_common import (
    # 상수
    STRAIGHT_LINE_RATES,
    DECLINING_BALANCE_RATES,
    DEFAULT_DECLINING_RATE,
    annual_straight_line, yearly_declining,
    # 데이터 클래스
    DepreciationMethod,
    AssetFinancials,
    AssetInfo,
    MonthlyDepreciation,
    YearlySummary,
    DepreciationResult,
    # 유틸리티 함수
    parse_date_safe,
    add_months_safe,
    to_int,
    round_half_up,
    safe_int_conversion
)

logger = logging.getLogger(__name__)

def _calculate_korean_straight_line_enhanced(cost: int, life_years: int,
                                           start_date: str, salvage_value: int = 0,
                                           memorandum_value: int = 1000,
                                           disposal_date: str = None,
                                           prior_accumulated: int = None,
                                           target_year: int = None,
                                           *,
                                           fiscal_year_end_month: int) -> List[MonthlyDepreciation]:
    """한국세법 정액법 감가상각 계산 - 회계기간(fiscal year) 기반 월할 계산.

    Args:
        cost: 취득원가
        life_years: 내용연수
        start_date: 취득일자
        salvage_value: 잔존가액 (기본 0)
        memorandum_value: 비망가액 (기본 1000)
        disposal_date: 양도일자/폐기일자 (YYYY-MM-DD)
        prior_accumulated: 전기말상각누계액 (분리자산 등 외부 기초값 사용 시)
        target_year: 분리자산 당기 회계연도
        fiscal_year_end_month: 회사 결산월 (1~12, 필수 keyword)

    Returns:
        List[MonthlyDepreciation]: 월별 감가상각 스케줄

    Note:
        - yearly_info 묶음은 fiscal_year_end_month 기반 회계기간 단위
        - 결산월 잔재 보정 발화 위치 = fiscal_year_end_month
        - 분리자산 경로(prior_accumulated): v2.2는 12월 결산만 지원 (v2.3 예정)
    """
    # v2.2 가드: 분리자산 경로는 12월 결산만 지원 (try 진입 전에 즉시 발화)
    if prior_accumulated is not None and fiscal_year_end_month != 12:
        raise ValueError(
            f"v2.2 분리자산 경로(prior_accumulated)는 12월 결산만 지원 "
            f"(fiscal_year_end_month={fiscal_year_end_month}). 비-12월 결산 분리자산은 v2.3 예정."
        )

    schedule = []

    try:
        # 잔존가치와 비망기록 고정값 적용
        salvage_value = 0
        memorandum_value = 1000

        # 날짜 파싱 (prior_accumulated 모드에서도 필요)
        start_year, start_month, start_day = parse_date_safe(start_date)

        # ============================================================
        # 분리자산 처리: prior_accumulated 지정 시 당기분만 계산
        # ============================================================
        if prior_accumulated is not None:
            logger.info(f"분리자산 처리: 전기말누적={prior_accumulated:,}원 기초, 당기분만 계산")
            
            # 양도/폐기일자 파싱
            if disposal_date:
                disposal_year, disposal_month, disposal_day = parse_date_safe(disposal_date)
            
            # 정액법 상각률 결정
            if life_years in STRAIGHT_LINE_RATES:
                straight_line_rate = STRAIGHT_LINE_RATES[life_years]
            else:
                available_years = sorted([y for y in STRAIGHT_LINE_RATES.keys() if y <= life_years])
                straight_line_rate = STRAIGHT_LINE_RATES[available_years[-1]] if available_years else STRAIGHT_LINE_RATES[60]
            
            annual_dep = annual_straight_line(cost, straight_line_rate)   # 정수 산술 (2026-09-03)
            
            # 당기 시작: 전기말 다음 회계연도 1월
            # 내용연수 완료 시점 계산
            total_life_months = life_years * 12
            dep_complete_year = start_year + life_years
            dep_complete_month = start_month - 1
            if dep_complete_month == 0:
                dep_complete_year -= 1
                dep_complete_month = 12
            
            remaining_depreciable = cost - prior_accumulated - memorandum_value
            
            if remaining_depreciable <= 0:
                logger.info(f"감가상각 완료 자산 (잔여상각액 {remaining_depreciable:,}원)")
                return schedule
            
            # 당기 연도 결정: target_year가 있으면 그대로 사용
            if target_year:
                current_year = target_year
            else:
                # target_year 없으면 경과월수로 추정
                elapsed_months_approx = int(prior_accumulated / annual_dep * 12) if annual_dep > 0 else 0
                first_year_months = 13 - start_month
                if elapsed_months_approx >= first_year_months:
                    full_years_after_first = (elapsed_months_approx - first_year_months) // 12
                    current_year = start_year + 1 + full_years_after_first + 1
                else:
                    current_year = start_year + 1
            
            # 당기 상각 월수 결정
            if disposal_date:
                # 양도자산: 더존식 양도월 포함(양도월까지 상각)
                current_year_months = disposal_month
                current_year = disposal_year
            else:
                # 정상: 12개월 (마지막 해에서 완료월 체크)
                current_year_months = 12
                if dep_complete_month < 12 and current_year == dep_complete_year:
                    current_year_months = dep_complete_month
            
            # 당기 상각비 계산
            yearly_dep = (annual_dep * current_year_months) // 12
            dep_amount = min(yearly_dep, remaining_depreciable)
            
            # 월별 스케줄 생성
            accumulated = prior_accumulated
            book_value = cost - accumulated
            
            if disposal_date and current_year_months > 0:
                # 양도자산: 균등 배분 + 마지막 월 나머지 보정
                monthly_base = dep_amount // current_year_months
                remainder_disposal = dep_amount - (monthly_base * current_year_months)
                for m_idx in range(current_year_months):
                    month_num = m_idx + 1
                    is_last = (m_idx == current_year_months - 1)
                    m_amount = monthly_base + (remainder_disposal if is_last else 0)
                    accumulated += m_amount
                    book_value = cost - accumulated
                    
                    schedule.append(MonthlyDepreciation(
                        year=current_year,
                        month=month_num,
                        monthly_depreciation=m_amount,
                        accumulated_depreciation=to_int(accumulated),
                        book_value=to_int(book_value),
                        calculation_method="한국세법정액법_분리자산(양도)",
                        is_partial_month=False,
                        is_last_month=(m_idx == current_year_months - 1)
                    ))
            elif current_year_months > 0:
                # 정상자산: 월균등 + 연말보정
                monthly_base = dep_amount // current_year_months
                remainder = dep_amount - (monthly_base * current_year_months)
                
                for m_idx in range(current_year_months):
                    month_num = m_idx + 1
                    is_last = (m_idx == current_year_months - 1)
                    
                    if is_last and remaining_depreciable <= yearly_dep:
                        # 마지막 해: 잔액 - 비망가 전부 상각
                        m_amount = dep_amount - (accumulated - prior_accumulated)
                    elif is_last:
                        # 연말보정
                        m_amount = monthly_base + remainder
                    else:
                        m_amount = monthly_base
                    
                    accumulated += m_amount
                    book_value = cost - accumulated
                    
                    schedule.append(MonthlyDepreciation(
                        year=current_year,
                        month=month_num,
                        monthly_depreciation=m_amount,
                        accumulated_depreciation=to_int(accumulated),
                        book_value=to_int(book_value),
                        calculation_method="한국세법정액법_분리자산",
                        is_partial_month=False,
                        is_last_month=is_last
                    ))
            
            logger.info(f"분리자산 당기 계산 완료: 당기상각비={dep_amount:,}원, 누적={accumulated:,}원")
            return schedule
        # ============================================================
        # 이하 기존 로직 (취득일부터 전체 재계산)
        # ============================================================

        # 양도/폐기일자 파싱 (양도 또는 폐기자산인 경우)
        disposal_year = None
        disposal_month = None
        disposal_day = None
        if disposal_date:
            disposal_year, disposal_month, disposal_day = parse_date_safe(disposal_date)
            logger.info(f"양도/폐기자산 처리: 양도/폐기일자={disposal_year}년 {disposal_month}월 {disposal_day}일 (직전월까지만 감가상각)")

        logger.info(f"한국세법 정액법 계산 시작: 취득원가={cost:,.0f}, 내용연수={life_years}년")
        
        # 입력값 검증
        if cost <= 0:
            raise ValueError("취득원가는 0보다 커야 합니다.")
        if life_years <= 0:
            raise ValueError("내용연수는 0보다 커야 합니다.")
        
        logger.info(f"취득일자: {start_year}년 {start_month}월 {start_day}일")

        # 감가상각 기간 계산
        total_depreciation_months = life_years * 12

        # 내용연수 자연 종료월 (양도 무관, base/is_final_month 판정용)
        depreciation_complete_year = start_year + life_years
        depreciation_complete_month = start_month - 1
        if depreciation_complete_month == 0:
            depreciation_complete_year -= 1
            depreciation_complete_month = 12
        dep_end_year = depreciation_complete_year
        dep_end_month = depreciation_complete_month

        # 루프 종료 경계 (양도가 있으면 양도 직전월과 내용연수 종료 중 이른 시점)
        if disposal_date:
            # 더존식: 양도월 포함(양도월까지 상각, 익월부터 중단)
            disposal_prev_year = disposal_year
            disposal_prev_month = disposal_month

            if (dep_end_year < disposal_prev_year or
                (dep_end_year == disposal_prev_year and dep_end_month < disposal_prev_month)):
                terminate_year = dep_end_year
                terminate_month = dep_end_month
                logger.info(f"감가상각 완료월({terminate_year}년 {terminate_month}월) < 양도 직전월({disposal_prev_year}년 {disposal_prev_month}월) → 완료월까지 계산")
            else:
                terminate_year = disposal_prev_year
                terminate_month = disposal_prev_month
                logger.info(f"양도 직전월({terminate_year}년 {terminate_month}월)까지 감가상각 (정상 base 유지, 매각처리는 별도)")
        else:
            terminate_year = dep_end_year
            terminate_month = dep_end_month

        # 1. 정액법 상각률 결정 (법인세법 [별표 4] 기준)
        if life_years in STRAIGHT_LINE_RATES:
            straight_line_rate = STRAIGHT_LINE_RATES[life_years]
            logger.info(f"정액법 상각률: {straight_line_rate:.3f} (법인세법 [별표 4], 내용연수 {life_years}년)")
        else:
            # 테이블에 없는 경우 (60년 초과)
            available_years = sorted([y for y in STRAIGHT_LINE_RATES.keys() if y <= life_years])
            if available_years:
                # 가장 가까운 작은 값 사용
                straight_line_rate = STRAIGHT_LINE_RATES[available_years[-1]]
                logger.warning(f"내용연수 {life_years}년은 테이블에 없음. {available_years[-1]}년 상각률 사용: {straight_line_rate:.3f}")
            else:
                # 최소값 사용 (60년 상각률)
                straight_line_rate = STRAIGHT_LINE_RATES[60]
                logger.warning(f"내용연수 {life_years}년은 테이블 범위 초과. 60년 상각률 사용: {straight_line_rate:.3f}")

        # 2. 일반적인 연간감가상각비 계산 (법인세법 상각률 적용)
        standard_annual_depreciation = annual_straight_line(cost, straight_line_rate)   # 정수 산술 (2026-09-03)
        logger.info(f"일반적인 연간감가상각비: {standard_annual_depreciation:,}원 (취득원가 {cost:,}원 × 상각률 {straight_line_rate:.3f})")
        
        # 계산 변수 초기화
        current_book_value = cost
        accumulated_depreciation = 0
        current_year = start_year
        current_month = start_month

        # 회계연도(fiscal year)별 계산 정보 저장
        yearly_info = {}

        # 월별 감가상각 처리
        for month_count in range(total_depreciation_months):
            year_offset = (current_year - start_year)

            # 현재 (year, month)이 속한 fiscal year (한국 관행: 결산일 속한 연도)
            from .dep_common import get_fiscal_year, get_fiscal_year_dep_window
            current_fy = get_fiscal_year(current_year, current_month, fiscal_year_end_month)

            # 해당 회계연도 묶음 초기화 (처음 만나는 fiscal year)
            if current_fy not in yearly_info:
                months_in_year, fy_first_y, fy_first_m, fy_last_y, fy_last_m = get_fiscal_year_dep_window(
                    current_fy, fiscal_year_end_month,
                    start_year, start_month, dep_end_year, dep_end_month
                )

                logger.info(
                    f"FY{current_fy} (결산월={fiscal_year_end_month}): "
                    f"자산 상각 {months_in_year}개월 "
                    f"({fy_first_y}-{fy_first_m:02d} ~ {fy_last_y}-{fy_last_m:02d})"
                )

                # 모든 회계연도에 동일한 정수값 기준 계산 적용
                if months_in_year > 0:
                    yearly_depreciation = (standard_annual_depreciation * months_in_year) // 12

                    # 비망가 한도 적용: 잔액 - 비망가를 초과하지 않도록.
                    # 이미 비망가에 도달했으면(remaining ≤ 0) 추가 상각은 0 — 과거 조건
                    # `remaining > 0 and ...`은 이 경우 캡을 통째로 건너뛰어 계속 상각했고
                    # 그 초과분이 종료해에 음수 상각으로 되돌아왔다(2026-07-25 발견,
                    # 소액 취득원가에서만 발화. vcore projection.capped_yearly와 동일 수정)
                    remaining_depreciable = cost - accumulated_depreciation - memorandum_value
                    if yearly_depreciation > remaining_depreciable:
                        yearly_depreciation = max(0, remaining_depreciable)
                        logger.info(f"비망가 한도 적용: {yearly_depreciation:,}원 (잔액-비망가)")

                    base_monthly_depreciation = yearly_depreciation // months_in_year
                    # 결산월 잔재 보정 (정수 연산)
                    remainder = yearly_depreciation - (base_monthly_depreciation * months_in_year)

                    logger.info(f"  연간상각비: {yearly_depreciation:,}원")
                    logger.info(f"  기본월상각비: {base_monthly_depreciation:,}원")
                    logger.info(f"  결산월 보정금액: {remainder:,}원")
                else:
                    yearly_depreciation = 0
                    base_monthly_depreciation = 0
                    remainder = 0

                yearly_info[current_fy] = {
                    'months_in_year': months_in_year,
                    'yearly_depreciation': yearly_depreciation,
                    'base_monthly_depreciation': base_monthly_depreciation,
                    'year_end_adjustment': remainder,
                    'fy_first_year': fy_first_y, 'fy_first_month': fy_first_m,
                    'fy_last_year': fy_last_y, 'fy_last_month': fy_last_m,
                    'year_accumulated': 0
                }

            # 현재 회계연도 정보 가져오기
            year_info = yearly_info[current_fy]

            # 루프 종료 조건 (양도 직전월 또는 내용연수 종료월 이후 stop)
            if (current_year > terminate_year or
                (current_year == terminate_year and current_month > terminate_month)):
                break

            # 내용연수 자연 종료월 여부 (비망가 1,000원 보정 발화 조건, calendar 단위)
            is_final_month = (current_year == dep_end_year and current_month == dep_end_month)

            # 결산월 잔재 보정 발화 = 현재 fiscal year의 자산 마지막 상각월 도달
            # (12월 결산이면 12월, 3월 결산이면 3월에 발화. 양도/내용연수 종료로 못 가면 break로 자연 처리)
            is_last_month_of_year = (
                current_year == year_info['fy_last_year'] and
                current_month == year_info['fy_last_month']
            )

            # 월 감가상각비 계산
            if is_final_month:
                # 내용연수 자연 종료월: 비망가액(1,000원)을 남기고 잔액 정리
                final_depreciation = current_book_value - memorandum_value
                monthly_amount = max(0, final_depreciation)
                logger.debug(f"감가상각 완료월 {current_year}년 {current_month}월: 비망가액 제외, 잔액 상각 {monthly_amount:,}원 (최종 장부가액 1,000원)")
            elif is_last_month_of_year:
                # 연말 보정: 기본월상각비 + 보정금액
                monthly_amount = year_info['base_monthly_depreciation'] + year_info['year_end_adjustment']
                logger.debug(f"보정 적용 {current_year}년 {current_month}월: {year_info['base_monthly_depreciation']:,} + {year_info['year_end_adjustment']:,} = {monthly_amount:,}원")
            else:
                # 일반월: 기본월상각비 (양도/폐기자산 포함)
                monthly_amount = year_info['base_monthly_depreciation']
            
            # 누적 업데이트
            accumulated_depreciation += monthly_amount
            current_book_value = cost - accumulated_depreciation
            year_info['year_accumulated'] += monthly_amount
            
            # MonthlyDepreciation 객체 생성
            schedule.append(MonthlyDepreciation(
                year=current_year,
                month=current_month,
                monthly_depreciation=monthly_amount,
                accumulated_depreciation=to_int(accumulated_depreciation),
                book_value=to_int(current_book_value),
                calculation_method="한국세법정액법_취득월할계산",
                is_partial_month=(year_offset == 0),
                is_last_month=is_final_month
            ))
            
            # 다음 달로 이동
            current_year, current_month = add_months_safe(current_year, current_month, 1)
        
        logger.info(f"한국세법 정액법 계산 완료: 총 {len(schedule)}개월")
        
        # 첫 해 실제 감가상각비 확인
        first_year_total = sum(m.numeric_depreciation for m in schedule if m.year == start_year)
        logger.info(f"취득년도({start_year}) 실제 감가상각비: {first_year_total:,}원")
        
    except Exception as e:
        logger.error(f"한국세법 정액법 계산 오류: {str(e)}")
        logger.error(traceback.format_exc())
        
    return schedule

def _calculate_korean_declining_balance_enhanced(cost: int, life_years: int,
                                               start_date: str, salvage_value: int = 0,
                                               memorandum_value: int = 1000,
                                               disposal_date: str = None,
                                               *,
                                               fiscal_year_end_month: int,
                                               settle_terminal_evenly: bool = True,
                                               prior_accumulated: int = None,
                                               target_year: int = None) -> List[MonthlyDepreciation]:
    """한국세법 정률법 감가상각 계산

    Args:
        cost: 취득원가
        life_years: 내용연수
        start_date: 취득일자
        salvage_value: 잔존가액 (기본 0)
        memorandum_value: 비망가액 (기본 1000)
        disposal_date: 양도일자/폐기일자 (양도 또는 폐기자산인 경우 지정, 형식: YYYY-MM-DD)

    Note:
        - 양도일자가 지정된 경우: 양도 직전월까지만 계산, 보정 없음
        - 정상 감가상각: 연말보정 및 감가상각 완료시 보정 적용
    """
    schedule = []

    try:
        # 잔존가치와 비망기록 고정값 적용
        salvage_value = 0
        memorandum_value = 1000

        # 양도/폐기일자 파싱 (양도 또는 폐기자산인 경우)
        disposal_year = None
        disposal_month = None
        disposal_day = None
        if disposal_date:
            disposal_year, disposal_month, disposal_day = parse_date_safe(disposal_date)
            logger.info(f"양도/폐기자산 처리: 양도/폐기일자={disposal_year}년 {disposal_month}월 {disposal_day}일 (직전월까지만 감가상각)")

        # ============================================================
        # 분리자산 처리: prior_accumulated 지정 시 당기분만 계산 (정액 분리자산과 동일 골격,
        # 연상각 산식만 정률(기초장부가×율)로 다름). 12월 결산만 지원(정액과 동일 제약).
        # ============================================================
        if prior_accumulated is not None:
            if fiscal_year_end_month != 12:
                raise ValueError(
                    f"분리자산 경로(prior_accumulated)는 12월 결산만 지원 "
                    f"(fiscal_year_end_month={fiscal_year_end_month}).")
            sep_start_year, sep_start_month, _ = parse_date_safe(start_date)
            if life_years in DECLINING_BALANCE_RATES:
                sep_rate = DECLINING_BALANCE_RATES[life_years]
            else:
                sep_avail = sorted([y for y in DECLINING_BALANCE_RATES if y <= life_years])
                sep_rate = DECLINING_BALANCE_RATES[sep_avail[-1]] if sep_avail else DEFAULT_DECLINING_RATE
            sep_book = cost - prior_accumulated               # 정률 기초장부가
            remaining_depreciable = sep_book - memorandum_value
            if remaining_depreciable <= 0:
                logger.info(f"감가상각 완료 자산 (잔여상각액 {remaining_depreciable:,}원)")
                return schedule
            dep_complete_year = sep_start_year + life_years
            dep_complete_month = sep_start_month - 1
            if dep_complete_month == 0:
                dep_complete_year -= 1
                dep_complete_month = 12
            current_year = target_year if target_year else sep_start_year + 1
            if disposal_date:                                 # 양도자산: 더존식 양도월 포함
                current_year_months = disposal_month
                current_year = disposal_year
            else:
                current_year_months = 12
                if dep_complete_month < 12 and current_year == dep_complete_year:
                    current_year_months = dep_complete_month
            yearly_dep = yearly_declining(sep_book, sep_rate, current_year_months)   # 정수 산술 (2026-09-03)
            if (not disposal_date) and current_year == dep_complete_year:
                dep_amount = remaining_depreciable                # 종료해: 잔액 전액(5% 잔재 정리)
            else:
                dep_amount = min(yearly_dep, remaining_depreciable)
            accumulated = prior_accumulated
            if current_year_months > 0:
                monthly_base = dep_amount // current_year_months
                remainder = dep_amount - monthly_base * current_year_months
                for m_idx in range(current_year_months):
                    is_last = (m_idx == current_year_months - 1)
                    if disposal_date:
                        m_amount = monthly_base + (remainder if is_last else 0)
                        method = "한국세법정률법_분리자산(양도)"
                    elif is_last:
                        m_amount = monthly_base + remainder
                        method = "한국세법정률법_분리자산"
                    else:
                        m_amount = monthly_base
                        method = "한국세법정률법_분리자산"
                    accumulated += m_amount
                    schedule.append(MonthlyDepreciation(
                        year=current_year, month=m_idx + 1, monthly_depreciation=m_amount,
                        accumulated_depreciation=to_int(accumulated),
                        book_value=to_int(cost - accumulated),
                        calculation_method=method, is_partial_month=False, is_last_month=is_last))
            logger.info(f"분리자산 당기 계산 완료(정률): 당기상각비={dep_amount:,}원, 누적={accumulated:,}원")
            return schedule

        logger.info(f"한국세법 정률법 계산 시작: 취득원가={cost:,.0f}, 내용연수={life_years}년")

        # 날짜 파싱 및 검증
        start_year, start_month, start_day = parse_date_safe(start_date)
        
        # 입력값 검증
        if cost <= 0:
            raise ValueError("취득원가는 0보다 커야 합니다.")
        if life_years <= 0:
            raise ValueError("내용연수는 0보다 커야 합니다.")
        
        # 정률법 상각률 결정
        if life_years in DECLINING_BALANCE_RATES:
            depreciation_rate = DECLINING_BALANCE_RATES[life_years]
        else:
            available_years = sorted([y for y in DECLINING_BALANCE_RATES.keys() if y <= life_years])
            if available_years:
                depreciation_rate = DECLINING_BALANCE_RATES[available_years[-1]]
            else:
                depreciation_rate = DEFAULT_DECLINING_RATE
        
        # 감가상각 기간 계산
        total_depreciation_months = life_years * 12

        # 내용연수 자연 종료월 (감가상각 보정 판정용, 양도와 무관)
        depreciation_complete_year = start_year + life_years
        depreciation_complete_month = start_month - 1
        if depreciation_complete_month == 0:
            depreciation_complete_year -= 1
            depreciation_complete_month = 12
        dep_end_year = depreciation_complete_year
        dep_end_month = depreciation_complete_month

        # 루프 종료 경계 (양도가 있으면 양도 직전월과 내용연수 종료 중 이른 시점)
        if disposal_date:
            # 더존식: 양도월 포함(양도월까지 상각, 익월부터 중단)
            disposal_prev_year = disposal_year
            disposal_prev_month = disposal_month

            if (dep_end_year < disposal_prev_year or
                (dep_end_year == disposal_prev_year and dep_end_month < disposal_prev_month)):
                terminate_year = dep_end_year
                terminate_month = dep_end_month
                logger.info(f"감가상각 완료월({terminate_year}년 {terminate_month}월) < 양도 직전월 → 완료월까지 계산")
            else:
                terminate_year = disposal_prev_year
                terminate_month = disposal_prev_month
                logger.info(f"양도 직전월({terminate_year}년 {terminate_month}월)까지 감가상각 (정상 base 유지, 매각처리는 별도)")
        else:
            terminate_year = dep_end_year
            terminate_month = dep_end_month

        # 계산 변수 초기화
        current_book_value = cost
        accumulated_depreciation = 0
        current_year = start_year
        current_month = start_month

        # 회계연도(fiscal year)별 계산 정보 저장
        yearly_info = {}

        # 월별 감가상각 처리
        for month_count in range(total_depreciation_months):
            year_offset = (current_year - start_year)

            from .dep_common import get_fiscal_year, get_fiscal_year_dep_window
            current_fy = get_fiscal_year(current_year, current_month, fiscal_year_end_month)

            # 해당 회계연도 묶음 초기화 (처음 만나는 fiscal year)
            if current_fy not in yearly_info:
                months_in_year, fy_first_y, fy_first_m, fy_last_y, fy_last_m = get_fiscal_year_dep_window(
                    current_fy, fiscal_year_end_month,
                    start_year, start_month, dep_end_year, dep_end_month
                )

                # 회계연도 시작 시점의 잔존 장부가액 (정률법 base)
                year_start_book_value = current_book_value

                # 연간상각비 = year_start_book_value × 상각률 × 회계기간 내 자산 상각 개월수 / 12
                yearly_depreciation = yearly_declining(year_start_book_value, depreciation_rate, months_in_year)   # 정수 산술 (2026-09-03)

                # 비망가 한도 적용 (정액 경로와 동일 — remaining ≤ 0도 캡 발동, 2026-07-25)
                remaining_depreciable = current_book_value - memorandum_value
                if yearly_depreciation > remaining_depreciable:
                    yearly_depreciation = max(0, remaining_depreciable)
                    logger.info(f"정률법 비망가 한도 적용: {yearly_depreciation:,}원 (잔액-비망가)")

                # 원칙 통일(2026-06): 종료해(자연 내용연수 종료 사업연도)는 잔액 전액
                # (기초장부가-비망가)을 그해 연간상각액으로 확정 → 월할 균등 배분. 정률법 5% 잔재를
                # 마지막 달에 몰아 dump하지 않고 연간상각액의 일부로 균등 안분(법인세법 시행령
                # 제26조⑥ '상각범위액에 가산'의 월 단위 적용). 이벤트 base 벡터(capex/부분양도)는
                # settle_terminal_evenly=False로, 전부양도는 disposal_date로 제외(미완료 구간 불정산).
                if settle_terminal_evenly and not disposal_date:
                    final_fy = get_fiscal_year(dep_end_year, dep_end_month, fiscal_year_end_month)
                    if current_fy == final_fy:
                        yearly_depreciation = year_start_book_value - memorandum_value

                monthly_depreciation = int(yearly_depreciation // months_in_year) if months_in_year > 0 else 0

                logger.info(
                    f"FY{current_fy} (결산월={fiscal_year_end_month}) 정률법: "
                    f"개월수={months_in_year}, 시작장부가={year_start_book_value:,}, "
                    f"연간={yearly_depreciation:,}, 월={monthly_depreciation:,}"
                )

                yearly_info[current_fy] = {
                    'months_in_year': months_in_year,
                    'yearly_depreciation': yearly_depreciation,
                    'monthly_depreciation': monthly_depreciation,
                    'year_accumulated': 0,
                    'year_start_book_value': year_start_book_value,
                    'fy_first_year': fy_first_y, 'fy_first_month': fy_first_m,
                    'fy_last_year': fy_last_y, 'fy_last_month': fy_last_m,
                }

            # 현재 회계연도 정보 가져오기
            year_info = yearly_info[current_fy]

            # 루프 종료 조건 (양도 직전월 또는 내용연수 종료월 이후 stop)
            if (current_year > terminate_year or
                (current_year == terminate_year and current_month > terminate_month)):
                break

            # 내용연수 자연 종료월 (calendar 단위, 결산월 무관)
            is_final_month = (current_year == dep_end_year and current_month == dep_end_month)

            # 결산월 잔재 보정 발화 = 현재 fiscal year의 자산 마지막 상각월 도달
            is_last_month_of_year = (
                current_year == year_info['fy_last_year'] and
                current_month == year_info['fy_last_month']
            )

            # 월 감가상각비 계산
            if is_final_month:
                # 내용연수 자연 종료월: 비망가액(1,000원)을 남기고 잔액 정리.
                # 정률법 특성상 잔액 × 상각률의 누적 감소로 내용연수 종료 시점 약 5% 잔재가 남는다
                # (예: 5년 상각률 0.451 → (1-0.451)^5 ≈ 5.0%). 이 잔재를 마지막 달에 비망가
                # 1,000원으로 일괄 정리하므로 마지막 달 상각비가 일반 월 base 대비 10~15배 폭증한다.
                # 회계·수학적 불가피이며 한국 법인세법 [별표 4] 정률법 + 비망가 1,000원의 자연 결과.
                final_depreciation = current_book_value - memorandum_value
                monthly_amount = max(0, final_depreciation)
                logger.debug(f"감가상각 완료월 (정률법): 비망가액 제외, 잔액 상각 {monthly_amount:,}원 (최종 장부가액 1,000원)")
            elif is_last_month_of_year:
                monthly_amount = year_info['yearly_depreciation'] - year_info['year_accumulated']
                logger.debug(f"보정 적용: {monthly_amount:,}원")
            else:
                monthly_amount = year_info['monthly_depreciation']

            # 누적 업데이트
            accumulated_depreciation += monthly_amount
            current_book_value = cost - accumulated_depreciation
            year_info['year_accumulated'] += monthly_amount

            # MonthlyDepreciation 객체 생성
            schedule.append(MonthlyDepreciation(
                year=current_year,
                month=current_month,
                monthly_depreciation=monthly_amount,
                accumulated_depreciation=to_int(accumulated_depreciation),
                book_value=to_int(current_book_value),
                calculation_method="한국세법정률법",
                is_partial_month=False,
                is_last_month=is_final_month
            ))
            
            # 다음 달로 이동
            current_year, current_month = add_months_safe(current_year, current_month, 1)
        
        logger.info(f"한국세법 정률법 계산 완료: 총 {len(schedule)}개월")
        
    except Exception as e:
        logger.error(f"한국세법 정률법 계산 오류: {str(e)}")
        logger.error(traceback.format_exc())

    return schedule


def _calculate_with_increase(cost: int, life_years: int, start_date: str,
                             increase_amount: int, increase_date: str,
                             salvage_value: int = 0, memorandum_value: int = 1000,
                             disposal_date: str = None, disposal_amount: int = 0,
                             *,
                             fiscal_year_end_month: int) -> List[MonthlyDepreciation]:
    """유형자산 증가 처리 감가상각 계산 (Vector 논리)

    핵심 개념:
    ---------
    1. 기존 자산의 감가상각 스케줄 = Vector (방향과 크기)
    2. 증가 자산도 동일한 Vector를 따름
    3. 부분양도가 있으면 양도 직전월까지 증가 처리 후, 양도월부터 잔존 부분 Vector 적용
    3. 증가 직전월까지: 기존 자산만 감가상각 (보정 없이)
    4. 증가월부터: (기존 장부가액 + 증가액) × Vector 비율
    5. 완료 시점: 기존 내용연수 유지, 비망가액 1,000원 통합

    Args:
        cost: 기존 취득원가
        life_years: 내용연수
        start_date: 기존 취득일자
        increase_amount: 증가액
        increase_date: 증가일자 (YYYY-MM-DD)
        salvage_value: 잔존가액 (기본 0)
        memorandum_value: 비망가액 (기본 1000)
        disposal_date: 양도/폐기일자

    Returns:
        List[MonthlyDepreciation]: 증가 처리된 월별 감가상각 스케줄
    """

    logger.info(f"증가 처리 계산 시작: 기존원가={cost:,}원, 증가액={increase_amount:,}원, 증가일={increase_date}")

    # Step 1: 기존 자산의 전체 Vector 계산 (증가 없이)
    base_schedule = _calculate_korean_straight_line_enhanced(
        cost=cost,
        life_years=life_years,
        start_date=start_date,
        salvage_value=salvage_value,
        memorandum_value=memorandum_value,
        disposal_date=None,  # 증가 시에는 disposal 무시
        fiscal_year_end_month=fiscal_year_end_month
    )

    # Step 2: 증가 시점 파싱
    increase_year, increase_month, increase_day = parse_date_safe(increase_date)
    logger.info(f"증가 시점: {increase_year}년 {increase_month}월")

    # Step 3: 증가 직전월 찾기
    # 증가월이 1월이면 직전월은 전년도 12월
    if increase_month == 1:
        prev_year = increase_year - 1
        prev_month = 12
    else:
        prev_year = increase_year
        prev_month = increase_month - 1

    # 증가 직전월 상태 찾기
    prev_month_record = None
    for m in base_schedule:
        if m.year == prev_year and m.month == prev_month:
            prev_month_record = m
            break

    if not prev_month_record:
        # base를 그대로 돌려주면 **자본적지출이 없던 것처럼** 상각표가 나온다(감사 G18-⑤).
        # 조용히 빠진 증가액은 표만 보고는 알 수 없다 — vcore의 같은 조건도 ValueError다.
        raise ValueError(
            f"자본적지출 직전월({prev_year}-{prev_month:02d})이 상각 기간 밖입니다 "
            f"— 증가 시점이 취득월 이전이거나 내용연수 종료 이후")

    logger.info(f"증가 직전월 ({prev_year}-{prev_month:02d}) 장부가액: {prev_month_record.book_value:,}원")

    # Step 4: 증가 후 통합 장부가액
    combined_book_value = prev_month_record.book_value + increase_amount
    ratio = combined_book_value / prev_month_record.book_value

    logger.info(f"증가 후 통합 장부가액: {combined_book_value:,}원")
    logger.info(f"Vector 비율: {ratio:.4f}")

    # Step 5: 새로운 스케줄 생성
    new_schedule = []

    # 증가 직전월까지는 기존 스케줄 그대로 복사 (보정 없이)
    for m in base_schedule:
        if m.year < increase_year or (m.year == increase_year and m.month < increase_month):
            new_schedule.append(m)
        else:
            # 증가월부터는 중단
            break

    # Step 6: 증가월부터 Vector 비율 적용 (연말 보정 포함)
    # 증가월부터 완료월까지의 기존 Vector
    vector_months = [m for m in base_schedule
                     if m.year > increase_year or (m.year == increase_year and m.month >= increase_month)]

    # 부분양도 여부 확인
    is_partial_disposal = (disposal_date and disposal_amount > 0 and disposal_amount < cost)

    vector_months_before_disposal = vector_months
    vector_months_after_disposal = []
    disposal_prev_year = None
    disposal_prev_month = None

    if disposal_date:
        disposal_year, disposal_month, disposal_day = parse_date_safe(disposal_date)

        # 더존식: 양도월 포함(양도월까지 상각, 익월부터 중단)
        disposal_prev_year = disposal_year
        disposal_prev_month = disposal_month

        if is_partial_disposal:
            logger.info(f"부분양도 처리: {disposal_date} (양도 후에도 잔존 부분 계속 감가상각)")

            # 양도 직전월까지와 양도월 이후로 분리
            vector_months_before_disposal = [m for m in vector_months
                            if m.year < disposal_prev_year or
                            (m.year == disposal_prev_year and m.month <= disposal_prev_month)]

            vector_months_after_disposal = [m for m in vector_months
                            if m.year > disposal_prev_year or
                            (m.year == disposal_prev_year and m.month > disposal_prev_month)]

            logger.info(f"양도 전({len(vector_months_before_disposal)}개월) + 양도 후({len(vector_months_after_disposal)}개월)")
        else:
            logger.info(f"전체양도 처리: {disposal_date} (양도 직전월까지 감가상각)")

            # 전체양도: 양도 직전월까지만
            vector_months_before_disposal = [m for m in vector_months
                            if m.year < disposal_prev_year or
                            (m.year == disposal_prev_year and m.month <= disposal_prev_month)]

            logger.info(f"양도 직전월({disposal_prev_year}-{disposal_prev_month:02d})까지 {len(vector_months_before_disposal)}개월")

    if not vector_months_before_disposal:
        # 위와 같은 이유로 조용히 넘기지 않는다 (감사 G18-⑤).
        raise ValueError("자본적지출 이후 상각할 기간이 없습니다 "
                         "— 증가 시점이 내용연수 종료 이후이거나 양도 이후")

    vector_months = vector_months_before_disposal

    # 증가 후 상태 초기화
    current_book_value = combined_book_value
    accumulated_depreciation = prev_month_record.accumulated_depreciation

    logger.info(f"증가월부터 Vector 적용: {len(vector_months)}개월")

    # 연도별 누적 관리 (연말 보정용)
    yearly_accumulated = {}

    from .dep_common import get_fiscal_year

    for idx, vector_month in enumerate(vector_months):
        current_fy = get_fiscal_year(vector_month.year, vector_month.month, fiscal_year_end_month)

        # 회계연도별 누적 초기화 (fiscal year 단위)
        if current_fy not in yearly_accumulated:
            yearly_accumulated[current_fy] = {
                'accumulated': 0,
                'months_in_year': 0
            }

        # Vector 비율 적용
        is_final_month = (idx == len(vector_months) - 1) and not disposal_date

        # 결산월 발화 = 현재 vector_month의 fiscal year가 다음 month의 fiscal year보다 이른 경우
        # 또는 마지막 vector이면서 결산월 도달 시
        is_last_month_of_year = False
        if idx + 1 < len(vector_months):
            next_month = vector_months[idx + 1]
            next_fy = get_fiscal_year(next_month.year, next_month.month, fiscal_year_end_month)
            is_last_month_of_year = (next_fy > current_fy)
        elif vector_month.month == fiscal_year_end_month:
            is_last_month_of_year = True

        if is_final_month:
            # 내용연수 자연 종료월: 비망가액 1,000원을 남기고 잔액 정리
            monthly_amount = max(0, current_book_value - memorandum_value)
            logger.debug(f"감가상각 완료월 ({vector_month.year}-{vector_month.month:02d}): 비망가액 제외, 잔액 상각 {monthly_amount:,}원")
        elif is_last_month_of_year:
            # 결산월 보정: 해당 fiscal year 연간 목표 달성
            year_vector_months = [
                m for m in vector_months
                if get_fiscal_year(m.year, m.month, fiscal_year_end_month) == current_fy
            ]
            year_target = int(sum(m.numeric_depreciation for m in year_vector_months) * ratio)
            monthly_amount = year_target - yearly_accumulated[current_fy]['accumulated']
            logger.debug(f"결산월 보정 ({vector_month.year}-{vector_month.month:02d} FY{current_fy}): 연간목표 {year_target:,}원, 보정금액 {monthly_amount:,}원")
        else:
            # 일반월: 기존 Vector × 비율
            monthly_amount = int(vector_month.numeric_depreciation * ratio)

        # 회계연도별 누적 업데이트
        yearly_accumulated[current_fy]['accumulated'] += monthly_amount
        yearly_accumulated[current_fy]['months_in_year'] += 1

        # 장부가액 및 누적상각 업데이트
        current_book_value -= monthly_amount
        accumulated_depreciation += monthly_amount

        # MonthlyDepreciation 생성
        new_schedule.append(MonthlyDepreciation(
            year=vector_month.year,
            month=vector_month.month,
            monthly_depreciation=monthly_amount,
            accumulated_depreciation=to_int(accumulated_depreciation),
            book_value=to_int(current_book_value),
            calculation_method="정액법(증가처리)",
            is_partial_month=False,
            is_last_month=is_final_month
        ))

    # Step 7: 부분양도 후 처리 (양도월부터 잔존 부분 계속 감가상각)
    if is_partial_disposal and vector_months_after_disposal:
        logger.info(f"\n부분양도 후 잔존 부분 감가상각 시작")

        # 양도 직전월 상태
        disposal_prev_record = new_schedule[-1]

        # 실제 통합 취득원가 (원래 + 증가)
        actual_cost_at_disposal = disposal_prev_record.book_value + disposal_prev_record.accumulated_depreciation

        # 처분 비율 계산 (통합 취득원가 기준)
        actual_disposal_ratio = disposal_amount / actual_cost_at_disposal
        remaining_ratio = 1.0 - actual_disposal_ratio

        logger.info(f"통합 취득원가: {actual_cost_at_disposal:,}원")
        logger.info(f"처분액: {disposal_amount:,}원 (실제 비율: {actual_disposal_ratio*100:.2f}%)")
        logger.info(f"잔존 비율: {remaining_ratio*100:.2f}%")

        # 양도 시점에서 감소 (Integer 기준 정확한 계산)
        # 양도 시점 분배 (회계 원칙: 양도 누계 = round, 잔존 = 차감으로 무결성 보장)
        disposal_accumulated = round_half_up(disposal_prev_record.accumulated_depreciation * disposal_amount / actual_cost_at_disposal)
        disposal_book_value = disposal_amount - disposal_accumulated

        disposal_check = disposal_book_value + disposal_accumulated
        logger.info(f"제거 검증: {disposal_book_value:,} + {disposal_accumulated:,} = {disposal_check:,}원 (목표: {disposal_amount:,}원)")

        current_book_value = disposal_prev_record.book_value - disposal_book_value
        accumulated_depreciation = disposal_prev_record.accumulated_depreciation - disposal_accumulated

        # 잔존 부분 회계 방정식 검증
        remaining_cost = actual_cost_at_disposal - disposal_amount
        calculated_cost = current_book_value + accumulated_depreciation

        logger.info(f"잔존 검증: {current_book_value:,} + {accumulated_depreciation:,} = {calculated_cost:,}원 (목표: {remaining_cost:,}원)")

        if calculated_cost != remaining_cost:
            # 오차가 있으면 누적상각액에서 조정
            rounding_error = calculated_cost - remaining_cost
            accumulated_depreciation -= rounding_error
            logger.info(f"⚠️ 반올림 오차 조정: {rounding_error:,}원")

        logger.info(f"양도 후 장부가액: {current_book_value:,}원")
        logger.info(f"양도 후 누적상각: {accumulated_depreciation:,}원")

        # 양도월부터 잔존 부분 Vector 적용
        yearly_accumulated_after = {}

        for idx, vector_month in enumerate(vector_months_after_disposal):
            current_fy = get_fiscal_year(vector_month.year, vector_month.month, fiscal_year_end_month)

            if current_fy not in yearly_accumulated_after:
                yearly_accumulated_after[current_fy] = {
                    'accumulated': 0,
                    'months_in_year': 0
                }

            is_final_month = (idx == len(vector_months_after_disposal) - 1)

            # 결산월 발화 (fiscal year 단위)
            is_last_month_of_year = False
            if idx < len(vector_months_after_disposal) - 1:
                next_month = vector_months_after_disposal[idx + 1]
                next_fy = get_fiscal_year(next_month.year, next_month.month, fiscal_year_end_month)
                is_last_month_of_year = (next_fy > current_fy)
            else:
                is_last_month_of_year = True

            if is_final_month:
                # 최종월: 비망가액을 남기고 나머지를 상각
                monthly_amount = max(0, current_book_value - memorandum_value)
                logger.debug(f"최종월 ({vector_month.year}-{vector_month.month:02d}): 비망가액 제외, 잔액 상각 {monthly_amount:,}원")
            elif is_last_month_of_year:
                # 결산월 보정 (fiscal year 단위)
                year_vector_months = [
                    m for m in vector_months_after_disposal
                    if get_fiscal_year(m.year, m.month, fiscal_year_end_month) == current_fy
                ]
                year_target = int(sum(m.numeric_depreciation for m in year_vector_months) * ratio * remaining_ratio)
                monthly_amount = year_target - yearly_accumulated_after[current_fy]['accumulated']
                logger.debug(f"결산월 보정 ({vector_month.year}-{vector_month.month:02d} FY{current_fy}): 연간목표 {year_target:,}원")
            else:
                # 일반월: 증가 비율 × 잔존 비율
                monthly_amount = int(vector_month.numeric_depreciation * ratio * remaining_ratio)

            yearly_accumulated_after[current_fy]['accumulated'] += monthly_amount
            yearly_accumulated_after[current_fy]['months_in_year'] += 1

            current_book_value -= monthly_amount
            accumulated_depreciation += monthly_amount

            new_schedule.append(MonthlyDepreciation(
                year=vector_month.year,
                month=vector_month.month,
                monthly_depreciation=monthly_amount,
                accumulated_depreciation=to_int(accumulated_depreciation),
                book_value=to_int(current_book_value),
                calculation_method="정액법(증가+부분양도)",
                is_partial_month=False,
                is_last_month=is_final_month
            ))

        logger.info(f"부분양도 후 처리 완료: {len(vector_months_after_disposal)}개월 추가")

    logger.info(f"증가 처리 계산 완료: 총 {len(new_schedule)}개월")
    logger.info(f"최종 장부가액: {new_schedule[-1].book_value:,}원")

    return new_schedule


def _calculate_with_increase_declining(cost: int, life_years: int, start_date: str,
                                        increase_amount: int, increase_date: str,
                                        salvage_value: int = 0, memorandum_value: int = 1000,
                                        disposal_date: str = None, disposal_amount: int = 0,
                                        *,
                                        fiscal_year_end_month: int) -> List[MonthlyDepreciation]:
    """유형자산 증가 처리 감가상각 계산 - 정률법 (Vector 논리)

    핵심 개념:
    ---------
    1. 기존 자산의 정률법 감가상각 스케줄 = Vector (방향과 크기)
    2. 증가 자산도 동일한 Vector를 따름
    3. 증가 직전월까지: 기존 자산만 감가상각 (보정 없이)
    4. 증가월부터: (기존 장부가액 + 증가액) × Vector 비율
    5. 부분양도 시: 양도 직전월까지 증가 처리 → 양도월부터 잔존 부분 계속 감가상각
    6. 완료 시점: 기존 내용연수 유지, 비망가액 1,000원 통합

    Args:
        cost: 기존 취득원가
        life_years: 내용연수
        start_date: 기존 취득일자
        increase_amount: 증가액
        increase_date: 증가일자 (YYYY-MM-DD)
        salvage_value: 잔존가액 (기본 0)
        memorandum_value: 비망가액 (기본 1000)
        disposal_date: 양도/폐기일자
        disposal_amount: 당기감소액 (0이면 전체양도 또는 양도 없음)

    Returns:
        List[MonthlyDepreciation]: 증가 처리된 월별 감가상각 스케줄
    """

    logger.info(f"증가 처리 계산 시작 (정률법): 기존원가={cost:,}원, 증가액={increase_amount:,}원, 증가일={increase_date}")

    # Step 1: 기존 자산의 전체 Vector 계산 (증가 없이, 정률법)
    base_schedule = _calculate_korean_declining_balance_enhanced(
        cost=cost,
        life_years=life_years,
        start_date=start_date,
        salvage_value=salvage_value,
        memorandum_value=memorandum_value,
        disposal_date=None,  # 증가 시에는 disposal 무시
        fiscal_year_end_month=fiscal_year_end_month,
        settle_terminal_evenly=False,  # 합성 base 벡터: 종료해 균등화 미적용(이벤트 후 재정산)
    )

    # Step 2: 증가 시점 파싱
    increase_year, increase_month, increase_day = parse_date_safe(increase_date)
    logger.info(f"증가 시점: {increase_year}년 {increase_month}월")

    # Step 3: 증가 직전월 찾기
    if increase_month == 1:
        prev_year = increase_year - 1
        prev_month = 12
    else:
        prev_year = increase_year
        prev_month = increase_month - 1

    # 증가 직전월 상태 찾기
    prev_month_record = None
    for m in base_schedule:
        if m.year == prev_year and m.month == prev_month:
            prev_month_record = m
            break

    if not prev_month_record:
        # base를 그대로 돌려주면 **자본적지출이 없던 것처럼** 상각표가 나온다(감사 G18-⑤).
        # 조용히 빠진 증가액은 표만 보고는 알 수 없다 — vcore의 같은 조건도 ValueError다.
        raise ValueError(
            f"자본적지출 직전월({prev_year}-{prev_month:02d})이 상각 기간 밖입니다 "
            f"— 증가 시점이 취득월 이전이거나 내용연수 종료 이후")

    logger.info(f"증가 직전월 ({prev_year}-{prev_month:02d}) 장부가액: {prev_month_record.book_value:,}원")

    # Step 4: 증가 후 통합 장부가액
    combined_book_value = prev_month_record.book_value + increase_amount
    ratio = combined_book_value / prev_month_record.book_value

    logger.info(f"증가 후 통합 장부가액: {combined_book_value:,}원")
    logger.info(f"Vector 비율: {ratio:.4f}")

    # Step 5: 새로운 스케줄 생성
    new_schedule = []

    # 증가 직전월까지는 기존 스케줄 그대로 복사 (보정 없이)
    for m in base_schedule:
        if m.year < increase_year or (m.year == increase_year and m.month < increase_month):
            new_schedule.append(m)
        else:
            # 증가월부터는 중단
            break

    # Step 6: 증가월부터 Vector 비율 적용 (연말 보정 포함)
    vector_months = [m for m in base_schedule
                     if m.year > increase_year or (m.year == increase_year and m.month >= increase_month)]

    # 부분양도 여부 확인
    is_partial_disposal = (disposal_date and disposal_amount > 0 and disposal_amount < cost)

    # 양도 직전월 정보 (부분/전체 양도 모두 필요)
    disposal_prev_year = None
    disposal_prev_month = None
    vector_months_before_disposal = vector_months
    vector_months_after_disposal = []

    if disposal_date:
        disposal_year, disposal_month, disposal_day = parse_date_safe(disposal_date)

        # 더존식: 양도월 포함(양도월까지 상각, 익월부터 중단)
        disposal_prev_year = disposal_year
        disposal_prev_month = disposal_month

        if is_partial_disposal:
            logger.info(f"부분양도 처리 (정률법): {disposal_date}, {disposal_amount:,}원 (양도 직전월까지 증가 처리 → 양도월부터 잔존 부분 계속)")

            # 양도 직전월까지와 양도월 이후로 분리
            vector_months_before_disposal = [m for m in vector_months
                            if m.year < disposal_prev_year or
                            (m.year == disposal_prev_year and m.month <= disposal_prev_month)]

            vector_months_after_disposal = [m for m in vector_months
                            if m.year > disposal_prev_year or
                            (m.year == disposal_prev_year and m.month > disposal_prev_month)]

            logger.info(f"양도 직전월({disposal_prev_year}-{disposal_prev_month:02d})까지 {len(vector_months_before_disposal)}개월, 양도월 이후 {len(vector_months_after_disposal)}개월")
        else:
            # 전체양도: 양도 직전월까지만
            logger.info(f"전체양도 처리 (정률법): {disposal_date} (양도 직전월까지 감가상각)")

            vector_months_before_disposal = [m for m in vector_months
                            if m.year < disposal_prev_year or
                            (m.year == disposal_prev_year and m.month <= disposal_prev_month)]

            logger.info(f"양도 직전월({disposal_prev_year}-{disposal_prev_month:02d})까지 {len(vector_months_before_disposal)}개월")

    # Step 6 처리용 vector_months는 부분양도 전까지
    vector_months = vector_months_before_disposal

    if not vector_months:
        # 위와 같은 이유로 조용히 넘기지 않는다 (감사 G18-⑤).
        raise ValueError("자본적지출 이후 상각할 기간이 없습니다 "
                         "— 증가 시점이 내용연수 종료 이후이거나 양도 이후")

    # 증가 후 상태 초기화
    current_book_value = combined_book_value
    accumulated_depreciation = prev_month_record.accumulated_depreciation

    logger.info(f"증가월부터 Vector 적용 (정률법): {len(vector_months)}개월")

    # 연도별 누적 관리 (연말 보정용)
    yearly_accumulated = {}

    from .dep_common import get_fiscal_year

    for idx, vector_month in enumerate(vector_months):
        current_fy = get_fiscal_year(vector_month.year, vector_month.month, fiscal_year_end_month)

        # 회계연도별 누적 초기화 (fiscal year 단위)
        if current_fy not in yearly_accumulated:
            yearly_accumulated[current_fy] = {
                'accumulated': 0,
                'months_in_year': 0
            }

        # Vector 비율 적용 (전체양도 시 비망가액 처리 안 함)
        is_final_month = (idx == len(vector_months) - 1) and not disposal_date

        # 결산월 발화 (fiscal year 단위)
        is_last_month_of_year = False
        if idx + 1 < len(vector_months):
            next_month = vector_months[idx + 1]
            next_fy = get_fiscal_year(next_month.year, next_month.month, fiscal_year_end_month)
            is_last_month_of_year = (next_fy > current_fy)
        elif vector_month.month == fiscal_year_end_month:
            is_last_month_of_year = True

        if is_final_month:
            # 내용연수 자연 종료월: 비망가액 1,000원을 남기고 잔액 정리
            monthly_amount = max(0, current_book_value - memorandum_value)
            logger.debug(f"감가상각 완료월 ({vector_month.year}-{vector_month.month:02d}): 비망가액 제외, 잔액 상각 {monthly_amount:,}원")
        elif is_last_month_of_year:
            # 결산월 보정 (fiscal year 단위)
            year_vector_months = [
                m for m in vector_months
                if get_fiscal_year(m.year, m.month, fiscal_year_end_month) == current_fy
            ]
            year_target = int(sum(m.numeric_depreciation for m in year_vector_months) * ratio)
            monthly_amount = year_target - yearly_accumulated[current_fy]['accumulated']
            logger.debug(f"결산월 보정 ({vector_month.year}-{vector_month.month:02d} FY{current_fy}): 연간목표 {year_target:,}원, 보정금액 {monthly_amount:,}원")
        else:
            # 일반월: 기존 Vector × 비율
            monthly_amount = int(vector_month.numeric_depreciation * ratio)

        # 회계연도별 누적 업데이트
        yearly_accumulated[current_fy]['accumulated'] += monthly_amount
        yearly_accumulated[current_fy]['months_in_year'] += 1

        # 장부가액 및 누적상각 업데이트
        current_book_value -= monthly_amount
        accumulated_depreciation += monthly_amount

        # MonthlyDepreciation 생성
        new_schedule.append(MonthlyDepreciation(
            year=vector_month.year,
            month=vector_month.month,
            monthly_depreciation=monthly_amount,
            accumulated_depreciation=to_int(accumulated_depreciation),
            book_value=to_int(current_book_value),
            calculation_method="정률법(증가처리)",
            is_partial_month=False,
            is_last_month=is_final_month
        ))

    # Step 7: 부분양도 후 처리 (양도월부터 잔존 부분 계속 감가상각)
    if is_partial_disposal and vector_months_after_disposal:
        logger.info(f"Step 7: 부분양도 후 잔존 부분 계속 감가상각 (정률법)")

        # 양도 직전월 상태 가져오기
        disposal_prev_record = new_schedule[-1]

        # 실제 통합 취득원가 (원래 + 증가)
        actual_cost_at_disposal = disposal_prev_record.book_value + disposal_prev_record.accumulated_depreciation

        # 처분 비율 계산 (통합 취득원가 기준)
        actual_disposal_ratio = disposal_amount / actual_cost_at_disposal
        remaining_ratio = 1.0 - actual_disposal_ratio

        logger.info(f"통합 취득원가: {actual_cost_at_disposal:,}원")
        logger.info(f"실제 처분 비율: {actual_disposal_ratio:.4f} ({actual_disposal_ratio*100:.2f}%)")
        logger.info(f"실제 잔존 비율: {remaining_ratio:.4f} ({remaining_ratio*100:.2f}%)")

        # 양도 시점 분배 (회계 원칙: 양도 누계 = round, 잔존 = 차감으로 무결성 보장)
        disposal_accumulated = round_half_up(disposal_prev_record.accumulated_depreciation * disposal_amount / actual_cost_at_disposal)
        disposal_book_value = disposal_amount - disposal_accumulated

        disposal_check = disposal_book_value + disposal_accumulated
        logger.info(f"제거 검증: {disposal_book_value:,} + {disposal_accumulated:,} = {disposal_check:,}원 (목표: {disposal_amount:,}원)")

        # 잔존 부분 (양도 직후)
        current_book_value = disposal_prev_record.book_value - disposal_book_value
        accumulated_depreciation = disposal_prev_record.accumulated_depreciation - disposal_accumulated

        # 잔존 부분 회계 방정식 검증
        remaining_cost = actual_cost_at_disposal - disposal_amount
        calculated_cost = current_book_value + accumulated_depreciation

        logger.info(f"잔존 검증: {current_book_value:,} + {accumulated_depreciation:,} = {calculated_cost:,}원 (목표: {remaining_cost:,}원)")

        if calculated_cost != remaining_cost:
            # 오차가 있으면 누적상각액에서 조정
            rounding_error = calculated_cost - remaining_cost
            accumulated_depreciation -= rounding_error
            logger.info(f"⚠️ 반올림 오차 조정: {rounding_error:,}원")

        logger.info(f"양도 후 장부가액: {current_book_value:,}원")
        logger.info(f"양도 후 누적상각: {accumulated_depreciation:,}원")

        # 양도월부터 잔존 부분 Vector 적용
        # 일반월: 증가 비율 × 잔존 비율
        # 연말보정: 해당 연도 목표 × 잔존 비율
        # 최종월: 비망가액까지
        #
        # [버그수정 2026-06-16] 양도 후 결산월 보정은 '양도 후 구간만'의 누적으로 해야 한다.
        # 부분양도 연도는 Step6(양도 전, full ratio)와 Step7(양도 후, remaining)에 걸치는데,
        # 공유 yearly_accumulated를 쓰면 양도 후 목표(작음)에서 양도 전 누적(큼)을 빼 음수
        # 월상각이 발생하고 미상각분이 종료해로 떠밀린다. 양도 후 전용 누적으로 분리한다.
        yearly_accumulated_after = {}

        for idx, vector_month in enumerate(vector_months_after_disposal):
            current_fy = get_fiscal_year(vector_month.year, vector_month.month, fiscal_year_end_month)

            # 회계연도별 누적 초기화 (양도 후 전용)
            if current_fy not in yearly_accumulated_after:
                yearly_accumulated_after[current_fy] = {
                    'accumulated': 0,
                    'months_in_year': 0
                }

            # Vector 비율 적용 (증가 비율 × 잔존 비율)
            is_final_month = (idx == len(vector_months_after_disposal) - 1)

            # 결산월 발화 (fiscal year 단위)
            is_last_month_of_year = False
            if idx < len(vector_months_after_disposal) - 1:
                next_month = vector_months_after_disposal[idx + 1]
                next_fy = get_fiscal_year(next_month.year, next_month.month, fiscal_year_end_month)
                is_last_month_of_year = (next_fy > current_fy)
            else:
                is_last_month_of_year = True

            if is_final_month:
                # 최종월: 비망가액 1,000원을 남기고 나머지를 상각
                monthly_amount = max(0, current_book_value - memorandum_value)
                logger.debug(f"최종월 ({vector_month.year}-{vector_month.month:02d}): 비망가액 제외, 잔액 상각 {monthly_amount:,}원")
            elif is_last_month_of_year:
                # 결산월 보정 (fiscal year 단위)
                year_vector_months = [
                    m for m in vector_months_after_disposal
                    if get_fiscal_year(m.year, m.month, fiscal_year_end_month) == current_fy
                ]
                year_target = int(sum(m.numeric_depreciation for m in year_vector_months) * ratio * remaining_ratio)
                monthly_amount = year_target - yearly_accumulated_after[current_fy]['accumulated']
                logger.debug(f"결산월 보정 ({vector_month.year}-{vector_month.month:02d} FY{current_fy}): 연간목표 {year_target:,}원, 보정금액 {monthly_amount:,}원")
            else:
                # 일반월: 기존 Vector × 증가 비율 × 잔존 비율
                monthly_amount = int(vector_month.numeric_depreciation * ratio * remaining_ratio)

            # 회계연도별 누적 업데이트 (양도 후 전용)
            yearly_accumulated_after[current_fy]['accumulated'] += monthly_amount
            yearly_accumulated_after[current_fy]['months_in_year'] += 1

            # 장부가액 및 누적상각 업데이트
            current_book_value -= monthly_amount
            accumulated_depreciation += monthly_amount

            # MonthlyDepreciation 생성
            new_schedule.append(MonthlyDepreciation(
                year=vector_month.year,
                month=vector_month.month,
                monthly_depreciation=monthly_amount,
                accumulated_depreciation=to_int(accumulated_depreciation),
                book_value=to_int(current_book_value),
                calculation_method="정률법(증가+부분양도)",
                is_partial_month=False,
                is_last_month=is_final_month
            ))

        logger.info(f"부분양도 후 계속 처리 완료: 양도월부터 {len(vector_months_after_disposal)}개월 추가")

    logger.info(f"증가 처리 계산 완료 (정률법): 총 {len(new_schedule)}개월")
    logger.info(f"최종 장부가액: {new_schedule[-1].book_value:,}원")

    return new_schedule


def _calculate_with_partial_disposal_declining(cost: int, life_years: int, start_date: str,
                                                 disposal_amount: int, disposal_date: str,
                                                 salvage_value: int = 0, memorandum_value: int = 1000,
                                                 *,
                                                 fiscal_year_end_month: int) -> List[MonthlyDepreciation]:
    """유형자산 부분양도 처리 감가상각 계산 - 정률법 (Vector 논리)

    핵심 개념:
    1. 기존 자산의 정률법 감가상각 스케줄 = Vector (방향과 크기)
    2. 부분양도 = Vector 축소 (방향은 유지, 크기만 축소)
    3. 양도 직전월까지: 기존 자산 정률법 감가상각 (그대로)
    4. 양도월부터: 잔존비율 × 기존 Vector

    Args:
        cost: 취득원가
        life_years: 내용연수
        start_date: 취득일자
        disposal_amount: 당기감소액
        disposal_date: 양도일자
        salvage_value: 잔존가액 (기본 0)
        memorandum_value: 비망가액 (기본 1000)

    Returns:
        List[MonthlyDepreciation]: 월별 감가상각 스케줄
    """
    logger.info(f"부분양도 처리 계산 시작 (정률법): 취득원가={cost:,}원, 양도액={disposal_amount:,}원, 양도일={disposal_date}")

    # 입력값 검증
    if disposal_amount <= 0:
        raise ValueError("당기감소액은 0보다 커야 합니다")

    if disposal_amount >= cost:
        raise ValueError(f"당기감소액({disposal_amount:,})이 취득원가({cost:,}) 이상입니다")

    if not disposal_date:
        raise ValueError("부분양도의 경우 양도일자가 필수입니다")

    # 양도비율 계산
    disposal_ratio = disposal_amount / cost
    remaining_ratio = 1.0 - disposal_ratio

    logger.info(f"양도비율: {disposal_ratio:.4f} ({disposal_ratio*100:.2f}%)")
    logger.info(f"잔존비율: {remaining_ratio:.4f} ({remaining_ratio*100:.2f}%)")

    # 양도일자 파싱
    disposal_year, disposal_month, disposal_day = parse_date_safe(disposal_date)
    logger.info(f"양도일자: {disposal_year}년 {disposal_month}월 {disposal_day}일")

    # Step 1: 기존 자산의 전체 Vector 계산 (양도 없이) - 정률법
    logger.info(f"Step 1: 기존 Vector 계산 (양도 없이) - 정률법")
    base_schedule = _calculate_korean_declining_balance_enhanced(
        cost=cost,
        life_years=life_years,
        start_date=start_date,
        salvage_value=salvage_value,
        memorandum_value=memorandum_value,
        disposal_date=None,  # 양도 없이 전체 스케줄 계산
        fiscal_year_end_month=fiscal_year_end_month,
        settle_terminal_evenly=False,  # 합성 base 벡터: 종료해 균등화 미적용(이벤트 후 재정산)
    )

    if not base_schedule:
        raise ValueError("기존 Vector 계산 실패")

    logger.info(f"기존 Vector 총 {len(base_schedule)}개월")

    # Step 2: 양도 직전월 찾기
    # 더존식: 양도월 포함(양도월까지 상각, 익월부터 중단)
    disposal_prev_year = disposal_year
    disposal_prev_month = disposal_month

    # 양도 직전월까지의 스케줄 (보정 없이 그대로)
    prev_month_records = [m for m in base_schedule
                          if m.year < disposal_prev_year or
                          (m.year == disposal_prev_year and m.month <= disposal_prev_month)]

    if not prev_month_records:
        raise ValueError(f"양도 직전월({disposal_prev_year}-{disposal_prev_month:02d})까지의 스케줄이 없습니다")

    prev_month_record = prev_month_records[-1]
    logger.info(f"양도 직전월 ({disposal_prev_year}-{disposal_prev_month:02d}):")
    logger.info(f"  전체 자산 장부가액: {prev_month_record.book_value:,}원")
    logger.info(f"  전체 자산 누적상각: {prev_month_record.accumulated_depreciation:,}원")

    # Step 3: 양도월부터의 Vector
    vector_months = [m for m in base_schedule
                     if m.year > disposal_prev_year or
                     (m.year == disposal_prev_year and m.month > disposal_prev_month)]

    if not vector_months:
        logger.warning("양도월부터의 Vector가 없습니다")
        return prev_month_records

    logger.info(f"양도월부터 Vector 적용: {len(vector_months)}개월")

    # Step 4: 양도 이전 기간은 그대로 유지
    new_schedule = []
    for record in prev_month_records:
        new_schedule.append(MonthlyDepreciation(
            year=record.year,
            month=record.month,
            monthly_depreciation=record.numeric_depreciation,
            accumulated_depreciation=record.accumulated_depreciation,
            book_value=record.book_value,
            calculation_method=record.calculation_method
        ))

    # 양도 시점 분배 (회계 원칙: 양도 누계 = round, 잔존 = 차감으로 무결성 보장)
    disposal_accumulated = round_half_up(prev_month_record.accumulated_depreciation * disposal_amount / cost)
    disposal_book_value = disposal_amount - disposal_accumulated

    disposal_check = disposal_book_value + disposal_accumulated
    logger.info(f"제거 검증: {disposal_book_value:,} + {disposal_accumulated:,} = {disposal_check:,}원 (목표: {disposal_amount:,}원)")

    current_book_value = prev_month_record.book_value - disposal_book_value
    current_accumulated = prev_month_record.accumulated_depreciation - disposal_accumulated

    # 잔존 부분 회계 방정식 검증
    remaining_cost = cost - disposal_amount
    calculated_cost = current_book_value + current_accumulated

    logger.info(f"잔존 검증: {current_book_value:,} + {current_accumulated:,} = {calculated_cost:,}원 (목표: {remaining_cost:,}원)")

    if calculated_cost != remaining_cost:
        # 오차가 있으면 누적상각액에서 조정
        rounding_error = calculated_cost - remaining_cost
        current_accumulated -= rounding_error
        logger.info(f"⚠️ 반올림 오차 조정: {rounding_error:,}원을 누적상각액에서 차감")

    logger.info(f"양도 시점 조정:")
    logger.info(f"  양도 전 장부가액: {prev_month_record.book_value:,}원")
    logger.info(f"  양도 전 누적상각액: {prev_month_record.accumulated_depreciation:,}원")
    logger.info(f"  제거 장부가액: {disposal_book_value:,}원")
    logger.info(f"  제거 누적상각: {disposal_accumulated:,}원")
    logger.info(f"  양도 후 장부가액: {current_book_value:,}원")
    logger.info(f"  양도 후 누적상각: {current_accumulated:,}원")

    # Step 5: 양도월부터 Vector 적용 (잔존비율)
    yearly_accumulated = {}

    from .dep_common import get_fiscal_year

    for idx, vector_month in enumerate(vector_months):
        current_fy = get_fiscal_year(vector_month.year, vector_month.month, fiscal_year_end_month)
        is_final_month = (idx == len(vector_months) - 1)

        # 결산월 발화 (fiscal year 단위)
        is_last_month_of_year = False
        if idx + 1 < len(vector_months):
            next_month = vector_months[idx + 1]
            next_fy = get_fiscal_year(next_month.year, next_month.month, fiscal_year_end_month)
            is_last_month_of_year = (next_fy > current_fy)
        elif vector_month.month == fiscal_year_end_month:
            is_last_month_of_year = True

        # 회계연도별 누적 초기화
        if current_fy not in yearly_accumulated:
            yearly_accumulated[current_fy] = {'accumulated': 0}

        # 기존 Vector의 월 감가상각비 추출
        base_monthly_dep = vector_month.numeric_depreciation

        # 월 감가상각비 계산
        if is_final_month:
            # 최종월: 비망가액까지
            monthly_amount = max(0, current_book_value - memorandum_value)
            calculation_method = "한국세법정률법(부분양도-최종월)"
        elif is_last_month_of_year:
            # 결산월 보정 (fiscal year 단위)
            year_vector_months = [
                m for m in vector_months
                if get_fiscal_year(m.year, m.month, fiscal_year_end_month) == current_fy
            ]
            year_target = int(sum(m.numeric_depreciation for m in year_vector_months) * remaining_ratio)
            monthly_amount = year_target - yearly_accumulated[current_fy]['accumulated']
            calculation_method = "한국세법정률법(부분양도-결산월보정)"
        else:
            # 일반월: Vector × 잔존비율
            monthly_amount = int(base_monthly_dep * remaining_ratio)
            calculation_method = "한국세법정률법(부분양도)"

        # 값 업데이트
        current_accumulated += monthly_amount
        current_book_value -= monthly_amount

        # 음수 방지
        if current_book_value < 0:
            monthly_amount += current_book_value
            current_book_value = 0

        # 회계연도별 누적 업데이트
        yearly_accumulated[current_fy]['accumulated'] += monthly_amount

        # 스케줄 추가
        new_schedule.append(MonthlyDepreciation(
            year=vector_month.year,
            month=vector_month.month,
            monthly_depreciation=monthly_amount,
            accumulated_depreciation=current_accumulated,
            book_value=current_book_value,
            calculation_method=calculation_method
        ))

    logger.info(f"부분양도 처리 완료 (정률법): 총 {len(new_schedule)}개월")
    return new_schedule


def _calculate_with_partial_disposal(cost: int, life_years: int, start_date: str,
                                      disposal_amount: int, disposal_date: str,
                                      salvage_value: int = 0, memorandum_value: int = 1000,
                                      prior_accumulated: int = None,
                                      target_year: int = None,
                                      *,
                                      fiscal_year_end_month: int) -> List[MonthlyDepreciation]:
    """유형자산 부분양도 처리 감가상각 계산 (Vector 논리)

    핵심 개념:
    1. 기존 자산의 감가상각 스케줄 = Vector (방향과 크기)
    2. 부분양도 = Vector 축소 (방향은 유지, 크기만 축소)
    3. 양도 직전월까지: 기존 자산만 감가상각 (보정 없이)
    4. 양도월부터: 잔존비율 × 기존 Vector
    5. 완료 시점: 기존 내용연수 유지, 비망가액 1,000원
    6. prior_accumulated 지정 시: 확정 전기말누적 기초 → 분리자산+부분양도 복합 처리

    Args:
        cost: 취득원가 (기초가액)
        life_years: 내용연수
        start_date: 취득일자
        disposal_amount: 당기감소액 (취득원가 기준)
        disposal_date: 양도일자
        salvage_value: 잔존가액 (기본 0)
        memorandum_value: 비망가액 (기본 1000)
        prior_accumulated: 전기말상각누계액 (분리자산 등 외부 확정값 사용 시)
        target_year: 대상 연도 (prior_accumulated 사용 시 필수)

    Returns:
        List[MonthlyDepreciation]: 월별 감가상각 스케줄

    Note:
        - 양도비율 = disposal_amount / cost
        - 잔존비율 = 1 - 양도비율
        - 양도 직전월까지 보정 없음
        - 양도월부터 기존 Vector × 잔존비율
        - prior_accumulated 지정 시: 확정 누적에서 출발하여 당기+부분양도 처리
    """
    logger.info(f"부분양도 처리 계산 시작: 취득원가={cost:,}원, 양도액={disposal_amount:,}원, 양도일={disposal_date}")
    if prior_accumulated is not None:
        logger.info(f"분리자산+부분양도 복합 처리: 전기말누적={prior_accumulated:,}원 기초")

    # 입력값 검증
    if disposal_amount <= 0:
        raise ValueError("당기감소액은 0보다 커야 합니다")

    if disposal_amount >= cost:
        raise ValueError(f"당기감소액({disposal_amount:,})이 취득원가({cost:,}) 이상입니다. 전부양도는 disposal_date만 사용하세요")

    if not disposal_date:
        raise ValueError("부분양도의 경우 양도일자(disposal_date)가 필수입니다")

    # 양도비율 계산
    disposal_ratio = disposal_amount / cost
    remaining_ratio = 1.0 - disposal_ratio

    logger.info(f"양도비율: {disposal_ratio:.4f} ({disposal_ratio*100:.2f}%)")
    logger.info(f"잔존비율: {remaining_ratio:.4f} ({remaining_ratio*100:.2f}%)")

    # 양도일자 파싱
    disposal_year, disposal_month, disposal_day = parse_date_safe(disposal_date)
    logger.info(f"양도일자: {disposal_year}년 {disposal_month}월 {disposal_day}일")

    # Step 1: 기존 자산의 전체 Vector 계산 (양도 없이)
    # 주의: 이 함수는 정액법용입니다. 정률법은 별도 함수 필요
    logger.info(f"Step 1: 기존 Vector 계산 (양도 없이) - 정액법")
    
    # 분리자산+부분양도 복합: prior_accumulated가 있으면 확정값 기초로 당기 계산
    # v2.2: 12월 결산만 지원, 비-12월은 v2.3 예정
    if prior_accumulated is not None and target_year is not None:
        if fiscal_year_end_month != 12:
            raise ValueError(
                f"v2.2 분리자산+부분양도 경로는 12월 결산만 지원 "
                f"(fiscal_year_end_month={fiscal_year_end_month}). 비-12월 결산 분리자산은 v2.3 예정."
            )
        # 확정 전기말누적에서 출발 → 당기 양도 직전월까지 상각 → 부분양도 처리
        logger.info(f"분리자산 기초: prior_accumulated={prior_accumulated:,}, target_year={target_year}")
        
        # 정액법 상각률
        if life_years in STRAIGHT_LINE_RATES:
            rate = STRAIGHT_LINE_RATES[life_years]
        else:
            available = sorted([y for y in STRAIGHT_LINE_RATES.keys() if y <= life_years])
            rate = STRAIGHT_LINE_RATES[available[-1]] if available else STRAIGHT_LINE_RATES[60]
        
        annual_dep = annual_straight_line(cost, rate)   # 정수 산술 (2026-09-03)
        remaining_depreciable = cost - prior_accumulated - memorandum_value
        
        if remaining_depreciable <= 0:
            logger.info(f"감가상각 완료 자산 (잔여상각액 {remaining_depreciable:,}원)")
            return []
        
        # 더존식: 양도월 포함(양도월까지 당기 상각)
        dp_prev_year, dp_prev_month = disposal_year, disposal_month

        months_before_disposal = dp_prev_month  # 1월~양도월(포함)
        yearly_dep_before = (annual_dep * months_before_disposal) // 12
        dep_before = min(yearly_dep_before, remaining_depreciable)
        
        # 양도 전 월별 스케줄 생성
        monthly_base = dep_before // months_before_disposal if months_before_disposal > 0 else 0
        remainder = dep_before - (monthly_base * months_before_disposal)
        
        accumulated = prior_accumulated
        schedule = []
        
        for m_idx in range(months_before_disposal):
            month_num = m_idx + 1
            is_last = (m_idx == months_before_disposal - 1)
            m_amount = monthly_base + (remainder if is_last else 0)
            accumulated += m_amount
            book_value = cost - accumulated
            
            schedule.append(MonthlyDepreciation(
                year=target_year, month=month_num,
                monthly_depreciation=m_amount,
                accumulated_depreciation=to_int(accumulated),
                book_value=to_int(book_value),
                calculation_method="한국세법정액법_분리자산",
                is_partial_month=False, is_last_month=False
            ))
        
        # 양도 시점에서 부분제거
        disposal_ratio = disposal_amount / cost
        remaining_ratio = 1.0 - disposal_ratio
        
        prev_acc = accumulated
        prev_bv = cost - accumulated
        
        disposal_acc = int(disposal_amount * (prev_acc / cost))
        current_accumulated = prev_acc - disposal_acc
        remaining_cost = cost - disposal_amount
        current_book_value = remaining_cost - current_accumulated
        
        # 반올림 오차 조정
        if current_book_value + current_accumulated != remaining_cost:
            current_accumulated = remaining_cost - current_book_value
        
        logger.info(f"부분양도 시점: 누적 {prev_acc:,} → 잔존누적 {current_accumulated:,}, 잔존BV {current_book_value:,}")
        
        # 양도 후: 잔존부분 계속 상각 (양도월~12월)
        remaining_annual = annual_straight_line(remaining_cost, rate)   # 정수 산술 (2026-09-03)
        months_after = 12 - dp_prev_month  # 양도월~12월
        
        # 내용연수 완료 확인
        start_year, start_month, _ = parse_date_safe(start_date)
        dep_complete_year = start_year + life_years
        dep_complete_month = start_month - 1
        if dep_complete_month == 0:
            dep_complete_year -= 1
            dep_complete_month = 12
        
        if target_year > dep_complete_year or (target_year == dep_complete_year and dp_prev_month >= dep_complete_month):
            months_after = 0  # 내용연수 이미 종료
        elif target_year == dep_complete_year:
            months_after = min(months_after, dep_complete_month - dp_prev_month)
        
        remaining_depreciable_after = current_book_value - memorandum_value
        
        if months_after > 0 and remaining_depreciable_after > 0:
            yearly_dep_after = (remaining_annual * months_after) // 12
            dep_after = min(yearly_dep_after, remaining_depreciable_after)
            monthly_after = dep_after // months_after if months_after > 0 else 0
            remainder_after = dep_after - (monthly_after * months_after)
            
            for m_idx in range(months_after):
                month_num = dp_prev_month + 1 + m_idx
                is_last = (m_idx == months_after - 1)
                
                if is_last:
                    m_amount = min(monthly_after + remainder_after, current_book_value - memorandum_value)
                else:
                    m_amount = monthly_after
                
                current_accumulated += m_amount
                current_book_value -= m_amount
                
                schedule.append(MonthlyDepreciation(
                    year=target_year, month=month_num,
                    monthly_depreciation=m_amount,
                    accumulated_depreciation=to_int(current_accumulated),
                    book_value=to_int(current_book_value),
                    calculation_method="정액법(분리+부분양도)",
                    is_partial_month=False, is_last_month=(is_last and current_book_value <= memorandum_value)
                ))
        
        logger.info(f"분리자산+부분양도 완료: {len(schedule)}개월, 최종BV={current_book_value:,}")
        return schedule
    
    base_schedule = _calculate_korean_straight_line_enhanced(
        cost=cost,
        life_years=life_years,
        start_date=start_date,
        salvage_value=salvage_value,
        memorandum_value=memorandum_value,
        disposal_date=None,  # 양도 없이 전체 스케줄 계산
        fiscal_year_end_month=fiscal_year_end_month
    )

    if not base_schedule:
        raise ValueError("기존 Vector 계산 실패")

    logger.info(f"기존 Vector 총 {len(base_schedule)}개월")

    # Step 2: 양도 직전월 찾기
    # 더존식: 양도월 포함(양도월까지 상각, 익월부터 중단)
    disposal_prev_year = disposal_year
    disposal_prev_month = disposal_month

    # 양도 직전월까지의 스케줄 (보정 없이)
    prev_month_records = [m for m in base_schedule
                          if m.year < disposal_prev_year or
                          (m.year == disposal_prev_year and m.month <= disposal_prev_month)]

    if not prev_month_records:
        raise ValueError(f"양도 직전월({disposal_prev_year}-{disposal_prev_month:02d})까지의 스케줄이 없습니다")

    prev_month_record = prev_month_records[-1]
    logger.info(f"양도 직전월 ({disposal_prev_year}-{disposal_prev_month:02d}):")
    logger.info(f"  전체 자산 장부가액: {prev_month_record.book_value:,}원")
    logger.info(f"  전체 자산 누적상각: {prev_month_record.accumulated_depreciation:,}원")

    # 양도 시점의 장부가액과 누적상각을 잔존비율로 재조정 (Integer 기준 정확한 계산)
    # 양도 시점 분배 (회계 원칙: 양도 누계 = round, 잔존 = 차감으로 무결성 보장)
    disposal_accumulated = round_half_up(prev_month_record.accumulated_depreciation * disposal_amount / cost)
    disposal_book_value = disposal_amount - disposal_accumulated

    disposal_check = disposal_book_value + disposal_accumulated
    logger.info(f"제거 검증: {disposal_book_value:,} + {disposal_accumulated:,} = {disposal_check:,}원 (목표: {disposal_amount:,}원)")

    remaining_book_value = prev_month_record.book_value - disposal_book_value
    remaining_accumulated = prev_month_record.accumulated_depreciation - disposal_accumulated

    # 잔존 부분 회계 방정식 검증
    remaining_cost = cost - disposal_amount
    calculated_cost = remaining_book_value + remaining_accumulated

    logger.info(f"잔존 검증: {remaining_book_value:,} + {remaining_accumulated:,} = {calculated_cost:,}원 (목표: {remaining_cost:,}원)")

    if calculated_cost != remaining_cost:
        # 오차가 있으면 누적상각액에서 조정
        rounding_error = calculated_cost - remaining_cost
        remaining_accumulated -= rounding_error
        logger.info(f"⚠️ 반올림 오차 조정: {rounding_error:,}원")

    logger.info(f"양도 후 재조정 ({disposal_year}-{disposal_month:02d} 직전):")
    logger.info(f"  잔존 장부가액: {remaining_book_value:,}원")
    logger.info(f"  잔존 누적상각: {remaining_accumulated:,}원")

    # Step 3: 양도월부터의 Vector (잔존비율 적용)
    vector_months = [m for m in base_schedule
                     if m.year > disposal_prev_year or
                     (m.year == disposal_prev_year and m.month > disposal_prev_month)]

    if not vector_months:
        logger.warning("양도월부터의 Vector가 없습니다 (양도 직전월이 마지막 감가상각월)")
        return prev_month_records

    logger.info(f"양도월부터 Vector 적용: {len(vector_months)}개월")

    # Step 4: 양도 이전 기간은 원래 그대로 유지 (재조정 없음)
    new_schedule = []
    for record in prev_month_records:
        # 양도 이전은 기존 Vector 그대로 사용 (보정 없음)
        new_schedule.append(MonthlyDepreciation(
            year=record.year,
            month=record.month,
            monthly_depreciation=record.numeric_depreciation,
            accumulated_depreciation=record.accumulated_depreciation,
            book_value=record.book_value,
            calculation_method=record.calculation_method
        ))

    # 양도 시점 분배 (회계 원칙: 양도 누계 = round, 잔존 = 차감으로 무결성 보장)
    disposal_accumulated = round_half_up(prev_month_record.accumulated_depreciation * disposal_amount / cost)
    disposal_book_value = disposal_amount - disposal_accumulated

    current_book_value = prev_month_record.book_value - disposal_book_value
    current_accumulated = prev_month_record.accumulated_depreciation - disposal_accumulated

    logger.info(f"양도 시점 조정:")
    logger.info(f"  양도 전 장부가액: {prev_month_record.book_value:,}원")
    logger.info(f"  양도 전 누적상각액: {prev_month_record.accumulated_depreciation:,}원")
    logger.info(f"  양도액(장부가액기준): {disposal_book_value:,}원")
    logger.info(f"  양도액(누적상각액기준): {disposal_accumulated:,}원")
    logger.info(f"  양도 후 장부가액: {current_book_value:,}원")
    logger.info(f"  양도 후 누적상각액: {current_accumulated:,}원")
    logger.info(f"  검증: {current_book_value:,} + {current_accumulated:,} = {current_book_value + current_accumulated:,}원 (목표: {remaining_cost:,}원)")

    # 결산월 보정을 위한 회계연도별 누적 추적
    yearly_accumulated = {}

    from .dep_common import get_fiscal_year

    for idx, vector_month in enumerate(vector_months):
        current_fy = get_fiscal_year(vector_month.year, vector_month.month, fiscal_year_end_month)
        is_final_month = (idx == len(vector_months) - 1)

        # 결산월 발화 (fiscal year 단위)
        is_last_month_of_year = False
        if idx + 1 < len(vector_months):
            next_month = vector_months[idx + 1]
            next_fy = get_fiscal_year(next_month.year, next_month.month, fiscal_year_end_month)
            is_last_month_of_year = (next_fy > current_fy)
        elif vector_month.month == fiscal_year_end_month:
            is_last_month_of_year = True

        # 회계연도별 누적 초기화
        if current_fy not in yearly_accumulated:
            yearly_accumulated[current_fy] = {'target': 0, 'accumulated': 0}

        # 기존 Vector의 월 감가상각비 추출
        base_monthly_dep = vector_month.numeric_depreciation

        # 월 감가상각비 계산 (integer 원칙 적용)
        if is_final_month:
            # 최종월: 비망가액까지 (완료시 보정)
            monthly_amount = max(0, current_book_value - memorandum_value)
            calculation_method = "정액법(부분양도-최종월)"
            logger.info(f"최종월 ({vector_month.year}-{vector_month.month:02d}): 비망가액까지 {monthly_amount:,}원")
        elif is_last_month_of_year:
            # 결산월 보정 (fiscal year 단위)
            year_vector_months = [
                m for m in vector_months
                if get_fiscal_year(m.year, m.month, fiscal_year_end_month) == current_fy
            ]
            year_target = int(sum(m.numeric_depreciation for m in year_vector_months) * remaining_ratio)
            monthly_amount = year_target - yearly_accumulated[current_fy]['accumulated']
            calculation_method = "정액법(부분양도-결산월보정)"
            logger.info(f"결산월 보정 ({vector_month.year}-{vector_month.month:02d} FY{current_fy}): 목표 {year_target:,}원, 보정 {monthly_amount:,}원")
        else:
            # 일반월: Vector × 잔존비율 (integer 변환)
            monthly_amount = int(base_monthly_dep * remaining_ratio)
            calculation_method = "정액법(부분양도)"

        # 값 업데이트
        current_accumulated += monthly_amount
        current_book_value -= monthly_amount

        # 음수 방지
        if current_book_value < 0:
            logger.warning(f"장부가액 음수 발생: {current_book_value:,}원 -> 0원으로 조정")
            monthly_amount += current_book_value  # 조정
            current_book_value = 0

        # 회계연도별 누적 업데이트
        yearly_accumulated[current_fy]['accumulated'] += monthly_amount

        # 스케줄 추가
        new_schedule.append(MonthlyDepreciation(
            year=vector_month.year,
            month=vector_month.month,
            monthly_depreciation=monthly_amount,
            accumulated_depreciation=current_accumulated,
            book_value=current_book_value,
            calculation_method=calculation_method
        ))

    logger.info(f"부분양도 처리 계산 완료: 총 {len(new_schedule)}개월")
    logger.info(f"최종 장부가액: {new_schedule[-1].book_value:,}원 (비망가액)")

    return new_schedule

