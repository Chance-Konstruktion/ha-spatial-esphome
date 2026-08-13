"""Home Assistant stubs, so the test suite needs nothing installed.

The adapter reaches into four corners of Home Assistant: the type it
annotates with, the device registry it filters for ESPHome boards, the
entity registry it counts entities in, and the timer it hangs its refresh
on. None of those need to be real to answer the only question these tests
ask -- what does this provider hand the hub? -- so they are stubbed here
rather than pulled in as a dependency.

Kept deliberately thin. A stub that grows features nobody asserts on is a
second implementation to keep in step with the first.
"""

from __future__ import annotations

import sys
import types


def _module(name: str, **attributes) -> types.ModuleType:
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__path__ = []  # importable as a package
        sys.modules[name] = module
    module = sys.modules[name]
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


class HomeAssistant:  # noqa: D101 - a name to annotate with, nothing more
    pass


def callback(func):  # noqa: D103 - HA's marker decorator, identity here
    return func


class ConfigEntry:  # noqa: D101 - another name to annotate with
    pass


_module("homeassistant")
_module("homeassistant.core", HomeAssistant=HomeAssistant, callback=callback)
_module("homeassistant.config_entries", ConfigEntry=ConfigEntry)
_module("homeassistant.helpers")


# ── The two registries ────────────────────────────────────────────────
#
# Both are iterated rather than queried: the adapter has no id to look a
# board up by, it wants every ESPHome device there is.


class FakeDevice:
    def __init__(self, device_id, *, identifiers=(("esphome", "aabbcc"),),
                 name="", name_by_user=None, area_id=None, model="",
                 sw_version="", config_entries=("esphome-entry",)):
        self.id = device_id
        self.identifiers = set(identifiers)
        self.config_entries = set(config_entries)
        self.name = name
        self.name_by_user = name_by_user
        self.area_id = area_id
        self.model = model
        self.sw_version = sw_version


class FakeEntity:
    def __init__(self, entity_id, *, device_id=None, entity_category=None,
                 platform="esphome"):
        self.entity_id = entity_id
        self.device_id = device_id
        self.entity_category = entity_category
        # Which integration put this entity on the device. Not always the
        # one that owns the box -- the router adds its own.
        self.platform = platform


class _Registry:
    def __init__(self):
        self.devices = {}
        self.entities = {}


_DEVICES = _Registry()
_ENTITIES = _Registry()

_module("homeassistant.helpers.device_registry", async_get=lambda _hass: _DEVICES)
_module("homeassistant.helpers.entity_registry", async_get=lambda _hass: _ENTITIES)


# ── The refresh timer ─────────────────────────────────────────────────
#
# Recorded rather than run: whether the adapter asks for a tick is worth
# asserting, whether the clock works is not this suite's problem.

SCHEDULED: list = []


def async_track_time_interval(_hass, action, interval, **_kwargs):
    SCHEDULED.append((action, interval))
    return lambda: SCHEDULED.remove((action, interval))


_module(
    "homeassistant.helpers.event",
    async_track_time_interval=async_track_time_interval,
)


def async_dispatcher_send(_hass, _signal, *_args):
    return None


def async_dispatcher_connect(_hass, _signal, _target):
    return lambda: None


_module(
    "homeassistant.helpers.dispatcher",
    async_dispatcher_send=async_dispatcher_send,
    async_dispatcher_connect=async_dispatcher_connect,
)


# ── Stand-ins the tests build with ────────────────────────────────────


class FakeState:
    def __init__(self, state):
        self.state = state


class FakeStates:
    def __init__(self):
        self._states = {}

    def set(self, entity_id, state):
        self._states[entity_id] = FakeState(state)

    def get(self, entity_id):
        return self._states.get(entity_id)


class FakeDeviceInfo:
    """ESPHome's own record of a board. Only the one flag is read."""

    def __init__(self, has_deep_sleep=False):
        self.has_deep_sleep = has_deep_sleep


class FakeRuntime:
    def __init__(self, device_info):
        self.device_info = device_info


class FakeEsphomeEntry:
    domain = "esphome"

    def __init__(self, entry_id="esphome-entry", has_deep_sleep=False):
        self.entry_id = entry_id
        self.runtime_data = FakeRuntime(FakeDeviceInfo(has_deep_sleep))


class FakeConfigEntries:
    def __init__(self):
        self.entries = {}

    def async_get_entry(self, entry_id):
        return self.entries.get(entry_id)


class FakeHass:
    """The ``data`` dict and the states -- the whole surface used here."""

    def __init__(self):
        self.data = {}
        self.states = FakeStates()
        self.config_entries = FakeConfigEntries()

    @property
    def registrations(self):
        return self.data.get("spatial_hub_providers", {})


class FakeEntry:
    """A ConfigEntry stand-in that records its unload hooks."""

    domain = "spatial_esphome"
    entry_id = "esphome"

    def __init__(self):
        self.unload_hooks = []

    def async_on_unload(self, func):
        self.unload_hooks.append(func)

    def unload(self):
        for hook in self.unload_hooks:
            hook()


def house(hass, *, entities, area_id="buero", device_id="b1", foreign=None,
          deep_sleep=False, **device):
    """One board with the given entities, wired into both registries.

    ``entities`` maps entity_id to state; a value of ``(state, category)``
    marks the entity as diagnostic. ``foreign`` maps entity_id to state for
    entities another integration put on the same device.
    """
    board = FakeDevice(device_id, area_id=area_id, name="Bürosensor",
                       model="ESP32", sw_version="2024.6.0", **device)
    _DEVICES.devices = {device_id: board}
    _ENTITIES.entities = {}
    hass.config_entries.entries = {
        "esphome-entry": FakeEsphomeEntry(has_deep_sleep=deep_sleep)
    }
    for entity_id, value in entities.items():
        state, category = value if isinstance(value, tuple) else (value, None)
        _ENTITIES.entities[entity_id] = FakeEntity(
            entity_id, device_id=device_id, entity_category=category
        )
        hass.states.set(entity_id, state)
    for entity_id, state in (foreign or {}).items():
        _ENTITIES.entities[entity_id] = FakeEntity(
            entity_id, device_id=device_id, platform="device_tracker_source"
        )
        hass.states.set(entity_id, state)
    return board
