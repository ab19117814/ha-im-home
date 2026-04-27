"""Binary sensor — one per user, ON when detected at home."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_USERS, CONF_USER_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    users = entry.options.get(CONF_USERS, [])
    entities = [ImHomeUserSensor(hass, entry, u[CONF_USER_NAME]) for u in users]
    # Register in store so __init__ can call set_detected()
    store = hass.data[DOMAIN][entry.entry_id]
    for e in entities:
        store["entities"][e.user_name] = e
    async_add_entities(entities)


class ImHomeUserSensor(BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PRESENCE
    _attr_should_poll  = False
    _attr_icon         = "mdi:cellphone-nfc"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, user_name: str):
        self._hass     = hass
        self._entry    = entry
        self.user_name = user_name
        self._is_on    = False
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{user_name}"
        self._attr_name      = f"HA Im Home — {user_name}"

    @property
    def is_on(self) -> bool:
        return self._is_on

    def set_detected(self, value: bool) -> None:
        self._is_on = value
        self.schedule_update_ha_state()
