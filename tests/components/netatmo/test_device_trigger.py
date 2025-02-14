"""The tests for Netatmo device triggers."""
import pytest

import homeassistant.components.automation as automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.components.netatmo import DOMAIN as NETATMO_DOMAIN
from homeassistant.components.netatmo.const import (
    CLIMATE_TRIGGERS,
    INDOOR_CAMERA_TRIGGERS,
    NETATMO_EVENT,
    OUTDOOR_CAMERA_TRIGGERS,
)
from homeassistant.components.netatmo.device_trigger import SUBTYPES
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.helpers import device_registry
from homeassistant.setup import async_setup_component

from tests.common import (
    MockConfigEntry,
    assert_lists_same,
    async_capture_events,
    async_get_device_automations,
    async_mock_service,
    mock_device_registry,
    mock_registry,
)


@pytest.fixture
def device_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_device_registry(hass)


@pytest.fixture
def entity_reg(hass):
    """Return an empty, loaded, registry."""
    return mock_registry(hass)


@pytest.fixture
def calls(hass):
    """Track calls to a mock service."""
    return async_mock_service(hass, "test", "automation")


@pytest.mark.parametrize(
    "platform,device_type,event_types",
    [
        ("camera", "NOC", OUTDOOR_CAMERA_TRIGGERS),
        ("camera", "NACamera", INDOOR_CAMERA_TRIGGERS),
        ("climate", "NRV", CLIMATE_TRIGGERS),
        ("climate", "NATherm1", CLIMATE_TRIGGERS),
    ],
)
async def test_get_triggers(
    hass, device_reg, entity_reg, platform, device_type, event_types
):
    """Test we get the expected triggers from a netatmo devices."""
    config_entry = MockConfigEntry(domain=NETATMO_DOMAIN, data={})
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={(device_registry.CONNECTION_NETWORK_MAC, "12:34:56:AB:CD:EF")},
        model=device_type,
    )
    entity_reg.async_get_or_create(
        platform, NETATMO_DOMAIN, "5678", device_id=device_entry.id
    )
    expected_triggers = []
    for event_type in event_types:
        if event_type in SUBTYPES:
            for subtype in SUBTYPES[event_type]:
                expected_triggers.append(
                    {
                        "platform": "device",
                        "domain": NETATMO_DOMAIN,
                        "type": event_type,
                        "subtype": subtype,
                        "device_id": device_entry.id,
                        "entity_id": f"{platform}.{NETATMO_DOMAIN}_5678",
                        "metadata": {"secondary": False},
                    }
                )
        else:
            expected_triggers.append(
                {
                    "platform": "device",
                    "domain": NETATMO_DOMAIN,
                    "type": event_type,
                    "device_id": device_entry.id,
                    "entity_id": f"{platform}.{NETATMO_DOMAIN}_5678",
                    "metadata": {"secondary": False},
                }
            )
    triggers = [
        trigger
        for trigger in await async_get_device_automations(
            hass, DeviceAutomationType.TRIGGER, device_entry.id
        )
        if trigger["domain"] == NETATMO_DOMAIN
    ]
    assert_lists_same(triggers, expected_triggers)


@pytest.mark.parametrize(
    "platform,camera_type,event_type",
    [("camera", "NOC", trigger) for trigger in OUTDOOR_CAMERA_TRIGGERS]
    + [("camera", "NACamera", trigger) for trigger in INDOOR_CAMERA_TRIGGERS]
    + [
        ("climate", "NRV", trigger)
        for trigger in CLIMATE_TRIGGERS
        if trigger not in SUBTYPES
    ]
    + [
        ("climate", "NATherm1", trigger)
        for trigger in CLIMATE_TRIGGERS
        if trigger not in SUBTYPES
    ],
)
async def test_if_fires_on_event(
    hass, calls, device_reg, entity_reg, platform, camera_type, event_type
):
    """Test for event triggers firing."""
    mac_address = "12:34:56:AB:CD:EF"
    connection = (device_registry.CONNECTION_NETWORK_MAC, mac_address)
    config_entry = MockConfigEntry(domain=NETATMO_DOMAIN, data={})
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={connection},
        identifiers={(NETATMO_DOMAIN, mac_address)},
        model=camera_type,
    )
    entity_reg.async_get_or_create(
        platform, NETATMO_DOMAIN, "5678", device_id=device_entry.id
    )
    events = async_capture_events(hass, "netatmo_event")

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "device",
                        "domain": NETATMO_DOMAIN,
                        "device_id": device_entry.id,
                        "entity_id": f"{platform}.{NETATMO_DOMAIN}_5678",
                        "type": event_type,
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": (
                                "{{trigger.event.data.type}} - {{trigger.platform}} - {{trigger.event.data.device_id}}"
                            )
                        },
                    },
                },
            ]
        },
    )

    device = device_reg.async_get_device(set(), {connection})
    assert device is not None

    # Fake that the entity is turning on.
    hass.bus.async_fire(
        event_type=NETATMO_EVENT,
        event_data={
            "type": event_type,
            ATTR_DEVICE_ID: device.id,
        },
    )
    await hass.async_block_till_done()
    assert len(events) == 1
    assert len(calls) == 1
    assert calls[0].data["some"] == f"{event_type} - device - {device.id}"


@pytest.mark.parametrize(
    "platform,camera_type,event_type,sub_type",
    [
        ("climate", "NRV", trigger, subtype)
        for trigger in SUBTYPES
        for subtype in SUBTYPES[trigger]
    ]
    + [
        ("climate", "NATherm1", trigger, subtype)
        for trigger in SUBTYPES
        for subtype in SUBTYPES[trigger]
    ],
)
async def test_if_fires_on_event_with_subtype(
    hass, calls, device_reg, entity_reg, platform, camera_type, event_type, sub_type
):
    """Test for event triggers firing."""
    mac_address = "12:34:56:AB:CD:EF"
    connection = (device_registry.CONNECTION_NETWORK_MAC, mac_address)
    config_entry = MockConfigEntry(domain=NETATMO_DOMAIN, data={})
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={connection},
        identifiers={(NETATMO_DOMAIN, mac_address)},
        model=camera_type,
    )
    entity_reg.async_get_or_create(
        platform, NETATMO_DOMAIN, "5678", device_id=device_entry.id
    )
    events = async_capture_events(hass, "netatmo_event")

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "device",
                        "domain": NETATMO_DOMAIN,
                        "device_id": device_entry.id,
                        "entity_id": f"{platform}.{NETATMO_DOMAIN}_5678",
                        "type": event_type,
                        "subtype": sub_type,
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": (
                                "{{trigger.event.data.type}} - {{trigger.event.data.data.mode}} - "
                                "{{trigger.platform}} - {{trigger.event.data.device_id}}"
                            )
                        },
                    },
                },
            ]
        },
    )

    device = device_reg.async_get_device(set(), {connection})
    assert device is not None

    # Fake that the entity is turning on.
    hass.bus.async_fire(
        event_type=NETATMO_EVENT,
        event_data={
            "type": event_type,
            "data": {
                "mode": sub_type,
            },
            ATTR_DEVICE_ID: device.id,
        },
    )
    await hass.async_block_till_done()
    assert len(events) == 1
    assert len(calls) == 1
    assert calls[0].data["some"] == f"{event_type} - {sub_type} - device - {device.id}"


@pytest.mark.parametrize(
    "platform,device_type,event_type",
    [("climate", "NAPLUG", trigger) for trigger in CLIMATE_TRIGGERS],
)
async def test_if_invalid_device(
    hass, device_reg, entity_reg, platform, device_type, event_type
):
    """Test for event triggers firing."""
    mac_address = "12:34:56:AB:CD:EF"
    connection = (device_registry.CONNECTION_NETWORK_MAC, mac_address)
    config_entry = MockConfigEntry(domain=NETATMO_DOMAIN, data={})
    config_entry.add_to_hass(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        connections={connection},
        identifiers={(NETATMO_DOMAIN, mac_address)},
        model=device_type,
    )
    entity_reg.async_get_or_create(
        platform, NETATMO_DOMAIN, "5678", device_id=device_entry.id
    )

    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {
                        "platform": "device",
                        "domain": NETATMO_DOMAIN,
                        "device_id": device_entry.id,
                        "entity_id": f"{platform}.{NETATMO_DOMAIN}_5678",
                        "type": event_type,
                    },
                    "action": {
                        "service": "test.automation",
                        "data_template": {
                            "some": (
                                "{{trigger.event.data.type}} - {{trigger.platform}} - {{trigger.event.data.device_id}}"
                            )
                        },
                    },
                },
            ]
        },
    )
