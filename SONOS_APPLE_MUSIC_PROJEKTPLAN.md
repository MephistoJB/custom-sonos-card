# Sonos Apple Music Projektplan

## Ziel

Apple Music soll in Home Assistant ueber eine eigene Sonos-Card-Suche bedienbar werden, ohne Music Assistant, ohne Sonos-Favoriten und ohne iframe der Sonos Web UI.

## Architekturentscheidung

- Die Lovelace Card stellt Suche, Ergebnisliste und Bedienung dar.
- Die Apple-Music-Suche laeuft primaer ueber Sonos SMAPI, also ueber denselben Apple-Music-Dienst, den Sonos selbst nutzt.
- Die persoenliche Mediathek wird ueber die Sonos-SMAPI-Kategorie `librarysong` gesucht; der Katalog ueber `song`.
- Die oeffentliche iTunes Search API bleibt nur Fallback fuer Katalogsuche, wenn Sonos-SMAPI noch nicht authentifiziert ist.
- Die Wiedergabe laeuft ueber echte Sonos `media_player` Entitaeten.
- Sonos-spezifische Apple-Music-URI-, DIDL-, AppLink- und Tokenlogik gehoert in die Home-Assistant-Custom-Integration `sonos_apple_music`.
- `entityPlatform: sonos_apple_music` ist eine Card-Funktionsplattform. Fuer die HA-Entity-Auswahl wird sie intern auf die echte Plattform `sonos` gemappt.

## Abnahmekriterien

- Die Card akzeptiert `entityPlatform: sonos_apple_music`.
- Sonos-Player werden weiterhin aus der HA-Plattform `sonos` gefunden.
- Die Search-Section listet Apple-Music-Tracks mit Titel, Kuenstler, Album und Artwork.
- Die Search-Section kann fuer Apple Music zwischen Katalog, Library und kombiniertem Modus unterscheiden.
- Ein Play-Klick ruft bei Apple-Music-Treffern `sonos_apple_music.play_media` auf.
- SMAPI-Treffer reichen DIDL-Metadaten bis zum Sonos-Playback-Service durch.
- Lint, TypeScript, Vitest und Produktionsbuild laufen gruen.
- Mindestens ein echter Sonos-Player wurde mit einem Apple-Music-Track live getestet.

## Status

- Fork: `https://github.com/MephistoJB/custom-sonos-card`
- Arbeitsbranch: `feature/apple-music-sonos-search`
- Lokaler Card-Pfad: `custom-sonos-card-apple`
- Lokaler HA-Integrationsentwurf: `custom_components/sonos_apple_music`

## Live-Erkenntnisse

- Apple Music ist in Sonos als Service `sid=204`, `serviceType=52231`, Account `sn=5` vorhanden.
- `media_player.play_media` spielt die URI `x-sonos-http:song%3a<ID>.mp4?sid=204&flags=8224&sn=5`.
- Sonos-SMAPI-Treffer brauchen die original passende DIDL-Metadatenkette; diese wird jetzt vom Backend an die Card und zurueck an `play_media` gereicht.
- Die oeffentliche iTunes Search API findet keine eigene Apple-Music-/iCloud-Mediathek. Das ist erwartetes Apple-Verhalten, kein Suchfehler.
- Apple Music akzeptiert bei `getAppLink` einen Home-Assistant-Callback; darueber kann die Integration `getDeviceAuthToken` abschliessen und das SMAPI-LoginToken lokal speichern.
- Die Apple-Presentation-Map nennt fuer Library-Tracks die Search-ID `librarysong`; damit muss die persoenliche Mediathek gefunden werden, sobald die SMAPI-Authentifizierung abgeschlossen ist.

## Testmatrix

- Card: `npm run lint -- --fix`
- Card: `npx tsc --noEmit`
- Card: `npm run test`
- Card: `npm run build`
- HA-Integration: `python3 -m py_compile custom_components/sonos_apple_music/__init__.py`
- Live: iTunes Search API liefert Track-IDs.
- Live: Sonos `Gaestebad` spielt eine Apple-Music-Track-URI und wird danach gestoppt.
- Live: HA Config-Check bleibt nach Deployment der Library-Erweiterung gueltig.
- Live: `sonos_apple_music.search` mit `source: catalog` liefert Treffer.
- Live: `sonos_apple_music.auth_begin` liefert einen Apple-Music-AppLink fuer die Sonos-SMAPI-Authentifizierung.
- Live: `sonos_apple_music.search` mit `source: library` liefert Treffer aus der persoenlichen Apple-Music-Mediathek nach erfolgreichem AppLink.

## Naechste Stufen

- Integration live deployen und Home Assistant neu starten.
- `sonos_apple_music.auth_begin` gegen einen echten Sonos-Player ausfuehren und den AppLink auf einem Apple-Music-faehigen Geraet oeffnen.
- Danach `sonos_apple_music.search` mit `source: library` gegen einen bekannten eigenen Library-Titel testen.
- Wenn Library-Suche und Playback funktionieren: Dashboard-Card dauerhaft auf `search.appleMusicSource: library` oder `all` stellen.
