"""ESPHome nodes on the floor plan -- one dot per board, not per entity.

The generic adapter can already put every ESPHome entity on the plan, and
for lights and switches that is the right answer. But an ESPHome board is
a *thing*: it hangs on a wall, it is reachable or it is not, and it has
eight sensors that are all reachable or not together. Eight dots for one
box is eight times the clutter and none of the information.

So this draws the board. Its state is whether Home Assistant can reach
it, which is what the entities of an unreachable board say anyway, and
its metadata is what the device registry already holds.

No edges. ESPHome boards talk to Home Assistant over the network and
nothing here measures that path; drawing a line to a router that may not
exist would be an invention. Where a board really is reached through
something else -- a Bluetooth proxy, say -- Home Assistant records it in
`via_device`, and the hub's own generic layer draws that without any help
from this file.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.event import async_track_time_interval

from .spatial_hub_provider import spatial_provider, node

ESPHOME_DOMAIN = "esphome"

# Availability is what changes here, and it changes through entity states
# rather than any signal this integration could subscribe to.
REFRESH = timedelta(seconds=30)

_UNREACHABLE = {"unavailable", "unknown", ""}


def _devices(hass: HomeAssistant) -> list[Any]:
    try:
        registry = dr.async_get(hass)
    except (AttributeError, KeyError):  # pragma: no cover
        return []
    return [
        device
        for device in getattr(registry, "devices", {}).values()
        if any(
            domain == ESPHOME_DOMAIN
            for domain, _ in getattr(device, "identifiers", ())
        )
    ]


def _entities_of(hass: HomeAssistant, device_id: str) -> list[str]:
    try:
        registry = er.async_get(hass)
    except (AttributeError, KeyError):  # pragma: no cover
        return []
    return [
        entry.entity_id
        for entry in getattr(registry, "entities", {}).values()
        if getattr(entry, "device_id", None) == device_id
    ]


def _reachable(hass: HomeAssistant, entity_ids: list[str]) -> str:
    """A board is up if any of its entities is answering.

    "Any" rather than "all" on purpose: a board can have a sensor that is
    legitimately unknown -- one that has not reported since boot -- while
    the board itself is perfectly reachable. Requiring all of them would
    paint working boards red.
    """
    if not entity_ids:
        return "unknown"
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state and str(state.state).lower() not in _UNREACHABLE:
            return "online"
    return "offline"


def async_setup_spatial(hass: HomeAssistant, entry: Any) -> None:
    def data() -> dict[str, list]:
        nodes = []
        for device in _devices(hass):
            entity_ids = _entities_of(hass, device.id)
            state = _reachable(hass, entity_ids)
            nodes.append(
                node(
                    f"board-{device.id}",
                    label=getattr(device, "name_by_user", None)
                    or getattr(device, "name", "")
                    or "ESPHome",
                    area_id=getattr(device, "area_id", None),
                    state=state,
                    icon="mdi:chip" if state == "online" else "mdi:chip-off",
                    modell=getattr(device, "model", "") or "",
                    firmware=getattr(device, "sw_version", "") or "",
                    # The number a wall-mounted board's owner actually wants:
                    # how much is hanging off this one box.
                    entitaeten=len(entity_ids),
                )
            )
        return {"nodes": nodes}

    provider = spatial_provider(
        hass,
        entry,
        name="ESPHome",
        icon="mdi:chip",
        data=data,
        version="0.1.0",
    )

    entry.async_on_unload(
        async_track_time_interval(
            hass, lambda _now: provider.async_notify(), REFRESH
        )
    )
