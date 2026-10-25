"""HA-side regression tests for the medium findings of the review of 2026-10-24."""

from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass

from custom_components.ev_charging_pilot.sensor import SENSORS


def test_m1_hv_cycles_are_no_rising_meter():
    """Frank's OVMS exposes the *remaining* contactor cycles (194 754, falling):
    TOTAL_INCREASING made the long-term statistics see a meter reset at every step."""
    hv = next(d for d in SENSORS if d.key == "hv_contactor_cycles")
    assert hv.state_class is SensorStateClass.MEASUREMENT
