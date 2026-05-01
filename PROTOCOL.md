# HA Im Home — Protocol Specification

This document describes the communication protocol used between the iOS app and any compatible daemon implementation.

## Overview
iPhone → BLE Write → Daemon → HTTP POST → Home Assistant

The iOS app connects to a BLE peripheral, writes an authenticated payload, and the daemon forwards the arrival event to Home Assistant via HTTP.

---

## 1. BLE Layer

### Service Discovery

The daemon advertises a BLE peripheral with:
```
| Field | Value |
|-------|-------|
| Local Name | `ImHome` |
| Service UUID | unique per installation (128-bit, stored in HA) |
```
The iOS app fetches the current `service_uuid` and `write_uuid` from Home Assistant before scanning.

### Characteristic
```
| Field | Value |
|-------|-------|
| Characteristic UUID | `write_uuid` (unique per installation, 128-bit) |
| Properties | Write |
| Permissions | Writeable |
```
### Payload Format

The iPhone writes exactly **40 bytes**:
[0:8]   — Unix timestamp, Int64, big-endian
[8:40]  — HMAC-SHA256(timestamp_bytes, user_secret), 32 bytes

**Example (Swift):**
```swift
var ts = Int64(Date().timeIntervalSince1970).bigEndian
let tsData = Data(bytes: &ts, count: 8)
let key = SymmetricKey(data: Data(secret.utf8))
let hmac = Data(HMAC<SHA256>.authenticationCode(for: tsData, using: key))
let payload = tsData + hmac // 40 bytes
```

---

## 2. Daemon Verification

Upon receiving the 40-byte payload, the daemon must:

1. **Extract** timestamp (first 8 bytes) and HMAC (last 32 bytes)
2. **Validate timestamp** — reject if `|now - timestamp| > 30 seconds`
3. **Replay protection** — reject if this timestamp was already used (nonce cache)
4. **Verify HMAC** — compute `HMAC-SHA256(timestamp_bytes, user_secret)` for each known user and compare with received HMAC
5. **Notify HA** — if HMAC matches, POST to Home Assistant

---

## 3. Home Assistant HTTP API

### Register daemon
POST /api/ha_im_home/register
Authorization: Bearer <ha_token>
Content-Type: application/json
{
"service_uuid": "...",
"write_uuid": "..."
}

### Fetch users and UUIDs
GET /api/ha_im_home/config
Authorization: Bearer <ha_token>
Response:
{
"users": [
{ "name": "alice", "secret": "..." }
],
"service_uuid": "...",
"write_uuid": "..."
}

### Notify arrival
POST /api/ha_im_home/arrived
Authorization: Bearer <ha_token>
Content-Type: application/json
{
"user": "alice"
}

---

## 4. Security Notes

- Secrets are minimum 16 characters, stored only in Home Assistant
- Timestamp window (±30s) prevents replay attacks
- Nonce cache prevents duplicate events within the window
- All communication is local network only — no external servers

---

## Reference Implementations

- **macOS** (Swift) — [ha-im-home-mac](https://github.com/ab19117814/ha-im-home-mac)
- **iOS app** (Swift) — source available in this repo

## Contributing

If you build a daemon for another platform, open a PR to add it here!
