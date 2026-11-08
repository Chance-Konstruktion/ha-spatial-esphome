"""Die Angaben, die HACS, Home Assistant und die Anleitung abgeben.

Die übrige Suite prüft Verhalten; diese prüft Versprechen -- die
Stellen, an denen die Durchsicht (Ticket #3) Lücken fand: Metadaten,
die etwas fordern, das es nicht gibt, Namen, die es so nicht gibt,
und Verweise, die einander widersprechen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

WURZEL = Path(__file__).resolve().parents[1]


def _lies(name: str):
    return (WURZEL / name).read_text(encoding="utf-8")


def _json(name: str):
    return json.loads(_lies(name))


def test_hacs_verspricht_kein_release_archiv():
    """``zip_release`` verlangt ein Release-Artefakt genau dieses Namens.

    Es gibt hier weder Tags noch Releases -- der beworbene HACS-Weg
    scheiterte also an einem Versprechen, das nie eingelöst wurde. Ohne
    ``zip_release`` installiert HACS die Integration direkt aus dem
    Repository (``custom_components/`` im Standardlayout), der Weg
    funktioniert dann tatsächlich.
    """
    hacs = _json("hacs.json")

    assert "zip_release" not in hacs, (
        "ohne Releases bleibt das versprochene Archiv aus"
    )
    assert "filename" not in hacs, (
        "ohne zip_release hat filename keinen Gegenstand"
    )


def test_die_anleitung_zitiert_den_namen_aus_dem_manifest():
    """Der Einrichtungsdialog zeigt den Namen aus manifest.json.

    Die Anleitung zitierte eine Zeichenkette, die es dort nicht gibt --
    wer ihr folgt, findet die Integration im Dialog nicht wieder.
    """
    name = _json("custom_components/spatial_esphome/manifest.json")["name"]

    zitat = re.search(
        r"Integration hinzufügen →\s*„([^“\"]+)[“\"]", _lies("README.md")
    )
    assert zitat, "die Anleitung nennt den Weg zur Einrichtung nicht mehr"
    assert zitat.group(1) == name, (
        f"die Anleitung schreibt {zitat.group(1)!r}, der Dialog zeigt {name!r}"
    )


def test_manifest_verweise_wohnen_beim_kanonischen_repo():
    """documentation und issue_tracker zeigen auf das kanonische Repo.

    Kanonisch ist das GitLab-Repo -- die README verlinkt den Spatial Hub
    dort, und der Beschluss in !1 war, GitHub-Verweise durch GitLab zu
    ersetzen. Der GitHub-Spiegel existiert nur als Installationsquelle
    für HACS, das kein GitLab kennt. Vorher zeigten die beiden
    Manifest-Verweise auf den Spiegel und widersprachen der README.
    """
    manifest = _json("custom_components/spatial_esphome/manifest.json")

    hub_link = re.search(r"\[Spatial Hub\]\((https://[^)]+)\)", _lies("README.md"))
    assert hub_link, "die README verlinkt den Spatial Hub nicht mehr"
    kanonisch = urlsplit(hub_link.group(1)).hostname

    for schluessel in ("documentation", "issue_tracker"):
        host = urlsplit(manifest[schluessel]).hostname
        assert host == kanonisch, (
            f"{schluessel} zeigt auf {host}, kanonisch ist {kanonisch}"
        )


def test_die_anleitung_erklaert_jeden_metadata_eintrag():
    """Was der Knoten ins Popup legt, muss die Tabelle der Anleitung nennen.

    Die Metadaten-Zeile nannte nur ``modell``, ``firmware`` und
    ``entitaeten`` -- der Knoten trägt aber auch ``schlafmodus`` und,
    wenn das Board sich selbst aufspaltet, ``untergeraete``. Gerade
    ``schlafmodus`` erklärt dem Nutzer, warum ein Board still ist.
    """
    from conftest import (
        _DEVICES,
        _ENTITIES,
        FakeDevice,
        FakeEntry,
        FakeEntity,
        FakeEsphomeEntry,
        FakeHass,
    )

    from custom_components.spatial_esphome.spatial import async_setup_spatial

    hass = FakeHass()
    board = FakeDevice("b1", area_id=None, name="Bürosensor")
    kind = FakeDevice("b1-relais", name="Bürosensor Relais")
    kind.via_device_id = "b1"
    _DEVICES.devices = {"b1": board, "b1-relais": kind}
    _ENTITIES.entities = {"sensor.a": FakeEntity("sensor.a", device_id="b1")}
    hass.states.set("sensor.a", "21.5")
    hass.config_entries.entries = {
        "esphome-entry": FakeEsphomeEntry(has_deep_sleep=True)
    }
    async_setup_spatial(hass, FakeEntry())

    knoten = hass.registrations["spatial_esphome"]["data"]()["nodes"][0]
    metadata = knoten["metadata"]
    assert {"modell", "firmware", "schlafmodus", "entitaeten", "untergeraete"} <= set(metadata), (
        "der Aufbau muss gerade die Sonderfälle zeigen, die die Doku erklären soll"
    )

    zeile = re.search(r"^\|\s*Metadaten\s*\|(.+)\|\s*$", _lies("README.md"), re.M)
    assert zeile, "die README-Tabelle hat keine Metadaten-Zeile mehr"
    erwaehnt = set(re.findall(r"`(\w+)`", zeile.group(1)))
    fehlen = set(metadata) - erwaehnt
    assert not fehlen, f"die Metadaten-Zeile erklärt nicht: {sorted(fehlen)}"


def test_der_changelog_endet_nicht_mehr_bei_260808():
    """Der Changelog stand still, während weiter gemergt wurde.

    Der oberste Abschnitt muss jenseits von 260808 datieren -- sonst sind
    die seither gemergten Änderungen wieder nicht dokumentiert. Eine
    Versionsanhebung ist das nicht: das Manifest bleibt, wie es ist.
    """
    kopf = re.search(r"^##\s+(\d{6})\b", _lies("CHANGELOG.md"), re.M)
    assert kopf, "der Changelog hat keinen Abschnittskopf"
    assert int(kopf.group(1)) > 260808, (
        "der neueste Changelog-Abschnitt ist 260808 -- die seither "
        "gemergten Änderungen sind nicht dokumentiert"
    )
