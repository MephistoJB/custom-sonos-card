# Sonos Apple Music Projektplan

## Ziel

Apple Music soll in Home Assistant ueber eine eigene Sonos-Card-Suche bedienbar werden, ohne Music Assistant, ohne Sonos-Favoriten und ohne iframe der Sonos Web UI.

## Architekturentscheidung

- Die Lovelace Card stellt Suche, Ergebnisliste und Bedienung dar.
- Die Suche nutzt zunaechst die oeffentliche iTunes Search API fuer Apple-Music-Track-Treffer.
- Die Wiedergabe laeuft ueber echte Sonos `media_player` Entitaeten.
- Sonos-spezifische Apple-Music-URI- und DIDL-Logik gehoert langfristig in eine kleine Home-Assistant-Custom-Integration `sonos_apple_music`.
- `entityPlatform: sonos_apple_music` ist eine Card-Funktionsplattform. Fuer die HA-Entity-Auswahl wird sie intern auf die echte Plattform `sonos` gemappt.

## Abnahmekriterien

- Die Card akzeptiert `entityPlatform: sonos_apple_music`.
- Sonos-Player werden weiterhin aus der HA-Plattform `sonos` gefunden.
- Die Search-Section listet Apple-Music-Tracks mit Titel, Kuenstler, Album und Artwork.
- Ein Play-Klick ruft bei Apple-Music-Treffern `sonos_apple_music.play_media` auf.
- Ohne installierte HA-Custom-Integration bleibt der verifizierte Roh-URI-Fallback dokumentiert.
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
- Sonos akzeptiert fuer diesen Pfad nur minimales `object.item` DIDL zuverlaessig.
- Angereichertes MusicTrack-DIDL mit Apple-Service-Descriptor wurde live mit UPnP 800 abgelehnt.
- Sichtbare Sonos-Metadaten sind daher noch nicht geloest und brauchen weitere SMAPI-/Token-Forschung.

## Testmatrix

- Card: `npm run lint -- --fix`
- Card: `npx tsc --noEmit`
- Card: `npm run test`
- Card: `npm run build`
- HA-Integration: `python3 -m py_compile custom_components/sonos_apple_music/__init__.py`
- Live: iTunes Search API liefert Track-IDs.
- Live: Sonos `Gaestebad` spielt eine Apple-Music-Track-URI und wird danach gestoppt.

## Naechste Stufen

- Custom Integration in die echte HA-Konfiguration deployen und HA neu starten.
- Card-Ressource testweise gegen das gebaute Fork-Bundle austauschen.
- Dashboard-Card mit `entityPlatform: sonos_apple_music`, `search.appleMusicAccountSn: "5"` und `search.appleMusicCountry: DE` anlegen.
- Optional: SMAPI/AppLink-Tokenzugang erforschen, um vollwertiges Browse, Album-Tracks und bessere Metadaten zu erreichen.
