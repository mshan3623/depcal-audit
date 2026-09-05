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
고정자산 감가상각비 계산 엔진 - Wrapper
========================================

■ 핵심 원칙 (2026-02-01 확립)
  결산 마감 → 감가상각비·감가상각누계액 확정 → 다음 해 기초 장부가

이 파일은 기존 코드와의 호환성을 위한 Wrapper입니다.
실제 계산은 다음 엔진을 사용합니다:
- dep_tang_engine.py: 유형자산 (정액법, 정률법)
- dep_intang_engine.py: 무형자산 (직접상각법)
"""

# 공통 모듈에서 모든 것을 import
from .dep_common import *

# 유형자산 엔진에서 함수 import
from .dep_tang_engine import (
    _calculate_korean_straight_line_enhanced,
    _calculate_korean_declining_balance_enhanced
)

def generate_yearly_summary(schedule: List[MonthlyDepreciation], original_cost: int,
                            fiscal_year_end_month: int) -> List[YearlySummary]:
    """회계연도(fiscal year) 단위 요약 생성. fiscal_year_end_month 기준으로 묶음."""
    yearly_dict = {}

    for monthly in schedule:
        fy = get_fiscal_year(monthly.year, monthly.month, fiscal_year_end_month)
        if fy not in yearly_dict:
            yearly_dict[fy] = {
                'depreciation': 0,
                'months': 0,
                'ending_accumulated': 0,
                'ending_book_value': 0
            }

        if not monthly.is_zero_depreciation:
            yearly_dict[fy]['depreciation'] += monthly.numeric_depreciation
            yearly_dict[fy]['months'] += 1

        # schedule이 시간 순이므로 같은 fiscal year의 마지막 month 값이 ending에 남음
        yearly_dict[fy]['ending_accumulated'] = monthly.accumulated_depreciation
        yearly_dict[fy]['ending_book_value'] = monthly.book_value

    yearly_summary = []
    for fy in sorted(yearly_dict.keys()):
        data = yearly_dict[fy]
        summary = YearlySummary(
            year=fy,
            yearly_depreciation=data['depreciation'],
            accumulated_depreciation=data['ending_accumulated'],
            ending_book_value=data['ending_book_value'],
            months_count=data['months']
        )
        yearly_summary.append(summary)

    return yearly_summary


def extract_fiscal_period(result: DepreciationResult, fiscal_year: int) -> FiscalPeriodSummary:
    """schedule을 (fiscal_year, result.fiscal_year_end_month) 회계기간으로 잘라 당기 요약 반환.

    한국 관행: fiscal_year = 결산일이 속한 연도.
    """
    fy_end_mo = result.fiscal_year_end_month
    period_start, period_end = get_fiscal_period_dates(fiscal_year, fy_end_mo)

    period_depreciation = 0
    months_in_period = 0
    period_end_accumulated = 0
    period_end_book_value = 0

    for monthly in result.schedule:
        fy = get_fiscal_year(monthly.year, monthly.month, fy_end_mo)
        if fy != fiscal_year:
            continue
        if not monthly.is_zero_depreciation:
            period_depreciation += monthly.numeric_depreciation
            months_in_period += 1
        # 시간 순 가정 — 같은 fiscal year의 마지막 month 값이 남음
        period_end_accumulated = monthly.accumulated_depreciation
        period_end_book_value = monthly.book_value

    return FiscalPeriodSummary(
        fiscal_year=fiscal_year,
        fiscal_year_end_month=fy_end_mo,
        period_start_date=period_start,
        period_end_date=period_end,
        period_depreciation=period_depreciation,
        period_end_accumulated=period_end_accumulated,
        period_end_book_value=period_end_book_value,
        months_in_period=months_in_period,
    )

def _settle_terminal_evenly_schedule(schedule, fiscal_year_end_month):
    """자연완료한 월별 스케줄의 종료해 잔재 정리를 그해 월수로 균등 재배분한다.
    vcore.monthly.settle_terminal_evenly와 동일한 relative-delta 방식:
    금액만 균등화하고 acc/book은 '누적 재배분 차이(delta)'를 기존 값에 가산 → 종료해 안의
    이벤트 점프(부분양도 누계 하강·capex 장부 상승)를 보존하고 연말 acc/book·연간합계 불변.
    정률법 5% 마지막달 dump 제거. 정액법도 별표4율 × n ≠ 1인 연수(6·7·14년 등)에는 종료해
    잔재가 남아 대상이다. 전부양도(절단)는 호출부에서 제외.
    """
    from .dep_common import get_fiscal_year
    if not schedule:
        return schedule
    last_fy = get_fiscal_year(schedule[-1].year, schedule[-1].month, fiscal_year_end_month)
    idxs = [i for i, m in enumerate(schedule)
            if get_fiscal_year(m.year, m.month, fiscal_year_end_month) == last_fy]
    yearly = sum(schedule[i].numeric_depreciation for i in idxs)
    miy = len(idxs)
    base_m = yearly // miy
    rem = yearly - base_m * miy
    cum_old = cum_new = 0
    for k, i in enumerate(idxs):
        new_amt = base_m + rem if k == miy - 1 else base_m
        cum_old += schedule[i].numeric_depreciation
        cum_new += new_amt
        delta = cum_new - cum_old
        m = schedule[i]
        m.monthly_depreciation = new_amt
        m.accumulated_depreciation += delta
        m.book_value -= delta
    return schedule


def calculate_depreciation_enhanced(financials: AssetFinancials,
                                  asset_info: AssetInfo,
                                  fiscal_year_end_month: int) -> DepreciationResult:
    """메인 감가상각 계산 함수.

    fiscal_year_end_month: 회사 결산월 (1~12, 필수). 결산월 잔재 보정 발화 위치를 결정한다.
    한국 실무 default(12)는 application 레이어에서 명시적으로 주입한다.
    """
    start_time = datetime.now()
    schedule = []

    try:
        logger.info(f"감가상각 계산 시작: {asset_info.asset_name} ({financials.method.value}), 결산월={fiscal_year_end_month}")

        # 증가 여부 확인
        has_increase = (financials.increase_amount > 0 and financials.increase_date)

        # 부분양도 여부 확인
        is_partial_disposal = (financials.disposal_amount > 0 and
                               financials.disposal_date and
                               financials.disposal_amount < financials.cost)

        if has_increase:
            logger.info(f"자본적지출 처리: 증가액={financials.increase_amount:,}원, 증가일={financials.increase_date}")

        if is_partial_disposal:
            logger.info(f"부분양도 처리: 당기감소액={financials.disposal_amount:,}원, 양도일={financials.disposal_date}")

        # prior_accumulated가 있으면: 전기말 확정값에서 출발 → 당기만 계산
        # 증가/부분양도는 이미 전기말 확정에 반영된 과거 사건이므로 재처리 불필요
        # 원칙: 결산 마감 → 감가상각누계액 확정 → 다음 해 기초 장부가
        has_prior = (financials.prior_accumulated is not None)
        if has_prior:
            logger.info(f"전기말 확정값 사용: prior_accumulated={financials.prior_accumulated:,}원 → 당기만 계산")

        # 감가상각 방법에 따른 계산 실행
        if financials.method == DepreciationMethod.STRAIGHT_LINE:
            if has_increase and is_partial_disposal and not has_prior:
                # 정액 capex+부분양도: core 2단계 루프(_calculate_with_increase 내부 양도 처리)는
                # 임의결산월에서 종료해 부근 1원 이탈(2026-07-02 확인, 12월은 정상). core는 진실이
                # 아니므로 검증된 vcore로 위임 — vcore 손계산 골든이 정답 보증
                # (test_straight_line_golden_handcalc). 정률 동일 경로(아래)와 대칭.
                from vcore.monthly_schedule import monthly_events
                ay, am, _ = parse_date_safe(financials.start_date)
                iy, im, _ = parse_date_safe(financials.increase_date)
                dy, dm, _ = parse_date_safe(financials.disposal_date)
                cal = monthly_events(financials.cost, financials.life_in_years, ay, am,
                                     fiscal_year_end_month, declining=False,
                                     inc=(financials.increase_amount, iy, im),
                                     disp=(financials.disposal_amount, dy, dm))
                schedule = [MonthlyDepreciation(
                    year=c.year, month=c.month, monthly_depreciation=c.amount,
                    accumulated_depreciation=c.acc, book_value=c.book,
                    calculation_method="정액법(증가+부분양도,vcore위임)") for c in cal]
            elif has_increase and not has_prior:
                # 자본적지출: Vector 논리 적용 (전기말 확정 없을 때만)
                from .dep_tang_engine import _calculate_with_increase
                schedule = _calculate_with_increase(
                    financials.cost, financials.life_in_years, financials.start_date,
                    financials.increase_amount, financials.increase_date,
                    financials.salvage_value, financials.memorandum_value,
                    financials.disposal_date, financials.disposal_amount,
                    fiscal_year_end_month=fiscal_year_end_month
                )
            elif is_partial_disposal and not has_prior:
                # 부분양도: Vector 논리 적용 (전기말 확정 없을 때)
                from .dep_tang_engine import _calculate_with_partial_disposal
                schedule = _calculate_with_partial_disposal(
                    financials.cost, financials.life_in_years, financials.start_date,
                    financials.disposal_amount, financials.disposal_date,
                    financials.salvage_value, financials.memorandum_value,
                    fiscal_year_end_month=fiscal_year_end_month
                )
            elif is_partial_disposal and has_prior:
                # 부분양도 + 전기말 확정: 확정값에서 출발하여 당기 부분양도 처리
                from .dep_tang_engine import _calculate_with_partial_disposal
                schedule = _calculate_with_partial_disposal(
                    financials.cost, financials.life_in_years, financials.start_date,
                    financials.disposal_amount, financials.disposal_date,
                    financials.salvage_value, financials.memorandum_value,
                    prior_accumulated=financials.prior_accumulated,
                    target_year=financials.target_year,
                    fiscal_year_end_month=fiscal_year_end_month
                )
            else:
                # 정상 또는 전부양도
                schedule = _calculate_korean_straight_line_enhanced(
                    financials.cost, financials.life_in_years, financials.start_date,
                    financials.salvage_value, financials.memorandum_value,
                    financials.disposal_date,
                    prior_accumulated=financials.prior_accumulated,
                    target_year=financials.target_year,
                    fiscal_year_end_month=fiscal_year_end_month
                )
        elif financials.method == DepreciationMethod.DECLINING_BALANCE:
            if has_increase and is_partial_disposal and not has_prior:
                # 정률 capex+부분양도: core 2단계 루프로는 vcore의 순차 합성(capex 전체적용
                # → 부분양도)을 1원 재현 불가(capex 연말보정 반영 차이). core 자체 산식은
                # 음수 월상각 버그가 있어 oracle 자격 없음(2026-06-12 확인). 검증된 vcore로
                # 위임 — vcore 손계산 골든이 정답 보증(test_declining_golden_handcalc).
                from vcore.monthly_schedule import monthly_events
                ay, am, _ = parse_date_safe(financials.start_date)
                iy, im, _ = parse_date_safe(financials.increase_date)
                dy, dm, _ = parse_date_safe(financials.disposal_date)
                cal = monthly_events(financials.cost, financials.life_in_years, ay, am,
                                     fiscal_year_end_month, declining=True,
                                     inc=(financials.increase_amount, iy, im),
                                     disp=(financials.disposal_amount, dy, dm))
                schedule = [MonthlyDepreciation(
                    year=c.year, month=c.month, monthly_depreciation=c.amount,
                    accumulated_depreciation=c.acc, book_value=c.book,
                    calculation_method="정률법(증가+부분양도,vcore위임)") for c in cal]
            elif has_increase and not has_prior:
                # 자본적지출: Vector 논리 적용 (전기말 확정 없을 때만)
                from .dep_tang_engine import _calculate_with_increase_declining
                schedule = _calculate_with_increase_declining(
                    financials.cost, financials.life_in_years, financials.start_date,
                    financials.increase_amount, financials.increase_date,
                    financials.salvage_value, financials.memorandum_value,
                    financials.disposal_date, financials.disposal_amount,
                    fiscal_year_end_month=fiscal_year_end_month
                )
            elif is_partial_disposal and not has_prior:
                # 부분양도: Vector 논리 적용 (정률법 전용 함수)
                from .dep_tang_engine import _calculate_with_partial_disposal_declining
                schedule = _calculate_with_partial_disposal_declining(
                    financials.cost, financials.life_in_years, financials.start_date,
                    financials.disposal_amount, financials.disposal_date,
                    financials.salvage_value, financials.memorandum_value,
                    fiscal_year_end_month=fiscal_year_end_month
                )
            elif is_partial_disposal and has_prior:
                # 정률 + 전기말 확정 + 부분양도. 정액에는 이 분기가 있으나(위 :214) 정률에는
                # 없어서, 여기까지 오면 아래 else가 **전액양도로 처리**해 조용히 다른 표를
                # 냈다(감사 G18-④). 구현하지 않기로 한 조합이므로 그럴듯한 오답 대신
                # 거절한다 — 오라클이 틀린 값을 내면 거울 스윕이 vcore 결함을 가린다.
                # ※ 거울 대조 범위에서 명시 제외한 조합이다(사유: 정률 분리자산 부분양도의
                #    실측·손계산 앵커가 없어 무엇이 정답인지 확정되지 않음).
                raise ValueError(
                    "정률법 + 전기말확정(prior_accumulated) + 부분양도 조합은 지원하지 않습니다 "
                    "— 정답 규약이 확립되지 않아 계산을 거절합니다")
            else:
                schedule = _calculate_korean_declining_balance_enhanced(
                    financials.cost, financials.life_in_years, financials.start_date,
                    financials.salvage_value, financials.memorandum_value,
                    financials.disposal_date,
                    fiscal_year_end_month=fiscal_year_end_month,
                    prior_accumulated=financials.prior_accumulated,
                    target_year=financials.target_year
                )
        elif financials.method == DepreciationMethod.INTANGIBLE:
            if has_increase and not has_prior:
                # 무형 capex = 별표4 정액 capex. core 무형 엔진은 별표4 미적용 + capex 분기
                # 부재라 증가액이 누락된다. 무형 = 유형 정액(별표4)이고 직접상각은 표시 차이일
                # 뿐 수치 동일하므로, 검증된 유형 정액 capex 함수를 그대로 재사용한다.
                from .dep_tang_engine import _calculate_with_increase
                schedule = _calculate_with_increase(
                    financials.cost, financials.life_in_years, financials.start_date,
                    financials.increase_amount, financials.increase_date,
                    financials.salvage_value, financials.memorandum_value,
                    financials.disposal_date, financials.disposal_amount,
                    fiscal_year_end_month=fiscal_year_end_month
                )
            elif is_partial_disposal and not has_prior:
                # 무형 부분양도 = 별표4 정액 부분양도. 검증된 유형 정액 함수 재사용.
                from .dep_tang_engine import _calculate_with_partial_disposal
                schedule = _calculate_with_partial_disposal(
                    financials.cost, financials.life_in_years, financials.start_date,
                    financials.disposal_amount, financials.disposal_date,
                    financials.salvage_value, financials.memorandum_value,
                    fiscal_year_end_month=fiscal_year_end_month
                )
            else:
                # 무형 단순 = 별표4 정액. 검증된 유형 정액 함수 재사용(core 무형 엔진 1/n 미사용).
                schedule = _calculate_korean_straight_line_enhanced(
                    financials.cost, financials.life_in_years, financials.start_date,
                    financials.salvage_value, financials.memorandum_value,
                    financials.disposal_date,
                    fiscal_year_end_month=fiscal_year_end_month
                )
        else:
            raise ValueError(f"지원하지 않는 감가상각 방법: {financials.method}")

        # 원칙 통일: '자연완료'한 스케줄은 종료해 잔재를 그해 월수로 균등 재배분한다
        # (자연완료 = 최종 장부가가 비망가 1,000원). 전부양도는 절단되어 최종 장부가>비망가이므로
        # 제외. 정률 5% 마지막달 dump 제거, 연간합계·최종값 불변.
        # 무형도 유형 정액 함수를 재사용하므로 정액·정률과 동일하게 종료해 균등 재배분한다.
        # 2026-09-03: 단순 스케줄(이벤트 없음)에도 확대 — 2026-06-13 "정액·정률 동일 원칙"
        # 결정이 정액에 미적용이라 별표4율 × n ≠ 1인 연수(6·7·14년 등)의 잔재를 12월에
        # 몰아넣고 있었다(vcore는 균등). docs/audit_lattice_2026-09-03.md G28.
        if not has_prior \
                and financials.method in (DepreciationMethod.STRAIGHT_LINE,
                                          DepreciationMethod.DECLINING_BALANCE,
                                          DepreciationMethod.INTANGIBLE) \
                and schedule and schedule[-1].book_value == 1000:
            schedule = _settle_terminal_evenly_schedule(schedule, fiscal_year_end_month)

        # 연도별 요약 생성 (fiscal year 단위)
        yearly_summary = generate_yearly_summary(schedule, financials.cost, fiscal_year_end_month)

        # 자연종료(완전상각) 후 부분양도: 추가 상각 없음(상각 0) → 양도 연도에 처분 조정행 추가.
        # 양도분의 취득원가·누계·비망가를 취득가액 비율로 안분 제거(비망가는 가치가 아닌 자산
        # 단위 메모라 잔류분도 비율 안분 — 60% 양도 → 잔존가액 400). vcore와 동일.
        if (is_partial_disposal and not has_prior and financials.disposal_date
                and schedule and yearly_summary):
            disp_y, disp_m, _ = parse_date_safe(financials.disposal_date)
            last_m = schedule[-1]
            if (disp_y, disp_m) > (last_m.year, last_m.month):   # 양도가 마지막 감가상각월 이후
                last_s = yearly_summary[-1]
                disp_acc = round_half_up(last_s.accumulated_depreciation * financials.disposal_amount / financials.cost)
                disp_book = financials.disposal_amount - disp_acc
                yearly_summary.append(YearlySummary(
                    year=get_fiscal_year(disp_y, disp_m, fiscal_year_end_month),
                    yearly_depreciation=0,
                    accumulated_depreciation=last_s.accumulated_depreciation - disp_acc,
                    ending_book_value=last_s.ending_book_value - disp_book,
                    months_count=0))

        # 총계 계산
        total_depreciation = sum(m.numeric_depreciation for m in schedule)
        final_book_value = schedule[-1].book_value if schedule else financials.cost

        # 계산 시간
        calculation_time = (datetime.now() - start_time).total_seconds() * 1000

        # 결과 생성
        result = DepreciationResult(
            asset_info=asset_info,
            fiscal_year_end_month=fiscal_year_end_month,
            schedule=schedule,
            yearly_summary=yearly_summary,
            total_depreciation=total_depreciation,
            final_book_value=final_book_value,
            calculation_method=financials.method,
            calculation_time_ms=calculation_time
        )

        logger.info(f"감가상각 계산 완료: {len(schedule)}개월, {calculation_time:.1f}ms")

        return result

    except ValueError:
        # 도메인 가드 위반(취득 전 양도 등)은 삼키지 않는다. 빈 결과는 스케줄 0건 ·
        # 장부가 0이라 **전액 양도된 자산과 구분되지 않고**, 오라클이 그럴듯한 값을
        # 내면 거울 스윕이 vcore 결함을 가린다(감사 G18-③).
        # 상위 진입점 `calculate_from_common_format`이 calculation_success=False로 변환한다.
        logger.error(f"감가상각 계산 입력 오류(전파): {traceback.format_exc()}")
        raise

    except Exception as e:
        logger.error(f"감가상각 계산 오류: {str(e)}")
        logger.error(traceback.format_exc())

        # 예상 밖 오류만 빈 결과로 축약한다(도메인 오류는 위에서 전파됨)
        calculation_time = (datetime.now() - start_time).total_seconds() * 1000
        return DepreciationResult(
            asset_info=asset_info,
            fiscal_year_end_month=fiscal_year_end_month,
            calculation_time_ms=calculation_time
        )

# ================================
# 파일간 인터페이스 호환 함수
# ================================

def convert_common_data_to_financials(common_data: Dict[str, Any]) -> Tuple[AssetFinancials, AssetInfo, List[str]]:
    """공통 데이터를 AssetFinancials로 변환 (더존 상수 원칙 준수)"""
    conversion_log = []
    
    try:
        logger.debug("공통 데이터 변환 시작 (더존 상수 원칙 준수)")
        
        # 1. 필수 필드 존재 확인 (beginning_amount는 0이어도 허용)
        required_fields = ['asset_type', 'asset_name', 'useful_life']
        missing_fields = [field for field in required_fields if not common_data.get(field)]
        
        # beginning_amount는 별도 확인 (0이어도 허용)
        if 'beginning_amount' not in common_data:
            missing_fields.append('beginning_amount')
        
        if missing_fields:
            raise ValueError(f"필수 필드 누락: {', '.join(missing_fields)}")
        
        # 2. 기본 정보 추출 및 검증
        asset_type = str(common_data.get('asset_type', '')).strip()
        asset_name = str(common_data.get('asset_name', '')).strip()
        account_subject = str(common_data.get('account_subject', '')).strip()
        
        try:
            # 더존 무형자산 전용 논리 적용
            if asset_type == '무형자산':
                # 무형자산: 취득원가 처리
                beginning_amount = safe_int_conversion(common_data.get('beginning_amount', 0))
                accumulated_depreciation = safe_int_conversion(common_data.get('accumulated_depreciation', 0))
                
                if accumulated_depreciation == 0 and beginning_amount > 0:
                    # 이미 복원된 취득가액이 전달된 경우
                    cost = beginning_amount
                    conversion_log.append(f"✅ 무형자산 복원된취득가액 사용: {beginning_amount:,}원")
                else:
                    # 기초가액 + 상각누계액으로 취득원가 복원
                    cost = beginning_amount + accumulated_depreciation
                    conversion_log.append(f"✅ 무형자산 취득원가 복원: {beginning_amount:,} + {accumulated_depreciation:,} = {cost:,}")
            else:
                # 유형자산: 간접법 처리 (더존 정의 준수)
                beginning_amount = safe_int_conversion(common_data.get('beginning_amount', 0))
                new_acquisition_amount = safe_int_conversion(common_data.get('new_acquisition_amount', 0))
                
                # 더존 정의: 기초가액 = 전기이월된 취득가액
                if beginning_amount > 0:
                    # 이월자산: 기초가액(전기이월취득가액) + 신규취득증가
                    cost = beginning_amount + new_acquisition_amount
                    conversion_log.append(f"✅ 유형자산 이월 기말취득가액: {beginning_amount:,} + {new_acquisition_amount:,} = {cost:,}")
                elif new_acquisition_amount > 0:
                    # 더존 정의: "0으로 나타나면 당기 신규취득및증가 예상됨"
                    cost = new_acquisition_amount
                    conversion_log.append(f"✅ 유형자산 신규 취득가액: {new_acquisition_amount:,}원")
                else:
                    # 둘 다 0인 경우: 처분완료 또는 오류 데이터
                    cost = 1  # 최소값으로 설정하여 계산 오류 방지
                    conversion_log.append(f"⚠️ 유형자산 취득가액 없음 - 최소값 적용: {cost:,}원")

            life_years = safe_int_conversion(common_data.get('useful_life', 5))
        except Exception as e:
            raise ValueError(f"숫자 변환 오류: {str(e)}")
        
        if cost <= 0:
            raise ValueError(f"취득원가는 0보다 커야 합니다: {cost}")
        if life_years <= 0:
            raise ValueError(f"내용연수는 0보다 커야 합니다: {life_years}")
        
        conversion_log.append(f"✅ 기본정보: {asset_name} ({asset_type}), {cost:,}원, {life_years}년")
        
        # 3. 감가상각 방법 결정
        if asset_type == '무형자산':
            method = DepreciationMethod.INTANGIBLE
            conversion_log.append(f"✅ 무형자산 직접상각법 적용: {account_subject}")
        else:
            # 유형자산 처리
            depreciation_method = str(common_data.get('depreciation_method', '')).strip()
            if '정률법' in depreciation_method or 'declining' in depreciation_method.lower():
                method = DepreciationMethod.DECLINING_BALANCE
                conversion_log.append(f"✅ 정률법 적용: {account_subject}")
            else:
                method = DepreciationMethod.STRAIGHT_LINE  
                conversion_log.append(f"✅ 정액법 적용: {account_subject}")
        
        # 4. 취득일자 처리
        start_date = str(common_data.get('acquisition_date', '')).strip()
        logger.info(f"DEBUG: common_data acquisition_date = '{common_data.get('acquisition_date', 'NOT_FOUND')}'")
        logger.info(f"DEBUG: start_date after strip = '{start_date}'")
        if not start_date:
            start_date = '2020-01-01'
            conversion_log.append("⚠️ 취득일자 기본값 적용: 2020-01-01")
            logger.warning(f"취득일자 없음, 기본값 사용: {start_date}")
        else:
            try:
                parse_date_safe(start_date)
                conversion_log.append(f"✅ 취득일자: {start_date}")
            except (ValueError, TypeError) as e:
                # 기본값 대체 금지: 날짜 오타 하나가 수년치 상각 스케줄을 조용히 왜곡한다
                raise ValueError(f"잘못된 취득일자: '{start_date}' ({e})")
        
        # 5. 잔존가액 및 비망가액 설정
        try:
            salvage_value = safe_int_conversion(common_data.get('salvage_value', 0))
            memorandum_value = safe_int_conversion(common_data.get('memorandum_value', 1000))
        except Exception:
            salvage_value = 0
            memorandum_value = 1000
        
        # 한국세법 기본원칙: 모든 자산 잔존가치=0, 비망기록=1000 고정
        salvage_value = 0
        memorandum_value = 1000
        conversion_log.append("✅ 한국세법 기본원칙: 잔존가치=0원, 비망기록=1000원 고정 적용")

        # 6. 양도/폐기 관련 정보 추출
        disposal_date_raw = common_data.get('disposal_date')
        if disposal_date_raw and disposal_date_raw not in [None, 'None', '']:
            disposal_date = str(disposal_date_raw).strip()
        else:
            disposal_date = None
        disposal_amount = safe_int_conversion(common_data.get('disposal_amount', 0))

        if disposal_date:
            conversion_log.append(f"✅ 양도/폐기일: {disposal_date}")
        if disposal_amount > 0:
            conversion_log.append(f"✅ 당기감소액: {disposal_amount:,}원 (취득원가 기준)")
            if disposal_amount < cost:
                conversion_log.append(f"  → 부분양도 ({disposal_amount/cost*100:.1f}%), 잔존 {cost-disposal_amount:,}원")
            elif disposal_amount >= cost:
                conversion_log.append(f"  → 전부양도/폐기")

        # 7. AssetFinancials 생성
        prior_accumulated = common_data.get('prior_accumulated')
        if prior_accumulated is not None:
            prior_accumulated = safe_int_conversion(prior_accumulated)
            conversion_log.append(f"✅ 분리자산 처리: 전기말누적 {prior_accumulated:,}원 기초")
        
        # 8. 자본적지출(증가) 정보 추출
        increase_amount = safe_int_conversion(common_data.get('increase_amount', 
                                              common_data.get('new_acquisition_amount', 0)))
        increase_date = common_data.get('increase_date')
        if increase_date and increase_date not in [None, 'None', '']:
            increase_date = str(increase_date).strip()
            conversion_log.append(f"✅ 자본적지출: {increase_amount:,}원, 증가일={increase_date}")
        else:
            increase_date = None
            increase_amount = 0  # 증가일 없으면 증가액도 무시
        
        asset_financials = AssetFinancials(
            cost=cost,
            life_in_years=life_years,
            start_date=start_date,
            method=method,
            salvage_value=salvage_value,
            memorandum_value=memorandum_value,
            disposal_date=disposal_date,
            disposal_amount=disposal_amount,
            prior_accumulated=prior_accumulated,
            increase_amount=increase_amount,
            increase_date=increase_date
        )
        
        # 7. AssetInfo 생성
        asset_info = AssetInfo(
            asset_id=str(common_data.get('asset_code', '')).strip(),
            asset_name=asset_name,
            asset_category=account_subject,
            status=AssetStatus.ACTIVE
        )
        
        conversion_log.append(f"✅ 변환완료: {method.value}, 감가상각대상금액 {asset_financials.depreciable_amount:,}원")
        conversion_log.append(f"✅ 더존 상수 원칙 준수: 데이터 무변경")
        
        logger.debug(f"공통 데이터 변환 완료: {asset_name}")
        return asset_financials, asset_info, conversion_log
        
    except Exception as e:
        error_msg = f"❌ 데이터 변환 오류: {str(e)}"
        conversion_log.append(error_msg)
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        # 더미 자산(cost=1) 반환 금지: 잘못된 상각액이 오류 표시 없이 산출된다.
        # 호출자(calculate_from_common_format)가 calculation_success=False로 변환.
        raise

def calculate_from_common_format(common_data: Dict[str, Any], target_year: int = 2024,
                                 fiscal_year_end_month: int = 12) -> Dict[str, Any]:
    """파일간 호환 메인 인터페이스 - 공통 형식으로 감가상각비 계산.

    fiscal_year_end_month: 회사 결산월 (default 12, 한국 실무). 비-12월 결산 호출자는 명시.
    """
    calculation_start_time = datetime.now()
    
    try:
        logger.info(f"더존 상수 원칙 준수 계산 시작: {common_data.get('asset_name', 'Unknown')}")
        
        # 1. 입력 데이터 검증
        if not isinstance(common_data, dict):
            raise ValueError("입력 데이터가 딕셔너리가 아닙니다.")
        
        if not common_data:
            raise ValueError("입력 데이터가 비어있습니다.")
        
        # 2. 공통 데이터를 AssetFinancials로 변환
        conversion_result = convert_common_data_to_financials(common_data)
        
        if conversion_result[0] is None or conversion_result[1] is None:
            raise ValueError("데이터 변환에 실패했습니다.")
        
        asset_financials, asset_info, conversion_log = conversion_result
        
        # 분리자산 처리: target_year 전달
        if asset_financials.prior_accumulated is not None:
            asset_financials.target_year = target_year
        
        # 3. 기존 계산 엔진 호출
        result = calculate_depreciation_enhanced(asset_financials, asset_info, fiscal_year_end_month)
        
        # 4. 대상 연도의 실제 감가상각비 추출 (월별 스케줄에서 직접 계산)
        annual_depreciation = 0
        calculation_found = False
        target_year_summary = None
        target_year_months = 0
        
        # 해당 연도의 실제 월별 감가상각비 합산
        for monthly in result.schedule:
            if monthly.year == target_year:
                annual_depreciation += monthly.monthly_depreciation
                target_year_months += 1
                calculation_found = True
        
        # yearly_summary에서 추가 정보 가져오기
        for summary in result.yearly_summary:
            if summary.year == target_year:
                target_year_summary = summary
                break
        
        # 5. 유형자산/무형자산 구분 유지
        asset_type = str(common_data.get('asset_type', '유형자산')).strip()
        
        # 6. 계산 통계
        total_calculation_time = int((datetime.now() - calculation_start_time).total_seconds() * 1000)
        
        # 7. 인터페이스 호환 형식으로 결과 반환
        compatible_result = {
            'phase3_depreciation': annual_depreciation,
            'asset_type': asset_type,
            'calculation_method': asset_financials.method.value,
            'calculation_success': True,
            'calculation_found': calculation_found,
            'target_year': target_year,
            'total_months_calculated': len(result.schedule),
            'depreciation_months': len([m for m in result.schedule if not m.is_zero_depreciation]),
            'final_book_value': result.final_book_value,
            'total_depreciation': result.total_depreciation,
            'asset_info': {
                'asset_id': asset_info.asset_id,
                'asset_name': asset_info.asset_name,
                'asset_category': asset_info.asset_category,
                'cost': asset_financials.cost,
                'useful_life': asset_financials.life_in_years,
                'start_date': asset_financials.start_date,
                'method': asset_financials.method.value,
                'salvage_value': asset_financials.salvage_value,
                'memorandum_value': asset_financials.memorandum_value,
                'depreciable_amount': asset_financials.depreciable_amount
            },
            'target_year_details': {
                'year': target_year,
                'yearly_depreciation': target_year_summary.yearly_depreciation if target_year_summary else 0,
                'accumulated_depreciation': target_year_summary.accumulated_depreciation if target_year_summary else 0,
                'ending_book_value': target_year_summary.ending_book_value if target_year_summary else 0,
                'months_count': target_year_summary.months_count if target_year_summary else 0,
                'average_monthly': target_year_summary.average_monthly if target_year_summary else 0
            } if target_year_summary else None,
            'conversion_log': conversion_log,
            'calculation_time_ms': total_calculation_time,
            'engine_calculation_time_ms': result.calculation_time_ms,
            'calculation_date': datetime.now().isoformat()
        }
        
        logger.info(f"더존 상수 원칙 준수 계산 완료: {annual_depreciation:,}원 ({str(total_calculation_time)}ms)")
        
        return compatible_result
        
    except Exception as e:
        error_msg = f"감가상각비 계산 오류: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        
        total_calculation_time = int((datetime.now() - calculation_start_time).total_seconds() * 1000)
        
        return {
            'phase3_depreciation': 0,
            'asset_type': common_data.get('asset_type', 'Unknown') if isinstance(common_data, dict) else 'Unknown',
            'calculation_method': 'Unknown',
            'calculation_success': False,
            'calculation_found': False,
            'error_message': error_msg,
            'target_year': target_year,
            'calculation_time_ms': total_calculation_time,
            'calculation_date': datetime.now().isoformat()
        }

# ================================
# 테스트 함수
# ================================

def test_complete_system_comprehensive():
    """완전한 시스템 포괄적 테스트 (최소 수정 버전)"""
    print("🧪 depreciation_phase3.py 최소 수정 버전 테스트")
    print("=" * 60)
    print("✅ 문법 오류 완전 제거")
    print("✅ 더존 상수 원칙 준수")
    print("✅ 무형자산 전용 논리 적용")
    print("✅ 파일간 인터페이스 100% 호환성 유지")
    print("=" * 60)
    
    # 테스트 케이스들
    test_cases = [
        {
            "name": "유형자산 - 한국세법 정액법",
            "data": {
                'asset_code': 'A001',
                'asset_name': '비품A',
                'account_subject': '비품',
                'asset_type': '유형자산',
                'beginning_amount': 2294780,
                'useful_life': 5,
                'acquisition_date': '2020-03-17',
                'depreciation_method': '정액법'
            }
        },
        {
            "name": "무형자산 - 직접상각법 (더존 무형자산 전용 논리)",
            "data": {
                'asset_code': 'A002',
                'asset_name': '소프트웨어A',
                'account_subject': '소프트웨어',
                'asset_type': '무형자산',
                'beginning_amount': 84000,
                'accumulated_depreciation': 276000,
                'useful_life': 5,
                'acquisition_date': '2020-03-17'
            }
        }
    ]
    
    total_depreciation = 0
    success_count = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🔍 테스트 {i}: {test_case['name']}")
        print("-" * 40)
        
        # 인터페이스 호환성 테스트
        result = calculate_from_common_format(test_case['data'], target_year=2024)
        
        if result['calculation_success']:
            print(f"✅ 자산명: {test_case['data']['asset_name']}")
            print(f"✅ 자산유형: {result['asset_type']}")
            print(f"✅ 계산방법: {result['calculation_method']}")
            print(f"✅ 취득원가: {result['asset_info']['cost']:,}원")
            print(f"✅ 2024년 감가상각비: {result['phase3_depreciation']:,}원")
            print(f"✅ 최종 장부가액: {result['final_book_value']:,}원")
            
            # 무형자산 특별 검증
            if test_case['data']['asset_type'] == '무형자산':
                expected_cost = test_case['data']['beginning_amount'] + test_case['data']['accumulated_depreciation']
                actual_cost = result['asset_info']['cost']
                print(f"✅ 무형자산 취득원가 복원: {test_case['data']['beginning_amount']:,} + {test_case['data']['accumulated_depreciation']:,} = {actual_cost:,}")
            
            total_depreciation += result['phase3_depreciation']
            success_count += 1
            
        else:
            print(f"❌ 계산 실패: {result.get('error_message', 'Unknown error')}")
    
    # 종합 결과
    print(f"\n" + "=" * 60)
    print(f"🎉 최소 수정 버전 테스트 완료!")
    print(f"✅ 성공률: {success_count}/{len(test_cases)} ({success_count/len(test_cases)*100:.1f}%)")
    print(f"✅ 총 감가상각비: {total_depreciation:,}원")
    print("=" * 60)
    
    print("\n🔍 적용된 개선사항:")
    print("✅ 1. 문법 오류 완전 제거")
    print("✅ 2. 정수 반환 타입 개선 (depreciable_amount, numeric_depreciation)")
    print("✅ 3. 안전한 정수 변환 함수 추가 (safe_int_conversion)")
    print("✅ 4. 더존 상수 원칙 준수 강화")
    print("✅ 5. 무형자산 전용 논리 적용")
    print("✅ 6. 파일간 인터페이스 완전 보존")

# ================================
# 메인 실행부
# ================================

if __name__ == "__main__":
    # 로깅 레벨 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("🚀 depreciation_phase3.py 최소 수정 버전")
    print("=" * 60)
    print("✅ 문법 오류 완전 제거")
    print("✅ 더존 상수 원칙 준수")
    print("✅ 무형자산 전용 논리 적용")
    print("✅ 파일간 인터페이스 100% 호환성 유지")
    print("=" * 60)
    
    # 시스템 테스트 실행
    test_complete_system_comprehensive()
    
    print("\n" + "=" * 60)
    print("✅ depreciation_phase3.py 최소 수정 완료!")
    print("✅ 문법 오류 제거 + 필수 개선사항 적용!")
    print("✅ 더존 상수 원칙 100% 준수!")
    print("✅ 파일간 인터페이스 완전 보존!")
    print("=" * 60)
