# Catalog administration and specification API

Patch 0007 adds structured, GSMArena-style specification sections without
locking the catalog into a fixed set of phone fields.

## Entering a phone in Django admin

1. Open `http://127.0.0.1:8000/admin/` and select **Devices**.
2. Add the identity, launch status, operating system, image, and publishing data.
3. Add device images and memory/storage variants on the same page.
4. Save the device.
5. Open **Specification sections**, choose the device, and add rows such as
   Network, Body, Display, Platform, Memory, Camera, Sound, Comms, and Battery.
6. Add specification items inside each section and use `sort_order` to control
   their public display order.

The legacy JSON `specifications` field remains available for imported data, but
new catalog entries should use structured sections and items.

## Device API filters

`GET /api/catalog/devices/` supports:

- `brand` — brand slug
- `status` — rumored, announced, available, or discontinued
- `os` — operating-system text
- `price_min` and `price_max`
- `ram_min` and `storage_min`
- `camera_score_min` and `gaming_score_min`
- `country` — two-letter offer country code
- `search` and `ordering`

Example:

```text
/api/catalog/devices/?price_max=500&gaming_score_min=85&country=US
```
