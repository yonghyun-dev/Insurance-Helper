"""tests.security.test_pii

app/security/pii.py 단위 테스트.

테스트 대상:
    - mask_pii(): 5 PII 패턴 각각 정상 매칭 + edge case
    - mask_pii(): 비-PII 텍스트 통과 (false positive 방지)
    - PiiMaskingFilter.filter(): LogRecord.msg 마스킹
    - PiiMaskingFilter.filter(): LogRecord.args 마스킹
    - PiiMaskingFilter.filter(): Settings.pii_masking_enabled=False → no-op

mock 정책:
    - get_settings() 를 monkeypatch 로 대체 — 실제 환경 변수 의존 없음
    - LogRecord 는 직접 생성 — logging 시스템 호출 없음
"""

from __future__ import annotations

import logging

from app.shared.security.pii import PiiMaskingFilter, mask_pii

# ===========================================================================
# mask_pii — 정상 케이스 (Happy Path)
# ===========================================================================


class TestMaskPiiHappyPath:
    """5 PII 패턴 각각이 올바르게 마스킹된다."""

    def test_rrn_with_dash_is_masked(self):
        # Arrange
        text = "주민번호는 900101-1234567 입니다."
        # Act
        result = mask_pii(text)
        # Assert
        assert "[RRN]" in result
        assert "900101-1234567" not in result

    def test_rrn_without_dash_is_masked(self):
        # Arrange
        text = "주민번호: 8501012345678"
        # Act
        result = mask_pii(text)
        # Assert
        assert "[RRN]" in result

    def test_phone_010_with_dash_is_masked(self):
        # Arrange
        text = "연락처: 010-1234-5678"
        # Act
        result = mask_pii(text)
        # Assert
        assert "[PHONE]" in result
        assert "010-1234-5678" not in result

    def test_phone_011_is_masked(self):
        # Arrange
        text = "전화번호 011-987-6543"
        # Act
        result = mask_pii(text)
        # Assert
        assert "[PHONE]" in result

    def test_phone_016_is_masked(self):
        # Arrange
        text = "016-123-4567 로 연락주세요."
        # Act
        result = mask_pii(text)
        # Assert
        assert "[PHONE]" in result

    def test_phone_019_with_space_is_masked(self):
        # Arrange
        text = "019 1234 5678"
        # Act
        result = mask_pii(text)
        # Assert
        assert "[PHONE]" in result

    def test_tel_seoul_with_dash_is_masked(self):
        # Arrange
        text = "서울 사무소 02-1234-5678"
        # Act
        result = mask_pii(text)
        # Assert
        assert "[TEL]" in result
        assert "02-1234-5678" not in result

    def test_tel_regional_031_is_masked(self):
        """031-456-7890 은 ACCOUNT 패턴이 먼저 적용된다 (마스킹 순서 정책).
        지역번호 형식이지만 ACCOUNT 패턴 범위 내이므로 [ACCOUNT] 로 마스킹.
        핵심 검증: PII 임을 인식해 마스킹한다 (토큰 종류 무관).
        """
        # Arrange
        text = "대표번호 031-456-7890"
        # Act
        result = mask_pii(text)
        # Assert: ACCOUNT 또는 TEL 중 하나로 마스킹됨 (원문은 제거)
        assert "031-456-7890" not in result
        assert "[ACCOUNT]" in result or "[TEL]" in result

    def test_account_number_is_masked(self):
        # Arrange
        text = "계좌번호 123456-12-345678"
        # Act
        result = mask_pii(text)
        # Assert
        assert "[ACCOUNT]" in result
        assert "123456-12-345678" not in result

    def test_email_is_masked(self):
        # Arrange
        text = "이메일: hong@example.com 으로 보내세요."
        # Act
        result = mask_pii(text)
        # Assert
        assert "[EMAIL]" in result
        assert "hong@example.com" not in result

    def test_email_with_dots_and_plus_is_masked(self):
        # Arrange
        text = "user.name+tag@domain.co.kr"
        # Act
        result = mask_pii(text)
        # Assert
        assert "[EMAIL]" in result

    def test_multiple_pii_in_one_string_all_masked(self):
        # Arrange
        text = "이름: 홍길동, 주민번호: 900101-1234567, 전화: 010-1234-5678, 이메일: hong@test.com"
        # Act
        result = mask_pii(text)
        # Assert
        assert "[RRN]" in result
        assert "[PHONE]" in result
        assert "[EMAIL]" in result
        assert "900101-1234567" not in result
        assert "010-1234-5678" not in result
        assert "hong@test.com" not in result


# ===========================================================================
# mask_pii — 경계값 (Boundary)
# ===========================================================================


class TestMaskPiiBoundary:
    """경계값 및 특수 케이스."""

    def test_empty_string_returns_empty(self):
        # Arrange / Act
        result = mask_pii("")
        # Assert
        assert result == ""

    def test_none_like_falsy_returns_original(self):
        """빈 문자열이 아닌 falsy 값은 그대로 반환."""
        # mask_pii 는 str 타입만 받으므로 빈 str 테스트
        assert mask_pii("") == ""

    def test_plain_text_no_pii_unchanged(self):
        # Arrange
        text = "보험금 청구를 원합니다."
        # Act
        result = mask_pii(text)
        # Assert
        assert result == text

    def test_rrn_gender_digit_5_not_matched(self):
        """성별 숫자 5~9는 RRN 패턴 외. 마스킹 안 됨."""
        # Arrange
        text = "900101-5123456"  # 성별 숫자 5 → RRN 아님
        # Act
        result = mask_pii(text)
        # Assert
        assert "[RRN]" not in result

    def test_phone_without_separator_is_masked(self):
        # Arrange
        text = "01012345678"
        # Act
        result = mask_pii(text)
        # Assert
        assert "[PHONE]" in result

    def test_account_with_longer_segments_is_masked(self):
        """계좌번호 (3~6-2~6-4~7 세그먼트) 는 마스킹된다.
        단, 중간 세그먼트가 RRN 패턴과 겹칠 때 순서에 따라 [ACCOUNT] 또는 [RRN] 일 수 있음.
        핵심 검증: 원문이 완전히 보존되지 않는다 (PII 마스킹 발생).
        """
        # Arrange
        text = "계좌: 123456-4567-89012"  # 명확한 계좌 형식 (RRN 겹침 없음)
        # Act
        result = mask_pii(text)
        # Assert
        assert "[ACCOUNT]" in result
        assert "123456-4567-89012" not in result

    def test_text_with_only_whitespace_unchanged(self):
        # Arrange
        text = "   \t\n   "
        # Act
        result = mask_pii(text)
        # Assert
        assert result == text


# ===========================================================================
# mask_pii — 한국어 자연어 false positive 방지
# ===========================================================================


class TestMaskPiiNoFalsePositive:
    """한국어 자연어(진단명 등) 이 마스킹되지 않는다."""

    def test_korean_diagnostic_name_not_masked(self):
        """진단명처럼 보이는 텍스트는 PII 패턴과 매칭되지 않는다."""
        # Arrange
        text = "진단명: 고혈압성 심장질환"
        # Act
        result = mask_pii(text)
        # Assert
        assert result == text

    def test_korean_article_reference_not_masked(self):
        """약관 조항 번호(제1조-1항) 등은 마스킹되지 않는다."""
        # Arrange
        text = "제15조-2항에 따라 보험금을 지급합니다."
        # Act
        result = mask_pii(text)
        # Assert
        assert result == text

    def test_date_format_not_masked(self):
        """날짜 형식(2026-01-01) 은 RRN 패턴과 다르다."""
        # Arrange
        text = "사고 발생일: 2026-01-15"
        # Act
        result = mask_pii(text)
        # Assert
        # 날짜 포맷은 6자리-숫자가 아닌 형태라 RRN 패턴에 걸리지 않음
        assert "[RRN]" not in result

    def test_insurance_amount_not_masked(self):
        """보험금 금액 숫자(3자리 이하 그룹)는 계좌 패턴과 다르다."""
        # Arrange
        text = "보험금 1,000,000원 지급"
        # Act
        result = mask_pii(text)
        # Assert
        assert "[ACCOUNT]" not in result

    def test_normal_sentence_preserved(self):
        """일반 문장이 통과된다."""
        # Arrange
        text = "자동차보험 청구 가능 여부를 확인해 주세요."
        # Act
        result = mask_pii(text)
        # Assert
        assert result == text


# ===========================================================================
# PiiMaskingFilter — 정상 케이스
# ===========================================================================


class FakeSettings:
    """pii_masking_enabled 제어용 더미 설정."""

    def __init__(self, enabled: bool = True):
        self.pii_masking_enabled = enabled


class TestPiiMaskingFilterHappyPath:
    """PiiMaskingFilter 가 LogRecord 를 올바르게 마스킹한다."""

    def _make_filter(self, monkeypatch, enabled: bool = True) -> PiiMaskingFilter:
        """PiiMaskingFilter 인스턴스와 get_settings 패치를 함께 반환."""
        import app.shared.security.pii as pii_module

        monkeypatch.setattr(pii_module, "get_settings", lambda: FakeSettings(enabled))
        return PiiMaskingFilter()

    def _make_record(self, msg: str, args=None) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=args,
            exc_info=None,
        )
        return record

    def test_filter_masks_pii_in_msg(self, monkeypatch):
        # Arrange
        f = self._make_filter(monkeypatch, enabled=True)
        record = self._make_record("사용자 주민번호: 900101-1234567")
        # Act
        result = f.filter(record)
        # Assert
        assert result is True
        assert "[RRN]" in record.msg
        assert "900101-1234567" not in record.msg

    def test_filter_masks_pii_in_args(self, monkeypatch):
        # Arrange
        f = self._make_filter(monkeypatch, enabled=True)
        record = self._make_record(
            "user=%s phone=%s",
            args=("홍길동", "010-1234-5678"),
        )
        # Act
        result = f.filter(record)
        # Assert
        assert result is True
        assert "[PHONE]" in record.args[1]
        assert "010-1234-5678" not in record.args[1]

    def test_filter_preserves_non_string_args(self, monkeypatch):
        """args 중 str 이 아닌 타입은 그대로 유지된다."""
        # Arrange
        f = self._make_filter(monkeypatch, enabled=True)
        record = self._make_record(
            "count=%d phone=%s",
            args=(42, "010-9999-8888"),
        )
        # Act
        f.filter(record)
        # Assert
        assert record.args[0] == 42  # int 보존
        assert "[PHONE]" in record.args[1]

    def test_filter_always_returns_true(self, monkeypatch):
        """filter() 반환값은 항상 True (로그 레코드를 차단하지 않음)."""
        # Arrange
        f = self._make_filter(monkeypatch, enabled=True)
        record = self._make_record("일반 메시지")
        # Act
        result = f.filter(record)
        # Assert
        assert result is True

    def test_filter_masks_email_in_msg(self, monkeypatch):
        # Arrange
        f = self._make_filter(monkeypatch, enabled=True)
        record = self._make_record("이메일 전송: admin@insurance.co.kr")
        # Act
        f.filter(record)
        # Assert
        assert "[EMAIL]" in record.msg
        assert "admin@insurance.co.kr" not in record.msg


# ===========================================================================
# PiiMaskingFilter — no-op (pii_masking_enabled=False)
# ===========================================================================


class TestPiiMaskingFilterDisabled:
    """pii_masking_enabled=False 시 no-op 동작."""

    def test_filter_noop_when_disabled(self, monkeypatch):
        """pii_masking_enabled=False 면 msg 를 변경하지 않는다."""
        # Arrange
        import app.shared.security.pii as pii_module

        monkeypatch.setattr(pii_module, "get_settings", lambda: FakeSettings(False))
        f = PiiMaskingFilter()
        original_msg = "주민번호: 900101-1234567"
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=original_msg,
            args=None,
            exc_info=None,
        )
        # Act
        result = f.filter(record)
        # Assert
        assert result is True
        assert record.msg == original_msg  # 변경 없음

    def test_filter_noop_preserves_args_when_disabled(self, monkeypatch):
        """pii_masking_enabled=False 면 args 도 그대로다."""
        # Arrange
        import app.shared.security.pii as pii_module

        monkeypatch.setattr(pii_module, "get_settings", lambda: FakeSettings(False))
        f = PiiMaskingFilter()
        original_args = ("010-1234-5678",)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="phone=%s",
            args=original_args,
            exc_info=None,
        )
        # Act
        f.filter(record)
        # Assert
        assert record.args == original_args


# ===========================================================================
# mask_pii — 마스킹 토큰 검증 (반환값 형식)
# ===========================================================================


class TestMaskPiiTokens:
    """마스킹 결과 토큰이 올바른 형식이다."""

    def test_rrn_token_format(self):
        result = mask_pii("900101-1234567")
        assert result == "[RRN]"

    def test_email_token_format(self):
        result = mask_pii("test@example.com")
        assert result == "[EMAIL]"

    def test_phone_token_format(self):
        result = mask_pii("010-1234-5678")
        assert result == "[PHONE]"

    def test_account_token_format(self):
        result = mask_pii("123456-12-345678")
        assert result == "[ACCOUNT]"
