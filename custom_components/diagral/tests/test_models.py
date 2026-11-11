"""Tests for options loaded from existing configuration entries."""

from types import SimpleNamespace

from custom_components.diagral.models import DiagralConfigData
import pytest


@pytest.mark.parametrize("use_topaze", [None, False, True])
def test_emergency_mode_defaults_off_for_existing_entry(use_topaze):
    """Missing options never migrate an existing installation to another API."""
    options = {"alarmpanel_options": {"alarmpanel_actiontype_code": "never"}}
    if use_topaze is not None:
        options["use_topaze"] = use_topaze
    entry = SimpleNamespace(data={"serial_id": "FAKECENTRAL01"}, options=options)

    config = DiagralConfigData.from_config_entry(entry)

    assert config.options.use_topaze is (use_topaze is True)
