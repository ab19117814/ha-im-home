"""HA Im Home — webhook from Mac daemon → binary_sensor / event."""
from __future__ import annotations

import logging

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from aiohttp import web

from .const import (
    CONF_UNLOCK_COOLDOWN,
    CONF_USERS,
    DEFAULT_UNLOCK_COOLDOWN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["binary_sensor"]

# Fixed URLs — Mac config only needs ha_url, nothing else changes
_ARRIVED_URL  = "/api/ha_im_home/arrived"
_CONFIG_URL   = "/api/ha_im_home/config"
_REGISTER_URL = "/api/ha_im_home/register"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register HTTP views once at startup — views cannot be re-registered on reload."""
    hass.http.register_view(ImHomeConfigView(hass))
    hass.http.register_view(ImHomeUnlockView(hass))
    hass.http.register_view(ImHomeRegisterView(hass))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    options = entry.options
    unlock_cooldown = int(options.get(CONF_UNLOCK_COOLDOWN, DEFAULT_UNLOCK_COOLDOWN))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "detected_users": {},
        "last_user":      None,
        "entities":       {},
    }

    def _on_user_detected(user_name: str) -> None:
        store = hass.data[DOMAIN][entry.entry_id]
        store["last_user"] = user_name

        hass.bus.async_fire(f"{DOMAIN}_detected", {"user": user_name})

        entity = store["entities"].get(user_name)
        if entity:
            entity.set_detected(True)

        prev = store["detected_users"].get(user_name)
        if prev:
            prev()

        def _auto_off(_now=None):
            store["detected_users"].pop(user_name, None)
            ent = store["entities"].get(user_name)
            if ent:
                ent.set_detected(False)

        cancel = async_call_later(hass, unlock_cooldown, _auto_off)
        store["detected_users"][user_name] = cancel
        _LOGGER.info("HA Im Home: user '%s' detected via Mac webhook", user_name)

    # Store callback so UnlockView can call it
    hass.data[DOMAIN][entry.entry_id]["on_detected"] = _on_user_detected

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info("HA Im Home ready — arrived: %s  config: %s", _ARRIVED_URL, _CONFIG_URL)
    return True


class ImHomeUnlockView(HomeAssistantView):
    """POST /api/ha_im_home/arrived — called by Mac daemon after HMAC verification."""

    url  = _ARRIVED_URL
    name = "ha_im_home:arrived"
    requires_auth = True  # Mac sends Bearer HA token

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def post(self, request: web.Request) -> web.Response:
        user_name = None
        try:
            body = await request.json()
            user_name = body.get("user")
        except Exception:
            pass
        if not user_name:
            user_name = request.query.get("user", "unknown")

        _LOGGER.info("HA Im Home: user '%s' arrived (ip=%s)", user_name, request.remote)

        # Call on_detected for every active entry
        domain_data = self._hass.data.get(DOMAIN, {})
        for entry_data in domain_data.values():
            on_detected = entry_data.get("on_detected")
            if on_detected:
                on_detected(user_name)

        return web.Response(text="ok")


class ImHomeConfigView(HomeAssistantView):
    """GET /api/ha_im_home/config — returns users+secrets for Mac daemon."""

    url  = _CONFIG_URL
    name = "ha_im_home:config"
    requires_auth = True  # Mac sends Bearer HA token

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request) -> web.Response:
        # Find first active ha_im_home entry
        entries = self._hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return web.Response(status=404, text="no ha_im_home entry")

        entry = entries[0]
        users = [
            {"name": u["name"], "secret": u["secret"]}
            for u in entry.options.get(CONF_USERS, [])
        ]
        # Include BLE UUIDs so iOS can discover the correct Mac
        domain_data = self._hass.data.get(DOMAIN, {})
        service_uuid = None
        write_uuid   = None
        for entry_data in domain_data.values():
            service_uuid = entry_data.get("service_uuid")
            write_uuid   = entry_data.get("write_uuid")
            if service_uuid:
                break

        return web.json_response({
            "users":        users,
            "service_uuid": service_uuid,
            "write_uuid":   write_uuid,
        })


class ImHomeRegisterView(HomeAssistantView):
    """POST /api/ha_im_home/register — Mac daemon registers its BLE service UUID on startup."""

    url  = _REGISTER_URL
    name = "ha_im_home:register"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def post(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            service_uuid = body.get("service_uuid")
            write_uuid   = body.get("write_uuid")
        except Exception:
            return web.Response(status=400, text="invalid json")

        if not service_uuid:
            return web.Response(status=400, text="missing service_uuid")

        domain_data = self._hass.data.get(DOMAIN, {})
        for entry_data in domain_data.values():
            entry_data["service_uuid"] = service_uuid
            if write_uuid:
                entry_data["write_uuid"] = write_uuid

        _LOGGER.info("HA Im Home: Mac registered service_uuid=%s write_uuid=%s", service_uuid, write_uuid)
        return web.Response(text="ok")


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload on options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
