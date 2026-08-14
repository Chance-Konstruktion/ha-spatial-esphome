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
