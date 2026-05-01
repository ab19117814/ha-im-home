"""Config Flow + Options Flow for HA Im Home."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_HA_USER_ID,
    CONF_SERVICE_UUID,
    CONF_UNLOCK_COOLDOWN,
    CONF_USER_NAME,
    CONF_USER_SECRET,
    CONF_USERS,
    CONF_WRITE_UUID,
    DEFAULT_UNLOCK_COOLDOWN,
    DOMAIN,
    MENU_ADD_USER,
    MENU_EDIT_SETTINGS,
    MENU_REMOVE_USER,
)

_LOGGER = logging.getLogger(__name__)


async def _ha_user_options(hass) -> list[selector.SelectOptionDict]:
    """Return list of non-system HA users for selector."""
    users = await hass.auth.async_get_users()
    return [
        selector.SelectOptionDict(value=u.id, label=u.name or u.id)
        for u in users
        if not u.system_generated and u.is_active
    ]


class ImHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Initial setup: cooldown + first user."""
    VERSION = 1

    def __init__(self):
        self._options: dict = {}

    async def async_step_user(self, user_input=None):
        """Step 1 — cooldown."""
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_first_user()

        schema = vol.Schema({
            vol.Optional(CONF_UNLOCK_COOLDOWN, default=DEFAULT_UNLOCK_COOLDOWN): selector.selector(
                {"number": {"min": 10, "max": 600, "step": 5,
                            "unit_of_measurement": "s", "mode": "slider"}}
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_first_user(self, user_input=None):
        """Step 2 — first user."""
        errors = {}
        ha_users = await _ha_user_options(self.hass)

        if user_input is not None:
            if len(user_input[CONF_USER_SECRET]) < 16:
                errors[CONF_USER_SECRET] = "secret_too_short"
            else:
                self._options[CONF_USERS] = [{
                    CONF_USER_NAME:   user_input[CONF_USER_NAME].strip(),
                    CONF_USER_SECRET: user_input[CONF_USER_SECRET].strip(),
                    CONF_HA_USER_ID:  user_input[CONF_HA_USER_ID],
                }]
                return self.async_create_entry(
                    title="HA Im Home",
                    data={},
                    options=self._options,
                )

        schema = vol.Schema({
            vol.Required(CONF_HA_USER_ID): selector.selector(
                {"select": {"options": ha_users}}
            ),
            vol.Required(CONF_USER_NAME):   selector.selector({"text": {}}),
            vol.Required(CONF_USER_SECRET): selector.selector({"text": {"type": "password"}}),
        })
        return self.async_show_form(
            step_id="first_user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ImHomeOptionsFlow(config_entry)


class ImHomeOptionsFlow(config_entries.OptionsFlow):

    def __init__(self, config_entry: config_entries.ConfigEntry):
        self._entry = config_entry
        self._users: list[dict] = list(config_entry.options.get(CONF_USERS, []))

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options={
                MENU_EDIT_SETTINGS: "Settings",
                MENU_ADD_USER:      "Add user",
                MENU_REMOVE_USER:   "Remove user",
            },
        )

    async def async_step_edit_settings(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data={
                **self._entry.options,
                CONF_UNLOCK_COOLDOWN: int(user_input[CONF_UNLOCK_COOLDOWN]),
                CONF_SERVICE_UUID:    user_input.get(CONF_SERVICE_UUID, "").strip(),
                CONF_WRITE_UUID:      user_input.get(CONF_WRITE_UUID, "").strip(),
            })

        cur = self._entry.options
        default_service = cur.get(CONF_SERVICE_UUID) or self._entry.data.get(CONF_SERVICE_UUID, "")
        default_write   = cur.get(CONF_WRITE_UUID)   or self._entry.data.get(CONF_WRITE_UUID, "")
        users_str = ", ".join(u[CONF_USER_NAME] for u in self._users) or "none"
        schema = vol.Schema({
            vol.Required(CONF_UNLOCK_COOLDOWN, default=cur.get(CONF_UNLOCK_COOLDOWN, DEFAULT_UNLOCK_COOLDOWN)):
                selector.selector({"number": {"min": 10, "max": 600, "step": 5,
                                              "unit_of_measurement": "s", "mode": "slider"}}),
            vol.Optional(CONF_SERVICE_UUID, default=default_service):
                selector.selector({"text": {}}),
            vol.Optional(CONF_WRITE_UUID, default=default_write):
                selector.selector({"text": {}}),
        })
        return self.async_show_form(
            step_id=MENU_EDIT_SETTINGS,
            data_schema=schema,
            description_placeholders={"users": users_str},
        )

    async def async_step_add_user(self, user_input=None):
        errors = {}
        ha_users = await _ha_user_options(self.hass)

        if user_input is not None:
            name   = user_input[CONF_USER_NAME].strip()
            secret = user_input[CONF_USER_SECRET].strip()
            ha_uid = user_input[CONF_HA_USER_ID]
            if any(u[CONF_USER_NAME] == name for u in self._users):
                errors[CONF_USER_NAME] = "user_exists"
            elif any(u.get(CONF_HA_USER_ID) == ha_uid for u in self._users):
                errors[CONF_HA_USER_ID] = "ha_user_already_linked"
            elif len(secret) < 16:
                errors[CONF_USER_SECRET] = "secret_too_short"
            else:
                self._users.append({
                    CONF_USER_NAME:   name,
                    CONF_USER_SECRET: secret,
                    CONF_HA_USER_ID:  ha_uid,
                })
                return self.async_create_entry(data={
                    **self._entry.options,
                    CONF_USERS: self._users,
                })

        schema = vol.Schema({
            vol.Required(CONF_HA_USER_ID): selector.selector(
                {"select": {"options": ha_users}}
            ),
            vol.Required(CONF_USER_NAME):   selector.selector({"text": {}}),
            vol.Required(CONF_USER_SECRET): selector.selector({"text": {"type": "password"}}),
        })
        return self.async_show_form(step_id=MENU_ADD_USER, data_schema=schema, errors=errors)

    async def async_step_remove_user(self, user_input=None):
        if not self._users:
            return self.async_abort(reason="no_users")
        if user_input is not None:
            selected = user_input.get(CONF_USER_NAME)
            if isinstance(selected, dict):
                selected = selected.get("value") or selected.get("label")
            elif isinstance(selected, list):
                selected = selected[0] if selected else None
            if selected is None:
                _LOGGER.warning("Remove user requested without a valid selection: %s", user_input)
                return self.async_show_form(step_id=MENU_REMOVE_USER, data_schema=vol.Schema({
                    vol.Required(CONF_USER_NAME): selector.selector({
                        "select": {"options": [u[CONF_USER_NAME] for u in self._users]}
                    }),
                }))

            before = len(self._users)
            self._users = [u for u in self._users if u[CONF_USER_NAME] != str(selected)]
            _LOGGER.info(
                "Options remove_user: selected=%s, before=%d, after=%d",
                selected, before, len(self._users),
            )
            return self.async_create_entry(data={**self._entry.options, CONF_USERS: self._users})

        schema = vol.Schema({
            vol.Required(CONF_USER_NAME): selector.selector({
                "select": {"options": [u[CONF_USER_NAME] for u in self._users]}
            }),
        })
        return self.async_show_form(step_id=MENU_REMOVE_USER, data_schema=schema)
