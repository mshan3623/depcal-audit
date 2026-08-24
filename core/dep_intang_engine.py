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
무형자산 감가상각 계산 엔진
==========================

무형자산 전용 감가상각 계산:
- 직접상각법: 자산계정에서 감가상각비 직접 차감
- 감가상각누계액: 기록만 유지, 별도 계정 없음
- 계산 로직: 유형자산 정액법과 동일

────────────────────────────────────────────────────────────────────────────
⚠️ 실행 경로에서 제거된 모듈 (off-execution-path, 2026-06-16 이후)
────────────────────────────────────────────────────────────────────────────
이 모듈의 무형자산 함수는 base_annual = int(cost // life), 즉 **1/n 직접 나눗셈**이라
3·6·7·9년 등에서 법인세법 [별표 4] 상각률과 어긋난다(1억/6년: 1/n = 16,666,666 vs
별표4 = 16,600,000). 2026-06-16부터 core(depreciation_engine)의 무형 경로 전체가 유형
정액 함수를 재사용해 별표4로 통일됐고, vcore.intangible도 별표4 정액 슬림을 그대로
쓴다 — **어느 실행 경로도 이 파일을 호출하지 않는다.**

보존 사유: tests/test_disposal_invariants.py 가 이 모듈을 직접 호출해 양도 불변식
(양도월 등가성·분배 무결성·잔존 비망가)을 검사한다. 값이 아니라 구조를 고정하는
검사라 별표4 전환과 무관하게 유효하고, 봉인된 레퍼런스의 증거로 남긴다.

⚠️ 여기 있는 수치를 새 코드의 기준으로 삼지 말 것 — 무형 상각의 oracle은 별표4
(= 유형 정액 슬림)다. 이 모듈의 삭제 여부는 별도 결정 사항이다 (2026-08-22 감사).
────────────────────────────────────────────────────────────────────────────
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import logging
import traceback
from .dep_common import (
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

def _calculate_intangible_with_partial_disposal(cost: int, life_years: int, start_date: str,
                                                 disposal_amount: int, disposal_date: str,
                                                 salvage_value: int = 0, memorandum_value: int = 1000,
                                                 *,
                                                 fiscal_year_end_month: int) -> List[MonthlyDepreciation]:
    """무형자산 부분양도 처리 감가상각 계산 (Vector 논리)

    핵심 개념:
    1. 기존 자산의 감가상각 스케줄 = Vector (방향과 크기)
    2. 부분양도 = Vector 축소 (방향은 유지, 크기만 축소)
    3. 양도 직전월까지: 기존 자산만 감가상각 (보정 없이)
    4. 양도월부터: 잔존비율 × 기존 Vector
    5. 완료 시점: 기존 내용연수 유지, 비망가액 1,000원

    Args:
        cost: 취득원가 (기초가액)
        life_years: 내용연수
        start_date: 취득일자
        disposal_amount: 당기감소액 (취득원가 기준)
        disposal_date: 양도일자
        salvage_value: 잔존가액 (무형자산은 항상 0, 파라미터 무시됨)
        memorandum_value: 비망가액 (기본 1000)

    Returns:
        List[MonthlyDepreciation]: 월별 감가상각 스케줄

    Note:
        - 무형자산은 잔존가액 = 0 고정 (salvage_value 파라미터 무시)
        - 양도비율 = disposal_amount / cost
        - 잔존비율 = 1 - 양도비율
        - 양도 직전월까지 보정 없음
        - 양도월부터 기존 Vector × 잔존비율
    """
    logger.info(f"무형자산 부분양도 처리 계산 시작: 취득원가={cost:,}원, 양도액={disposal_amount:,}원, 양도일={disposal_date}")

    # 무형자산은 잔존가액 항상 0
    salvage_value = 0

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
    logger.info(f"Step 1: 기존 Vector 계산 (양도 없이)")
    base_schedule = _calculate_intangible_asset_enhanced(
        cost=cost,
        life_years=life_years,
        start_date=start_date,
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

    # 양도 시점의 장부가액과 누적상각을 제거 비율로 배분
    # 핵심 원칙: 양도 직전월까지의 history는 그대로 유지하고,
    # 양도월부터만 잔존 자산 기준으로 계속 감가상각한다.
    # 양도 시점 분배 (회계 원칙: 양도 누계 = round, 잔존 = 차감으로 무결성 보장)
    disposal_accumulated = round_half_up(prev_month_record.accumulated_depreciation * disposal_amount / cost)
    disposal_book_value = disposal_amount - disposal_accumulated

    disposal_check = disposal_book_value + disposal_accumulated
    logger.info(
        f"제거 검증: {disposal_book_value:,} + {disposal_accumulated:,} = {disposal_check:,}원 "
        f"(목표: {disposal_amount:,}원)"
    )

    remaining_book_value = prev_month_record.book_value - disposal_book_value
    remaining_accumulated = prev_month_record.accumulated_depreciation - disposal_accumulated

    remaining_cost = cost - disposal_amount
    calculated_cost = remaining_book_value + remaining_accumulated
    logger.info(
        f"잔존 검증: {remaining_book_value:,} + {remaining_accumulated:,} = {calculated_cost:,}원 "
        f"(목표: {remaining_cost:,}원)"
    )

    if calculated_cost != remaining_cost:
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
        new_schedule.append(MonthlyDepreciation(
            year=record.year,
            month=record.month,
            monthly_depreciation=record.numeric_depreciation,
            accumulated_depreciation=record.accumulated_depreciation,
            book_value=record.book_value,
            calculation_method=record.calculation_method
        ))

    # 양도 직후부터 시작
    current_book_value = remaining_book_value
    current_accumulated = remaining_accumulated

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
            calculation_method = "무형자산직접상각법(부분양도-최종월)"
            logger.info(f"최종월 ({vector_month.year}-{vector_month.month:02d}): 비망가액까지 {monthly_amount:,}원")
        elif is_last_month_of_year:
            # 결산월 보정 (fiscal year 단위)
            year_vector_months = [
                m for m in vector_months
                if get_fiscal_year(m.year, m.month, fiscal_year_end_month) == current_fy
            ]
            year_target = int(sum(m.numeric_depreciation for m in year_vector_months) * remaining_ratio)
            monthly_amount = year_target - yearly_accumulated[current_fy]['accumulated']
            calculation_method = "무형자산직접상각법(부분양도-결산월보정)"
            logger.info(f"결산월 보정 ({vector_month.year}-{vector_month.month:02d} FY{current_fy}): 목표 {year_target:,}원, 보정 {monthly_amount:,}원")
        else:
            # 일반월: Vector × 잔존비율 (integer 변환)
            monthly_amount = int(base_monthly_dep * remaining_ratio)
            calculation_method = "무형자산직접상각법(부분양도)"

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

    logger.info(f"무형자산 부분양도 처리 계산 완료: 총 {len(new_schedule)}개월")
    logger.info(f"최종 장부가액: {new_schedule[-1].book_value:,}원 (비망가액)")

    return new_schedule


def _calculate_intangible_asset_enhanced(cost: int, life_years: int,
                                       start_date: str,
                                       disposal_date: str = None,
                                       *,
                                       fiscal_year_end_month: int) -> List[MonthlyDepreciation]:
    """무형자산 직접상각법 계산 (더존 무형자산 전용 논리 적용)

    Args:
        cost: 취득원가
        life_years: 내용연수
        start_date: 취득일자
        disposal_date: 양도일자/폐기일자 (양도 또는 폐기자산인 경우 지정, 형식: YYYY-MM-DD)

    Note:
        - 양도일자가 지정된 경우: 양도 직전월까지만 계산, 보정 없음
        - 정상 감가상각: 연말보정 및 감가상각 완료시 보정 적용
    """
    schedule = []

    try:
        # 무형자산 고정값 적용
        salvage_value = 0
        memorandum_value = 1000

        # 양도/폐기일자 파싱 (양도 또는 폐기자산인 경우)
        disposal_year = None
        disposal_month = None
        disposal_day = None
        if disposal_date:
            disposal_year, disposal_month, disposal_day = parse_date_safe(disposal_date)
            logger.info(f"양도/폐기자산 처리: 양도/폐기일자={disposal_year}년 {disposal_month}월 {disposal_day}일 (직전월까지만 감가상각)")

        logger.info(f"무형자산 직접상각법 계산 시작: 취득원가={cost:,.0f}, 내용연수={life_years}년")

        # 날짜 파싱 및 검증
        start_year, start_month, start_day = parse_date_safe(start_date)
        
        # 입력값 검증
        if cost <= 0:
            raise ValueError("취득원가는 0보다 커야 합니다.")
        if life_years <= 0:
            raise ValueError("내용연수는 0보다 커야 합니다.")
        
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

        # 감가상각 대상금액 (무형자산은 취득원가 전액)
        depreciable_amount = cost

        # 기본 연간감가상각비 계산
        base_annual_depreciation = int(depreciable_amount // life_years)
        
        # 계산 변수 초기화 (직접상각법)
        current_book_value = cost
        accumulated_amortization = 0
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

                yearly_depreciation = int(base_annual_depreciation * months_in_year // 12) if months_in_year > 0 else 0
                monthly_depreciation = int(yearly_depreciation // months_in_year) if months_in_year > 0 else 0

                logger.info(
                    f"FY{current_fy} (결산월={fiscal_year_end_month}) 무형: "
                    f"개월수={months_in_year}, 연간={yearly_depreciation:,}, 월={monthly_depreciation:,}"
                )

                yearly_info[current_fy] = {
                    'months_in_year': months_in_year,
                    'yearly_depreciation': yearly_depreciation,
                    'monthly_depreciation': monthly_depreciation,
                    'year_accumulated': 0,
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
                # 내용연수 자연 종료월: 비망가액을 남기고 잔액 정리
                final_depreciation = current_book_value - memorandum_value
                monthly_amount = max(0, final_depreciation)
                logger.debug(f"감가상각 완료월: 비망가액 제외, 잔액 상각 {monthly_amount:,}원 (최종 장부가액 1,000원)")
            elif is_last_month_of_year:
                monthly_amount = year_info['yearly_depreciation'] - year_info['year_accumulated']
                logger.debug(f"보정 적용: {monthly_amount:,}원")
            else:
                monthly_amount = year_info['monthly_depreciation']

            # 직접상각법 적용: 취득원가에서 직접 차감
            current_book_value -= monthly_amount
            accumulated_amortization += monthly_amount
            year_info['year_accumulated'] += monthly_amount

            # MonthlyDepreciation 객체 생성
            schedule.append(MonthlyDepreciation(
                year=current_year,
                month=current_month,
                monthly_depreciation=monthly_amount,
                accumulated_depreciation=to_int(accumulated_amortization),
                book_value=to_int(current_book_value),
                calculation_method="무형자산직접상각법",
                is_partial_month=False,
                is_last_month=is_final_month
            ))
            
            # 다음 달로 이동
            current_year, current_month = add_months_safe(current_year, current_month, 1)
        
        logger.info(f"무형자산 직접상각법 계산 완료: 총 {len(schedule)}개월")
        
    except Exception as e:
        logger.error(f"무형자산 직접상각법 계산 오류: {str(e)}")
        logger.error(traceback.format_exc())
        
    return schedule

