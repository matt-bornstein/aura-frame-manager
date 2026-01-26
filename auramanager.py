"""
Aura Frame Manager - API Client for Aura Digital Picture Frames

This module provides a clean interface for managing photos and videos on Aura frames.
It supports downloading, uploading, syncing, and metadata management operations.
"""

import yaml
import requests
import json
import os
import time
import shutil
import pathlib
import mimetypes
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import boto3
from PIL import Image, ExifTags
import cv2


@dataclass
class Asset:
    """Represents a photo or video asset on an Aura frame."""
    id: str
    user_id: str
    file_name: str
    width: int
    height: int
    video_file_name: Optional[str] = None
    video_url: Optional[str] = None
    taken_at: Optional[str] = None
    auto_portrait_4_5_rect: Optional[str] = None
    raw_data: Optional[Dict] = None

    @property
    def is_video(self) -> bool:
        """Check if this asset is a video."""
        return self.video_file_name is not None and self.video_file_name != "null"

    @property
    def extension(self) -> str:
        """Get the file extension."""
        if self.is_video:
            return os.path.splitext(self.video_file_name)[1]
        return os.path.splitext(self.file_name)[1]

    @classmethod
    def from_api_response(cls, data: Dict) -> "Asset":
        """Create an Asset from API response data."""
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            file_name=data["file_name"],
            width=data.get("width", 0),
            height=data.get("height", 0),
            video_file_name=data.get("video_file_name"),
            video_url=data.get("video_url"),
            taken_at=data.get("taken_at"),
            auto_portrait_4_5_rect=data.get("auto_portrait_4_5_rect"),
            raw_data=data,
        )


class AuraManager:
    """
    Manager class for interacting with Aura digital picture frames.
    
    Provides methods for:
    - Downloading assets (photos/videos) from frames
    - Uploading assets to frames
    - Synchronizing assets between frames
    - Updating asset metadata (cropping, fitting, etc.)
    """

    # API endpoints
    BASE_API_URL = "https://api.pushd.com/v5"
    IMAGE_PROXY_URL = "https://imgproxy.pushd.com"
    DEFAULT_USER_AGENT = "Aura/4.7.1523 (Android 35; Client)"

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize the AuraManager with configuration.
        
        Args:
            config_path: Path to the YAML configuration file.
        """
        self.config = self._load_config(config_path)
        self.email = self.config["accounts"][0]["email"]
        self.password = self.config["accounts"][0]["password"]
        self.base_file_path = self.config.get("base_file_path", "images")
        self.debug_file_path = self.config.get("debug_file_path", "debug")
        self.device_identifier = self.config.get("device_identifier", "aura-frame-manager")
        self.client_device_id = self.config.get("client_device_id", self.device_identifier)
        self.cognito_identity_id = self.config.get("cognito_identity_id")
        self.cognito_region = self.config.get("cognito_region", "us-east-1")
        self.s3_bucket = self.config.get("s3_bucket", "images.senseapp.co")
        self.s3_region = self.config.get("s3_region", "us-east-1")
        self._cognito_credentials: Optional[Dict[str, Any]] = None
        self.session: Optional[requests.Session] = None
        self.user_id: Optional[str] = None
        
        # Ensure directories exist
        pathlib.Path(self.debug_file_path).mkdir(parents=True, exist_ok=True)
        
        # Authenticate
        self.login()

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file."""
        with open(config_path, "r") as config_file:
            return yaml.safe_load(config_file)

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    def login(self) -> bool:
        """
        Authenticate with the Aura API.
        
        Returns:
            True if login was successful, False otherwise.
        """
        login_url = f"{self.BASE_API_URL}/login.json"
        login_payload = {
            "identifier_for_vendor": self.device_identifier,
            "client_device_id": self.client_device_id,
            "app_identifier": "com.pushd.Framelord",
            "locale": "en",
            "user": {"email": self.email, "password": self.password},
        }

        print(f"Logging into Aura as {self.email}...")

        self.session = requests.Session()
        response = self.session.post(login_url, json=login_payload)

        if response.status_code != 200:
            print(f"Login Error: {response.status_code} - Check your credentials")
            return False

        print("Login successful")

        json_data = response.json()
        self.user_id = json_data["result"]["current_user"]["id"]
        self.session.headers.update({
            "X-User-Id": self.user_id,
            "X-Token-Auth": json_data["result"]["current_user"]["auth_token"],
            "X-Device-Identifier": self.device_identifier,
            "X-Client-Device-Id": self.client_device_id,
            "User-Agent": self.DEFAULT_USER_AGENT,
        })

        return True

    # =========================================================================
    # ASSET LISTING (READ FROM FRAME)
    # =========================================================================

    def list_assets(
        self, 
        frame_id: str, 
        write_to_file: bool = False
    ) -> List[Asset]:
        """
        List all assets on a specific frame.
        
        Args:
            frame_id: The ID of the frame to list assets from.
            write_to_file: If True, save the raw response to a JSON file for debugging.
            
        Returns:
            List of Asset objects on the frame.
        """
        print(f"Listing assets for frame {frame_id}...")
        
        url = f"{self.BASE_API_URL}/frames/{frame_id}/assets.json?side_load_users=false"
        response = self.session.get(url)
        json_data = response.json()

        if "assets" not in json_data:
            print(f"Error: No assets found for frame {frame_id}")
            if write_to_file:
                self._write_debug_file(f"{frame_id}_error.json", json_data)
            return []

        if write_to_file:
            self._write_debug_file(f"{frame_id}_assets.json", json_data)

        assets = [Asset.from_api_response(item) for item in json_data["assets"]]
        print(f"Found {len(assets)} assets ({sum(1 for a in assets if a.is_video)} videos, {sum(1 for a in assets if not a.is_video)} photos)")

        return assets

    def list_all_assets(
        self, 
        write_to_file: bool = False
    ) -> Dict[str, List[Asset]]:
        """
        List all assets from all configured frames.
        
        Args:
            write_to_file: If True, save the raw responses to JSON files.
            
        Returns:
            Dictionary mapping frame_id to list of assets.
        """
        all_assets = {}
        for frame in self.config["frames"]:
            frame_id = frame["frame_id"]
            frame_name = frame.get("name", frame_id)
            print(f"\n--- Frame: {frame_name} ---")
            all_assets[frame_id] = self.list_assets(frame_id, write_to_file)
        return all_assets

    def get_asset_by_id(self, frame_id: str, asset_id: str) -> Optional[Asset]:
        """
        Get a specific asset by its ID.
        
        Args:
            frame_id: The frame containing the asset.
            asset_id: The ID of the asset to find.
            
        Returns:
            The Asset if found, None otherwise.
        """
        assets = self.list_assets(frame_id)
        for asset in assets:
            if asset.id == asset_id:
                return asset
        return None

    # =========================================================================
    # ASSET DOWNLOAD (FRAME -> LOCAL)
    # =========================================================================

    def download_asset(
        self, 
        asset: Asset, 
        output_dir: str,
        use_original_name: bool = False
    ) -> Optional[str]:
        """
        Download a single asset to a local directory.
        
        Args:
            asset: The asset to download.
            output_dir: Directory to save the file.
            use_original_name: If True, use original filename; otherwise use asset ID.
            
        Returns:
            Path to the downloaded file, or None if download failed.
        """
        pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Determine URL and filename
        if asset.is_video:
            url = asset.video_url
            source_name = asset.video_file_name
        else:
            url = f"{self.IMAGE_PROXY_URL}/{asset.user_id}/{asset.file_name}"
            source_name = asset.file_name

        if use_original_name:
            filename = source_name
        else:
            filename = f"{asset.id}{asset.extension}"

        file_path = os.path.join(output_dir, filename)

        # Skip if already downloaded
        if os.path.isfile(file_path):
            return file_path

        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(file_path, "wb") as out_file:
                shutil.copyfileobj(response.raw, out_file)
            
            return file_path

        except Exception as e:
            print(f"Error downloading {asset.id}: {e}, retrying in 2 seconds...")
            time.sleep(2)
            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()
                
                with open(file_path, "wb") as out_file:
                    shutil.copyfileobj(response.raw, out_file)
                
                return file_path
            except Exception as e2:
                print(f"Retry failed for {asset.id}: {e2}")
                return None

    def download_all_assets(
        self,
        frame_id: str,
        output_dir: Optional[str] = None,
        photos_only: bool = False,
        videos_only: bool = False,
        delay: float = 0
    ) -> Tuple[int, int]:
        """
        Download all assets from a frame.
        
        Args:
            frame_id: The frame to download from.
            output_dir: Directory to save files (defaults to base_file_path/frame_id).
            photos_only: If True, only download photos.
            videos_only: If True, only download videos.
            delay: Delay between downloads to avoid throttling (seconds).
            
        Returns:
            Tuple of (downloaded_count, skipped_count).
        """
        if output_dir is None:
            output_dir = os.path.join(self.base_file_path, frame_id)

        assets = self.list_assets(frame_id)
        
        downloaded = 0
        skipped = 0

        for i, asset in enumerate(assets, 1):
            # Filter by type
            if photos_only and asset.is_video:
                skipped += 1
                continue
            if videos_only and not asset.is_video:
                skipped += 1
                continue

            asset_type = "video" if asset.is_video else "photo"
            
            # Check if file already exists (cached) before downloading
            filename = f"{asset.id}{asset.extension}"
            file_path = os.path.join(output_dir, filename)
            
            if os.path.isfile(file_path) and os.path.getsize(file_path) > 0:
                print(f"[{i}/{len(assets)}] Cached {asset_type}: {asset.id}")
                skipped += 1
                continue

            print(f"[{i}/{len(assets)}] Downloading {asset_type}: {asset.id}...")

            result = self.download_asset(asset, output_dir)
            
            if result and os.path.getsize(result) > 0:
                downloaded += 1
            else:
                print(f"  Failed to download")
                skipped += 1

            # Delay to avoid throttling (only for actual downloads)
            if i < len(assets) and delay > 0:
                time.sleep(delay)

        print(f"\nDownload complete: {downloaded} downloaded, {skipped} skipped")
        return downloaded, skipped

    def download_from_all_frames(
        self,
        photos_only: bool = False,
        videos_only: bool = False
    ) -> Dict[str, Tuple[int, int]]:
        """
        Download all assets from all configured frames.
        
        Args:
            photos_only: If True, only download photos.
            videos_only: If True, only download videos.
            
        Returns:
            Dictionary mapping frame_id to (downloaded, skipped) counts.
        """
        results = {}
        for frame in self.config["frames"]:
            frame_id = frame["frame_id"]
            frame_name = frame.get("name", frame_id)
            print(f"\n{'='*60}")
            print(f"Downloading from: {frame_name}")
            print(f"{'='*60}")
            results[frame_id] = self.download_all_assets(
                frame_id, 
                photos_only=photos_only, 
                videos_only=videos_only
            )
        return results

    # =========================================================================
    # ASSET UPLOAD (LOCAL -> FRAME)
    # =========================================================================
    #
    # Uses Aura Android flow: Cognito creds -> S3 PUT -> assets/batch_update -> select_asset.
    # Legacy upload helpers remain below for reference.
    # =========================================================================

    def _build_local_identifier(self, filename: str) -> str:
        """Build a synthetic local identifier for Aura uploads."""
        return f"{self.device_identifier}:/upload/{filename}"

    def _format_timestamp(self, timestamp: float) -> str:
        """Format a UNIX timestamp as ISO-8601 with Z suffix."""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    def _get_exif_orientation(self, image: Image.Image) -> int:
        """Extract EXIF orientation if available, otherwise default to 1."""
        try:
            exif = image._getexif() or {}
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == "Orientation":
                    return int(value)
        except Exception:
            pass
        return 1

    def _get_exif_datetime(self, image: Image.Image) -> Optional[datetime]:
        """Extract EXIF DateTimeOriginal if present."""
        try:
            exif = image._getexif() or {}
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == "DateTimeOriginal" and isinstance(value, str):
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            return None
        return None

    def _get_image_metadata(self, file_path: str) -> Tuple[int, int, int, Optional[str]]:
        """Return (width, height, orientation, taken_at) for an image file."""
        with Image.open(file_path) as img:
            width, height = img.size
            orientation = self._get_exif_orientation(img)
            taken_at_dt = self._get_exif_datetime(img)
            taken_at = taken_at_dt.isoformat().replace("+00:00", "Z") if taken_at_dt else None
        return width, height, orientation, taken_at

    def _get_video_metadata(self, file_path: str) -> Tuple[int, int, float]:
        """Return (width, height, duration_seconds) for a video file."""
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return 0, 0, 0.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        cap.release()
        duration = float(frame_count / fps) if fps > 0 else 0.0
        return width, height, duration

    def _get_cognito_credentials(self) -> Optional[Dict[str, Any]]:
        """Fetch (and cache) Cognito credentials used for S3 uploads."""
        if not self.cognito_identity_id:
            print("Error: cognito_identity_id is not configured.")
            return None

        now = datetime.now(timezone.utc)
        if self._cognito_credentials:
            expiration = self._cognito_credentials.get("expiration")
            if isinstance(expiration, datetime) and now < expiration - timedelta(seconds=60):
                return self._cognito_credentials

        url = f"https://cognito-identity.{self.cognito_region}.amazonaws.com/"
        headers = {
            "x-amz-target": "AWSCognitoIdentityService.GetCredentialsForIdentity",
            "content-type": "application/x-amz-json-1.1",
        }
        payload = {"IdentityId": self.cognito_identity_id, "Logins": {}}
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        if response.status_code != 200:
            print(f"Cognito credentials error: {response.status_code} - {response.text}")
            return None

        data = response.json()
        creds = data.get("Credentials") or {}
        try:
            expiration = datetime.fromtimestamp(float(creds["Expiration"]), tz=timezone.utc)
        except Exception:
            expiration = None

        self._cognito_credentials = {
            "access_key": creds.get("AccessKeyId"),
            "secret_key": creds.get("SecretKey"),
            "session_token": creds.get("SessionToken"),
            "expiration": expiration,
        }
        return self._cognito_credentials

    def _get_s3_client(self):
        """Create an S3 client using Cognito credentials."""
        creds = self._get_cognito_credentials()
        if not creds or not creds.get("access_key"):
            return None
        session = boto3.session.Session(
            aws_access_key_id=creds["access_key"],
            aws_secret_access_key=creds["secret_key"],
            aws_session_token=creds["session_token"],
            region_name=self.s3_region,
        )
        return session.client("s3")

    def _s3_put_object(self, file_path: str, key: str) -> bool:
        """Upload a file to S3 using Cognito credentials."""
        s3_client = self._get_s3_client()
        if s3_client is None:
            return False
        try:
            with open(file_path, "rb") as f:
                s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=key,
                    Body=f,
                    ContentType="application/octet-stream",
                    GrantRead='uri="http://acs.amazonaws.com/groups/global/AllUsers"',
                )
            return True
        except Exception as e:
            print(f"S3 upload failed: {e}")
            return False

    def upload_photo_mobile(
        self,
        frame_id: str,
        file_path: str,
        caption: Optional[str] = None,
    ) -> Optional[Dict]:
        """Upload a photo using the Aura Android app flow."""
        if not os.path.isfile(file_path):
            print(f"Error: File not found: {file_path}")
            return None

        ext = os.path.splitext(file_path)[1].lower() or ".jpg"
        file_name = f"{uuid.uuid4()}{ext}"
        local_identifier = self._build_local_identifier(file_name)

        width, height, orientation, taken_at = self._get_image_metadata(file_path)
        modified_at = self._format_timestamp(os.path.getmtime(file_path))
        if taken_at is None:
            taken_at = modified_at

        if not self._s3_put_object(file_path, file_name):
            return None

        batch_url = f"{self.BASE_API_URL}/assets/batch_update.json"
        payload = {
            "assets": [
                {
                    "local_identifier": local_identifier,
                    "original_file_name": file_path,
                    "width": width,
                    "height": height,
                    "taken_at": taken_at,
                    "modified_at": modified_at,
                    "selected": True,
                    "favorite": False,
                    "orientation": orientation,
                    "file_name": file_name,
                    "upload_priority": 20,
                }
            ]
        }
        batch_response = self.session.put(batch_url, json=payload)
        if batch_response.status_code != 200:
            print(f"Asset registration failed: {batch_response.status_code} - {batch_response.text}")
            return None

        select_url = f"{self.BASE_API_URL}/frames/{frame_id}/select_asset.json"
        select_payload = {
            "assets": [
                {
                    "user_id": self.user_id,
                    "asset_local_identifier": local_identifier,
                }
            ]
        }
        select_response = self.session.post(select_url, json=select_payload)
        if select_response.status_code != 200:
            print(f"Select asset failed: {select_response.status_code} - {select_response.text}")
            return None

        return select_response.json()

    def upload_video_mobile(
        self,
        frame_id: str,
        file_path: str,
        caption: Optional[str] = None,
    ) -> Optional[Dict]:
        """Upload a video using the Aura Android app flow."""
        if not os.path.isfile(file_path):
            print(f"Error: File not found: {file_path}")
            return None

        video_ext = os.path.splitext(file_path)[1].lower() or ".mp4"
        video_file_name = f"{uuid.uuid4()}{video_ext}"
        thumb_file_name = f"{uuid.uuid4()}.jpg"
        local_identifier = self._build_local_identifier(video_file_name)

        width, height, duration = self._get_video_metadata(file_path)
        taken_at = self._format_timestamp(os.path.getmtime(file_path))
        modified_at = taken_at

        with tempfile.TemporaryDirectory() as temp_dir:
            thumb_path = os.path.join(temp_dir, thumb_file_name)
            if not self.generate_video_thumbnail(file_path, thumb_path):
                print("Error: Failed to generate video thumbnail.")
                return None

            if not self._s3_put_object(thumb_path, thumb_file_name):
                return None
            if not self._s3_put_object(file_path, video_file_name):
                return None

        batch_url = f"{self.BASE_API_URL}/assets/batch_update.json"
        payload = {
            "assets": [
                {
                    "local_identifier": local_identifier,
                    "original_file_name": file_path,
                    "width": width,
                    "height": height,
                    "taken_at": taken_at,
                    "modified_at": modified_at,
                    "selected": True,
                    "favorite": False,
                    "orientation": 1,
                    "file_name": thumb_file_name,
                    "video_file_name": video_file_name,
                    "upload_priority": 20,
                    "duration": duration,
                    "video_clip_start": 0,
                }
            ]
        }
        batch_response = self.session.put(batch_url, json=payload)
        if batch_response.status_code != 200:
            print(f"Asset registration failed: {batch_response.status_code} - {batch_response.text}")
            return None

        select_url = f"{self.BASE_API_URL}/frames/{frame_id}/select_asset.json"
        select_payload = {
            "assets": [
                {
                    "user_id": self.user_id,
                    "asset_local_identifier": local_identifier,
                }
            ]
        }
        select_response = self.session.post(select_url, json=select_payload)
        if select_response.status_code != 200:
            print(f"Select asset failed: {select_response.status_code} - {select_response.text}")
            return None

        return select_response.json()

    def _get_upload_url(self, frame_id: str) -> Optional[Dict]:
        """
        Get a presigned URL for uploading an asset.
        
        NOTE: This endpoint is experimental and may not exist.
        
        Args:
            frame_id: The frame to upload to.
            
        Returns:
            Dictionary with upload URL and fields, or None on failure.
        """
        # Try different possible endpoint patterns
        endpoints_to_try = [
            f"{self.BASE_API_URL}/frames/{frame_id}/assets/upload_url.json",
            f"{self.BASE_API_URL}/frames/{frame_id}/upload_url.json",
            f"{self.BASE_API_URL}/assets/upload_url.json",
        ]
        
        for url in endpoints_to_try:
            response = self.session.get(url)
            if response.status_code == 200:
                print(f"Found upload endpoint: {url}")
                return response.json()
            elif response.status_code != 404:
                print(f"Upload URL request to {url}: {response.status_code}")
                print(f"Response: {response.text[:500]}")
        
        print("Error: Could not find upload URL endpoint. Upload may not be supported via API.")
        print("Consider uploading via the Aura mobile app or web interface.")
        return None

    def upload_photo(
        self,
        frame_id: str,
        file_path: str,
        caption: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Upload a photo to a frame using the mobile upload flow.
        """
        return self.upload_photo_mobile(frame_id, file_path, caption=caption)

    def upload_video(
        self,
        frame_id: str,
        file_path: str,
        caption: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Upload a video to a frame using the mobile upload flow.
        """
        return self.upload_video_mobile(frame_id, file_path, caption=caption)

    def upload_file(
        self,
        frame_id: str,
        file_path: str,
        caption: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Upload a file (photo or video) to a frame.
        Automatically detects the file type and uses the appropriate upload method.
        
        Args:
            frame_id: The frame to upload to.
            file_path: Path to the file.
            caption: Optional caption.
            
        Returns:
            The created asset data, or None on failure.
        """
        mime_type, _ = mimetypes.guess_type(file_path)
        
        if mime_type and mime_type.startswith("video/"):
            return self.upload_video(frame_id, file_path, caption)
        else:
            return self.upload_photo(frame_id, file_path, caption)

    def upload_directory(
        self,
        frame_id: str,
        directory: str,
        photos_only: bool = False,
        videos_only: bool = False,
        delay: float = 2.0
    ) -> Tuple[int, int]:
        """
        Upload all media files from a directory to a frame.
        
        Args:
            frame_id: The frame to upload to.
            directory: Path to the directory containing files.
            photos_only: If True, only upload photos.
            videos_only: If True, only upload videos.
            delay: Delay between uploads (seconds).
            
        Returns:
            Tuple of (uploaded_count, failed_count).
        """
        if not os.path.isdir(directory):
            print(f"Error: Directory not found: {directory}")
            return 0, 0

        # Supported extensions
        photo_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}
        video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

        files = []
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            if not os.path.isfile(file_path):
                continue
                
            ext = os.path.splitext(filename)[1].lower()
            is_photo = ext in photo_extensions
            is_video = ext in video_extensions
            
            if photos_only and not is_photo:
                continue
            if videos_only and not is_video:
                continue
            if is_photo or is_video:
                files.append(file_path)

        print(f"Found {len(files)} files to upload")

        uploaded = 0
        failed = 0

        for i, file_path in enumerate(files, 1):
            print(f"[{i}/{len(files)}] ", end="")
            result = self.upload_file(frame_id, file_path)
            
            if result:
                uploaded += 1
            else:
                failed += 1

            if i < len(files) and delay > 0:
                time.sleep(delay)

        print(f"\nUpload complete: {uploaded} uploaded, {failed} failed")
        return uploaded, failed

    # =========================================================================
    # ASSET SYNCHRONIZATION (BETWEEN FRAMES)
    # =========================================================================

    def sync_frames(
        self,
        source_frame_id: str,
        target_frame_id: str,
        photos_only: bool = False,
        videos_only: bool = False,
        dry_run: bool = False
    ) -> Tuple[int, int]:
        """
        Synchronize assets from source frame to target frame.
        
        Copies assets that exist on source but not on target.
        
        Args:
            source_frame_id: Frame to copy from.
            target_frame_id: Frame to copy to.
            photos_only: If True, only sync photos.
            videos_only: If True, only sync videos.
            dry_run: If True, only report what would be synced.
            
        Returns:
            Tuple of (synced_count, skipped_count).
        """
        print(f"Syncing from {source_frame_id} to {target_frame_id}...")
        
        source_assets = self.list_assets(source_frame_id)
        target_assets = self.list_assets(target_frame_id)
        
        # Create set of target asset IDs for fast lookup
        target_ids = {a.id for a in target_assets}
        
        # Find assets to sync
        to_sync = []
        for asset in source_assets:
            if asset.id in target_ids:
                continue
            if photos_only and asset.is_video:
                continue
            if videos_only and not asset.is_video:
                continue
            to_sync.append(asset)

        print(f"Found {len(to_sync)} assets to sync")
        
        if dry_run:
            for asset in to_sync:
                asset_type = "video" if asset.is_video else "photo"
                print(f"  Would sync: {asset.id} ({asset_type}) from {source_frame_id} -> {target_frame_id}")
            return len(to_sync), 0

        # Download to the normal images directory (uses cache if already downloaded)
        output_dir = os.path.join(self.base_file_path, source_frame_id)
        pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)

        synced = 0
        skipped = 0

        for i, asset in enumerate(to_sync, 1):
            asset_type = "video" if asset.is_video else "photo"
            print(f"[{i}/{len(to_sync)}] Syncing {asset_type}: {asset.id}")

            # Download from source (will use cache if already exists)
            local_path = self.download_asset(asset, output_dir)
            if not local_path:
                print(f"  Failed to download")
                skipped += 1
                continue

            # Upload to target
            result = self.upload_file(target_frame_id, local_path)
            if result:
                synced += 1
            else:
                skipped += 1

            time.sleep(2)

        print(f"\nSync complete: {synced} synced, {skipped} skipped")
        return synced, skipped

    def sync_frames_detailed(
        self,
        source_frame_id: str,
        target_frame_id: str,
        photos_only: bool = False,
        videos_only: bool = False,
        dry_run: bool = False,
        source_label: Optional[str] = None,
        target_label: Optional[str] = None,
    ) -> Tuple[int, int, List[str]]:
        """
        Synchronize assets from source frame to target frame with detailed output.
        
        Returns:
            Tuple of (synced_count, skipped_count, output_lines).
        """
        source_label = source_label or source_frame_id
        target_label = target_label or target_frame_id

        lines: List[str] = []
        lines.append(f"Source: {source_label} ({source_frame_id})")
        lines.append(f"Target: {target_label} ({target_frame_id})")
        lines.append(f"Dry run: {'yes' if dry_run else 'no'}")

        source_assets = self.list_assets(source_frame_id)
        target_assets = self.list_assets(target_frame_id)

        target_ids = {a.id for a in target_assets}
        to_sync = []
        for asset in source_assets:
            if asset.id in target_ids:
                continue
            if photos_only and asset.is_video:
                continue
            if videos_only and not asset.is_video:
                continue
            to_sync.append(asset)

        lines.append(f"Assets to sync: {len(to_sync)}")

        def get_display_name(asset: Asset) -> str:
            if asset.is_video and asset.video_file_name:
                return asset.video_file_name
            return asset.file_name

        if dry_run:
            for asset in to_sync:
                asset_type = "video" if asset.is_video else "photo"
                display_name = get_display_name(asset)
                lines.append(
                    f"Would sync: {display_name} ({asset.id}, {asset_type}) from {source_label} -> {target_label}"
                )
            lines.append("Dry run complete")
            return len(to_sync), 0, lines

        output_dir = os.path.join(self.base_file_path, source_frame_id)
        pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)

        synced = 0
        skipped = 0

        for asset in to_sync:
            display_name = get_display_name(asset)
            lines.append(f"Downloading: {display_name} ({asset.id})")

            local_path = self.download_asset(asset, output_dir)
            if not local_path:
                lines.append(f"Download failed: {display_name} ({asset.id})")
                skipped += 1
                continue

            lines.append(f"Downloaded: {display_name}")
            lines.append(f"Uploading: {display_name} ({asset.id})")

            result = self.upload_file(target_frame_id, local_path)
            if result:
                synced += 1
                lines.append(f"Uploaded: {display_name}")
            else:
                skipped += 1
                lines.append(f"Upload failed: {display_name} ({asset.id})")

            time.sleep(2)

        lines.append(f"Sync complete: {synced} synced, {skipped} skipped")
        return synced, skipped, lines

    def sync_selected_frames(
        self,
        frame_ids: List[str],
        dry_run: bool = False,
        photos_only: bool = False,
        videos_only: bool = False,
    ) -> Tuple[int, int, List[str]]:
        """
        Synchronize assets across a selected set of frames.

        Returns:
            Tuple of (total_synced, total_skipped, output_lines).
        """
        unique_frame_ids = list(dict.fromkeys(frame_ids))
        if len(unique_frame_ids) < 2:
            raise ValueError("Select at least two frames to sync")

        frame_name_map = {
            frame["frame_id"]: frame.get("name", frame["frame_id"])
            for frame in self.config["frames"]
        }
        missing = [frame_id for frame_id in unique_frame_ids if frame_id not in frame_name_map]
        if missing:
            raise ValueError(f"Unknown frame IDs: {', '.join(missing)}")

        lines: List[str] = []
        lines.append(f"{'Dry run' if dry_run else 'Sync'} across {len(unique_frame_ids)} frames")

        total_synced = 0
        total_skipped = 0

        for source_id in unique_frame_ids:
            for target_id in unique_frame_ids:
                if source_id == target_id:
                    continue

                source_label = frame_name_map[source_id]
                target_label = frame_name_map[target_id]
                lines.append("")
                lines.append("=" * 60)
                lines.append(f"{source_label} -> {target_label}")
                lines.append("=" * 60)

                synced, skipped, pair_lines = self.sync_frames_detailed(
                    source_id,
                    target_id,
                    photos_only=photos_only,
                    videos_only=videos_only,
                    dry_run=dry_run,
                    source_label=source_label,
                    target_label=target_label,
                )
                total_synced += synced
                total_skipped += skipped
                lines.extend(pair_lines)

        lines.append("")
        lines.append(f"Summary: {total_synced} synced, {total_skipped} skipped")
        return total_synced, total_skipped, lines

    def sync_all_frames(
        self,
        photos_only: bool = False,
        videos_only: bool = False,
        dry_run: bool = False
    ) -> Dict[str, Tuple[int, int]]:
        """
        Synchronize all assets across all configured frames.
        
        Makes all frames have the same content by syncing from each frame
        to all other frames.
        
        Args:
            photos_only: If True, only sync photos.
            videos_only: If True, only sync videos.
            dry_run: If True, only report what would be synced.
            
        Returns:
            Dictionary mapping "source->target" to (synced, skipped) counts.
        """
        results = {}
        frames = self.config["frames"]
        
        for source in frames:
            for target in frames:
                if source["frame_id"] == target["frame_id"]:
                    continue
                    
                key = f"{source.get('name', source['frame_id'])} -> {target.get('name', target['frame_id'])}"
                print(f"\n{'='*60}")
                print(f"Syncing: {key}")
                print(f"{'='*60}")
                
                results[key] = self.sync_frames(
                    source["frame_id"],
                    target["frame_id"],
                    photos_only=photos_only,
                    videos_only=videos_only,
                    dry_run=dry_run
                )
        
        return results

    # =========================================================================
    # METADATA OPERATIONS
    # =========================================================================

    def update_asset_crop(
        self,
        asset: Asset,
        fit_to_frame: bool = True,
        rotation_cw: int = 0,
        landscape_rect: Optional[str] = None,
        portrait_rect: Optional[str] = None
    ) -> Optional[Asset]:
        """
        Update crop/fit settings for an asset.
        
        Args:
            asset: The asset to update.
            fit_to_frame: If True, fit the entire image (no crop).
            rotation_cw: Clockwise rotation in degrees (0, 90, 180, 270).
            landscape_rect: Custom landscape crop rect (format: "x,y,width,height").
            portrait_rect: Custom portrait crop rect.
            
        Returns:
            Updated Asset, or None on failure.
        """
        print(f"Updating crop for {asset.id} (fit={fit_to_frame})")

        url = f"{self.BASE_API_URL}/assets/crop.json"
        payload = {
            "id": asset.id,
            "local_identifier": None,
            "user_id": asset.user_id,
            "rotation_cw": rotation_cw,
        }

        if fit_to_frame:
            # Set to show entire image in both orientations
            full_rect = f"0,0,{asset.width},{asset.height}"
            payload.update({
                "user_landscape_16_10_rect": None,
                "user_landscape_rect": full_rect,
                "user_portrait_4_5_rect": None,
                "user_portrait_rect": full_rect,
            })
        else:
            # Use custom rects
            if landscape_rect:
                payload["user_landscape_rect"] = landscape_rect
            if portrait_rect:
                payload["user_portrait_rect"] = portrait_rect

        response = self.session.post(url, json=payload)

        if response.status_code != 200:
            print(f"Crop update failed: {response.status_code} - {response.text}")
            return None

        print("Crop updated successfully")
        return Asset.from_api_response(response.json()["asset"])

    def fit_all_assets(
        self,
        frame_id: str,
        portraits_only: bool = True
    ) -> Tuple[int, int]:
        """
        Fit all assets on a frame to show the complete image.
        
        By default, only adjusts portrait images that have auto-cropping applied.
        
        Args:
            frame_id: The frame to update.
            portraits_only: If True, only fit portrait-oriented images.
            
        Returns:
            Tuple of (fitted_count, skipped_count).
        """
        assets = self.list_assets(frame_id)
        print(f"Checking {len(assets)} assets for fitting...")

        fitted = 0
        skipped = 0

        for asset in assets:
            # Check if portrait and has auto-crop
            is_portrait = asset.width < asset.height
            has_auto_crop = asset.auto_portrait_4_5_rect is not None
            
            if portraits_only and not (is_portrait and has_auto_crop):
                skipped += 1
                continue

            result = self.update_asset_crop(asset, fit_to_frame=True)
            if result:
                fitted += 1
            else:
                skipped += 1

        print(f"\nFit complete: {fitted} fitted, {skipped} skipped")
        return fitted, skipped

    def delete_asset(self, frame_id: str, asset_id: str) -> bool:
        """
        Delete an asset from a frame.
        
        Args:
            frame_id: The frame containing the asset.
            asset_id: The ID of the asset to delete.
            
        Returns:
            True if deletion was successful, False otherwise.
        """
        print(f"Deleting asset {asset_id} from frame {frame_id}")

        url = f"{self.BASE_API_URL}/assets/{asset_id}.json"
        response = self.session.delete(url)
        if response.status_code in [200, 204]:
            print(f"Asset deleted successfully via {url}")
            return True
        print(f"Delete failed at {url}: {response.status_code} - {response.text[:500]}")
        return False

    def get_frame_info(self, frame_id: str) -> Optional[Dict]:
        """
        Get information about a frame.
        
        Args:
            frame_id: The frame to get info for.
            
        Returns:
            Frame information dictionary, or None on failure.
        """
        url = f"{self.BASE_API_URL}/frames/{frame_id}.json"
        response = self.session.get(url)
        
        if response.status_code != 200:
            print(f"Error getting frame info: {response.status_code}")
            return None
            
        return response.json()

    def list_frames(self) -> List[Dict]:
        """
        List all frames associated with the account.
        
        Returns:
            List of frame information dictionaries.
        """
        url = f"{self.BASE_API_URL}/users/{self.user_id}/frames.json"
        response = self.session.get(url)
        
        if response.status_code != 200:
            print(f"Error listing frames: {response.status_code}")
            return []
            
        return response.json().get("frames", [])

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _write_debug_file(self, filename: str, data: Any) -> None:
        """Write data to a debug file as JSON."""
        file_path = os.path.join(self.debug_file_path, filename)
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        print(f"Debug data written to: {file_path}")

    def get_asset_stats(self, frame_id: str) -> Dict[str, int]:
        """
        Get statistics about assets on a frame.
        
        Args:
            frame_id: The frame to analyze.
            
        Returns:
            Dictionary with counts for different asset types.
        """
        assets = self.list_assets(frame_id)
        
        stats = {
            "total": len(assets),
            "photos": sum(1 for a in assets if not a.is_video),
            "videos": sum(1 for a in assets if a.is_video),
            "portrait": sum(1 for a in assets if a.width < a.height),
            "landscape": sum(1 for a in assets if a.width >= a.height),
        }
        
        return stats

    # =========================================================================
    # THUMBNAIL GENERATION
    # =========================================================================

    # Thumbnail size - 400px on longest side for future-proofing
    THUMBNAIL_MAX_SIZE = 400

    def get_thumbnail_dir(self, frame_id: str) -> str:
        """Get the thumbnail directory path for a frame."""
        return os.path.join(self.base_file_path, frame_id, "thumbnails")

    def get_thumbnail_path(self, frame_id: str, asset_id: str) -> Optional[str]:
        """
        Get the path to an existing thumbnail if it exists.
        
        Args:
            frame_id: The frame ID.
            asset_id: The asset ID.
            
        Returns:
            Path to thumbnail if it exists, None otherwise.
        """
        thumb_dir = self.get_thumbnail_dir(frame_id)
        if not os.path.isdir(thumb_dir):
            return None
        
        # Look for thumbnail with any extension
        for filename in os.listdir(thumb_dir):
            if filename.startswith(asset_id + "."):
                return os.path.join(thumb_dir, filename)
        return None

    def generate_thumbnail(self, source_path: str, thumb_path: str) -> Optional[str]:
        """
        Generate a thumbnail from a source image.
        
        Args:
            source_path: Path to the full-size image.
            thumb_path: Path where thumbnail should be saved.
            
        Returns:
            Path to generated thumbnail, or None on failure.
        """
        try:
            with Image.open(source_path) as img:
                # Convert to RGB if necessary (handles RGBA, P mode, etc.)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                # Calculate thumbnail size maintaining aspect ratio
                img.thumbnail((self.THUMBNAIL_MAX_SIZE, self.THUMBNAIL_MAX_SIZE), Image.Resampling.LANCZOS)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
                
                # Save as JPEG for smaller file size
                img.save(thumb_path, "JPEG", quality=85, optimize=True)
                
            return thumb_path
        except Exception as e:
            print(f"Error generating thumbnail: {e}")
            return None

    def generate_video_thumbnail(self, source_path: str, thumb_path: str) -> Optional[str]:
        """
        Generate a thumbnail from the first frame of a video.
        
        Args:
            source_path: Path to the video file.
            thumb_path: Path where thumbnail should be saved.
            
        Returns:
            Path to generated thumbnail, or None on failure.
        """
        try:
            # Open video and grab the first frame
            cap = cv2.VideoCapture(source_path)
            if not cap.isOpened():
                print(f"Error: Could not open video {source_path}")
                return None
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                print(f"Error: Could not read first frame from {source_path}")
                return None
            
            # Convert BGR (OpenCV) to RGB (PIL)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            
            # Calculate thumbnail size maintaining aspect ratio
            img.thumbnail((self.THUMBNAIL_MAX_SIZE, self.THUMBNAIL_MAX_SIZE), Image.Resampling.LANCZOS)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
            
            # Save as JPEG for smaller file size
            img.save(thumb_path, "JPEG", quality=85, optimize=True)
            
            return thumb_path
        except Exception as e:
            print(f"Error generating video thumbnail: {e}")
            return None

    def get_cached_asset_path(self, frame_id: str, asset_id: str) -> Optional[str]:
        """
        Get the path to a cached full-size asset if it exists.
        
        Args:
            frame_id: The frame ID.
            asset_id: The asset ID.
            
        Returns:
            Path to cached asset if it exists, None otherwise.
        """
        cache_dir = os.path.join(self.base_file_path, frame_id)
        if not os.path.isdir(cache_dir):
            return None
        
        for filename in os.listdir(cache_dir):
            # Skip thumbnails directory
            if filename == "thumbnails":
                continue
            if filename.startswith(asset_id + ".") or filename.startswith(asset_id + "_"):
                return os.path.join(cache_dir, filename)
        return None

    def get_or_create_thumbnail(self, frame_id: str, asset: Asset) -> Optional[str]:
        """
        Get or create a thumbnail for an asset (image or video).
        
        Logic:
        1. Check for thumbnail in cache - return if exists
        2. Check for full asset in cache - generate thumbnail if exists
        3. Download full asset from Aura, cache it, generate thumbnail
        
        For videos, extracts the first frame as thumbnail.
        
        Args:
            frame_id: The frame ID.
            asset: The asset to get/create thumbnail for.
            
        Returns:
            Path to thumbnail, or None on failure.
        """
        # 1. Check for existing thumbnail
        thumb_path = self.get_thumbnail_path(frame_id, asset.id)
        if thumb_path:
            return thumb_path
        
        # 2. Check for cached full-size asset
        full_path = self.get_cached_asset_path(frame_id, asset.id)
        
        # 3. If no cached full-size, download it
        if not full_path:
            cache_dir = os.path.join(self.base_file_path, frame_id)
            os.makedirs(cache_dir, exist_ok=True)
            full_path = self.download_asset(asset, cache_dir)
            if not full_path:
                return None
        
        # 4. Generate thumbnail from full-size asset
        thumb_dir = self.get_thumbnail_dir(frame_id)
        thumb_path = os.path.join(thumb_dir, f"{asset.id}.jpg")
        
        if asset.is_video:
            return self.generate_video_thumbnail(full_path, thumb_path)
        else:
            return self.generate_thumbnail(full_path, thumb_path)
