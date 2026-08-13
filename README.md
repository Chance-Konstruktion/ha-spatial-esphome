# Spatial Hub: ESPHome

Zeichnet ESPHome-**Platinen** auf den Grundriss: einen Punkt pro Board,
nicht pro Entität. Der Punkt sitzt in dem Bereich, den Home Assistant dem
Gerät ohnehin schon gegeben hat, und sagt, ob die Platine erreichbar ist.

Diese Integration rendert nichts selbst. Sie meldet ihre Daten bei
[Spatial Hub](https://github.com/Chance-Konstruktion/ha-spatial-hub) an —
der Hub entscheidet, wo gezeichnet wird. Ohne installierten Hub tut sie
nichts, kostet aber auch nichts.

## Warum eine eigene Integration

Die generische Ebene des Hubs kann jede ESPHome-Entität auf den Plan
setzen, und für Licht und Schalter ist das die richtige Antwort. Aber ein
ESPHome-Board ist ein **Ding**: es hängt an einer Wand, es ist erreichbar
oder nicht, und seine acht Sensoren sind es alle gemeinsam. Acht Punkte
für eine Box sind achtmal die Unruhe und kein bisschen mehr Information.

Deshalb ein eigenes Paket statt eines Sonderfalls im Hub. Der Hub kennt
keine Integration beim Namen — der Moment, in dem er zwei kennt, ist der
Moment, in dem er ein Katalog ist statt einer Plattform.

## Installation

### Über HACS

1. HACS → **Integrationen** → Menü oben rechts → **Benutzerdefinierte
   Repositories**.
2. `https://github.com/Chance-Konstruktion/ha-spatial-esphome` als
   Kategorie **Integration** hinzufügen.
3. Installieren, Home Assistant neu starten.

### Von Hand

`custom_components/spatial_esphome` nach `<config>/custom_components/`
kopieren, Home Assistant neu starten.

### Danach

**Einstellungen → Geräte & Dienste → Integration hinzufügen → „Spatial
Hub: ESPHome"**.

Es gibt nichts einzustellen. Voraussetzungen sind eine laufende
ESPHome-Integration und der Spatial Hub; ohne sie geht nichts kaputt, die
Ebene wird nur nicht sichtbar.

## Woher die Daten kommen

Ausschließlich aus den beiden **öffentlichen Registries** von Home
Assistant — Geräte und Entitäten. Kein Zugriff auf Interna der
ESPHome-Integration, keine eigene Verbindung zu den Boards, kein API-Key.

| Feld | Herkunft |
| --- | --- |
| Bereich | der Bereich, dem das Gerät in HA schon zugeordnet ist |
| Name | der eigene Gerätename, sonst der von ESPHome gemeldete |
| Zustand | siehe unten |
| Metadaten | `modell`, `firmware`, `entitaeten` (wie viel an dieser Box hängt) |
| Verlinkung | eine Entität des Boards, damit der Popup eine Tür nach HA hat |

Aktualisiert wird alle **30 Sekunden**. Es gibt kein Signal, auf das sich
hier lauschen ließe: was sich ändert, ist die Erreichbarkeit, und die
ändert sich über Entitätszustände.

### Erreichbar oder nicht

| Lage | Zustand |
| --- | --- |
| irgendeine Entität des Boards antwortet | `online` |
| alle still, Board hat **Deep Sleep** | `asleep` |
| alle still, Board hängt am Strom | `offline` |
| das Board hat gar keine Entitäten | `unknown` |

„Irgendeine" statt „alle" mit Absicht: ein Board darf einen Sensor haben,
der seit dem Start nichts gemeldet hat, während die Platine tadellos
erreichbar ist. „Alle" würde funktionierende Boards rot färben.

Gezählt werden dabei nur die Entitäten, die **ESPHome selbst** meldet. Ein
Gerät gehört keiner Integration allein: der Router hängt einen
`device_tracker` an dieselbe MAC, und der sagt noch `not_home`, wenn das
Board längst tot ist — der Router erinnert sich an die Adresse, die
Platine ist weg. Mitzuzählen hieße, ein totes Board grün zu malen, weil
jemand anders noch eine Meinung dazu hat.

### Deep Sleep

Ein Board mit `deep_sleep` wacht auf, meldet und ist wieder weg.
Unerreichbar zu sein ist seine Aufgabe, nicht sein Fehler — deshalb
bekommt es `asleep` statt `offline`, einen eigenen Zustand und kein
weicheres Rot. So kann der Grundriss „hier ist nichts kaputt" sagen, ohne
zu behaupten, das Board sei wach.

Wo das herkommt: Home Assistant hat keinen Platz dafür. Die
Geräte-Registry kennt die Box, nicht ihr Verhalten. Der einzige Ort ist
ESPHomes eigene Laufzeitdaten — fremde Interna, kein zugesichertes
Interface. Jeder Schritt dorthin ist defensiv, und ein Board, dessen
Antwort sich nicht lesen lässt, gilt als eins, das nie schläft: eine
falsche Farbe an einem Board ist besser als eine verschwundene Ebene nach
dem nächsten HA-Update.

### Was der Adapter nicht kann

- **Entitäten in anderen Bereichen als ihr Board.** Home Assistant
  erlaubt es, eine einzelne Entität einem anderen Bereich zuzuordnen als
  dem Gerät. Ein Punkt pro Platine kann nur an einer Stelle stehen, und
  das ist der Bereich des *Geräts*. Wer einen Bewegungsmelder bewusst in
  einen anderen Raum gelegt hat, sieht ihn hier nicht dort — dafür ist die
  generische Ebene des Hubs da, die jede Entität einzeln setzt.

### Die Verlinkung

Jeder Knoten trägt eine Entität des Boards. Ohne sie hat der Popup des
Hubs nichts zu verlinken und wirkt wie eine leere Karte — kein
Info-Dialog, keine Geräteseite, keine Einstellungen. Welche Entität es
ist, ist fast egal (alle öffnen denselben Dialog), nur Diagnose-Entitäten
kommen zuletzt: „Firmware" ist eine schlechte Antwort auf „zeig mir dieses
Board".

## Was **nicht** gezeichnet wird

**Keine Kanten.** ESPHome-Boards sprechen über das Netzwerk mit Home
Assistant, und nichts hier misst diesen Weg. Eine Linie zu einem Router,
den es vielleicht gar nicht gibt, wäre eine Erfindung.

Wo ein Board wirklich über etwas anderes erreicht wird — einen
Bluetooth-Proxy etwa — steht das als `via_device` in der Registry, und die
generische Ebene des Hubs zeichnet das ohne Zutun dieser Integration.

## Aufbau

```
custom_components/spatial_esphome/
├── __init__.py               Setup und Unload des Config-Entries
├── config_flow.py            Ein-Klick-Flow, nur eine Instanz
├── const.py                  DOMAIN
├── spatial.py                die eigentliche Arbeit: ein Knoten pro Board
├── spatial_hub_provider.py   Kopie des Hub-Shims (nicht bearbeiten)
├── manifest.json
└── strings.json
```

`spatial_hub_provider.py` wird bewusst **kopiert und nicht importiert**:
So hat diese Integration keinerlei Import vom Hub, funktioniert also auch
dann, wenn der Hub fehlt, eine andere Version hat oder im laufenden
Betrieb entfernt wird. Änderungen daran gehören stromaufwärts, nicht
hierher.

## Tests

```
python -m pytest
```

Braucht kein installiertes Home Assistant — `tests/conftest.py` stellt die
vier Ecken bereit, die der Adapter anfasst. `tests/test_spatial.py` prüft
die Entscheidungen, `tests/test_spatial_conformance.py` fährt das
Conformance-Kit des Hubs unverändert dagegen.

## Stand

**Ungetestet an echter Hardware.** Gegen die dokumentierten Strukturen
gebaut und mit Fakes geprüft — ob ein echtes Board sich so verhält, wie
der Adapter es annimmt, weiß nur ein echtes Board.

## Lizenz

MIT — siehe [LICENSE](LICENSE).
