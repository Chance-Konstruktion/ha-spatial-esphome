"""Der Adapter gegen ein echtes Home Assistant.

Die Suite in ``tests/`` baut sich Home Assistant selbst nach. Das ist
schnell und liest sich gut, hat aber eine Luecke, die genau einmal
zuschlaegt und dann richtig: eine Attrappe bestaetigt immer die Annahme,
die man beim Schreiben hatte. Ob ``dr.async_entries_for_config_entry``
wirklich so heisst, wirklich diese Reihenfolge liefert, wirklich
Untergeraete mitbringt -- das beantwortet nur die Bibliothek selbst.

Hier laeuft deshalb ein echtes ``hass``: echte Geraete-Registry, echte
Entitaeten-Registry, echte Config Entries, echte States. Nichts an Home
Assistant ist ersetzt. Was hier gruen ist, ist gegen die Schnittstelle
gruen, die die Integration im Haus wirklich vorfindet.

Der Preis ist die Abhaengigkeit ``pytest-homeassistant-custom-component``
und rund eine Minute Laufzeit -- deshalb ein eigenes Verzeichnis und ein
eigener CI-Job, nicht als Ersatz fuer ``tests/``, sondern daneben.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spatial_esphome.spatial import async_setup_spatial

ESPHOME = "esphome"
EIGENE_DOMAIN = "spatial_esphome"


# ── Aufbau ────────────────────────────────────────────────────────────


def _esphome_eintrag(hass: HomeAssistant, *, tiefschlaf: bool = False):
    """Ein Config Entry, wie ESPHome ihn anlegt.

    ``runtime_data`` ist der Ort, an dem ESPHome sein Wissen ueber das
    Board ablegt -- unter anderem, ob es Tiefschlaf faehrt. Das ist
    fremdes Innenleben und keine zugesagte Schnittstelle; der Adapter
    liest es deshalb defensiv. Hier wird genau die Form nachgestellt, die
    er dort erwartet.
    """
    eintrag = MockConfigEntry(domain=ESPHOME, title="ESPHome")
    eintrag.add_to_hass(hass)

    class _DeviceInfo:
        has_deep_sleep = tiefschlaf

    class _Runtime:
        device_info = _DeviceInfo()

    hass.config_entries.async_update_entry(eintrag, data={})
    eintrag.runtime_data = _Runtime()
    return eintrag


def _board(hass: HomeAssistant, eintrag, *, mac="aa:bb:cc:dd:ee:01",
           name="Bürosensor", **felder):
    """Ein Board in der echten Geraete-Registry.

    Angemeldet wird es ueber ``connections`` und **ohne** identifiers --
    genau so, wie ESPHome es tut. Das ist der Grund, warum der Adapter
    ueber die Config Entries sucht: eine Suche nach einem
    ``esphome``-Identifier faende hier nichts.
    """
    registry = dr.async_get(hass)
    return registry.async_get_or_create(
        config_entry_id=eintrag.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        name=name,
        model=felder.pop("model", "ESP32"),
        sw_version=felder.pop("sw_version", "2024.6.0"),
        **felder,
    )


def _entitaet(hass: HomeAssistant, geraet, objekt_id, zustand, *,
              plattform=ESPHOME, kategorie=None, eindeutig=None):
    """Eine Entitaet auf dem Board, mit echtem Registry-Eintrag und State."""
    registry = er.async_get(hass)
    eintrag = registry.async_get_or_create(
        "sensor",
        plattform,
        eindeutig or f"{plattform}-{objekt_id}",
        device_id=geraet.id,
        suggested_object_id=objekt_id,
        entity_category=kategorie,
    )
    hass.states.async_set(eintrag.entity_id, zustand)
    return eintrag


def _knoten(hass: HomeAssistant) -> list[dict]:
    registrierung = hass.data["spatial_hub_providers"][EIGENE_DOMAIN]
    return registrierung["data"]()["nodes"]


@pytest.fixture
def eintrag(hass: HomeAssistant):
    """Der Config Entry der eigenen Integration."""
    eigener = MockConfigEntry(domain=EIGENE_DOMAIN, title="Spatial ESPHome")
    eigener.add_to_hass(hass)
    return eigener


# ── Die Tests ─────────────────────────────────────────────────────────


async def test_ein_board_wird_zu_genau_einem_knoten(hass, eintrag):
    """Der Kern des Layers: ein Kasten an der Wand, ein Punkt im Plan.

    Acht Sensoren auf einem Board sind acht Punkte zu viel -- das war der
    ganze Anlass fuer diese Datei neben dem allgemeinen Adapter.
    """
    esphome = _esphome_eintrag(hass)
    board = _board(hass, esphome)
    for nummer in range(8):
        _entitaet(hass, board, f"buero_{nummer}", "21.5")

    async_setup_spatial(hass, eintrag)
    knoten = _knoten(hass)

    assert len(knoten) == 1
    assert knoten[0]["label"] == "Bürosensor"
    assert knoten[0]["state"] == "online"
    assert knoten[0]["metadata"]["entitaeten"] == 8


async def test_boards_werden_ueber_die_config_entries_gefunden(hass, eintrag):
    """Die Annahme, die eine Attrappe nie widerlegen kann.

    ESPHome meldet ein Board allein ueber seine MAC an. Wuerde der Adapter
    ueber ``identifiers`` suchen, faende er in einem Haus voller Boards
    genau null -- und die Attrappe in tests/ wuerde das nicht merken,
    weil sie ihre FakeDevices mit einem esphome-Identifier ausstattet.
    Hier hat das Geraet bewusst keinen.
    """
    esphome = _esphome_eintrag(hass)
    board = _board(hass, esphome)
    _entitaet(hass, board, "buero_temp", "21.5")

    assert board.identifiers == set(), (
        "Das Geraet soll wie bei ESPHome ohne identifiers angelegt sein"
    )

    async_setup_spatial(hass, eintrag)
    assert len(_knoten(hass)) == 1


async def test_via_device_haengt_an_identifiers_nicht_an_connections(hass):
    """Woran die Verkettung von Geraeten wirklich haengt.

    Home Assistant loest ``via_device`` ausschliesslich gegen
    ``identifiers`` auf. Zeigt es auf eine ``connection`` -- eine MAC etwa
    --, bleibt ``via_device_id`` still auf ``None``, und Home Assistant
    schreibt eine Warnung, die ab 2025.12 ein Fehler wird.

    Das steht hier als eigener Test, weil es sich nicht ableiten laesst
    und weil eine Attrappe genau das aufloest, was man ihr beibringt. Wer
    spaeter Untergeraete verkettet, soll das hier finden, bevor er einen
    Nachmittag sucht.
    """
    esphome = _esphome_eintrag(hass)
    registry = dr.async_get(hass)

    ueber_mac = registry.async_get_or_create(
        config_entry_id=esphome.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:01")},
        name="Board mit MAC",
    )
    kind_per_mac = registry.async_get_or_create(
        config_entry_id=esphome.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:02")},
        name="Kind ueber MAC",
        via_device=(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:01"),
    )
    assert kind_per_mac.via_device_id is None, (
        "Wenn Home Assistant das eines Tages doch aufloest, gehoert der "
        "Adapter darauf angepasst -- und dieser Test gestrichen"
    )
    assert ueber_mac.id != kind_per_mac.via_device_id

    ueber_id = registry.async_get_or_create(
        config_entry_id=esphome.entry_id,
        identifiers={("esphome", "board-1")},
        name="Board mit Identifier",
    )
    kind_per_id = registry.async_get_or_create(
        config_entry_id=esphome.entry_id,
        identifiers={("esphome", "board-1-relais")},
        name="Kind ueber Identifier",
        via_device=("esphome", "board-1"),
    )
    assert kind_per_id.via_device_id == ueber_id.id


async def test_untergeraete_werden_eingeklappt(hass, eintrag):
    """Ein Board, das sich als mehrere Geraete meldet, bleibt ein Punkt.

    Verkettet wird ueber ``identifiers``, weil das der einzige Weg ist,
    auf dem Home Assistant ``via_device`` aufloest -- siehe den Test
    darueber. Der Adapter selbst liest nur das Ergebnis,
    ``via_device_id``, und dem ist gleich, woraus es entstanden ist.
    """
    esphome = _esphome_eintrag(hass)
    registry = dr.async_get(hass)
    board = registry.async_get_or_create(
        config_entry_id=esphome.entry_id,
        identifiers={("esphome", "buero")},
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:01")},
        name="Bürosensor",
        model="ESP32",
        sw_version="2024.6.0",
    )
    _entitaet(hass, board, "buero_temp", "21.5")

    kind = registry.async_get_or_create(
        config_entry_id=esphome.entry_id,
        identifiers={("esphome", "buero-relais")},
        name="Bürosensor Relais",
        via_device=("esphome", "buero"),
    )
    assert kind.via_device_id == board.id, (
        "Home Assistant hat via_device nicht aufgeloest -- ohne das ist "
        "der Test wertlos"
    )
    _entitaet(hass, kind, "buero_relais", "on", eindeutig="esphome-relais")

    async_setup_spatial(hass, eintrag)
    knoten = _knoten(hass)

    assert len(knoten) == 1
    assert knoten[0]["metadata"]["untergeraete"] == 1
    # Die Entitaet des Untergeraets zaehlt zum Board: sie geht mit ihm
    # zusammen still.
    assert knoten[0]["metadata"]["entitaeten"] == 2


async def test_fremde_entitaeten_faerben_das_board_nicht_gruen(hass, eintrag):
    """Der Router legt seinen device_tracker auf dieselbe MAC.

    Er sagt noch lange ``not_home``, wenn das Board schon tot ist -- der
    Router erinnert sich an die Adresse. Wuerde er mitzaehlen, waere das
    Board gruen, weil jemand anderes noch eine Meinung dazu hat.
    """
    esphome = _esphome_eintrag(hass)
    board = _board(hass, esphome)
    _entitaet(hass, board, "buero_temp", "unavailable")
    _entitaet(hass, board, "buero_tracker", "not_home",
              plattform="device_tracker_source")

    async_setup_spatial(hass, eintrag)
    assert _knoten(hass)[0]["state"] == "offline"


async def test_ein_stiller_tiefschlaefer_ist_nicht_kaputt(hass, eintrag):
    """Ein Tiefschlaf-Board ist nachts still, weil es das soll.

    ``asleep`` statt ``offline`` -- ein eigener Zustand, kein weicheres
    Rot. Der Wert dafuer steht in ESPHomes runtime_data.
    """
    esphome = _esphome_eintrag(hass, tiefschlaf=True)
    board = _board(hass, esphome)
    _entitaet(hass, board, "buero_temp", "unavailable")

    async_setup_spatial(hass, eintrag)
    knoten = _knoten(hass)

    assert knoten[0]["state"] == "asleep"
    assert knoten[0]["metadata"]["schlafmodus"] == "ja"
    assert knoten[0]["icon"] == "mdi:sleep"


async def test_ein_board_ohne_lesbaren_schlafwert_gilt_als_wach(hass, eintrag):
    """Fremdes Innenleben darf fehlen, ohne das Layer mitzunehmen.

    Faellt runtime_data weg -- ein Home-Assistant-Update, eine Umbenennung
    -- ist die falsche Farbe auf einem Board hinnehmbar. Eine Ausnahme an
    dieser Stelle waere es nicht: der Hub verwirft dann die ganze Ebene.
    """
    esphome = _esphome_eintrag(hass)
    esphome.runtime_data = None
    board = _board(hass, esphome)
    _entitaet(hass, board, "buero_temp", "unavailable")

    async_setup_spatial(hass, eintrag)
    knoten = _knoten(hass)

    assert knoten[0]["state"] == "offline"
    assert knoten[0]["metadata"]["schlafmodus"] == "nein"


async def test_knoten_ids_bleiben_ueber_neustarts_gleich(hass, eintrag):
    """Die teuerste Sorte Fehler: der Nutzer verliert seinen Grundriss.

    Positionen werden gegen die Knoten-ID gespeichert. Die ID haengt hier
    an der Geraete-ID der Registry -- und die ueberlebt einen Neustart,
    solange das Geraet dasselbe ist. Genau das wird hier nachgestellt,
    indem der Adapter zweimal aufgebaut wird.
    """
    esphome = _esphome_eintrag(hass)
    board = _board(hass, esphome)
    _entitaet(hass, board, "buero_temp", "21.5")

    async_setup_spatial(hass, eintrag)
    vorher = [knoten["id"] for knoten in _knoten(hass)]

    hass.data.pop("spatial_hub_providers")
    async_setup_spatial(hass, eintrag)
    nachher = [knoten["id"] for knoten in _knoten(hass)]

    assert vorher == nachher
    assert vorher == [f"board-{board.id}"]


async def test_ohne_esphome_im_haus_bleibt_die_ebene_leer(hass, eintrag):
    """Kein ESPHome installiert heisst keine Knoten, keine Ausnahme."""
    async_setup_spatial(hass, eintrag)
    assert _knoten(hass) == []
