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

import importlib
import sys
from pathlib import Path

import pytest

# Home Assistant's test config dir is temporary. Point the package loader at
# this checkout even if a plugin imported another custom_components package.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY_ROOT))
custom_components = importlib.import_module("custom_components")
_LOCAL_CUSTOM_COMPONENTS = str(_REPOSITORY_ROOT / "custom_components")
custom_components.__path__ = [
    _LOCAL_CUSTOM_COMPONENTS,
    *(
        search_path
        for search_path in getattr(custom_components, "__path__", [])
        if search_path != _LOCAL_CUSTOM_COMPONENTS
    ),
]
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


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
async def eintrag(hass: HomeAssistant, enable_custom_integrations):
    """Der Config Entry der eigenen Integration mit echtem Setup und Rueckbau."""
    eigener = MockConfigEntry(domain=EIGENE_DOMAIN, title="Spatial ESPHome")
    eigener.add_to_hass(hass)
    yield eigener
    if eigener.state is ConfigEntryState.LOADED:
        assert await hass.config_entries.async_unload(eigener.entry_id)
        await hass.async_block_till_done()
        assert EIGENE_DOMAIN not in hass.data.get("spatial_hub_providers", {})


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

    assert await hass.config_entries.async_setup(eintrag.entry_id)
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

    assert await hass.config_entries.async_setup(eintrag.entry_id)
    assert len(_knoten(hass)) == 1


async def test_via_device_id_verweist_direkt_auf_geraete_id(hass):
    """Untergeraete verweisen auf die ID, nicht auf die MAC des Eltern-Geraets.

    ESPHome legt das Board nur mit einer MAC-Connection und ohne Identifier
    an. Eine MAC ist deshalb kein gueltiger Wert fuer `via_device_id`;
    eine echte Registry-Geraete-ID muss direkt uebergeben werden.
    """
    esphome = _esphome_eintrag(hass)
    registry = dr.async_get(hass)

    board = registry.async_get_or_create(
        config_entry_id=esphome.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:01")},
        name="Board mit MAC",
    )
    assert board.identifiers == set()

    with pytest.raises(
        dr.DeviceInfoError,
        match="via_device_id .* is not a registered device id",
    ):
        registry.async_get_or_create(
            config_entry_id=esphome.entry_id,
            identifiers={("esphome", "child-with-mac-as-parent")},
            name="Kind ueber MAC statt ID",
            via_device_id="aa:bb:cc:dd:ee:01",
        )

    kind = registry.async_get_or_create(
        config_entry_id=esphome.entry_id,
        identifiers={("esphome", "board-relais")},
        name="Kind ueber Geraete-ID",
        via_device_id=board.id,
    )
    assert kind.via_device_id == board.id
    assert kind.id != board.id


async def test_untergeraete_werden_eingeklappt(hass, eintrag):
    """Ein Board, das sich als mehrere Geraete meldet, bleibt ein Punkt.

    Aufgebaut wie ESPHome es wirklich tut, und das ist ein dritter Weg
    neben den beiden aus dem Test darueber:

    * Das **Board** bekommt nur ``connections`` mit seiner MAC, keinen
      Identifier.
    * Das **Untergeraet** bekommt einen eigenen Identifier aus MAC und
      Geraete-Nummer.
    * Die Verkettung entsteht **nicht** ueber ``via_device``, sondern
      danach von Hand mit ``async_update_device(..., via_device_id=...)``.

    Damit umgeht ESPHome die Identifier-Aufloesung vollstaendig -- und
    genau deshalb funktioniert die Kette, obwohl das Board keinen
    Identifier hat, auf den ``via_device`` zeigen koennte. Der frueher
    hier gebaute Aufbau (Board *mit* Identifier) hat den Adapter richtig
    geprueft, aber an einem Haus, das es nicht gibt.

    Nachzulesen in ``homeassistant/components/esphome/manager.py``.
    """
    esphome = _esphome_eintrag(hass)
    registry = dr.async_get(hass)
    mac = "aa:bb:cc:dd:ee:01"

    board = registry.async_get_or_create(
        config_entry_id=esphome.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        name="Bürosensor",
        model="ESP32",
        sw_version="2024.6.0",
    )
    assert not board.identifiers, (
        "ESPHome vergibt fuer das Board keinen Identifier -- steht diese "
        "Annahme eines Tages nicht mehr, gehoert der Docstring von "
        "_boards() korrigiert"
    )
    _entitaet(hass, board, "buero_temp", "21.5")

    kind = registry.async_get_or_create(
        config_entry_id=esphome.entry_id,
        identifiers={("esphome", f"{mac}_relais")},
        name="Bürosensor Relais",
    )
    kind = registry.async_update_device(kind.id, via_device_id=board.id)
    assert kind.via_device_id == board.id
    _entitaet(hass, kind, "buero_relais", "on", eindeutig="esphome-relais")

    assert await hass.config_entries.async_setup(eintrag.entry_id)
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

    assert await hass.config_entries.async_setup(eintrag.entry_id)
    assert _knoten(hass)[0]["state"] == "offline"


async def test_ein_stiller_tiefschlaefer_ist_nicht_kaputt(hass, eintrag):
    """Ein Tiefschlaf-Board ist nachts still, weil es das soll.

    ``asleep`` statt ``offline`` -- ein eigener Zustand, kein weicheres
    Rot. Der Wert dafuer steht in ESPHomes runtime_data.
    """
    esphome = _esphome_eintrag(hass, tiefschlaf=True)
    board = _board(hass, esphome)
    _entitaet(hass, board, "buero_temp", "unavailable")

    assert await hass.config_entries.async_setup(eintrag.entry_id)
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

    assert await hass.config_entries.async_setup(eintrag.entry_id)
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

    assert await hass.config_entries.async_setup(eintrag.entry_id)
    vorher = [knoten["id"] for knoten in _knoten(hass)]

    assert await hass.config_entries.async_unload(eintrag.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    nachher = [knoten["id"] for knoten in _knoten(hass)]

    assert vorher == nachher
    assert vorher == [f"board-{board.id}"]


async def test_ohne_esphome_im_haus_bleibt_die_ebene_leer(hass, eintrag):
    """Kein ESPHome installiert heisst keine Knoten, keine Ausnahme.

    Die leere Liste ist hier ausdruecklich das richtige Ergebnis und
    nicht der Ausfall, gegen den ``_sleeps()`` sich absichert. Die
    Begruendung steht bei ``_boards()``: einen Rueckfall gaebe es nur
    ueber ``identifiers``, und der findet bauartbedingt null Boards --
    er wuerde eine ehrliche leere Liste gegen eine stille tauschen.
    """
    assert await hass.config_entries.async_setup(eintrag.entry_id)
    assert _knoten(hass) == []


async def test_eintrags_setup_datenpfad_und_entladen(hass, eintrag):
    """Der echte Config-Entry-Lebenszyklus umfasst Anmeldung, Nutzlast und Rueckbau.

    Neben den gezielten Tests prueft dieser Test den vollstaendigen
    Setup-/Unload-Pfad ueber Home Assistants Config-Entry-Verwaltung.
    Der Knoten stammt von einem synthetischen ESPHome-Geraet; die MAC ist
    erfunden und lokal administriert.
    """
    esphome_eintrag = _esphome_eintrag(hass)
    board = _board(hass, esphome_eintrag, mac="02:00:00:00:00:01")
    _entitaet(hass, board, "spatial-lifecycle", "online")

    assert await hass.config_entries.async_setup(eintrag.entry_id)
    await hass.async_block_till_done()
    assert eintrag.state is ConfigEntryState.LOADED

    providers = hass.data.get("spatial_hub_providers", {})
    assert EIGENE_DOMAIN in providers
    nutzlast = providers[EIGENE_DOMAIN]["data"]()
    knoten = next(
        knoten
        for knoten in nutzlast["nodes"]
        if knoten["id"] == f"board-{board.id}"
    )
    assert knoten["state"] == "online"
    assert knoten["label"] == board.name

    assert await hass.config_entries.async_unload(eintrag.entry_id)
    await hass.async_block_till_done()
    assert eintrag.state is ConfigEntryState.NOT_LOADED
    assert EIGENE_DOMAIN not in hass.data.get("spatial_hub_providers", {})
