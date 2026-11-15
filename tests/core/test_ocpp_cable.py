"""Cable input derived from an OCPP connector status text (HACS "ocpp")."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.ev_charging_pilot.core.inputs import Inp, RawState, to_value

NOW = datetime(2026, 11, 15, 20, 0, tzinfo=UTC)


def _cable(state: str):
    return to_value(Inp.CABLE_CONNECTED, RawState(state, NOW))


@pytest.mark.parametrize("state", ["Preparing", "Charging", "SuspendedEV", "SuspendedEVSE",
                                   "Finishing"])
def test_plugged_statuses_mean_cable_connected(state):
    assert _cable(state).normalized is True


def test_available_means_no_cable():
    assert _cable("Available").normalized is False


def test_ha_unavailable_stays_missing_but_device_unavailable_is_a_value():
    assert _cable("unavailable").normalized is None
    assert _cable("Unavailable").normalized is False


def test_binary_sensor_states_still_work():
    assert _cable("on").normalized is True
    assert _cable("off").normalized is False
