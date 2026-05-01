# HA Im Home — Home Assistant Integration

Custom integration for [Home Assistant](https://www.home-assistant.io/) that works together with the **HA Im Home iOS app** and **Mac daemon** to automatically detect when you arrive home via Bluetooth Low Energy.

## How It Works

```
iPhone (HA Im Home app)
  └─ detects arrival via GPS + elevator pressure drop
      └─ connects via BLE
          └─ Mac Mini daemon verifies HMAC signature
              └─ notifies Home Assistant webhook
```

The integration exposes a **binary sensor per user** (`device_class: presence`) that turns `ON` when the user arrives and automatically resets after a configurable cooldown.

## Requirements

- Home Assistant 2024.1.0+
- [HA Im Home Mac daemon](https://github.com/ab19117814/ha-im-home-mac) running on an always-on Mac with Bluetooth
- HA Im Home iOS app

## Installation

### HACS (recommended)

1. Open HACS → **Integrations** → ⋮ → **Custom repositories**
2. Add `https://github.com/ab19117814/ha-im-home` as **Integration**
3. Find **HA Im Home** and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/ha_im_home/` to your HA `custom_components/` folder
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **HA Im Home**
3. Set the presence cooldown (how long the sensor stays ON after arrival)
4. Add your first user — enter a name and a shared secret (min 16 characters)

The same secret must be entered in the iOS app under **Settings → Secret**.

### Managing Users

After setup, go to **Settings → Devices & Services → HA Im Home → Configure** to:
- Add users
- Remove users  
- Change presence cooldown

## Entities

For each user, one binary sensor is created:

| Entity | Device Class | Description |
|--------|-------------|-------------|
| `binary_sensor.ha_im_home_<name>` | `presence` | `ON` when user has arrived, auto-resets after cooldown |

## Security

- HMAC-SHA256 authentication — secrets never leave your local network
- 30-second timestamp window prevents replay attacks
- Nonce tracking prevents duplicate requests
- Secrets stored only in Home Assistant, not on the Mac or iOS device

## Related Projects

- [HA Im Home Mac daemon](https://github.com/ab19117814/ha-im-home-mac) — BLE bridge for macOS
- HA Im Home iOS app — arrival detection

## License

MIT © [ab19117814](https://github.com/ab19117814)
