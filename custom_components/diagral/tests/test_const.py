"""Tier 1 tests for const.py — no Home Assistant dependency.

Uses importlib to load const.py directly, bypassing the package __init__.py
which imports Home Assistant modules.
"""
import importlib.util
import pathlib

import pytest


def load_const():
    """Load const.py directly without importing the HA package."""
    const_path = pathlib.Path(__file__).parent.parent / "const.py"
    spec = importlib.util.spec_from_file_location("diagral_const", const_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def const():
    """Return the loaded const module."""
    return load_const()


class TestDomainAndBrand:
    """Tests for DOMAIN and BRAND constants."""

    def test_domain(self, const):
        """DOMAIN must be 'diagral'."""
        assert const.DOMAIN == "diagral"

    def test_brand(self, const):
        """BRAND must be 'Diagral'."""
        assert const.BRAND == "Diagral"


class TestConfigVersion:
    """Tests for config version constants."""

    def test_config_version(self, const):
        """CONFIG_VERSION must be a positive integer."""
        assert isinstance(const.CONFIG_VERSION, int)
        assert const.CONFIG_VERSION > 0

    def test_config_minor_version(self, const):
        """CONFIG_MINOR_VERSION must be a non-negative integer."""
        assert isinstance(const.CONFIG_MINOR_VERSION, int)
        assert const.CONFIG_MINOR_VERSION >= 0


class TestScanInterval:
    """Tests for DEFAULT_SCAN_INTERVAL."""

    def test_default_scan_interval(self, const):
        """DEFAULT_SCAN_INTERVAL must be a positive integer (seconds)."""
        assert isinstance(const.DEFAULT_SCAN_INTERVAL, int)
        assert const.DEFAULT_SCAN_INTERVAL > 0


class TestHaCloudDomain:
    """Tests for HA_CLOUD_DOMAIN."""

    def test_ha_cloud_domain(self, const):
        """HA_CLOUD_DOMAIN must contain '.nabu.casa'."""
        assert ".nabu.casa" in const.HA_CLOUD_DOMAIN


class TestAlarmPanelActionType:
    """Tests for CONF_ALARMPANEL_ACTIONTYPE_CODE_OPTIONS."""

    def test_alarmpanel_actiontype_options_contains_never(self, const):
        """Options must include 'never'."""
        assert "never" in const.CONF_ALARMPANEL_ACTIONTYPE_CODE_OPTIONS

    def test_alarmpanel_actiontype_options_contains_disarm(self, const):
        """Options must include 'disarm'."""
        assert "disarm" in const.CONF_ALARMPANEL_ACTIONTYPE_CODE_OPTIONS

    def test_alarmpanel_actiontype_options_contains_always(self, const):
        """Options must include 'always'."""
        assert "always" in const.CONF_ALARMPANEL_ACTIONTYPE_CODE_OPTIONS

    def test_alarmpanel_actiontype_options_is_list(self, const):
        """Options must be a list."""
        assert isinstance(const.CONF_ALARMPANEL_ACTIONTYPE_CODE_OPTIONS, list)


class TestServiceNames:
    """Tests for service name constants."""

    def test_service_arm_group(self, const):
        """SERVICE_ARM_GROUP must be a non-empty string."""
        assert isinstance(const.SERVICE_ARM_GROUP, str)
        assert len(const.SERVICE_ARM_GROUP) > 0

    def test_service_disarm_group(self, const):
        """SERVICE_DISARMGROUP must be a non-empty string."""
        assert isinstance(const.SERVICE_DISARMGROUP, str)
        assert len(const.SERVICE_DISARMGROUP) > 0

    def test_service_register_webhook(self, const):
        """SERVICE_REGISTER_WEBHOOK must be a non-empty string."""
        assert isinstance(const.SERVICE_REGISTER_WEBHOOK, str)
        assert len(const.SERVICE_REGISTER_WEBHOOK) > 0

    def test_service_unregister_webhook(self, const):
        """SERVICE_UNREGISTER_WEBHOOK must be a non-empty string."""
        assert isinstance(const.SERVICE_UNREGISTER_WEBHOOK, str)
        assert len(const.SERVICE_UNREGISTER_WEBHOOK) > 0


class TestConfKeys:
    """Tests for CONF_* key constants."""

    def test_conf_serial_id_defined(self, const):
        """CONF_SERIAL_ID must be defined."""
        assert hasattr(const, "CONF_SERIAL_ID")
        assert isinstance(const.CONF_SERIAL_ID, str)

    def test_conf_pin_code_defined(self, const):
        """CONF_PIN_CODE must be defined."""
        assert hasattr(const, "CONF_PIN_CODE")
        assert isinstance(const.CONF_PIN_CODE, str)

    def test_conf_api_key_defined(self, const):
        """CONF_API_KEY must be defined."""
        assert hasattr(const, "CONF_API_KEY")
        assert isinstance(const.CONF_API_KEY, str)

    def test_conf_alarmpanel_code_defined(self, const):
        """CONF_ALARMPANEL_CODE must be defined."""
        assert hasattr(const, "CONF_ALARMPANEL_CODE")
        assert isinstance(const.CONF_ALARMPANEL_CODE, str)
