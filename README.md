# Aura Frame Manager

A Python tool for managing photos and videos on Aura digital picture frames (auraframes.com). This tool provides a clean interface for downloading, uploading, syncing, and managing media assets on your Aura frames.

## Features

- **Download** - Download all photos and videos from any Aura frame
- **Upload** - Upload photos and videos from your local machine to a frame
- **Sync** - Synchronize content between multiple frames
- **Metadata Management** - Update crop settings, fit images to show complete picture
- **Multi-frame Support** - Manage multiple frames from a single configuration

## Setup

### Requirements

- Python 3.9+
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip

### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/aura-frame-manager.git
   cd aura-frame-manager
   ```

2. Install dependencies using uv:
   ```bash
   uv sync
   ```

   Or with pip:
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

Create a `config.yaml` file with your Aura credentials and frame IDs:

```yaml
base_file_path: images      # Where downloaded files will be saved
debug_file_path: debug      # Where debug/log files will be saved

accounts:
  - email: your-email@example.com
    password: your-password

# Get your frame ID from https://app.auraframes.com
# Log in, click "View Photos", and grab the ID from the URL
frames:
  - name: Living Room Frame
    frame_id: your-frame-id-here
  - name: Kitchen Frame
    frame_id: another-frame-id
```

## Usage

Run commands using:

```bash
python main.py <command> [options]
```

Or with uv:

```bash
uv run python main.py <command> [options]
```

### Available Commands

#### List Assets

List all assets on a frame:

```bash
# List assets on the first configured frame
python main.py list

# List assets on a specific frame
python main.py list --frame-id YOUR_FRAME_ID

# List assets on all frames
python main.py list --all

# Show detailed info and save to debug file
python main.py list --verbose --save
```

#### Download Assets

Download photos and videos from a frame:

```bash
# Download all assets from the first configured frame
python main.py download

# Download from a specific frame
python main.py download --frame-id YOUR_FRAME_ID

# Download from all frames
python main.py download --all

# Download only photos
python main.py download --photos-only

# Download only videos
python main.py download --videos-only

# Specify output directory
python main.py download --output /path/to/save
```

#### Upload Assets

Upload photos and videos to a frame:

```bash
# Upload a single file
python main.py upload --file /path/to/photo.jpg

# Upload with a caption
python main.py upload --file /path/to/photo.jpg --caption "Family vacation"

# Upload all files from a directory
python main.py upload --directory /path/to/photos

# Upload only photos from a directory
python main.py upload --directory /path/to/media --photos-only

# Upload only videos from a directory  
python main.py upload --directory /path/to/media --videos-only

# Upload to a specific frame
python main.py upload --frame-id YOUR_FRAME_ID --directory /path/to/photos
```

#### Sync Between Frames

Synchronize content between frames:

```bash
# Sync from one frame to another
python main.py sync --source SOURCE_FRAME_ID --target TARGET_FRAME_ID

# Sync all frames with each other (makes all frames have the same content)
python main.py sync --all

# Preview what would be synced (dry run)
python main.py sync --all --dry-run

# Sync only photos
python main.py sync --all --photos-only

# Sync only videos
python main.py sync --all --videos-only
```

#### Fit Images

Remove auto-crop and show complete images:

```bash
# Fit portrait images on the first frame
python main.py fit

# Fit images on all frames
python main.py fit --all

# Also fit landscape images
python main.py fit --include-landscape
```

#### View Statistics

Show statistics about frame content:

```bash
# Show stats for the first frame
python main.py stats

# Show stats for all frames
python main.py stats --all
```

#### List Frames

View all configured and available frames:

```bash
python main.py frames
```

#### Delete Asset

Remove an asset from a frame:

```bash
# Delete with confirmation prompt
python main.py delete --asset-id ASSET_ID

# Delete without confirmation
python main.py delete --asset-id ASSET_ID --force
```

### Global Options

- `--config PATH` - Use a different config file (default: config.yaml)

## API Notes

This tool uses the undocumented Aura API (`api.pushd.com`). Key points:

- **Rate Limiting**: The API may throttle requests. The tool includes automatic delays between operations.
- **Authentication**: Uses email/password authentication with token-based sessions.
- **File Storage**: Assets are stored on Aura's cloud servers, so no physical access to frames is needed.

## Supported File Types

### Photos
- JPEG/JPG
- PNG
- GIF
- WebP
- HEIC

### Videos
- MP4
- MOV
- AVI
- MKV
- WebM

## Programmatic Usage

You can also use the `AuraManager` class directly in your Python code:

```python
from auramanager import AuraManager

# Initialize with default config
aura = AuraManager()

# Or specify a config file
aura = AuraManager(config_path="my_config.yaml")

# List assets
assets = aura.list_assets("your-frame-id")
for asset in assets:
    print(f"{asset.id}: {asset.file_name} ({'video' if asset.is_video else 'photo'})")

# Download all assets
aura.download_all_assets("your-frame-id", output_dir="./downloads")

# Upload a file
aura.upload_file("your-frame-id", "/path/to/photo.jpg")

# Upload a directory
aura.upload_directory("your-frame-id", "/path/to/photos")

# Sync between frames
aura.sync_frames("source-frame-id", "target-frame-id")

# Fit all portrait images
aura.fit_all_assets("your-frame-id")

# Get frame statistics
stats = aura.get_asset_stats("your-frame-id")
print(f"Total: {stats['total']}, Photos: {stats['photos']}, Videos: {stats['videos']}")
```

## Troubleshooting

### Login Errors
- Verify your email and password in `config.yaml`
- Make sure you're using the same credentials as the Aura mobile app

### Throttling Issues
- Increase the delay between operations using `--delay`
- The default delay is 2 seconds between downloads/uploads

### Frame ID Not Found
- Go to https://app.auraframes.com
- Log in and click "View Photos" under your frame
- Copy the ID from the URL: `https://app.auraframes.com/frame/<FRAME_ID>`

### Duplicate Photos
Multiple users can upload the same photo to a frame, resulting in duplicates when downloaded. Consider using a duplicate photo finder on your downloaded images.

## Web UI

The Aura Frame Manager includes a modern web interface for managing your frames.

### Running the Web UI

```bash
# Install dependencies
uv sync  # or: pip install fastapi uvicorn python-multipart

# Start the server
uvicorn api:app --reload
# or
python api.py
```

Then open your browser to `http://localhost:8000`

### Features

- **Frame Selection** - Switch between multiple configured frames
- **Asset Grid/List View** - View all photos and videos with thumbnails
- **Search & Filter** - Filter by type (photos/videos) and search by filename
- **Upload** - Drag-and-drop or browse to upload files
- **Download** - Download individual assets
- **Sync** - Synchronize content between frames
- **Fit Images** - Remove auto-crop to show complete pictures
- **Delete** - Remove assets from frames
- **Real-time Stats** - View counts of photos, videos, portrait/landscape

## REST API

The web UI is powered by a REST API that you can also use directly.

### API Documentation

Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### API Endpoints

#### Frames

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/frames` | List all configured frames |
| GET | `/frames/{frame_id}/info` | Get frame details |
| GET | `/frames/{frame_id}/stats` | Get frame statistics |

#### Assets

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/frames/{frame_id}/assets` | List all assets on a frame |
| GET | `/frames/{frame_id}/assets/{asset_id}` | Get a specific asset |
| DELETE | `/frames/{frame_id}/assets/{asset_id}` | Delete an asset |

#### Download

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/frames/{frame_id}/assets/{asset_id}/download` | Download a single asset |
| POST | `/frames/{frame_id}/download?output_dir=/path` | Download all assets to directory |

#### Upload

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/frames/{frame_id}/upload` | Upload a single file (multipart) |
| POST | `/frames/{frame_id}/upload/batch` | Upload multiple files |
| POST | `/frames/{frame_id}/upload/directory?directory=/path` | Upload from local directory |

#### Sync

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sync` | Sync between two specific frames |
| POST | `/sync/all` | Sync all frames with each other |

#### Metadata

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/frames/{frame_id}/assets/{asset_id}/crop` | Update crop/fit settings |
| POST | `/frames/{frame_id}/fit` | Fit all images on frame |

#### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Check API health status |

### API Examples

#### List assets on a frame

```bash
curl http://localhost:8000/frames/YOUR_FRAME_ID/assets
```

#### Upload a photo

```bash
curl -X POST http://localhost:8000/frames/YOUR_FRAME_ID/upload \
  -F "file=@/path/to/photo.jpg" \
  -F "caption=My vacation photo"
```

#### Sync two frames

```bash
curl -X POST http://localhost:8000/sync \
  -H "Content-Type: application/json" \
  -d '{
    "source_frame_id": "SOURCE_ID",
    "target_frame_id": "TARGET_ID",
    "dry_run": true
  }'
```

#### Fit all images on a frame

```bash
curl -X POST "http://localhost:8000/frames/YOUR_FRAME_ID/fit?include_landscape=false"
```

#### Get frame statistics

```bash
curl http://localhost:8000/frames/YOUR_FRAME_ID/stats
```

## License

See LICENSE file for details.
