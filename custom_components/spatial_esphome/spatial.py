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


def _boards(hass: HomeAssistant) -> list[tuple[Any, list[Any]]]:
    """Every ESPHome board, with the sub-devices that hang off it.

    Asked via the config entries, not via ``identifiers``. A board carries
    no identifier at all -- ESPHome registers it as
    ``connections={(CONNECTION_NETWORK_MAC, mac)}`` and nothing else -- so
    looking for an ``esphome`` identifier finds precisely zero boards in a
    house full of them. What every ESPHome device *does* have is the
    config entry it was created under, and that is public, stable and true
    for boards and sub-devices alike.

    Sub-devices (one ESPHome node presenting itself as several devices)
    point at their board with ``via_device_id``. They are folded into it
    rather than drawn: this layer exists to be *one dot per board*, and a
    board that splits itself into six is still one thing on the wall.

    That fold does run in the field, which is not obvious given the
    sentence above: Home Assistant resolves ``via_device`` against
    ``identifiers`` only, and a board has none. ESPHome sidesteps the
    lookup entirely -- it creates the sub-device, then sets the link by
    hand with ``async_update_device(sub.id, via_device_id=board.id)``.
    The chain therefore exists without the board ever needing an
    identifier. See ``esphome/manager.py``; the test
    ``test_untergeraete_werden_eingeklappt`` builds it that way.
    """
    try:
        registry = dr.async_get(hass)
    except (AttributeError, KeyError):  # pragma: no cover
        return []

    # An empty result is an answer, not a failure, and is deliberately
    # not guarded against.
    #
    # Losing every board at once is worse than colouring one wrongly --
    # that is the argument ``_sleeps()`` makes one level down, and it
    # would apply here too if there were anything to fall back on. There
    # is not: searching by ``identifiers`` finds zero boards by design,
    # so a fallback would only trade an honest empty list for a silently
    # empty one. If ESPHome has no config entries, the house has no
    # ESPHome boards, and drawing none of them is correct.
    devices: dict[str, Any] = {}
    for entry in hass.config_entries.async_entries(ESPHOME_DOMAIN):
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
            devices[device.id] = device

    children: dict[str, list[Any]] = {}
    for device in devices.values():
        parent = getattr(device, "via_device_id", None)
        if parent in devices:
            children.setdefault(parent, []).append(device)

    return [
        (device, sorted(children.get(device.id, []), key=lambda child: child.id))
        # Sorted so the plan draws the same order on every reload.
        for device in sorted(devices.values(), key=lambda device: device.id)
        if getattr(device, "via_device_id", None) not in devices
    ]


def _entities_of(hass: HomeAssistant, device_ids: set[str]) -> list[Any]:
    """The board's own entities -- the ones ESPHome itself reports.

    ``device_ids`` is the board plus its sub-devices, because an entity
    sitting on a sub-device is still hanging off that one box and still
    goes quiet with it.

    A device is not one integration's property. The router puts a
    ``device_tracker`` on the same device, because it is the same MAC, and
    that tracker keeps saying ``not_home`` long after the board is dead:
    the router remembers the address, the board is gone. Counting it would
    paint a board green because something else still has an opinion about
    it, which is exactly the answer nobody asked for.
    """
    try:
        registry = er.async_get(hass)
    except (AttributeError, KeyError):  # pragma: no cover
        return []
    return [
        entry
        for entry in getattr(registry, "entities", {}).values()
        if getattr(entry, "device_id", None) in device_ids
        and getattr(entry, "platform", ESPHOME_DOMAIN) == ESPHOME_DOMAIN
    ]


def _sleeps(hass: HomeAssistant, device: Any) -> bool:
    """Whether this board is *meant* to be gone most of the time.

    A ``deep_sleep`` board wakes, reports, and goes away again -- being
    unreachable is its job, not its failure, and painting it red every
    night is the same mistake as painting a sleeping battery sensor red.

    Home Assistant has nowhere to put this: the device registry knows the
    box, not how it behaves. The only place it exists is ESPHome's own
    runtime data, which is another integration's internals and no promised
    interface -- so every step of the way down is defensive, and a board
    whose answer cannot be read is simply treated as one that never
    sleeps. Wrong colour on one board beats no layer at all.
    """
    try:
        for entry_id in getattr(device, "config_entries", ()) or ():
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None or getattr(entry, "domain", "") != ESPHOME_DOMAIN:
                continue
            runtime = getattr(entry, "runtime_data", None)
            if runtime is None:  # pragma: no cover - older Home Assistant
                runtime = (hass.data.get(ESPHOME_DOMAIN) or {}).get(entry_id)
            info = getattr(runtime, "device_info", None)
            if info is not None:
                return bool(getattr(info, "has_deep_sleep", False))
    except (AttributeError, KeyError, TypeError):  # pragma: no cover
        return False
    return False


def _representative(entries: list[Any]) -> str | None:
    """One entity to stand for the whole board in the hub's popup.

    Without one the popup has nothing to link to and reads as an empty
    card: no more-info dialog, no device page, no settings. Any entity of
    the board opens the same dialog, so the only thing that matters is
    picking a useful one -- diagnostics sort last, because "Firmware" is a
    poor answer to "show me this board".
    """
    if not entries:
        return None
    return sorted(
        entries,
        key=lambda entry: (
            getattr(entry, "entity_category", None) is not None,
            entry.entity_id,
        ),
    )[0].entity_id


def _reachable(hass: HomeAssistant, entries: list[Any], sleeps: bool) -> str:
    """A board is up if any of its entities is answering.

    "Any" rather than "all" on purpose: a board can have a sensor that is
    legitimately unknown -- one that has not reported since boot -- while
    the board itself is perfectly reachable. Requiring all of them would
    paint working boards red.

    Silence means two different things depending on the board. A mains-fed
    one that stops answering has a problem; a deep-sleep one that stops
    answering is doing what it was built to do, and gets `asleep` -- its
    own state rather than a softer shade of broken, so a plan can show
    "nothing is wrong here" without pretending the board is awake.
    """
    if not entries:
        return "unknown"
    for entry in entries:
        state = hass.states.get(entry.entity_id)
        if state and str(state.state).lower() not in _UNREACHABLE:
            return "online"
    return "asleep" if sleeps else "offline"


# What the dot looks like in each of the three states a board can be in.
_ICONS = {
    "online": "mdi:chip",
    "asleep": "mdi:sleep",
    "offline": "mdi:chip-off",
}


def async_setup_spatial(hass: HomeAssistant, entry: Any) -> None:
    def data() -> dict[str, list]:
        nodes = []
        for device, children in _boards(hass):
            entries = _entities_of(
                hass, {device.id, *(child.id for child in children)}
            )
            sleeps = _sleeps(hass, device)
            state = _reachable(hass, entries, sleeps)
            nodes.append(
                node(
                    f"board-{device.id}",
                    label=getattr(device, "name_by_user", None)
                    or getattr(device, "name", "")
                    or "ESPHome",
                    area_id=getattr(device, "area_id", None),
                    # The door into Home Assistant itself. The hub fills in
                    # the device behind the entity on its own.
                    entity_id=_representative(entries),
                    state=state,
                    icon=_ICONS.get(state, "mdi:chip-off"),
                    modell=getattr(device, "model", "") or "",
                    firmware=getattr(device, "sw_version", "") or "",
                    # Says why a board is quiet, so "offline" and "schläft
                    # gerade" are not the same shrug in the popup.
                    schlafmodus="ja" if sleeps else "nein",
                    # The number a wall-mounted board's owner actually wants:
                    # how much is hanging off this one box.
                    entitaeten=len(entries),
                    # Only worth a line when the board really did split
                    # itself up; an ordinary one says nothing here.
                    **({"untergeraete": len(children)} if children else {}),
                )
            )
        return {"nodes": nodes}

    provider = spatial_provider(
        hass,
        entry,
        name="ESPHome",
        icon="mdi:chip",
        data=data,
        version="260808",
    )

    entry.async_on_unload(
        async_track_time_interval(
            hass, lambda _now: provider.async_notify(), REFRESH
        )
    )
