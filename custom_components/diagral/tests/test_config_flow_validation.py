"""Tests for pure validation functions in config_flow.py (Tier 2).

Tests is_valid_email(), is_valid_pin(), and is_valid_alarmpanel_code()
which have no side effects and require only Home Assistant to be importable.
"""
import pytest

from custom_components.diagral.config_flow import (
    is_valid_alarmpanel_code,
    is_valid_email,
    is_valid_pin,
)


class TestIsValidEmail:
    """Tests for is_valid_email()."""

    def test_valid_simple_email(self):
        """Standard email address must be valid."""
        assert is_valid_email("user@example.com") is True

    def test_valid_email_with_subdomain(self):
        """Email with subdomain must be valid."""
        assert is_valid_email("user@mail.example.com") is True

    def test_valid_email_with_plus(self):
        """Email with plus tag must be valid."""
        assert is_valid_email("user+tag@example.com") is True

    def test_valid_email_with_dots_in_local(self):
        """Email with dots in local part must be valid."""
        assert is_valid_email("first.last@example.com") is True

    def test_invalid_email_missing_at(self):
        """String without @ must be invalid."""
        assert is_valid_email("userexample.com") is False

    def test_invalid_email_missing_domain(self):
        """Email without domain must be invalid."""
        assert is_valid_email("user@") is False

    def test_invalid_email_missing_tld(self):
        """Email without TLD must be invalid."""
        assert is_valid_email("user@example") is False

    def test_invalid_email_empty_string(self):
        """Empty string must be invalid."""
        assert is_valid_email("") is False

    def test_invalid_email_spaces(self):
        """Email with spaces must be invalid."""
        assert is_valid_email("user @example.com") is False


class TestIsValidPin:
    """Tests for is_valid_pin()."""

    def test_valid_pin_four_digits(self):
        """4-digit string pin must be valid."""
        assert is_valid_pin("1234") is True

    def test_valid_pin_single_zero(self):
        """Single '0' is a valid pin (>= 0)."""
        assert is_valid_pin("0") is True

    def test_valid_pin_long(self):
        """Long numeric pin must be valid."""
        assert is_valid_pin("123456789") is True

    def test_invalid_pin_with_letters(self):
        """Pin containing letters must be invalid."""
        assert is_valid_pin("123a") is False

    def test_invalid_pin_empty(self):
        """Empty string must be invalid."""
        assert is_valid_pin("") is False

    def test_invalid_pin_float_string(self):
        """Decimal string must be invalid (not all digits)."""
        assert is_valid_pin("12.34") is False

    def test_invalid_pin_negative_string(self):
        """Negative string must be invalid (contains '-')."""
        assert is_valid_pin("-123") is False

    def test_invalid_pin_integer_type(self):
        """Integer (not string) must be invalid."""
        assert is_valid_pin(1234) is False


class TestIsValidAlarmPanelCode:
    """Tests for is_valid_alarmpanel_code()."""

    def test_valid_code_four_digits(self):
        """4-digit integer code must be valid."""
        assert is_valid_alarmpanel_code(1234) is True

    def test_valid_code_six_digits(self):
        """6-digit code must be valid."""
        assert is_valid_alarmpanel_code(123456) is True

    def test_valid_code_minimum_boundary(self):
        """Exactly 4-digit boundary (1000) must be valid."""
        assert is_valid_alarmpanel_code(1000) is True

    def test_invalid_code_three_digits(self):
        """3-digit code (999) must be invalid (less than 4 digits)."""
        assert is_valid_alarmpanel_code(999) is False

    def test_invalid_code_zero(self):
        """0 must be invalid (only 1 digit)."""
        assert is_valid_alarmpanel_code(0) is False

    def test_invalid_code_string(self):
        """String type must be invalid."""
        assert is_valid_alarmpanel_code("1234") is False

    def test_invalid_code_none(self):
        """None must be invalid."""
        assert is_valid_alarmpanel_code(None) is False
