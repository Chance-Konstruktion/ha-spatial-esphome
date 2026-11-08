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
