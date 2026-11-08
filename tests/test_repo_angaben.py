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
