"""Config flow for Morning Commute Multileg."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN


class MorningCommuteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Morning Commute Multileg."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # Only allow one instance
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="Morning Commute (Twyford → Farringdon → City Thameslink)",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={
                "leg1": "Twyford → Farringdon (Elizabeth line, my_rail_commute)",
                "leg2": "Farringdon → City Thameslink (5 min walk + Thameslink, TfL sensor)",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MorningCommuteOptionsFlow(config_entry)


class MorningCommuteOptionsFlow(config_entries.OptionsFlow):
    """Options flow."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({}))
