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
utils.py - 감가상각 시스템 공통 유틸리티
=============================================

목적: 중복 코드 제거 및 재사용성 향상
- 안전한 데이터 변환 함수들
- 공통 로깅 유틸리티
- 날짜 처리 유틸리티
- 검증 함수들
"""

from typing import Any, Union
import logging
import re
from datetime import datetime, date, timedelta

# 로깅 설정
logger = logging.getLogger(__name__)

class DataConverter:
    """데이터 변환 유틸리티 클래스"""
    
    @staticmethod
    def safe_int_conversion(value: Any, default: int = 0) -> int:
        """
        안전한 정수 변환 (더존 상수 원칙 준수)
        
        Args:
            value: 변환할 값
            default: 변환 실패시 기본값
            
        Returns:
            int: 변환된 정수값
            
        Examples:
            >>> DataConverter.safe_int_conversion("123,456")
            123456
            >>> DataConverter.safe_int_conversion(None)
            0
            >>> DataConverter.safe_int_conversion("invalid", 100)
            100
        """
        try:
            if value is None or (isinstance(value, str) and value.strip() == ''):
                return default
            if isinstance(value, str):
                # 쉼표, 원 단위, 공백 제거
                value = value.replace(',', '').replace('원', '').replace('₩', '').strip()
                if not value or value == '-':
                    return default
            return int(float(value))
        except (ValueError, TypeError):
            logger.warning(f"정수 변환 실패: {value}, 기본값 {default} 사용")
            return default
    
    @staticmethod
    def safe_float_conversion(value: Any, default: float = 0.0) -> float:
        """
        안전한 실수 변환
        
        Args:
            value: 변환할 값
            default: 변환 실패시 기본값
            
        Returns:
            float: 변환된 실수값
            
        Examples:
            >>> DataConverter.safe_float_conversion("12.5%")
            12.5
            >>> DataConverter.safe_float_conversion("1,234.56")
            1234.56
        """
        try:
            if value is None or (isinstance(value, str) and value.strip() == ''):
                return default
            if isinstance(value, str):
                value = value.replace(',', '').replace('%', '').replace('원', '').strip()
                if not value or value == '-':
                    return default
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"실수 변환 실패: {value}, 기본값 {default} 사용")
            return default
    
    @staticmethod
    def safe_str_conversion(value: Any, default: str = '') -> str:
        """
        안전한 문자열 변환
        
        Args:
            value: 변환할 값
            default: 변환 실패시 기본값
            
        Returns:
            str: 변환된 문자열
        """
        try:
            if value is None:
                return default
            return str(value).strip()
        except Exception:
            logger.warning(f"문자열 변환 실패: {value}, 기본값 '{default}' 사용")
            return default


class DateProcessor:
    """날짜 처리 유틸리티 클래스"""
    
    @staticmethod
    def process_acquisition_date(date_value: Any) -> str:
        """
        취득일자 처리 (더존 상수 원칙 준수)
        
        Args:
            date_value: 날짜 값 (다양한 형식 지원)
            
        Returns:
            str: YYYY-MM-DD 형식의 날짜
            
        Examples:
            >>> DateProcessor.process_acquisition_date("2020.03.15")
            "2020-03-15"
            >>> DateProcessor.process_acquisition_date("20200315")
            "2020-03-15"
        """
        try:
            if not date_value or date_value in ['', '-', None]:
                return "1900-01-01"  # 기본값 (더존 상수)
            
            date_str = str(date_value).strip()
            
            # YYYY-MM-DD 형식 (더존 표준)
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                return date_str
            
            # YYYY.MM.DD 형식
            if re.match(r'^\d{4}\.\d{2}\.\d{2}$', date_str):
                return date_str.replace('.', '-')
            
            # YYYYMMDD 형식
            if re.match(r'^\d{8}$', date_str):
                return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            
            # Excel 날짜 숫자 형식
            try:
                days = int(float(date_str))
                if days > 25000:  # Excel epoch 이후
                    excel_epoch = date(1900, 1, 1)
                    actual_date = excel_epoch + timedelta(days=days-2)
                    return actual_date.strftime('%Y-%m-%d')
            except (ValueError, OverflowError):
                pass    # 숫자 형식이 아니면 다음 단계(형식 인식 불가 경고)로
            
            logger.warning(f"날짜 형식 인식 불가: {date_value}, 기본값 사용")
            return "1900-01-01"
            
        except Exception as e:
            logger.warning(f"취득일자 처리 오류: {date_value} → {str(e)}")
            return "1900-01-01"


class ValidationUtils:
    """검증 유틸리티 클래스"""
    
    @staticmethod
    def validate_asset_code(code: Union[str, int]) -> bool:
        """
        자산 코드 유효성 검증
        
        Args:
            code: 검증할 자산 코드
            
        Returns:
            bool: 유효하면 True, 그렇지 않으면 False
        """
        try:
            code_int = int(code)
            return 20000 <= code_int <= 25000  # 더존 자산 코드 범위
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_useful_life(years: Any) -> bool:
        """
        내용연수 유효성 검증
        
        Args:
            years: 검증할 내용연수
            
        Returns:
            bool: 유효하면 True (1~50년 범위)
        """
        try:
            years_int = DataConverter.safe_int_conversion(years)
            return 1 <= years_int <= 50
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_amount(amount: Any) -> bool:
        """
        금액 유효성 검증
        
        Args:
            amount: 검증할 금액
            
        Returns:
            bool: 유효하면 True (0 이상)
        """
        try:
            amount_float = DataConverter.safe_float_conversion(amount)
            return amount_float >= 0
        except (ValueError, TypeError):
            return False


class LoggingUtils:
    """로깅 유틸리티 클래스"""
    
    @staticmethod
    def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
        """
        표준 로거 설정
        
        Args:
            name: 로거 이름
            level: 로그 레벨
            
        Returns:
            logging.Logger: 설정된 로거
        """
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    @staticmethod
    def log_processing_stats(logger: logging.Logger, stats: dict):
        """
        처리 통계 로깅
        
        Args:
            logger: 사용할 로거
            stats: 통계 딕셔너리
        """
        logger.info("=" * 50)
        logger.info("처리 통계")
        logger.info("=" * 50)
        for key, value in stats.items():
            logger.info(f"{key}: {value}")
        logger.info("=" * 50)


class FormatUtils:
    """포맷팅 유틸리티 클래스"""
    
    @staticmethod
    def format_currency(amount: Union[int, float]) -> str:
        """
        통화 포맷팅
        
        Args:
            amount: 포맷할 금액
            
        Returns:
            str: 포맷된 금액 문자열
            
        Examples:
            >>> FormatUtils.format_currency(1234567)
            "1,234,567원"
        """
        try:
            return f"{int(amount):,}원"
        except (ValueError, TypeError):
            return "0원"
    
    @staticmethod
    def format_percentage(value: Union[int, float], decimals: int = 1) -> str:
        """
        퍼센트 포맷팅
        
        Args:
            value: 포맷할 값
            decimals: 소수점 자릿수
            
        Returns:
            str: 포맷된 퍼센트 문자열
        """
        try:
            return f"{float(value):.{decimals}f}%"
        except (ValueError, TypeError):
            return "0.0%"


# 하위 호환성을 위한 함수들 (기존 코드에서 직접 호출 가능)
def safe_int_conversion(value: Any, default: int = 0) -> int:
    """하위 호환성을 위한 함수"""
    return DataConverter.safe_int_conversion(value, default)

def safe_float_conversion(value: Any, default: float = 0.0) -> float:
    """하위 호환성을 위한 함수"""
    return DataConverter.safe_float_conversion(value, default)

def process_acquisition_date(date_value: Any) -> str:
    """하위 호환성을 위한 함수"""
    return DateProcessor.process_acquisition_date(date_value)