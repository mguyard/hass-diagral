"""Tests for pure validation functions in config_flow.py (Tier 2).

Tests is_valid_email(), is_valid_pin(), and is_valid_alarmpanel_code()
which have no side effects and require only Home Assistant to be importable.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.diagral.config_flow import (
    CannotConnect,
    DiagralConfigFlow,
    DiagralOptionsFlow,
    InvalidAuth,
    is_valid_alarmpanel_code,
    is_valid_email,
    is_valid_pin,
    list_serials,
    validate_account,
)
from custom_components.diagral.const import (
    CONF_ALARMPANEL_ACTIONTYPE_CODE,
    CONF_ALARMPANEL_CODE,
    CONF_PIN_CODE,
    CONF_SERIAL_ID,
    DIAGRAL_VENDOR,
    INTERACTIVE_REQUEST_TIMEOUT,
    LIST_SERIALS_ATTEMPTS,
    SERIAL_GUIDE_URL,
    SERIAL_IMAGE_URL,
)
from custom_components.diagral.models import AccountInfoData
from pydiagral.exceptions import (
    AuthenticationError,
    ClientError,
    DiagralAPIError,
    ServerError,
)
import pytest

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import AbortFlow


@pytest.fixture(autouse=True)
def client_session():
    """Hand each client the session of the Home Assistant it is given."""
    with patch(
        "custom_components.diagral.config_flow.async_get_clientsession",
        lambda hass: hass.http_session,
    ):
        yield


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
            result = await validate_account(
                MagicMock(), account, previous_data=previous
            )
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
            result = await validate_account(MagicMock(), account)
        diagral.try_connection.assert_awaited_once_with(ephemeral=True)
        assert result.keys == "KEYS"

    async def test_client_uses_home_assistant_session(self):
        """The client shares Home Assistant's HTTP session, closed by HA alone."""
        hass = MagicMock()
        diagral = MagicMock()
        diagral.try_connection = AsyncMock(return_value=MagicMock(keys="KEYS"))
        with patch("custom_components.diagral.config_flow.DiagralAPI") as api_cls:
            api_cls.return_value.__aenter__ = AsyncMock(return_value=diagral)
            api_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            await validate_account(hass, ACCOUNT)
        assert api_cls.call_args.kwargs["session"] is hass.http_session

    async def test_client_logs_in_as_diagral(self):
        """The client states the vendor instead of relying on pydiagral's default."""
        diagral = MagicMock()
        diagral.try_connection = AsyncMock(return_value=MagicMock(keys="KEYS"))
        with patch("custom_components.diagral.config_flow.DiagralAPI") as api_cls:
            api_cls.return_value.__aenter__ = AsyncMock(return_value=diagral)
            api_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            await validate_account(MagicMock(), ACCOUNT)
        assert api_cls.call_args.kwargs["vendor"] == DIAGRAL_VENDOR

    @pytest.mark.parametrize(
        ("alarm_name", "expected_title"),
        [("Home", "Home (FAKECENTRAL01)"), (None, "Diagral (FAKECENTRAL01)")],
        ids=["named", "unnamed"],
    )
    async def test_title_names_the_alarm(self, alarm_name, expected_title):
        """The entry title uses the alarm name, or Diagral when it has none."""
        diagral = MagicMock()
        diagral.try_connection = AsyncMock(return_value=MagicMock(keys="KEYS"))
        diagral.get_alarm_name = AsyncMock(return_value=alarm_name)
        with patch("custom_components.diagral.config_flow.DiagralAPI") as api_cls:
            api_cls.return_value.__aenter__ = AsyncMock(return_value=diagral)
            api_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await validate_account(MagicMock(), ACCOUNT, ephemeral=False)
        assert result.title == expected_title


class TestConfigFlowLogs:
    """The config flow must never log credentials or the panel code."""

    @staticmethod
    def make_flow() -> DiagralConfigFlow:
        """Return a config flow bound to a mocked Home Assistant."""
        flow = DiagralConfigFlow()
        flow.hass = MagicMock()
        flow.serialid = "FAKECENTRAL01"
        flow.serials = ["FAKECENTRAL01"]
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow._async_current_entries = MagicMock(return_value=[])
        return flow

    async def test_user_step_hides_credentials(self, caplog):
        """Submitting the account step logs neither password nor PIN."""
        caplog.set_level(logging.DEBUG, logger="custom_components.diagral")
        flow = self.make_flow()
        with (
            patch(
                "custom_components.diagral.config_flow.list_serials",
                AsyncMock(return_value=["FAKECENTRAL01"]),
            ),
            patch.object(flow, "async_step_central", AsyncMock()),
        ):
            await flow.async_step_user(
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


ACCOUNT = AccountInfoData(
    username="user@example.com",
    password="secret",
    serial_id="FAKECENTRAL01",
    pin_code="1234",
)


class TestValidateAccountErrors:
    """validate_account() tells a refused login from a failed connection."""

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (AuthenticationError("Authentication rejected by Diagral"), InvalidAuth),
            (ServerError("Diagral service error (HTTP 503)"), CannotConnect),
            (ClientError("Diagral request timed out"), CannotConnect),
            (DiagralAPIError("Diagral API error (HTTP 400)"), CannotConnect),
        ],
        ids=["refused-login", "server-error", "network-error", "other-api-error"],
    )
    async def test_error_is_classified(self, error, expected):
        """Only a refused login is reported as invalid authentication."""
        diagral = MagicMock()
        diagral.try_connection = AsyncMock(side_effect=error)
        with patch("custom_components.diagral.config_flow.DiagralAPI") as api_cls:
            api_cls.return_value.__aenter__ = AsyncMock(return_value=diagral)
            api_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            with pytest.raises(expected):
                await validate_account(MagicMock(), ACCOUNT)


def make_step(step: str) -> tuple[DiagralConfigFlow, dict]:
    """Return a config flow ready to submit the given step, and its input."""
    flow = TestConfigFlowLogs.make_flow()
    flow.account_username = ACCOUNT.username
    flow.account_password = ACCOUNT.password
    flow.account_pincode = ACCOUNT.pin_code
    credentials = {
        CONF_USERNAME: ACCOUNT.username,
        CONF_PASSWORD: "new-secret",
        CONF_PIN_CODE: ACCOUNT.pin_code,
    }
    if step == "options":
        return flow, {"alarmpanel_options": {CONF_ALARMPANEL_ACTIONTYPE_CODE: "never"}}
    if step in ("central", "serial"):
        return flow, {CONF_SERIAL_ID: ACCOUNT.serial_id}
    if step == "reconfigure":
        flow.context = {"entry_id": "entry"}
        flow.hass.config_entries.async_get_entry.return_value.data = {
            "serial_id": ACCOUNT.serial_id,
            CONF_USERNAME: ACCOUNT.username,
            CONF_PASSWORD: ACCOUNT.password,
            CONF_PIN_CODE: ACCOUNT.pin_code,
        }
    return flow, credentials


class TestFlowErrorMessages:
    """Each step shows a translated error, never the exception text."""

    @pytest.mark.parametrize("step", ["central", "serial", "options", "reconfigure"])
    @pytest.mark.parametrize(
        ("raised", "key"),
        [
            (CannotConnect, "cannot_connect"),
            (InvalidAuth, "invalid_auth"),
            (RuntimeError, "unknown"),
        ],
        ids=["cannot-connect", "invalid-auth", "unexpected"],
    )
    async def test_error_shows_translation_key(self, step, raised, key):
        """The form error is a translation key present in both languages."""
        flow, user_input = make_step(step)

        async def fail(*_, **__):
            raise raised from DiagralAPIError("Diagral API error (HTTP 401)")

        with patch("custom_components.diagral.config_flow.validate_account", fail):
            result = await getattr(flow, f"async_step_{step}")(user_input)

        assert result["errors"] == {"base": key}


def account_input() -> dict:
    """Return a valid submission of the account step."""
    return {
        CONF_USERNAME: ACCOUNT.username,
        CONF_PASSWORD: ACCOUNT.password,
        CONF_PIN_CODE: ACCOUNT.pin_code,
    }


CONFIGURED_ENTRY = SimpleNamespace(
    unique_id="FAKECENTRAL01", title="fake home (FAKECENTRAL01)"
)


def central_choices(result: dict) -> list[str]:
    """Return the serials the central step offers."""
    return result["data_schema"].schema[CONF_SERIAL_ID].config["options"]


class TestListSerials:
    """list_serials() asks the account for its centrals, without a serial."""

    @staticmethod
    def make_api(**get_systems) -> MagicMock:
        """Return a DiagralAPI class whose client answers get_systems()."""
        diagral = MagicMock()
        diagral.get_systems = AsyncMock(**get_systems)
        api_cls = MagicMock()
        api_cls.return_value.__aenter__ = AsyncMock(return_value=diagral)
        api_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        return api_cls

    async def test_lists_the_serials_without_a_serial(self, caplog):
        """The client has no serial; the serials are returned, never logged."""
        caplog.set_level(logging.DEBUG, logger="custom_components.diagral")
        hass = MagicMock()
        api_cls = self.make_api(
            return_value=[
                SimpleNamespace(serial_id="FAKECENTRAL01", api_keys=["SECRETKEY"]),
                SimpleNamespace(serial_id="FAKECENTRAL02", api_keys=[]),
            ]
        )
        with patch("custom_components.diagral.config_flow.DiagralAPI", api_cls):
            serials = await list_serials(hass, ACCOUNT.username, ACCOUNT.password)

        assert serials == ["FAKECENTRAL01", "FAKECENTRAL02"]
        kwargs = api_cls.call_args.kwargs
        assert "serial_id" not in kwargs
        assert kwargs["vendor"] == DIAGRAL_VENDOR
        assert kwargs["session"] is hass.http_session
        assert kwargs["request_timeout"] == INTERACTIVE_REQUEST_TIMEOUT
        assert "FAKECENTRAL0" not in caplog.text
        assert "SECRETKEY" not in caplog.text

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (AuthenticationError("Authentication rejected by Diagral"), InvalidAuth),
            (ServerError("Diagral service error (HTTP 503)"), CannotConnect),
            (ClientError("Diagral request timed out"), CannotConnect),
        ],
        ids=["refused-login", "server-error", "network-error"],
    )
    async def test_error_is_classified(self, error, expected):
        """A refused login stays an authentication error, anything else a failure."""
        api_cls = self.make_api(side_effect=error)
        with (
            patch("custom_components.diagral.config_flow.DiagralAPI", api_cls),
            pytest.raises(expected),
        ):
            await list_serials(MagicMock(), ACCOUNT.username, ACCOUNT.password)

    async def test_a_stalled_listing_is_tried_again(self):
        """Diagral stalls now and then: a second try is made before falling back."""
        api_cls = self.make_api(
            side_effect=[
                ClientError("Diagral request timed out"),
                [SimpleNamespace(serial_id="FAKECENTRAL01", api_keys=[])],
            ]
        )
        with patch("custom_components.diagral.config_flow.DiagralAPI", api_cls):
            serials = await list_serials(
                MagicMock(), ACCOUNT.username, ACCOUNT.password
            )

        assert serials == ["FAKECENTRAL01"]

    @pytest.mark.parametrize(
        ("error", "expected", "attempts"),
        [
            (
                ClientError("Diagral request timed out"),
                CannotConnect,
                LIST_SERIALS_ATTEMPTS,
            ),
            (AuthenticationError("Authentication rejected by Diagral"), InvalidAuth, 1),
        ],
        ids=["stalled-twice", "refused-login"],
    )
    async def test_attempts_are_bounded(self, error, expected, attempts):
        """A stall is tried again up to the limit; refused credentials are not."""
        api_cls = self.make_api(side_effect=error)
        with (
            patch("custom_components.diagral.config_flow.DiagralAPI", api_cls),
            pytest.raises(expected),
        ):
            await list_serials(MagicMock(), ACCOUNT.username, ACCOUNT.password)

        diagral = api_cls.return_value.__aenter__.return_value
        assert diagral.get_systems.await_count == attempts


class TestAccountStep:
    """The account step lists the centrals, or falls back to typing the serial."""

    async def test_lists_only_the_centrals_not_in_home_assistant(self):
        """Centrals already set up are left out and named above, as Name (Serial)."""
        flow = TestConfigFlowLogs.make_flow()
        flow._async_current_entries = MagicMock(return_value=[CONFIGURED_ENTRY])
        with patch(
            "custom_components.diagral.config_flow.list_serials",
            AsyncMock(return_value=["FAKECENTRAL01", "FAKECENTRAL02"]),
        ):
            result = await flow.async_step_user(account_input())

        assert result["step_id"] == "central"
        assert central_choices(result) == ["FAKECENTRAL02"]
        assert result["description_placeholders"]["configured"] == (
            "fake home (FAKECENTRAL01)"
        )

    async def test_central_step_shows_where_the_serial_is(self):
        """No name before a key exists: the step helps check the serial instead."""
        flow = TestConfigFlowLogs.make_flow()
        with patch(
            "custom_components.diagral.config_flow.list_serials",
            AsyncMock(return_value=["FAKECENTRAL01"]),
        ):
            result = await flow.async_step_user(account_input())

        placeholders = result["description_placeholders"]
        assert placeholders["setup_guide_url"] == SERIAL_GUIDE_URL
        assert placeholders["serial_id_image_url"] == SERIAL_IMAGE_URL

    async def test_single_central_is_still_shown(self):
        """A single available central is listed, so the user sees what is added."""
        flow = TestConfigFlowLogs.make_flow()
        with patch(
            "custom_components.diagral.config_flow.list_serials",
            AsyncMock(return_value=["FAKECENTRAL01"]),
        ):
            result = await flow.async_step_user(account_input())

        assert result["step_id"] == "central"
        assert central_choices(result) == ["FAKECENTRAL01"]
        assert result["description_placeholders"]["configured"] == "-"

    async def test_every_central_already_set_up_aborts(self):
        """Nothing left to add: the flow stops, without asking for anything."""
        flow = TestConfigFlowLogs.make_flow()
        flow._async_current_entries = MagicMock(return_value=[CONFIGURED_ENTRY])
        with patch(
            "custom_components.diagral.config_flow.list_serials",
            AsyncMock(return_value=["FAKECENTRAL01"]),
        ):
            result = await flow.async_step_user(account_input())

        assert result["type"] == "abort"
        assert result["reason"] == "already_configured"

    @pytest.mark.parametrize(
        "listing",
        [AsyncMock(side_effect=CannotConnect), AsyncMock(return_value=[])],
        ids=["listing-failed", "no-central-listed"],
    )
    async def test_falls_back_to_typing_the_serial(self, listing):
        """When the account's centrals cannot be listed, the serial is typed."""
        flow = TestConfigFlowLogs.make_flow()
        with patch("custom_components.diagral.config_flow.list_serials", listing):
            result = await flow.async_step_user(account_input())

        assert result["step_id"] == "serial"

    async def test_refused_login_stays_on_the_account_step(self):
        """Wrong credentials are reported on the form, not hidden by a fallback."""
        flow = TestConfigFlowLogs.make_flow()
        with patch(
            "custom_components.diagral.config_flow.list_serials",
            AsyncMock(side_effect=InvalidAuth),
        ):
            result = await flow.async_step_user(account_input())

        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "invalid_auth"}


class TestSerialStep:
    """The manual serial step shows where to find the serial."""

    async def test_guide_points_to_the_serial_section(self):
        """The link opens the docs section on the serial, under its real anchor."""
        flow = TestConfigFlowLogs.make_flow()

        result = await flow.async_step_serial()

        assert result["description_placeholders"]["setup_guide_url"].endswith(
            "/integration/setup#finding-your-system-serial-id"
        )


class TestCentralChoice:
    """Choosing a central claims it before any API key is created."""

    @pytest.mark.parametrize("step", ["central", "serial"])
    async def test_chosen_central_is_claimed_then_checked(self, step):
        """The unique id is set first, then the account is checked on that central."""
        flow, user_input = make_step(step)
        validate = AsyncMock(return_value=None)
        with (
            patch("custom_components.diagral.config_flow.validate_account", validate),
            patch.object(flow, "async_step_options", AsyncMock()) as options,
        ):
            await getattr(flow, f"async_step_{step}")(user_input)

        flow.async_set_unique_id.assert_awaited_once_with(ACCOUNT.serial_id)
        assert validate.call_args.kwargs["account_info"].serial_id == ACCOUNT.serial_id
        assert validate.call_args.kwargs["ephemeral"] is True
        assert flow.serialid == ACCOUNT.serial_id
        options.assert_awaited_once()

    @pytest.mark.parametrize("step", ["central", "serial"])
    async def test_central_already_set_up_aborts_before_any_key(self, step):
        """A duplicate stops before the account is checked: no key is created."""
        flow, user_input = make_step(step)
        flow._abort_if_unique_id_configured = MagicMock(
            side_effect=AbortFlow("already_configured")
        )
        validate = AsyncMock()
        with (
            patch("custom_components.diagral.config_flow.validate_account", validate),
            pytest.raises(AbortFlow),
        ):
            await getattr(flow, f"async_step_{step}")(user_input)

        validate.assert_not_awaited()


class TestReconfigureSecrets:
    """The reconfigure form never shows the stored password or PIN."""

    async def test_form_does_not_prefill_secrets(self):
        """Password and PIN are blank, only the username is pre-filled."""
        flow, _ = make_step("reconfigure")
        result = await flow.async_step_reconfigure()

        defaults = {
            str(key): key.default()
            for key in result["data_schema"].schema
            if callable(getattr(key, "default", None))
        }
        assert defaults == {CONF_USERNAME: ACCOUNT.username}

    async def test_blank_secrets_keep_stored_values(self):
        """Leaving password and PIN empty keeps them, so only the email changes."""
        flow, _ = make_step("reconfigure")
        validate = AsyncMock(return_value=None)
        with patch("custom_components.diagral.config_flow.validate_account", validate):
            await flow.async_step_reconfigure({CONF_USERNAME: "new@example.com"})

        account = validate.call_args.kwargs["account_info"]
        assert account.username == "new@example.com"
        assert account.password == ACCOUNT.password
        assert account.pin_code == ACCOUNT.pin_code
