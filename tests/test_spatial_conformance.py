"""ESPHome against the Spatial Hub conformance kit.

`tests/spatial_hub_conformance.py` is copied verbatim from the hub's
`sdk/` -- it is the same file every provider author is asked to drop in.
If this file ever fails, our provider drifted from the contract, not the
other way round.

It is run against a house with a board in it rather than an empty one,
because an empty payload conforms trivially and would prove nothing.
"""

from __future__ import annotations

from spatial_hub_conformance import SpatialHubConformance

from conftest import FakeEntry, FakeHass, house


class TestSpatialHubConformance(SpatialHubConformance):
    """The whole integration of the kit: one class, one method."""

    def build_registration(self):
        from custom_components.spatial_esphome.spatial import async_setup_spatial

        hass = FakeHass()
        house(hass, entities={"sensor.a": "21.5", "sensor.b": "unavailable"})
        async_setup_spatial(hass, FakeEntry())
        return hass.registrations["spatial_esphome"]
