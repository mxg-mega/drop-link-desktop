# DropLink

DropLink moves text and files between a phone and a laptop over the phone's hotspot.

## Features

- **mDNS Discovery**: The laptop advertises itself automatically so the phone can find it
- **Incremental Sync**: Reliable sync with sequence numbers and tombstones for deletions
- **Idempotent Operations**: Retried uploads never create duplicates
- **Offline Support**: The web UI shows cached data when the server is unreachable
- **Delivery Tracking**: See when laptop-origin items have been synced to the phone

## Installation

### Development

```bash
pip install -r requirements.txt
python main.py
```

### Building with PyInstaller

```bash
pip install pyinstaller
pyinstaller --onedir --noconsole --collect-submodules zeroconf --hidden-import zeroconf --add-data "templates:templates" --add-data "app:app" main.py
```

**Important PyInstaller flags:**
- `--onedir`: Creates a directory distribution (recommended for stability)
- `--noconsole`: Hides the console window in the packaged build
- `--collect-submodules zeroconf`: Ensures all zeroconf submodules are included
- `--hidden-import zeroconf`: Explicitly imports zeroconf
- `--add-data "templates:templates"`: Includes Jinja2 templates
- `--add-data "app:app"`: Includes the app module

After building, the executable will be in `dist/main/`.

## Configuration

Environment variables:

- `DROPLINK_HOST`: Server host (default: `0.0.0.0`)
- `DROPLINK_PORT`: Server port (default: `8000`)
- `DROPLINK_REQUIRE_TOKEN`: Enable token auth (`1` for on, `0` for off)
- `DROPLINK_CORS`: Enable CORS (`1` for on, `0` for off)
- `DROPLINK_MDNS`: Enable mDNS advertising (`1` for on, `0` for off)
- `DROPLINK_DEVICE_NAME`: Override device name for mDNS
- `DROPLINK_DATA_DIR`: Override data directory

## Windows Firewall Requirements

For mDNS to work on Windows, you need to allow:

1. **Inbound TCP** on the server port (default: 8000) for the Private/Public profile used by the hotspot
2. **UDP 5353** for mDNS on the same profile

You can configure this in Windows Defender Firewall with Advanced Security:

1. Open "Windows Defender Firewall with Advanced Security"
2. Click "Inbound Rules" → "New Rule"
3. Select "Port" → "TCP" → "Specific local ports: 8000"
4. Select "Allow the connection"
5. Check "Private" and "Public" (whichever your hotspot uses)
6. Name it "DropLink Server"

Repeat for UDP port 5353 for mDNS.

## API Endpoints

### Public

- `GET /ping` - Health check and discovery info

### Authenticated (when `DROPLINK_REQUIRE_TOKEN=1`)

- `GET /` - Laptop web UI (laptop-only when auth is on)
- `GET /history?since=<id>` - Legacy history endpoint
- `GET /sync?after=<int>` - Incremental sync
- `POST /text` - Send text
- `POST /upload` - Upload file
- `GET /shared` - List shared files
- `GET /download/{filename}` - Download file
- `DELETE /history/{id}` - Delete item

## Sync Protocol

The `/sync` endpoint supports incremental synchronization:

```json
{
  "latest_seq": 120,
  "full_resync": false,
  "items": [...],
  "deleted": ["id1", "id2"]
}
```

- `latest_seq`: Current sequence number
- `full_resync`: If true, replace entire local copy
- `items`: New or changed items
- `deleted`: IDs of deleted items

## Testing

```bash
pytest
```

Tests cover:
- v1 to v2 migration
- Sequence number monotonicity
- Idempotent creation with client_id
- Sync endpoint behavior
- Delete idempotency
- mDNS service info creation
- Backward compatibility
