# Changelog

## 261108 — Nachgetragen: die Änderungen seit 260808

Der Changelog war stehen geblieben, während weiter gemergt wurde. Hier die
gemergten Änderungen im Nachhinein — ohne Anhebung der Versionsnummer, das
Manifest bleibt auf `260808`:

- **Verweise** (!1): die README-Verweise von GitHub auf GitLab gezogen;
  das Manifest zog noch nicht nach.
- **CI-Einbindung** (!2): die gemeinsame CI-Vorlage wird eingebunden statt
  in jedes Repository kopiert.
- **Anzeigename** (!3): das Manifest nennt die Integration
  `spatial-hub: esphome`; die Anleitung zitiert denselben Namen.
- **SDK v7** (!4): Anbieter-Shim und Konformitätssatz vom Hub übernommen,
  die Anker kamen mit.
- **README-Knöpfe** (!5): HACS- und Einrichtungs-Badges, die über die
  eigene Home-Assistant-Instanz umleiten.
- **Übernahme** (!6): veralteter Config-Entry-Zugriff auf den aktuellen
  Lesepfad gestellt; Entitäten, die jemand anders stillgelegt hat, färben
  ihr Board nicht mehr.
- **Perf-Index** (!7): die Entitäten-Registry wird pro Aktualisierung
  einmal gelesen statt pro Board; der dadurch unbelegte Helfer
  `_entities_of` fiel später ersatzlos weg.
- **Registry-/Lebenszyklus-Tests** (!9): eine Suite gegen ein echtes Home
  Assistant (`tests_ha/`), Verkettung von Untergeräten über
  `async_update_device` mit der Registry-ID (!8 ging in ihr auf).

## 260808 — Boards werden wieder gefunden

**Fehler:** Die Ebene blieb leer, auch in Häusern mit mehreren
ESPHome-Boards.

**Ursache:** Der Filter suchte Boards über `identifiers` mit der Domain
`esphome`. Die ESPHome-Integration setzt für ein Board aber überhaupt keine
Identifiers — sie registriert es über
`connections={{(CONNECTION_NETWORK_MAC, mac)}}`. Der Filter konnte also nie
etwas finden. Nur Sub-Devices tragen einen Identifier, und die sind selten.

Dazu ein zweiter, latenter Fehler in derselben Zeile: `for domain, _ in
identifiers` wirft `ValueError`, sobald irgendein **fremdes** Gerät im
Register ein Identifier-Tupel mit drei Elementen führt — derselbe Fehler, der
in `ha-spatial-zwave` in `_is_zwave()` bereits behoben und dokumentiert war.

**Behoben:** Boards kommen jetzt über die Config-Entries der Domain
`esphome` — das ist für jedes ESPHome-Gerät wahr, für Boards wie für
Sub-Devices. Sub-Devices werden in ihr Board eingefaltet, ihre Entitäten
zählen zum Board.

**Geprüft:** Gegen eine Registry-Nachbildung mit einem Board ohne
Identifiers (nur MAC-Connection), einem Sub-Device und einem fremden Gerät
mit Drei-Tupel-Identifier. Vorher: 0 Knoten bzw. `ValueError`. Nachher:
1 Knoten, `entitaeten: 3`, `untergeraete: 1`. Eine Entität derselben MAC von
einer anderen Integration zählt weiterhin nicht mit. Gegen eine laufende
Home-Assistant-Instanz ist diese Fassung **noch nicht** verifiziert.

## 260729 — Erste Fassung
