"""Huawei router buttons."""

from abc import ABC
import asyncio
import logging
from typing import Final

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .classes import ConnectedDevice
from .client.classes import MAC_ADDR
from .client.huaweiapi import ACTION_REBOOT
from .const import DOMAIN
from .update_coordinator import HuaweiControllerDataUpdateCoordinator, RoutersWatcher

_LOGGER = logging.getLogger(__name__)

_FUNCTION_DISPLAYED_NAME_REBOOT: Final = "Reboot"
_FUNCTION_UID_REBOOT: Final = "button_reboot"

ENTITY_DOMAIN: Final = "button"
ENTITY_ID_FORMAT: Final = ENTITY_DOMAIN + ".{}"


# ---------------------------
#   _generate_button_name
# ---------------------------
def _generate_button_name(
        button_function_displayed_name: str,
        device_name: str
) -> str:
    return f"{device_name} {button_function_displayed_name}"


# ---------------------------
#   _generate_button_id
# ---------------------------
def _generate_button_id(
        coordinator: HuaweiControllerDataUpdateCoordinator,
        button_function_displayed_name: str,
        device_name: str
) -> str:
    preferred_id = f"{coordinator.name} {button_function_displayed_name} {device_name}"
    return generate_entity_id(ENTITY_ID_FORMAT, preferred_id, hass=coordinator.hass)


# ---------------------------
#   _generate_button_unique_id
# ---------------------------
def _generate_button_unique_id(
        coordinator: HuaweiControllerDataUpdateCoordinator,
        button_function_id: str,
        device_mac: MAC_ADDR | None
) -> str:
    prefix = coordinator.unique_id
    suffix = coordinator.get_router_info().serial_number if not device_mac else device_mac
    return f"{prefix}_{button_function_id}_{suffix.lower()}"


# ---------------------------
#   async_setup_entry
# ---------------------------
async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities) -> None:
    """Set up buttons for Huawei Router component."""
    coordinator: HuaweiControllerDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    buttons = [
        HuaweiRebootButton(coordinator, None)
    ]

    async_add_entities(buttons)

    watcher: RoutersWatcher = RoutersWatcher()
    known_buttons: dict[MAC_ADDR, HuaweiButton] = {}

    @callback
    def on_router_added(mac: MAC_ADDR, router: ConnectedDevice) -> None:
        """When a new mesh router is detected."""
        if not known_buttons.get(mac):
            entity = HuaweiRebootButton(coordinator, router)
            async_add_entities([entity])
            known_buttons[mac] = entity

    @callback
    def coordinator_updated() -> None:
        """Update the status of the device."""
        watcher.look_for_changes(coordinator, on_router_added)

    config_entry.async_on_unload(coordinator.async_add_listener(coordinator_updated))


# ---------------------------
#   HuaweiButton
# ---------------------------
class HuaweiButton(CoordinatorEntity[HuaweiControllerDataUpdateCoordinator], ButtonEntity, ABC):
    _update_url: str

    def __init__(
            self,
            coordinator: HuaweiControllerDataUpdateCoordinator,
            action_name: str,
            device_mac: MAC_ADDR | None
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._action_name: str = action_name
        self._device_mac: MAC_ADDR = device_mac
        self._attr_device_info = coordinator.get_device_info(device_mac)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.is_router_online(self._device_mac)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()
        if self._device_mac:
            _LOGGER.debug("Button %s (%s) added to hass", self._action_name, self._device_mac)
        else:
            _LOGGER.debug("Button %s added to hass", self._action_name)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()

    async def async_press(self) -> None:
        """Triggers the button press service."""
        await self.coordinator.execute_action(self._action_name, self._device_mac)

    def press(self) -> None:
        """Press the button."""
        return asyncio.run_coroutine_threadsafe(
            self.async_press(), self.hass.loop
        ).result()


# ---------------------------
#   HuaweiRebootButton
# ---------------------------
class HuaweiRebootButton(HuaweiButton):

    def __init__(
            self,
            coordinator: HuaweiControllerDataUpdateCoordinator,
            device: ConnectedDevice | None
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, ACTION_REBOOT, device.mac if device else None)

        self._attr_device_class = ButtonDeviceClass.RESTART

        self._attr_name = _generate_button_name(
            _FUNCTION_DISPLAYED_NAME_REBOOT,
            device.name if device else coordinator.primary_router_name
        )

        self.entity_id = _generate_button_id(
            coordinator,
            _FUNCTION_DISPLAYED_NAME_REBOOT,
            device.name if device else coordinator.primary_router_name)

        self._attr_unique_id = _generate_button_unique_id(
            coordinator,
            _FUNCTION_UID_REBOOT,
            device.mac if device else None
        )
        self._attr_icon = "mdi:restart"
