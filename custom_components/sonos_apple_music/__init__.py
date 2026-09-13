"""Apple Music search and playback helpers for Sonos."""

from __future__ import annotations

import logging
import re
from typing import Any
from xml.sax.saxutils import escape

import voluptuous as vol

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

DOMAIN = "sonos_apple_music"

SERVICE_SEARCH = "search"
SERVICE_BUILD_DIDL = "build_didl"
SERVICE_PLAY_MEDIA = "play_media"

APPLE_MUSIC_SERVICE_ID = "204"
APPLE_MUSIC_FLAGS = "8224"
DEFAULT_COUNTRY = "DE"
DEFAULT_ACCOUNT_SN = "5"

_LOGGER = logging.getLogger(__name__)
_TRACK_ID_RE = re.compile(r"song%3a([^.?]+)\.mp4", re.IGNORECASE)


SEARCH_SCHEMA = vol.Schema(
    {
        vol.Required("query"): cv.string,
        vol.Optional("country", default=DEFAULT_COUNTRY): cv.string,
        vol.Optional("limit", default=20): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
    }
)

BUILD_DIDL_SCHEMA = vol.Schema(
    {
        vol.Required("track_id"): cv.string,
        vol.Optional("title", default=""): cv.string,
        vol.Optional("artist", default=""): cv.string,
        vol.Optional("album", default=""): cv.string,
        vol.Optional("thumbnail", default=""): cv.string,
        vol.Optional("account_sn", default=DEFAULT_ACCOUNT_SN): cv.string,
    }
)

PLAY_MEDIA_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional("track_id"): cv.string,
        vol.Optional("media_content_id"): cv.string,
        vol.Optional("title", default=""): cv.string,
        vol.Optional("artist", default=""): cv.string,
        vol.Optional("album", default=""): cv.string,
        vol.Optional("thumbnail", default=""): cv.string,
        vol.Optional("enqueue", default="replace"): vol.In(["replace", "play", "add", "next"]),
        vol.Optional("account_sn", default=DEFAULT_ACCOUNT_SN): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up service-only Sonos Apple Music helpers."""

    async def async_search(call: ServiceCall) -> dict[str, Any]:
        items = await _async_search_itunes(
            hass,
            call.data["query"],
            call.data["country"],
            call.data["limit"],
            DEFAULT_ACCOUNT_SN,
        )
        return {"items": items}

    async def async_build_didl(call: ServiceCall) -> dict[str, Any]:
        media_content_id = _build_sonos_track_uri(call.data["track_id"], call.data["account_sn"])
        didl = _build_didl(
            track_id=call.data["track_id"],
            media_content_id=media_content_id,
            title=call.data["title"],
            artist=call.data["artist"],
            album=call.data["album"],
            thumbnail=call.data["thumbnail"],
        )
        return {"media_content_id": media_content_id, "didl": didl}

    async def async_play_media(call: ServiceCall) -> None:
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        if not entity_ids:
            raise HomeAssistantError("Target a Sonos media_player entity")

        track_id = call.data.get("track_id")
        media_content_id = call.data.get("media_content_id")
        if bool(track_id) == bool(media_content_id):
            raise HomeAssistantError("Set exactly one of track_id or media_content_id")

        if media_content_id:
            track_id = _track_id_from_media_content_id(media_content_id)
        else:
            media_content_id = _build_sonos_track_uri(track_id, call.data["account_sn"])

        didl = _build_didl(
            track_id=track_id,
            media_content_id=media_content_id,
            title=call.data["title"],
            artist=call.data["artist"],
            album=call.data["album"],
            thumbnail=call.data["thumbnail"],
        )

        for entity_id in entity_ids:
            await hass.async_add_executor_job(
                _play_on_sonos,
                hass,
                entity_id,
                media_content_id,
                didl,
                call.data["enqueue"],
            )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH,
        async_search,
        schema=SEARCH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_BUILD_DIDL,
        async_build_didl,
        schema=BUILD_DIDL_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(DOMAIN, SERVICE_PLAY_MEDIA, async_play_media, schema=PLAY_MEDIA_SCHEMA)
    return True


async def _async_search_itunes(hass: HomeAssistant, query: str, country: str, limit: int, account_sn: str) -> list[dict[str, Any]]:
    session = async_get_clientsession(hass)
    params = {
        "term": query,
        "media": "music",
        "entity": "song",
        "limit": str(limit),
        "country": country,
    }
    async with session.get("https://itunes.apple.com/search", params=params, timeout=10) as response:
        response.raise_for_status()
        payload = await response.json(content_type=None)

    items = []
    for result in payload.get("results", []):
        if result.get("wrapperType") != "track" or result.get("kind") != "song":
            continue
        track_id = str(result.get("trackId", ""))
        title = result.get("trackName") or ""
        if not track_id or not title:
            continue
        artist = result.get("artistName") or ""
        album = result.get("collectionName") or ""
        thumbnail = _upscale_artwork(result.get("artworkUrl100") or "")
        items.append(
            {
                "title": title,
                "artist": artist,
                "album": album,
                "track_id": track_id,
                "media_content_id": _build_sonos_track_uri(track_id, account_sn),
                "media_content_type": "track",
                "thumbnail": thumbnail,
                "provider": "apple_music",
            }
        )
    return items


def _play_on_sonos(hass: HomeAssistant, entity_id: str, media_content_id: str, didl: str, enqueue: str) -> None:
    from soco import discover

    speaker = _find_speaker(hass, entity_id, discover(timeout=5) or set())
    if speaker is None:
        raise HomeAssistantError(f"Could not find Sonos speaker for {entity_id}")

    if enqueue in {"replace", "play"}:
        speaker.avTransport.SetAVTransportURI(
            [
                ("InstanceID", 0),
                ("CurrentURI", media_content_id),
                ("CurrentURIMetaData", didl),
            ]
        )
        speaker.play()
        return

    speaker.avTransport.AddURIToQueue(
        [
            ("InstanceID", 0),
            ("EnqueuedURI", media_content_id),
            ("EnqueuedURIMetaData", didl),
            ("DesiredFirstTrackNumberEnqueued", 0),
            ("EnqueueAsNext", 1 if enqueue == "next" else 0),
        ]
    )


def _find_speaker(hass: HomeAssistant, entity_id: str, speakers: set[Any]) -> Any | None:
    registry = er.async_get(hass)
    entity = registry.async_get(entity_id)
    unique_id = entity.unique_id if entity else None
    if unique_id:
        for speaker in speakers:
            if getattr(speaker, "uid", "").upper() == unique_id.upper():
                return speaker

    state = hass.states.get(entity_id)
    friendly_name = state.attributes.get("friendly_name") if state else None
    for speaker in speakers:
        if getattr(speaker, "player_name", None) == friendly_name:
            return speaker
    return None


def _build_sonos_track_uri(track_id: str, account_sn: str) -> str:
    return f"x-sonos-http:song%3a{track_id}.mp4?sid={APPLE_MUSIC_SERVICE_ID}&flags={APPLE_MUSIC_FLAGS}&sn={account_sn}"


def _track_id_from_media_content_id(media_content_id: str) -> str:
    match = _TRACK_ID_RE.search(media_content_id)
    if not match:
        raise HomeAssistantError("media_content_id is not a Sonos Apple Music track URI")
    return match.group(1)


def _build_didl(track_id: str, media_content_id: str, title: str, artist: str, album: str, thumbnail: str) -> str:
    escaped_uri = escape(media_content_id)

    return (
        '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
        'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
        'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        '<item id="-1" parentID="-1" restricted="true">'
        '<res protocolInfo="sonos.com-http:*:application/octet-stream:*">'
        f"{escaped_uri}"
        "</res>"
        "<r:streamContent></r:streamContent>"
        "<upnp:class>object.item</upnp:class>"
        "</item>"
        "</DIDL-Lite>"
    )


def _upscale_artwork(url: str) -> str:
    return re.sub(r"100x100bb\.(jpg|png|webp)$", r"600x600bb.\1", url)
