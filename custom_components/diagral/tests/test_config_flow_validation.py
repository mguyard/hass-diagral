"""Tests for pure validation functions in config_flow.py (Tier 2).

Tests is_valid_email(), is_valid_pin(), and is_valid_alarmpanel_code()
which have no side effects and require only Home Assistant to be importable.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral.config_flow import (
    CannotConnect,
    DiagralConfigFlow,
    DiagralOptionsFlow,
    is_valid_alarmpanel_code,
    is_valid_email,
    is_valid_pin,
    validate_account,
)
from custom_components.diagral.const import (
    CONF_ALARMPANEL_ACTIONTYPE_CODE,
    CONF_ALARMPANEL_CODE,
    CONF_PIN_CODE,
)
from custom_components.diagral.models import AccountInfoData

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME


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


class TestAlarmPanelFlowValidation:
    """Simulate the alarm panel code validation logic from async_step_options / async_step_init.

    These tests cover the coercion + validation path without requiring a live HA flow context.
    """

    def _validate(self, typecode: str, code) -> str | None:
        """Replicate the core validation logic from the config/options flow steps.

        Returns the error key string, or None when no error.
        """
        alarmpanelcode = code
        # Coercion: float from HA frontend → int (mirrors the fix in both flow methods)
        if alarmpanelcode is not None:
            alarmpanelcode = int(alarmpanelcode)

        # "never" + non-None code → code is cleared, no error
        if typecode == "never" and alarmpanelcode is not None:
            return None
        # non-"never" + None code → missing code error
        elif typecode != "never" and alarmpanelcode is None:
            return "missing_alarmpanel_code"

        # Validate code length / type
        if alarmpanelcode is not None and not is_valid_alarmpanel_code(alarmpanelcode):
            return "invalid_alarmpanel_code"

        return None

    def test_never_type_with_none_code_no_error(self):
        """'never' type with None code must not raise an error."""
        assert self._validate("never", None) is None

    def test_always_type_with_none_code_raises_missing(self):
        """'always' type with None code must raise missing_alarmpanel_code."""
        assert self._validate("always", None) == "missing_alarmpanel_code"

    def test_disarm_only_type_with_none_code_raises_missing(self):
        """'disarm_only' type with None code must raise missing_alarmpanel_code."""
        assert self._validate("disarm_only", None) == "missing_alarmpanel_code"

    def test_always_type_with_valid_int_code_no_error(self):
        """'always' type with valid 4-digit int code must not raise an error."""
        assert self._validate("always", 1234) is None

    def test_always_type_with_float_code_is_coerced_and_valid(self):
        """Float code from HA frontend (1234.0) must be coerced to int and pass validation."""
        assert self._validate("always", 1234.0) is None

    def test_disarm_only_type_with_float_code_is_coerced_and_valid(self):
        """Float code from HA frontend must be coerced and pass validation for 'disarm_only'."""
        assert self._validate("disarm_only", 5678.0) is None

    def test_always_type_with_short_code_raises_invalid(self):
        """'always' type with 3-digit code must raise invalid_alarmpanel_code."""
        assert self._validate("always", 123) == "invalid_alarmpanel_code"

    def test_float_coercion_preserves_value(self):
        """int(1234.0) must equal 1234 (basic coercion sanity check)."""
        assert int(1234.0) == 1234

    def test_float_without_coercion_fails_alarmpanel_validation(self):
        """Float 1234.0 without coercion must fail is_valid_alarmpanel_code (not isinstance int)."""
        assert is_valid_alarmpanel_code(1234.0) is False


class TestDiagralOptionsFlowRegression:
    """Regression tests for options flow input handling."""

    async def test_async_step_init_missing_alarmpanel_code_key_returns_missing_error(
        self,
    ):
        """Missing alarm panel code key must return missing_alarmpanel_code instead of raising KeyError."""
        flow = object.__new__(DiagralOptionsFlow)
        flow.handler = "entry_id"

        config_entry = MagicMock()
        config_entry.options = {
            "alarmpanel_options": {
                CONF_ALARMPANEL_ACTIONTYPE_CODE: "never",
                CONF_ALARMPANEL_CODE: None,
            }
        }

        flow.hass = MagicMock()
        flow.hass.config_entries.async_get_known_entry.return_value = config_entry

        result = await flow.async_step_init(
            {
                "alarmpanel_options": {
                    CONF_ALARMPANEL_ACTIONTYPE_CODE: "always",
                }
            }
        )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "missing_alarmpanel_code"


class TestValidateAccount:
    """Tests for validate_account()."""

    async def test_unchanged_credentials_skip_validation(self):
        """Credentials identical to the stored ones must not reach the API."""
        account = AccountInfoData(
            username="user@example.com",
            password="secret",
            serial_id="SERIAL123",
            pin_code="1234",
        )
        previous = {
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_PIN_CODE: "1234",
        }
        with patch("custom_components.diagral.config_flow.DiagralAPI") as api_cls:
            result = await validate_account(account, previous_data=previous)
        assert result is None
        api_cls.assert_not_called()

    async def test_no_previous_data_validates_against_api(self):
        """Without stored data, the credentials must be checked against the API."""
        account = AccountInfoData(
            username="user@example.com",
            password="secret",
            serial_id="SERIAL123",
            pin_code="1234",
        )
        diagral = MagicMock()
        diagral.try_connection = AsyncMock(return_value=MagicMock(keys="KEYS"))
        with patch("custom_components.diagral.config_flow.DiagralAPI") as api_cls:
            api_cls.return_value.__aenter__ = AsyncMock(return_value=diagral)
            api_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await validate_account(account)
        diagral.try_connection.assert_awaited_once_with(ephemeral=True)
        assert result.keys == "KEYS"


class TestConfigFlowLogs:
    """The config flow must never log credentials or the panel code."""

    @staticmethod
    def make_flow() -> DiagralConfigFlow:
        """Return a config flow bound to a mocked Home Assistant."""
        flow = DiagralConfigFlow()
        flow.hass = MagicMock()
        flow.serialid = "FAKECENTRAL01"
        return flow

    async def test_account_step_hides_credentials(self, caplog):
        """Submitting the account step logs neither password nor PIN."""
        caplog.set_level(logging.DEBUG, logger="custom_components.diagral")
        flow = self.make_flow()
        with (
            patch(
                "custom_components.diagral.config_flow.validate_account",
                AsyncMock(),
            ),
            patch.object(flow, "async_step_options", AsyncMock()),
        ):
            await flow.async_step_account(
                {
                    CONF_USERNAME: "user@example.com",
                    CONF_PASSWORD: "SECRETPASSWORD",
                    CONF_PIN_CODE: "97531",
                }
            )
        assert "SECRETPASSWORD" not in caplog.text
        assert "97531" not in caplog.text

    async def test_reconfigure_step_hides_credentials(self, caplog):
        """Submitting the reconfigure step logs neither password nor PIN."""
        caplog.set_level(logging.DEBUG, logger="custom_components.diagral")
        flow = self.make_flow()
        flow.context = {"entry_id": "entry"}
        flow.hass.config_entries.async_get_entry.return_value.data = {
            "serial_id": "FAKECENTRAL01",
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "old",
            CONF_PIN_CODE: "1111",
        }
        with patch(
            "custom_components.diagral.config_flow.validate_account",
            AsyncMock(side_effect=CannotConnect),
        ):
            await flow.async_step_reconfigure(
                {
                    CONF_USERNAME: "user@example.com",
                    CONF_PASSWORD: "SECRETPASSWORD",
                    CONF_PIN_CODE: "97531",
                }
            )
        assert "SECRETPASSWORD" not in caplog.text
        assert "97531" not in caplog.text

    async def test_options_step_hides_panel_code(self, caplog):
        """Submitting the options step does not log the alarm panel code."""
        caplog.set_level(logging.DEBUG, logger="custom_components.diagral")
        flow = self.make_flow()
        with patch(
            "custom_components.diagral.config_flow.validate_account",
            AsyncMock(side_effect=CannotConnect),
        ):
            await flow.async_step_options(
                {
                    "alarmpanel_options": {
                        CONF_ALARMPANEL_ACTIONTYPE_CODE: "always",
                        CONF_ALARMPANEL_CODE: 24680,
                    }
                }
            )
        assert "24680" not in caplog.text
