"""HA Im Home — webhook from Mac daemon → binary_sensor / event."""
from __future__ import annotations

import logging

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from aiohttp import web

from .const import (
    CONF_HA_USER_ID,
    CONF_SERVICE_UUID,
    CONF_UNLOCK_COOLDOWN,
    CONF_USERS,
    CONF_WRITE_UUID,
    DEFAULT_UNLOCK_COOLDOWN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["binary_sensor"]

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

    hass.data[DOMAIN][entry.entry_id]["on_detected"] = _on_user_detected

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _LOGGER.info("HA Im Home ready — arrived: %s  config: %s", _ARRIVED_URL, _CONFIG_URL)
    return True


class ImHomeUnlockView(HomeAssistantView):
    """POST /api/ha_im_home/arrived — called by Mac daemon after HMAC verification."""

    url  = _ARRIVED_URL
    name = "ha_im_home:arrived"
    requires_auth = True

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

        domain_data = self._hass.data.get(DOMAIN, {})
        for entry_data in domain_data.values():
            on_detected = entry_data.get("on_detected")
            if on_detected:
                on_detected(user_name)

        return web.Response(text="ok")


class ImHomeConfigView(HomeAssistantView):
    """GET /api/ha_im_home/config — returns config for the authenticated HA user."""

    url  = _CONFIG_URL
    name = "ha_im_home:config"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request) -> web.Response:
        entries = self._hass.config_entries.async_entries(DOMAIN)
        if not entries:
            return web.Response(status=404, text="no ha_im_home entry")

        entry = entries[0]
        ha_user = request.get("hass_user"); ha_user_id = ha_user.id if ha_user else None

        # Find the integration user linked to this HA user
        all_users = entry.options.get(CONF_USERS, [])
        matched = next(
            (u for u in all_users if u.get(CONF_HA_USER_ID) == ha_user_id),
            None,
        )
        if matched is None:
            # Fallback: legacy entries without ha_user_id — return first user
            matched = next((u for u in all_users if CONF_HA_USER_ID not in u), None)

        if matched is None:
            _LOGGER.warning("HA Im Home: no user linked to HA user %s", ha_user_id)
            return web.Response(status=403, text="no integration user linked to your HA account")

        # Priority: RAM → options → data
        domain_data = self._hass.data.get(DOMAIN, {})
        service_uuid = None
        write_uuid   = None
        for entry_data in domain_data.values():
            service_uuid = entry_data.get(CONF_SERVICE_UUID)
            write_uuid   = entry_data.get(CONF_WRITE_UUID)
            if service_uuid:
                break
        if not service_uuid:
            service_uuid = entry.options.get(CONF_SERVICE_UUID) or entry.data.get(CONF_SERVICE_UUID)
            write_uuid   = entry.options.get(CONF_WRITE_UUID)   or entry.data.get(CONF_WRITE_UUID)

        return web.json_response({
            "users":        [{"name": matched["name"], "secret": matched["secret"]}],
            "service_uuid": service_uuid,
            "write_uuid":   write_uuid,
        })


class ImHomeRegisterView(HomeAssistantView):
    """POST /api/ha_im_home/register — Mac daemon registers its BLE UUIDs on startup."""

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
            entry_data[CONF_SERVICE_UUID] = service_uuid
            if write_uuid:
                entry_data[CONF_WRITE_UUID] = write_uuid

        entries = self._hass.config_entries.async_entries(DOMAIN)
        if entries:
            entry = entries[0]
            self._hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_SERVICE_UUID: service_uuid, CONF_WRITE_UUID: write_uuid},
            )

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
