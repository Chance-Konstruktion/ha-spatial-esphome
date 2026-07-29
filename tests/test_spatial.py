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
