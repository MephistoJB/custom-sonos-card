"""Apple Music search and playback helpers for Sonos."""

from __future__ import annotations

import html
import logging
import re
from typing import Any
from urllib.parse import quote
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from aiohttp import ClientResponse, web
import voluptuous as vol

from homeassistant.components.http import HomeAssistantView
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

DOMAIN = "sonos_apple_music"

SERVICE_AUTH_BEGIN = "auth_begin"
SERVICE_SEARCH = "search"
SERVICE_BUILD_DIDL = "build_didl"
SERVICE_PLAY_MEDIA = "play_media"

APPLE_MUSIC_SERVICE_ID = "204"
APPLE_MUSIC_SERVICE_TYPE = "52231"
APPLE_MUSIC_FLAGS = "8224"
APPLE_MUSIC_LIBRARY_FLAGS = "8232"
DEFAULT_COUNTRY = "DE"
DEFAULT_ACCOUNT_SN = "5"

CONF_ACCOUNT_SN = "account_sn"
CONF_BASE_URL = "base_url"

SOURCE_CATALOG = "catalog"
SOURCE_LIBRARY = "library"
SOURCE_ALL = "all"
TOKEN_STORAGE_VERSION = 1
TOKEN_STORAGE_KEY = f"{DOMAIN}.smapi_tokens"

SMAPI_NAMESPACE = "http://www.sonos.com/Services/1.1"
SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"

_LOGGER = logging.getLogger(__name__)
_TRACK_ID_RE = re.compile(r"(song|librarytrack)%3a([^?]+?)\.mp4", re.IGNORECASE)


CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(DOMAIN, default={}): vol.Any(
            None,
            vol.Schema(
                {
                    vol.Optional(CONF_ACCOUNT_SN, default=DEFAULT_ACCOUNT_SN): cv.string,
                    vol.Optional(CONF_BASE_URL): cv.url,
                }
            ),
        )
    },
    extra=vol.ALLOW_EXTRA,
)


AUTH_BEGIN_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional(CONF_BASE_URL): cv.url,
    }
)

SEARCH_SCHEMA = vol.Schema(
    {
        vol.Required("query"): cv.string,
        vol.Optional("country", default=DEFAULT_COUNTRY): cv.string,
        vol.Optional("source", default=SOURCE_CATALOG): vol.In([SOURCE_CATALOG, SOURCE_LIBRARY, SOURCE_ALL]),
        vol.Optional("limit", default=20): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
        vol.Optional("account_sn", default=DEFAULT_ACCOUNT_SN): cv.string,
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
        vol.Optional("source", default=SOURCE_CATALOG): vol.In([SOURCE_CATALOG, SOURCE_LIBRARY]),
    }
)

PLAY_MEDIA_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Optional("track_id"): cv.string,
        vol.Optional("media_content_id"): cv.string,
        vol.Optional("didl", default=""): cv.string,
        vol.Optional("title", default=""): cv.string,
        vol.Optional("artist", default=""): cv.string,
        vol.Optional("album", default=""): cv.string,
        vol.Optional("thumbnail", default=""): cv.string,
        vol.Optional("enqueue", default="replace"): vol.In(["replace", "play", "add", "next"]),
        vol.Optional("account_sn", default=DEFAULT_ACCOUNT_SN): cv.string,
        vol.Optional("source", default=SOURCE_CATALOG): vol.In([SOURCE_CATALOG, SOURCE_LIBRARY]),
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up service-only Sonos Apple Music helpers."""
    domain_config = config.get(DOMAIN) or {}
    default_account_sn = domain_config.get(CONF_ACCOUNT_SN, DEFAULT_ACCOUNT_SN)
    default_base_url = domain_config.get(CONF_BASE_URL)
    token_store: Store[dict[str, Any]] = Store(hass, TOKEN_STORAGE_VERSION, TOKEN_STORAGE_KEY)

    async def async_auth_begin(call: ServiceCall) -> dict[str, Any]:
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        speaker = await hass.async_add_executor_job(_get_speaker_for_call, hass, entity_ids)
        descriptor = await _async_get_apple_music_descriptor(hass, speaker["ip"])
        household_id = await _async_sonos_upnp_string(
            hass,
            speaker["ip"],
            "/DeviceProperties/Control",
            "urn:schemas-upnp-org:service:DeviceProperties:1",
            "GetHouseholdID",
            {},
            "CurrentHouseholdID",
        )
        device_id = await _async_sonos_upnp_string(
            hass,
            speaker["ip"],
            "/SystemProperties/Control",
            "urn:schemas-upnp-org:service:SystemProperties:1",
            "GetString",
            {"VariableName": "R_TrialZPSerial"},
            "StringValue",
        )
        base_url = (call.data.get(CONF_BASE_URL) or default_base_url or _default_base_url(hass)).rstrip("/")
        callback_url = (
            f"{base_url}/api/sonos_apple_music/smapi_auth_callback"
            f"?service_id={quote(descriptor['id'])}&household_id={quote(household_id)}&device_id={quote(device_id)}"
        )
        result = await _async_smapi_get_app_link(hass, descriptor, household_id, callback_url)
        return {
            "app_url": result["app_url"],
            "callback_url": callback_url,
            "household_id": household_id,
            "service_id": descriptor["id"],
        }

    async def async_search(call: ServiceCall) -> dict[str, Any]:
        items = await _async_search(
            hass=hass,
            query=call.data["query"],
            country=call.data["country"],
            limit=call.data["limit"],
            account_sn=call.data.get("account_sn") or default_account_sn,
            source=call.data["source"],
            token_store=token_store,
        )
        return {"items": items}

    async def async_build_didl(call: ServiceCall) -> dict[str, Any]:
        media_content_id = _build_sonos_track_uri(call.data["track_id"], call.data["account_sn"], call.data["source"])
        didl = _build_didl(call.data["track_id"], media_content_id, call.data["title"], call.data["artist"], call.data["album"], call.data["thumbnail"])
        return {"media_content_id": media_content_id, "didl": didl}

    async def async_play_media(call: ServiceCall) -> None:
        entity_ids = call.data.get(ATTR_ENTITY_ID)
        if not entity_ids:
            raise HomeAssistantError("Target a Sonos media_player entity")

        track_id = call.data.get("track_id")
        media_content_id = call.data.get("media_content_id")
        if bool(track_id) == bool(media_content_id):
            raise HomeAssistantError("Set exactly one of track_id or media_content_id")

        didl = call.data.get("didl") or ""
        if media_content_id:
            extracted_track_id = _track_id_from_media_content_id(media_content_id)
            if not extracted_track_id and not didl:
                raise HomeAssistantError("SMAPI media_content_id needs DIDL metadata")
            track_id = extracted_track_id or media_content_id
        else:
            media_content_id = _build_sonos_track_uri(track_id, call.data["account_sn"], call.data["source"])

        if not didl:
            didl = _build_didl(track_id, media_content_id, call.data["title"], call.data["artist"], call.data["album"], call.data["thumbnail"])

        for entity_id in entity_ids:
            await hass.async_add_executor_job(_play_on_sonos, hass, entity_id, media_content_id, didl, call.data["enqueue"])

    hass.services.async_register(DOMAIN, SERVICE_AUTH_BEGIN, async_auth_begin, schema=AUTH_BEGIN_SCHEMA, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, SERVICE_SEARCH, async_search, schema=SEARCH_SCHEMA, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, SERVICE_BUILD_DIDL, async_build_didl, schema=BUILD_DIDL_SCHEMA, supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, SERVICE_PLAY_MEDIA, async_play_media, schema=PLAY_MEDIA_SCHEMA)
    hass.http.register_view(SonosAppleMusicSearchView(hass, default_account_sn, token_store))
    hass.http.register_view(SonosAppleMusicAuthCallbackView(hass, token_store))
    return True


class SonosAppleMusicSearchView(HomeAssistantView):
    """Authenticated API for the custom card Apple Music search."""

    url = "/api/sonos_apple_music/search"
    name = "api:sonos_apple_music:search"
    requires_auth = True

    def __init__(self, hass: HomeAssistant, default_account_sn: str, token_store: Store[dict[str, Any]]) -> None:
        self.hass = hass
        self.default_account_sn = default_account_sn
        self.token_store = token_store

    async def get(self, request: web.Request) -> web.Response:
        query = request.query.get("query", "").strip()
        if not query:
            return self.json({"items": []})

        source = request.query.get("source", SOURCE_CATALOG)
        if source not in {SOURCE_CATALOG, SOURCE_LIBRARY, SOURCE_ALL}:
            return self.json_message("Invalid source", status_code=400)

        try:
            limit = max(1, min(50, int(request.query.get("limit", "20"))))
            items = await _async_search(
                hass=self.hass,
                query=query,
                country=request.query.get("country", DEFAULT_COUNTRY),
                limit=limit,
                account_sn=request.query.get("account_sn") or self.default_account_sn,
                source=source,
                token_store=self.token_store,
            )
        except (HomeAssistantError, ValueError) as err:
            return self.json_message(str(err), status_code=400)

        return self.json({"items": items})


class SonosAppleMusicAuthCallbackView(HomeAssistantView):
    """Receive Apple Music AppLink callbacks and store SMAPI tokens."""

    url = "/api/sonos_apple_music/smapi_auth_callback"
    name = "api:sonos_apple_music:smapi_auth_callback"
    requires_auth = False

    def __init__(self, hass: HomeAssistant, token_store: Store[dict[str, Any]]) -> None:
        self.hass = hass
        self.token_store = token_store

    async def get(self, request: web.Request) -> web.Response:
        if request.query.get("errorCode"):
            return web.Response(text="Apple Music authorization failed.", content_type="text/plain", status=400)

        code = (request.query.get("code") or request.query.get("responseCode") or request.query.get("linkCode") or "").strip()
        service_id = request.query.get("service_id", APPLE_MUSIC_SERVICE_ID).strip()
        household_id = request.query.get("household_id", "").strip()
        device_id = request.query.get("device_id", "").strip()
        if not code or not household_id:
            return web.Response(text="Apple Music authorization callback is missing code or household.", content_type="text/plain", status=400)

        descriptor = _apple_music_descriptor()
        descriptor["id"] = service_id
        try:
            pair = await _async_smapi_get_device_auth_token(self.hass, descriptor, household_id, code, device_id)
            await _async_save_token_pair(self.token_store, service_id, household_id, pair)
        except HomeAssistantError as err:
            return web.Response(text=f"Apple Music authorization could not be completed: {err}", content_type="text/plain", status=400)

        return web.Response(text="Apple Music is connected for Sonos SMAPI. You can close this page.", content_type="text/plain")


async def _async_search(
    hass: HomeAssistant,
    query: str,
    country: str,
    limit: int,
    account_sn: str,
    source: str,
    token_store: Store[dict[str, Any]],
) -> list[dict[str, Any]]:
    if source == SOURCE_LIBRARY:
        return await _async_search_smapi(hass, query, limit, SOURCE_LIBRARY, token_store)
    if source == SOURCE_ALL:
        library_items = await _async_search_smapi(hass, query, limit, SOURCE_LIBRARY, token_store)
        catalog_items = await _async_search_smapi(hass, query, limit, SOURCE_CATALOG, token_store)
        return [*library_items, *catalog_items][:limit]

    try:
        return await _async_search_smapi(hass, query, limit, SOURCE_CATALOG, token_store)
    except HomeAssistantError:
        return await _async_search_itunes(hass, query, country, limit, account_sn)


async def _async_search_itunes(hass: HomeAssistant, query: str, country: str, limit: int, account_sn: str) -> list[dict[str, Any]]:
    session = async_get_clientsession(hass)
    params = {"term": query, "media": "music", "entity": "song", "limit": str(limit), "country": country}
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
                "source": SOURCE_CATALOG,
            }
        )
    return items


async def _async_search_smapi(
    hass: HomeAssistant,
    query: str,
    limit: int,
    source: str,
    token_store: Store[dict[str, Any]],
) -> list[dict[str, Any]]:
    speaker = await hass.async_add_executor_job(_get_speaker_for_call, hass, None)
    descriptor = await _async_get_apple_music_descriptor(hass, speaker["ip"])
    household_id = await _async_sonos_upnp_string(
        hass,
        speaker["ip"],
        "/DeviceProperties/Control",
        "urn:schemas-upnp-org:service:DeviceProperties:1",
        "GetHouseholdID",
        {},
        "CurrentHouseholdID",
    )
    token_pair = await _async_load_token_pair(token_store, descriptor["id"], household_id)
    if not token_pair:
        raise HomeAssistantError("Apple Music Sonos-SMAPI is not authenticated. Run sonos_apple_music.auth_begin and open the returned app_url.")

    category = "librarysong" if source == SOURCE_LIBRARY else "song"
    raw = await _async_smapi_call(
        hass,
        descriptor["secure_uri"],
        "search",
        {"id": category, "term": query, "index": "0", "count": str(limit)},
        _credentials_header(speaker["device_id"], household_id, token_pair),
    )
    return [_smapi_item_to_search_result(item, descriptor, source) for item in _parse_smapi_items(raw)]


async def _async_get_apple_music_descriptor(hass: HomeAssistant, speaker_ip: str) -> dict[str, str]:
    raw = await _async_sonos_upnp_call(
        hass,
        speaker_ip,
        "/MusicServices/Control",
        "urn:schemas-upnp-org:service:MusicServices:1",
        "ListAvailableServices",
        {},
    )
    list_xml = _find_text(ET.fromstring(raw), "AvailableServiceDescriptorList")
    try:
        services = ET.fromstring(list_xml)
    except ET.ParseError:
        services = ET.fromstring(html.unescape(list_xml))
    for service in services:
        if service.attrib.get("Id") == APPLE_MUSIC_SERVICE_ID or service.attrib.get("Name") == "Apple Music":
            policy = service.find("Policy")
            manifest = service.find("Manifest")
            return {
                "id": service.attrib.get("Id", APPLE_MUSIC_SERVICE_ID),
                "name": service.attrib.get("Name", "Apple Music"),
                "secure_uri": service.attrib.get("SecureUri") or service.attrib.get("Uri") or "https://sonos-music.apple.com/ws/SonosSoap",
                "service_type": service.attrib.get("ServiceType", APPLE_MUSIC_SERVICE_TYPE),
                "auth": policy.attrib.get("Auth", "AppLink") if policy is not None else "AppLink",
                "manifest_uri": manifest.attrib.get("Uri", "") if manifest is not None else "",
            }
    raise HomeAssistantError("Apple Music service was not found in Sonos")


async def _async_smapi_get_app_link(hass: HomeAssistant, descriptor: dict[str, str], household_id: str, callback_url: str) -> dict[str, str]:
    raw = await _async_smapi_call(
        hass,
        descriptor["secure_uri"],
        "getAppLink",
        {
            "callbackPath": callback_url,
            "hardware": "iPhone15,2",
            "householdId": household_id,
            "osVersion": "Version 17.5",
            "sonosAppName": "ICRU_iPhone15,2",
        },
        _credentials_header("", household_id, None),
    )
    root = ET.fromstring(raw)
    app_url = _find_text(root, "appUrl")
    if not app_url:
        raise HomeAssistantError("Apple Music did not return an AppLink URL")
    return {"app_url": app_url}


async def _async_smapi_get_device_auth_token(
    hass: HomeAssistant,
    descriptor: dict[str, str],
    household_id: str,
    code: str,
    device_id: str,
) -> dict[str, str]:
    raw = await _async_smapi_call(
        hass,
        descriptor["secure_uri"],
        "getDeviceAuthToken",
        {"householdId": household_id, "linkCode": code, "linkDeviceId": device_id},
        _credentials_header(device_id, household_id, None),
    )
    root = ET.fromstring(raw)
    auth_token = _find_text(root, "authToken")
    if not auth_token:
        raise HomeAssistantError("Apple Music did not return an SMAPI auth token")
    return {"auth_token": auth_token, "private_key": _find_text(root, "privateKey")}


async def _async_sonos_upnp_string(
    hass: HomeAssistant,
    speaker_ip: str,
    path: str,
    urn: str,
    action: str,
    args: dict[str, str],
    result_tag: str,
) -> str:
    raw = await _async_sonos_upnp_call(hass, speaker_ip, path, urn, action, args)
    value = _find_text(ET.fromstring(raw), result_tag)
    if not value:
        raise HomeAssistantError(f"Sonos did not return {result_tag}")
    return value


async def _async_sonos_upnp_call(hass: HomeAssistant, speaker_ip: str, path: str, urn: str, action: str, args: dict[str, str]) -> str:
    body = _soap_body(action, urn, args, prefixed=True)
    session = async_get_clientsession(hass)
    async with session.post(
        f"http://{speaker_ip}:1400{path}",
        data=body,
        headers={"Content-Type": 'text/xml; charset="utf-8"', "SOAPACTION": f'"{urn}#{action}"'},
        timeout=10,
    ) as response:
        return await _response_text_or_error(response)


async def _async_smapi_call(hass: HomeAssistant, endpoint: str, method: str, args: dict[str, str], credentials: str) -> str:
    body = _smapi_body(method, args, credentials)
    session = async_get_clientsession(hass)
    async with session.post(
        endpoint,
        data=body,
        headers={"Content-Type": 'text/xml; charset="utf-8"', "SOAPACTION": f'"{SMAPI_NAMESPACE}#{method}"'},
        timeout=15,
    ) as response:
        return await _response_text_or_error(response)


async def _response_text_or_error(response: ClientResponse) -> str:
    raw = await response.text()
    if 200 <= response.status < 300:
        return raw
    fault = _parse_fault(raw)
    raise HomeAssistantError(fault or f"SOAP request failed with HTTP {response.status}")


def _soap_body(method: str, namespace: str, args: dict[str, str], prefixed: bool = False) -> str:
    tag = f"u:{method}" if prefixed else method
    parts = [
        '<?xml version="1.0"?>',
        f'<s:Envelope xmlns:s="{SOAP_ENV}" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">',
        "<s:Body>",
        f'<{tag} xmlns:u="{namespace}">' if prefixed else f'<{tag} xmlns="{namespace}">',
    ]
    for key, value in sorted(args.items()):
        parts.append(f"<{key}>{escape(value)}</{key}>")
    parts.extend([f"</{tag}>", "</s:Body></s:Envelope>"])
    return "".join(parts)


def _smapi_body(method: str, args: dict[str, str], credentials: str) -> str:
    body = _soap_body(method, SMAPI_NAMESPACE, args)
    return body.replace("<s:Body>", f"<s:Header>{credentials}</s:Header><s:Body>", 1)


def _credentials_header(device_id: str, household_id: str, token_pair: dict[str, str] | None) -> str:
    parts = [f'<credentials xmlns="{SMAPI_NAMESPACE}">']
    if device_id:
        parts.append(f"<deviceId>{escape(device_id)}</deviceId>")
    parts.append("<deviceProvider>Sonos</deviceProvider><context></context>")
    if token_pair:
        parts.append("<loginToken>")
        parts.append(f"<token>{escape(token_pair['auth_token'])}</token>")
        if token_pair.get("private_key"):
            parts.append(f"<key>{escape(token_pair['private_key'])}</key>")
        parts.append(f"<householdId>{escape(household_id)}</householdId>")
        parts.append("</loginToken>")
    parts.append("</credentials>")
    return "".join(parts)


def _parse_smapi_items(raw: str) -> list[dict[str, str]]:
    root = ET.fromstring(raw)
    items = []
    for metadata in _iter_local(root, "mediaMetadata"):
        track = _first_local(metadata, "trackMetadata")
        items.append(
            {
                "id": _find_text(metadata, "id"),
                "item_type": _find_text(metadata, "itemType") or "track",
                "title": _find_text(metadata, "title"),
                "mime_type": _find_text(metadata, "mimeType"),
                "summary": _find_text(metadata, "summary"),
                "artist": _find_text(track, "artist") if track is not None else "",
                "album": _find_text(track, "album") if track is not None else "",
                "thumbnail": _find_text(track, "albumArtURI") if track is not None else "",
            }
        )
    return [item for item in items if item["id"] and item["title"]]


def _smapi_item_to_search_result(item: dict[str, str], descriptor: dict[str, str], source: str) -> dict[str, str]:
    media_content_id = _smapi_enqueued_uri(item["id"], item["item_type"], descriptor["id"])
    return {
        "title": item["title"],
        "artist": item["artist"],
        "album": item["album"],
        "track_id": item["id"],
        "media_content_id": media_content_id,
        "media_content_type": "track",
        "thumbnail": item["thumbnail"],
        "provider": "apple_music",
        "source": source,
        "didl": _build_smapi_didl(item["id"], media_content_id, descriptor),
    }


def _smapi_enqueued_uri(item_id: str, item_type: str, service_id: str) -> str:
    didl_id = _smapi_didl_id(item_id)
    if item_type.lower() in {"album", "artist", "container", "playlist"}:
        return f"x-rincon-cpcontainer:{didl_id}"
    return f"soco://{_quote_smapi(didl_id)}?sid={quote(service_id)}&sn=0"


def _smapi_didl_id(item_id: str) -> str:
    return "0fffffff" + _quote_smapi(item_id)


def _quote_smapi(value: str) -> str:
    return quote(value, safe="").replace("+", "%20")


def _build_smapi_didl(item_id: str, media_content_id: str, descriptor: dict[str, str]) -> str:
    didl_id = _smapi_didl_id(item_id)
    service_desc = f"SA_RINCON{descriptor.get('service_type') or APPLE_MUSIC_SERVICE_TYPE}_"
    return (
        '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
        'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
        'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        f'<item id="{escape(didl_id)}" parentID="DUMMY" restricted="true">'
        "<dc:title>DUMMY</dc:title>"
        f'<res protocolInfo="DUMMY">{escape(media_content_id)}</res>'
        "<upnp:class>object.item</upnp:class>"
        f'<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">{escape(service_desc)}</desc>'
        "</item></DIDL-Lite>"
    )


async def _async_load_token_pair(token_store: Store[dict[str, Any]], service_id: str, household_id: str) -> dict[str, str] | None:
    data = await token_store.async_load() or {}
    pair = data.get("tokens", {}).get(_token_key(service_id, household_id))
    return pair if isinstance(pair, dict) else None


async def _async_save_token_pair(token_store: Store[dict[str, Any]], service_id: str, household_id: str, pair: dict[str, str]) -> None:
    data = await token_store.async_load() or {}
    tokens = data.setdefault("tokens", {})
    tokens[_token_key(service_id, household_id)] = pair
    await token_store.async_save(data)


def _token_key(service_id: str, household_id: str) -> str:
    return f"{service_id.strip()}#{household_id.strip()}"


def _play_on_sonos(hass: HomeAssistant, entity_id: str, media_content_id: str, didl: str, enqueue: str) -> None:
    from soco import discover

    speaker = _find_speaker(hass, entity_id, discover(timeout=5) or set())
    if speaker is None:
        raise HomeAssistantError(f"Could not find Sonos speaker for {entity_id}")

    if enqueue in {"replace", "play"}:
        speaker.avTransport.SetAVTransportURI([("InstanceID", 0), ("CurrentURI", media_content_id), ("CurrentURIMetaData", didl)])
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


def _get_speaker_for_call(hass: HomeAssistant, entity_ids: str | list[str] | None) -> dict[str, str]:
    from soco import discover

    speakers = discover(timeout=5) or set()
    speaker = None
    if entity_ids:
        target_entity_id = entity_ids if isinstance(entity_ids, str) else entity_ids[0]
        speaker = _find_speaker(hass, target_entity_id, speakers)
    if speaker is None and speakers:
        speaker = next(iter(speakers))
    if speaker is None:
        raise HomeAssistantError("Could not discover a Sonos speaker")
    return {"ip": speaker.ip_address, "device_id": getattr(speaker, "uid", "")}


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


def _apple_music_descriptor() -> dict[str, str]:
    return {
        "id": APPLE_MUSIC_SERVICE_ID,
        "name": "Apple Music",
        "secure_uri": "https://sonos-music.apple.com/ws/SonosSoap",
        "service_type": APPLE_MUSIC_SERVICE_TYPE,
        "auth": "AppLink",
    }


def _default_base_url(hass: HomeAssistant) -> str:
    return str(hass.config.internal_url or hass.config.external_url or "http://homeassistant.local:8123")


def _find_text(root: ET.Element | None, local_name: str) -> str:
    if root is None:
        return ""
    node = _first_local(root, local_name)
    return (node.text or "").strip() if node is not None else ""


def _first_local(root: ET.Element, local_name: str) -> ET.Element | None:
    for node in root.iter():
        if _local_name(node.tag) == local_name:
            return node
    return None


def _iter_local(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [node for node in root.iter() if _local_name(node.tag) == local_name]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_fault(raw: str) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""
    code = _find_text(root, "faultcode")
    message = _find_text(root, "faultstring")
    return ": ".join(part for part in (code, message) if part)


def _build_sonos_track_uri(track_id: str, account_sn: str, source: str = SOURCE_CATALOG) -> str:
    if source == SOURCE_LIBRARY:
        return f"x-sonos-http:librarytrack%3a{track_id}.mp4?sid={APPLE_MUSIC_SERVICE_ID}&flags={APPLE_MUSIC_LIBRARY_FLAGS}&sn={account_sn}"
    return f"x-sonos-http:song%3a{track_id}.mp4?sid={APPLE_MUSIC_SERVICE_ID}&flags={APPLE_MUSIC_FLAGS}&sn={account_sn}"


def _track_id_from_media_content_id(media_content_id: str) -> str:
    match = _TRACK_ID_RE.search(media_content_id)
    return match.group(2) if match else ""


def _build_didl(track_id: str, media_content_id: str, title: str, artist: str, album: str, thumbnail: str) -> str:
    if media_content_id.startswith("soco://") or media_content_id.startswith("x-rincon-cpcontainer:"):
        return _build_smapi_didl(track_id, media_content_id, _apple_music_descriptor())

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
        "</item></DIDL-Lite>"
    )


def _upscale_artwork(url: str) -> str:
    return re.sub(r"100x100bb\.(jpg|png|webp)$", r"600x600bb.\1", url)
