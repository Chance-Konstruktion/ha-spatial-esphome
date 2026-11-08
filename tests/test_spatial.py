"""What this adapter hands the hub -- one board at a time.

The interesting decisions are all judgement calls that a passing import
would not catch: one dot per board rather than per entity, "up if
anything answers" rather than "up if everything answers", and a door back
into Home Assistant on every node.
"""

from __future__ import annotations

from custom_components.spatial_esphome.spatial import async_setup_spatial

from conftest import FakeEntry, FakeHass, house


def _nodes(hass):
    return hass.registrations["spatial_esphome"]["data"]()["nodes"]


def _setup(entities, **kwargs):
    hass = FakeHass()
    house(hass, entities=entities, **kwargs)
    async_setup_spatial(hass, FakeEntry())
    return hass


def test_one_dot_per_board_not_per_entity():
    """Eight dots for one box is eight times the clutter and no more news."""
    nodes = _nodes(_setup({f"sensor.s{i}": "21.5" for i in range(8)}))

    assert len(nodes) == 1
    assert nodes[0]["metadata"]["entitaeten"] == 8


def test_a_board_is_up_if_anything_on_it_answers():
    """Requiring all of them would paint working boards red -- a sensor
    that has not reported since boot is not a dead board."""
    nodes = _nodes(_setup({"sensor.a": "unknown", "sensor.b": "21.5"}))

    assert nodes[0]["state"] == "online"


def test_a_board_nobody_can_reach_is_offline():
    nodes = _nodes(_setup({"sensor.a": "unavailable", "sensor.b": "unavailable"}))

    assert nodes[0]["state"] == "offline"
    assert nodes[0]["icon"] == "mdi:chip-off"


def test_disabled_entities_do_not_make_a_board_look_offline():
    from conftest import _ENTITIES

    hass = _setup({"sensor.a": "unavailable"})
    _ENTITIES.entities["sensor.a"].disabled_by = "user"

    node = _nodes(hass)[0]

    assert node["state"] == "unknown"
    assert node["metadata"]["entitaeten"] == 0
    assert "entity_id" not in node


def test_entity_registry_is_scanned_once_per_refresh(monkeypatch):
    from homeassistant.helpers import entity_registry as er
    from conftest import _DEVICES, _ENTITIES, FakeDevice, FakeEntity

    hass = FakeHass()
    house(hass, entities={"sensor.a": "21.5"})
    _DEVICES.devices["b2"] = FakeDevice("b2")
    _ENTITIES.entities["sensor.b"] = FakeEntity(
        "sensor.b", device_id="b2"
    )
    hass.states.set("sensor.b", "18.0")
    async_setup_spatial(hass, FakeEntry())

    original_get = er.async_get
    calls = 0

    def counted_get(instance):
        nonlocal calls
        calls += 1
        return original_get(instance)

    monkeypatch.setattr(er, "async_get", counted_get)
    nodes = _nodes(hass)

    assert len(nodes) == 2
    assert calls == 1, "the entity registry should be indexed once per refresh"


def test_a_board_without_entities_says_it_does_not_know():
    """Nothing answered because nothing was asked. That is not "offline"."""
    nodes = _nodes(_setup({}))

    assert nodes[0]["state"] == "unknown"


def test_a_node_carries_the_door_into_home_assistant():
    """Without an entity the hub's popup has nothing to link to and reads
    as an empty card."""
    nodes = _nodes(_setup({"sensor.b": "21.5", "sensor.a": "18.0"}))

    assert nodes[0]["entity_id"] == "sensor.a"


def test_a_diagnostic_entity_is_the_last_resort():
    """"Firmware" is a poor answer to "show me this board"."""
    nodes = _nodes(
        _setup({"sensor.aa_firmware": ("2024.6.0", "diagnostic"),
                "sensor.zz_temperature": "21.5"})
    )

    assert nodes[0]["entity_id"] == "sensor.zz_temperature"


def test_a_board_with_no_entities_links_nowhere_rather_than_lying():
    node = _nodes(_setup({}))[0]

    assert "entity_id" not in node


def test_a_deep_sleep_board_is_asleep_and_not_broken():
    """Being gone is its job. Red every night would say the opposite."""
    nodes = _nodes(_setup({"sensor.a": "unavailable"}, deep_sleep=True))

    assert nodes[0]["state"] == "asleep"
    assert nodes[0]["icon"] == "mdi:sleep"


def test_a_deep_sleep_board_that_is_awake_is_simply_online():
    """`asleep` is what silence means here, not what the board always is."""
    nodes = _nodes(_setup({"sensor.a": "12.4"}, deep_sleep=True))

    assert nodes[0]["state"] == "online"


def test_sleep_lookup_prefers_current_single_config_entry_id():
    """Current HA device entries must not touch deprecated config_entries."""
    from custom_components.spatial_esphome.spatial import _sleeps
    from conftest import FakeEsphomeEntry

    hass = FakeHass()
    hass.config_entries.entries = {
        "esphome-entry": FakeEsphomeEntry(has_deep_sleep=True)
    }

    class CurrentDevice:
        config_entry_id = "esphome-entry"

        @property
        def config_entries(self):
            raise AssertionError(
                "the deprecated multi-entry property must not be read"
            )

    assert _sleeps(hass, CurrentDevice()) is True


def test_a_mains_fed_board_that_goes_quiet_still_says_offline():
    """The distinction only exists because the two are different."""
    nodes = _nodes(_setup({"sensor.a": "unavailable"}, deep_sleep=False))

    assert nodes[0]["state"] == "offline"


def test_the_popup_says_why_a_board_is_quiet():
    awake = _nodes(_setup({"sensor.a": "12.4"}, deep_sleep=True))[0]

    assert awake["metadata"]["schlafmodus"] == "ja"


def test_a_board_whose_sleep_cannot_be_read_is_treated_as_never_sleeping():
    """ESPHome's runtime data is somebody else's internals. A plan that
    loses the layer after an HA update is worse than one wrong colour.

    Der Ausfall wird hier am ``runtime_data`` nachgestellt und nicht mehr
    am ganzen Config Entry: Seit die Boards ueber die Config Entries
    gefunden werden, wuerde ein leeres Verzeichnis nicht das Innenleben
    abschalten, sondern das Layer. Fremdes Terrain ist das, was *im*
    Eintrag steht -- der Eintrag selbst ist oeffentlich und bleibt.
    """
    hass = FakeHass()
    house(hass, entities={"sensor.a": "unavailable"})
    hass.config_entries.entries["esphome-entry"].runtime_data = None
    async_setup_spatial(hass, FakeEntry())

    knoten = _nodes(hass)[0]
    assert knoten["state"] == "offline"
    assert knoten["metadata"]["schlafmodus"] == "nein"


def test_a_router_that_remembers_the_mac_does_not_revive_a_dead_board():
    """The router keeps saying `not_home` long after the board is gone --
    that is the router having an opinion, not the board answering."""
    nodes = _nodes(
        _setup(
            {"sensor.a": "unavailable", "sensor.b": "unavailable"},
            foreign={"device_tracker.b1": "not_home"},
        )
    )

    assert nodes[0]["state"] == "offline"


def test_a_foreign_entity_is_not_counted_as_the_boards_own():
    """"Wie viel hängt an dieser Box" means the box's own entities."""
    nodes = _nodes(
        _setup({"sensor.a": "21.5"}, foreign={"device_tracker.b1": "home"})
    )

    assert nodes[0]["metadata"]["entitaeten"] == 1


def test_a_foreign_entity_never_becomes_the_link():
    """A router's tracker opens the router's dialog, not the board's."""
    nodes = _nodes(
        _setup({"sensor.z": "21.5"}, foreign={"device_tracker.aaa": "home"})
    )

    assert nodes[0]["entity_id"] == "sensor.z"


def test_the_board_stands_in_the_area_home_assistant_gave_it():
    nodes = _nodes(_setup({"sensor.a": "21.5"}, area_id="buero"))

    assert nodes[0]["area_id"] == "buero"


def test_the_users_own_name_wins():
    hass = FakeHass()
    board = house(hass, entities={"sensor.a": "21.5"})
    board.name_by_user = "Sensor Küche"
    async_setup_spatial(hass, FakeEntry())

    assert _nodes(hass)[0]["label"] == "Sensor Küche"


def test_esphome_invents_no_edges():
    """Nothing here measures the path to a board, and drawing a line to a
    router that may not exist would be an invention."""
    payload = _setup({"sensor.a": "21.5"}).registrations["spatial_esphome"]["data"]()

    assert not payload.get("edges")


def test_the_plan_follows_the_boards_without_a_push():
    """ESPHome sends no signal this adapter could subscribe to, so it asks."""
    from conftest import SCHEDULED

    SCHEDULED.clear()
    _setup({"sensor.a": "21.5"})

    assert SCHEDULED, "nothing would ever refresh the layer"


def test_the_scheduled_tick_notifies_from_the_event_loop(monkeypatch):
    """The tick must run in the event loop, and it must actually notify.

    A bare lambda is executor work to Home Assistant: the tick goes to the
    worker thread pool, and from there async_dispatcher_send is refused --
    every 30 seconds an exception, and the hub never hears anything after
    the first draw. A callback runs in the loop, where the notification
    belongs. Nothing before asserted either half: the scheduled action was
    recorded, never called.
    """
    import custom_components.spatial_esphome.spatial_hub_provider as shim
    from conftest import SCHEDULED

    from custom_components.spatial_esphome.spatial_hub_provider import (
        SIGNAL_DATA_UPDATED,
    )

    gesendet: list[tuple] = []
    monkeypatch.setattr(
        shim,
        "async_dispatcher_send",
        lambda hass, signal, *args: gesendet.append((signal, *args)),
    )

    SCHEDULED.clear()
    _setup({"sensor.a": "21.5"})
    (action, _interval) = SCHEDULED[0]

    assert getattr(action, "__hass_callback__", False) is True, (
        "the refresh tick must be a callback -- executor work is refused"
    )
    action(None)
    aktualisierungen = [s for s in gesendet if s[0] == SIGNAL_DATA_UPDATED]
    assert aktualisierungen == [(SIGNAL_DATA_UPDATED, "spatial_esphome")], (
        "a tick that never notifies leaves the plan frozen at one frame"
    )


def test_no_dead_entity_gatherer_remains():
    """Since the perf takeover data() builds its entity index inline.

    ``_entities_of()`` had no caller left -- a second gatherer beside the
    inline one invites exactly the drift that made it dead code.
    """
    import custom_components.spatial_esphome.spatial as spatial

    assert not hasattr(spatial, "_entities_of"), (
        "data() builds its index inline -- a second gatherer would drift"
    )


def test_a_deactivated_esphome_entry_draws_nothing():
    """A deactivated entry never builds its entities, so its boards would
    sit on the plan forever without a real state. Not drawing them is the
    honest answer -- the same decision as the empty list: what the user
    turned off has no business on a live plan.
    """
    from conftest import (
        _DEVICES,
        _ENTITIES,
        FakeDevice,
        FakeEntity,
        FakeEntry,
        FakeEsphomeEntry,
        FakeHass,
    )

    hass = FakeHass()
    _DEVICES.devices = {
        "b1": FakeDevice("b1", config_entries=("e1",), name="Lebend"),
        "b2": FakeDevice("b2", config_entries=("e2",), name="Stillgelegt"),
    }
    _ENTITIES.entities = {
        "sensor.a": FakeEntity("sensor.a", device_id="b1"),
        "sensor.b": FakeEntity("sensor.b", device_id="b2"),
    }
    hass.states.set("sensor.a", "21.5")
    hass.states.set("sensor.b", "unavailable")
    hass.config_entries.entries = {
        "e1": FakeEsphomeEntry("e1"),
        "e2": FakeEsphomeEntry("e2"),
    }
    hass.config_entries.entries["e2"].disabled_by = "user"
    async_setup_spatial(hass, FakeEntry())

    knoten = hass.registrations["spatial_esphome"]["data"]()["nodes"]

    assert [ein_knoten["label"] for ein_knoten in knoten] == ["Lebend"], (
        "ein stillgelegter Eintrag ist kein dauerhaft totes Board -- "
        "er wird gar nicht gezeichnet"
    )


def test_grandchildren_are_an_assumption_not_a_guarantee():
    """ESPHome baut hoechstens eine Ebene Untergeraete -- mehr gibt es
    nicht, aber geschrieben steht das nur im Docstring von ``_boards()``.

    Ein Geraet, dessen ``via_device_id`` auf ein Untergeraet zeigt (ein
    Enkel des Boards), faellt unter das Untergeraet und verschwindet
    still aus Knoten und Zaehlung. Diese Annahme haelt der Test fest:
    bricht sie eines Tages, wird das hier rot statt leise.
    """
    from conftest import (
        _DEVICES,
        _ENTITIES,
        FakeDevice,
        FakeEntity,
        FakeEntry,
        FakeEsphomeEntry,
        FakeHass,
    )

    hass = FakeHass()
    board = FakeDevice("b1", config_entries=("e1",), name="Board")
    kind = FakeDevice("b1-relais", config_entries=("e1",), name="Relais")
    kind.via_device_id = "b1"
    enkel = FakeDevice("b1-relais-ext", config_entries=("e1",), name="Ext")
    enkel.via_device_id = "b1-relais"
    _DEVICES.devices = {
        "b1": board,
        "b1-relais": kind,
        "b1-relais-ext": enkel,
    }
    _ENTITIES.entities = {
        "sensor.board": FakeEntity("sensor.board", device_id="b1"),
        "sensor.relais": FakeEntity("sensor.relais", device_id="b1-relais"),
        "sensor.ext": FakeEntity("sensor.ext", device_id="b1-relais-ext"),
    }
    hass.states.set("sensor.board", "21.5")
    hass.states.set("sensor.relais", "on")
    hass.states.set("sensor.ext", "21.5")
    hass.config_entries.entries = {"e1": FakeEsphomeEntry("e1")}
    async_setup_spatial(hass, FakeEntry())

    knoten = hass.registrations["spatial_esphome"]["data"]()["nodes"]

    assert len(knoten) == 1
    assert knoten[0]["metadata"]["untergeraete"] == 1
    assert knoten[0]["metadata"]["entitaeten"] == 2, (
        "der Enkel faellt unter das Untergeraet und zaehlt nicht mit -- "
        "genau die Ein-Schicht-Annahme aus dem Docstring von _boards()"
    )


def test_the_30_second_contract_holds_on_both_sides():
    """README promises an update every 30 seconds; REFRESH is that same
    promise in code. Each side must keep the other honest: change one
    without the other and one of them lies.
    """
    from datetime import timedelta
    from pathlib import Path

    from custom_components.spatial_esphome.spatial import REFRESH

    assert REFRESH == timedelta(seconds=30)
    readme = (
        Path(__file__).resolve().parents[1] / "README.md"
    ).read_text(encoding="utf-8")
    assert "**30 Sekunden**" in readme, (
        "the README's update promise no longer matches REFRESH"
    )


def test_two_esphome_entries_are_two_boards():
    """Every other case builds exactly one entry; two entries must mean
    two dots, not one or zero. A house with several ESPHome configs is
    the normal case, not the exotic one.
    """
    from conftest import (
        _DEVICES,
        _ENTITIES,
        FakeDevice,
        FakeEntity,
        FakeEntry,
        FakeEsphomeEntry,
        FakeHass,
    )

    hass = FakeHass()
    _DEVICES.devices = {
        "b1": FakeDevice("b1", config_entries=("e1",), name="Wohnzimmer"),
        "b2": FakeDevice("b2", config_entries=("e2",), name="Keller"),
    }
    _ENTITIES.entities = {
        "sensor.a": FakeEntity("sensor.a", device_id="b1"),
        "sensor.b": FakeEntity("sensor.b", device_id="b2"),
    }
    hass.states.set("sensor.a", "21.5")
    hass.states.set("sensor.b", "18.0")
    hass.config_entries.entries = {
        "e1": FakeEsphomeEntry("e1"),
        "e2": FakeEsphomeEntry("e2"),
    }
    async_setup_spatial(hass, FakeEntry())

    knoten = hass.registrations["spatial_esphome"]["data"]()["nodes"]

    assert sorted(
        ein_knoten["label"] for ein_knoten in knoten
    ) == ["Keller", "Wohnzimmer"], (
        "two config entries carry two boards -- each its own dot"
    )


def test_unloading_the_entry_takes_the_tick_with_it():
    """The refresh tick is registered on the entry's unload hook: once the
    entry is gone, nothing may keep ticking. An orphaned tick would fire
    into a world that no longer listens.
    """
    from conftest import SCHEDULED

    SCHEDULED.clear()
    hass = FakeHass()
    house(hass, entities={"sensor.a": "21.5"})
    entry = FakeEntry()
    async_setup_spatial(hass, entry)

    assert SCHEDULED, "the tick should be scheduled while the entry lives"
    entry.unload()
    assert not SCHEDULED, "the tick must die with the entry it serves"


def test_a_nameless_board_still_says_esphome():
    """Neither the user nor ESPHome named the board: the label falls back
    to "ESPHome" rather than drawing a dot with no name at all.
    """
    from conftest import (
        _DEVICES,
        _ENTITIES,
        FakeDevice,
        FakeEntity,
        FakeEntry,
        FakeEsphomeEntry,
        FakeHass,
    )

    hass = FakeHass()
    _DEVICES.devices = {"b1": FakeDevice("b1", name="", name_by_user=None)}
    _ENTITIES.entities = {"sensor.a": FakeEntity("sensor.a", device_id="b1")}
    hass.states.set("sensor.a", "21.5")
    hass.config_entries.entries = {"esphome-entry": FakeEsphomeEntry()}
    async_setup_spatial(hass, FakeEntry())

    assert _nodes(hass)[0]["label"] == "ESPHome"
