#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
감가상각 스케줄 생성기 CLI
Interactive CLI for Depreciation Schedule Generator

사용자로부터 자산 정보를 입력받아 월별 감가상각 스케줄을 Excel로 생성합니다.
"""

import sys
import os
from datetime import datetime

# asset_schedule_generator 모듈 import
from asset_schedule_generator import generate_depreciation_schedule


def print_header():
    """헤더 출력"""
    print("\n" + "=" * 80)
    print("감가상각 월별 스케줄 자동 생성기")
    print("Depreciation Schedule Generator")
    print("=" * 80)


def print_separator():
    """구분선 출력"""
    print("-" * 80)


def get_input(prompt: str, required: bool = True) -> str:
    """사용자 입력 받기"""
    while True:
        value = input(prompt).strip()
        if value or not required:
            return value
        print("[주의] 필수 입력 항목입니다. 다시 입력해주세요.")


def get_integer_input(prompt: str, min_value: int = None, max_value: int = None, required: bool = True) -> int:
    """정수 입력 받기"""
    while True:
        value_str = get_input(prompt, required)

        if not value_str and not required:
            return None

        # 콤마 제거
        value_str = value_str.replace(',', '')

        try:
            value = int(value_str)

            if min_value is not None and value < min_value:
                print(f"[주의] {min_value} 이상의 값을 입력해주세요.")
                continue

            if max_value is not None and value > max_value:
                print(f"[주의] {max_value} 이하의 값을 입력해주세요.")
                continue

            return value

        except ValueError:
            print("[주의] 올바른 숫자를 입력해주세요.")


def get_float_input(prompt: str, min_value: float = None, max_value: float = None, required: bool = True) -> float:
    """실수 입력 받기 (소수점 허용, 처분비율 등)"""
    while True:
        value_str = get_input(prompt, required)

        if not value_str and not required:
            return None

        value_str = value_str.replace(',', '')

        try:
            value = float(value_str)

            if min_value is not None and value < min_value:
                print(f"[주의] {min_value} 이상의 값을 입력해주세요.")
                continue

            if max_value is not None and value > max_value:
                print(f"[주의] {max_value} 이하의 값을 입력해주세요.")
                continue

            return value

        except ValueError:
            print("[주의] 올바른 숫자를 입력해주세요.")


def get_date_input(prompt: str, required: bool = True) -> str:
    """날짜 입력 받기 (YYYY-MM-DD)"""
    while True:
        value = get_input(prompt, required)

        if not value and not required:
            return None

        try:
            # 날짜 형식 검증
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            print("[주의] 올바른 날짜 형식이 아닙니다. YYYY-MM-DD 형식으로 입력해주세요. (예: 2023-03-15)")


def get_choice_input(prompt: str, choices: list, display_names: list = None) -> str:
    """선택지 입력 받기"""
    if display_names is None:
        display_names = choices

    print(f"\n{prompt}")
    for idx, display_name in enumerate(display_names, 1):
        print(f"  {idx}. {display_name}")

    while True:
        choice_str = input("선택 (번호 입력): ").strip()

        try:
            choice_idx = int(choice_str)
            if 1 <= choice_idx <= len(choices):
                return choices[choice_idx - 1]
            else:
                print(f"[주의] 1~{len(choices)} 사이의 번호를 입력해주세요.")
        except ValueError:
            print("[주의] 올바른 번호를 입력해주세요.")


def get_yes_no_input(prompt: str) -> bool:
    """예/아니오 입력 받기"""
    while True:
        value = input(f"{prompt} (y/n): ").strip().lower()
        if value in ['y', 'yes', '예', 'ㅇ']:
            return True
        elif value in ['n', 'no', '아니오', 'ㄴ']:
            return False
        else:
            print("[주의] y(예) 또는 n(아니오)를 입력해주세요.")


def collect_asset_info():
    """자산 정보 수집"""
    print("\n[입력] 자산 정보를 입력해주세요")
    print_separator()

    # 1. 자산명
    asset_name = get_input("1. 자산명: ")

    # 2. 취득일자
    print("\n[참고] 예시: 2023-03-15")
    acquisition_date = get_date_input("2. 취득일자 (YYYY-MM-DD): ")

    # 3. 취득원가
    print("\n[참고] 단위: 원 (콤마 입력 가능, 예: 10,000,000)")
    acquisition_cost = get_integer_input("3. 취득원가: ", min_value=1)

    # 4. 내용연수
    print("\n[참고] 단위: 년 (2~60년)")
    useful_life = get_integer_input("4. 내용연수: ", min_value=2, max_value=60)

    # 5. 자산유형
    asset_type = get_choice_input(
        "5. 자산유형:",
        choices=["유형자산", "무형자산"]
    )

    # 6. 감가상각방법
    if asset_type == "무형자산":
        print("\n6. 감가상각방법: 정액법 (무형자산은 정액법만 적용)")
        depreciation_method = "정액법"
    else:
        depreciation_method = get_choice_input(
            "6. 감가상각방법:",
            choices=["정액법", "정률법"]
        )

    # 7. 자본적지출(증가) 정보 (선택) - 처분보다 먼저 입력
    print_separator()
    has_increase = get_yes_no_input("\n[증가] 자본적지출(증가) 정보를 입력하시겠습니까?")

    increase_date = None
    increase_amount = None

    if has_increase:
        print("\n[참고] 예시: 2023-07-12")
        while True:
            increase_date = get_date_input("7. 증가일자 (YYYY-MM-DD): ")

            # 증가일자가 취득일자보다 이후인지 검증
            if increase_date > acquisition_date:
                break
            else:
                print(f"[주의] 증가일자는 취득일자({acquisition_date})보다 이후여야 합니다.")

        print("\n[참고] 단위: 원 (콤마 입력 가능, 예: 1,000,000)")
        increase_amount = get_integer_input("8. 증가금액: ", min_value=1)

        print(f"\n   [완료] 자본적지출: {increase_amount:,}원, 증가일: {increase_date}")

    # 8. 처분정보 (선택) - 자본적지출 이후 입력
    print_separator()
    has_disposal = get_yes_no_input("\n[처분] 처분정보를 입력하시겠습니까?")

    disposal_date = None
    disposal_amount = None
    disposal_ratio = None

    if has_disposal:
        print("\n[참고] 예시: 2025-06-30")
        while True:
            disposal_date = get_date_input("9. 처분일자 (YYYY-MM-DD): ")

            # 처분일자가 취득일자보다 이후인지 검증
            if disposal_date <= acquisition_date:
                print(f"[주의] 처분일자는 취득일자({acquisition_date})보다 이후여야 합니다.")
                continue

            # 자본적지출이 있는 경우, 처분일자가 증가일자보다 이후인지 검증
            if has_increase and increase_date and disposal_date <= increase_date:
                print(f"[주의] 처분일자는 증가일자({increase_date})보다 이후여야 합니다.")
                continue

            break

        # 전체양도 vs 부분양도 선택
        disposal_type = get_choice_input(
            "10. 처분유형:",
            choices=["전체양도", "부분양도"]
        )

        if disposal_type == "전체양도":
            disposal_amount = acquisition_cost
            disposal_ratio = 100.0
            if has_increase:
                print(f"\n   [완료] 전체양도: {disposal_amount:,}원 (원래 취득원가 100%)")
                print(f"   [참고] 주의: 자본적지출이 있어도 처분금액은 원래 취득원가 기준입니다")
            else:
                print(f"\n   [완료] 전체양도: {disposal_amount:,}원 (취득원가 100%)")
        else:
            # 부분양도: 입력 방식 선택
            input_method = get_choice_input(
                "11. 입력 방식:",
                choices=["비율(%)로 입력", "금액(원)으로 입력"]
            )

            if input_method == "비율(%)로 입력":
                # 방식 1: 비율 입력
                print(f"\n[참고] 원래 취득원가: {acquisition_cost:,}원")
                print("[참고] 원래 취득원가 대비 처분비율을 입력해주세요 (예: 60)")
                if has_increase:
                    print("[참고] 주의: 자본적지출이 있어도 비율은 원래 취득원가 기준입니다")
                disposal_ratio = get_float_input("12. 처분비율 (%): ", min_value=0.01, max_value=99.99)
                disposal_amount = int(acquisition_cost * disposal_ratio / 100)
                print(f"\n   [완료] 부분양도 {disposal_ratio:g}%: {disposal_amount:,}원 (자동계산)")
            else:
                # 방식 2: 금액 입력
                print(f"\n[참고] 원래 취득원가: {acquisition_cost:,}원")
                print("[참고] 원래 취득원가 기준으로 처분할 금액을 입력해주세요 (콤마 입력 가능)")
                if has_increase:
                    print("[참고] 주의: 자본적지출이 있어도 금액은 원래 취득원가 기준입니다")
                disposal_amount = get_integer_input("12. 처분금액 (원래 취득원가 기준): ", min_value=1, max_value=acquisition_cost - 1)
                disposal_ratio = round(disposal_amount / acquisition_cost * 100, 2)
                print(f"\n   [완료] 부분양도 {disposal_ratio:.1f}%: {disposal_amount:,}원")

    # [회사 회계정책] 결산월 (한국 12월 결산이 99%, 기본값 12)
    print_separator()
    print("\n[회사 회계정책] 결산월 (한국 실무 기본값 12월)")
    print("[참고] 12월 결산 회사면 그대로 12 입력, 미국 1월/일본 3월/9월 결산 등은 해당 월 명시")
    fiscal_year_end_month = get_integer_input(
        "13. 결산월 (1~12, default=12): ",
        min_value=1, max_value=12, required=False
    )
    if fiscal_year_end_month is None or fiscal_year_end_month == 0:
        fiscal_year_end_month = 12

    return {
        "asset_name": asset_name,
        "acquisition_date": acquisition_date,
        "acquisition_cost": acquisition_cost,
        "useful_life": useful_life,
        "asset_type": asset_type,
        "depreciation_method": depreciation_method,
        "disposal_date": disposal_date,
        "disposal_amount": disposal_amount,
        "disposal_ratio": disposal_ratio,
        "increase_date": increase_date,
        "increase_amount": increase_amount,
        "fiscal_year_end_month": fiscal_year_end_month
    }


def display_summary(info: dict):
    """입력 정보 요약 출력"""
    print("\n" + "=" * 80)
    print("[확인] 입력 정보 확인")
    print("=" * 80)
    print(f"자산명:           {info['asset_name']}")
    print(f"취득일자:         {info['acquisition_date']}")
    print(f"취득원가:         {info['acquisition_cost']:,}원")
    print(f"내용연수:         {info['useful_life']}년")
    print(f"자산유형:         {info['asset_type']}")
    print(f"감가상각방법:     {info['depreciation_method']}")
    if info.get('fiscal_year_end_month', 12) != 12:
        print(f"결산월:           {info['fiscal_year_end_month']}월 (비-12월 결산)")

    # 자본적지출 정보 먼저 표시
    if info.get('increase_date'):
        print(f"\n[자본적지출]")
        print(f"증가일자:         {info['increase_date']}")
        print(f"증가금액:         {info['increase_amount']:,}원")

    # 처분 정보 나중에 표시
    if info['disposal_date']:
        disposal_type = "전체양도" if info.get('disposal_ratio') == 100.0 else "부분양도"
        print(f"\n[처분 정보]")
        print(f"처분일자:         {info['disposal_date']}")
        print(f"처분유형:         {disposal_type}")
        if info.get('disposal_ratio'):
            print(f"처분비율:         {info['disposal_ratio']:.0f}%")
        # 자본적지출이 있으면 "원래 취득원가 기준" 명시
        if info.get('increase_date'):
            print(f"처분금액:         {info['disposal_amount']:,}원 (원래 취득원가 기준)")
        else:
            print(f"처분금액:         {info['disposal_amount']:,}원 (취득원가 기준)")

    print("=" * 80)


def main():
    """메인 함수"""
    try:
        print_header()

        # 자산 정보 수집
        asset_info = collect_asset_info()

        # 입력 정보 확인
        display_summary(asset_info)

        # 확인
        if not get_yes_no_input("\n[확인] 위 정보로 감가상각 스케줄을 생성하시겠습니까?"):
            print("\n[취소] 작업이 취소되었습니다.")
            return

        # Excel 파일 생성
        print("\n[진행] 감가상각 스케줄을 생성 중입니다...")

        output_path = generate_depreciation_schedule(
            asset_name=asset_info['asset_name'],
            acquisition_date=asset_info['acquisition_date'],
            acquisition_cost=asset_info['acquisition_cost'],
            useful_life=asset_info['useful_life'],
            asset_type=asset_info['asset_type'],
            depreciation_method=asset_info['depreciation_method'],
            disposal_date=asset_info['disposal_date'],
            disposal_amount=asset_info['disposal_amount'],
            increase_date=asset_info.get('increase_date'),
            increase_amount=asset_info.get('increase_amount'),
            fiscal_year_end_month=asset_info.get('fiscal_year_end_month', 12)
        )

        # 성공 메시지
        print("\n" + "=" * 80)
        print("[완료] 감가상각 스케줄이 성공적으로 생성되었습니다!")
        print("=" * 80)
        print(f"[파일] 파일 경로: {output_path}")
        print(f"[크기] 파일 크기: {os.path.getsize(output_path) / 1024:.1f} KB")
        print("=" * 80)

        # 추가 생성 여부
        print()
        if get_yes_no_input("[재실행] 다른 자산의 스케줄을 생성하시겠습니까?"):
            print("\n")
            main()  # 재귀 호출
        else:
            print("\n[종료] 프로그램을 종료합니다. 감사합니다!")

    except KeyboardInterrupt:
        print("\n\n[주의] 사용자가 작업을 중단했습니다.")
        sys.exit(0)

    except Exception as e:
        print("\n" + "=" * 80)
        print("[오류] 오류가 발생했습니다")
        print("=" * 80)
        print(f"오류 내용: {str(e)}")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
