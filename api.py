"""
Aura Frame Manager - FastAPI REST API

A REST API for managing photos and videos on Aura digital picture frames.

Run with:
    uvicorn api:app --reload

Or:
    python api.py
"""

import os
import tempfile
import shutil
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from auramanager import AuraManager, Asset


# =============================================================================
# Pydantic Models for Request/Response
# =============================================================================

class AssetResponse(BaseModel):
    """Response model for an asset."""
    id: str
    user_id: str
    file_name: str
    width: int
    height: int
    is_video: bool
    video_file_name: Optional[str] = None
    taken_at: Optional[str] = None

    @classmethod
    def from_asset(cls, asset: Asset) -> "AssetResponse":
        return cls(
            id=asset.id,
            user_id=asset.user_id,
            file_name=asset.file_name,
            width=asset.width,
            height=asset.height,
            is_video=asset.is_video,
            video_file_name=asset.video_file_name,
            taken_at=asset.taken_at,
        )


class AssetListResponse(BaseModel):
    """Response model for listing assets."""
    frame_id: str
    total: int
    photos: int
    videos: int
    assets: List[AssetResponse]


class FrameConfig(BaseModel):
    """Frame configuration from config file."""
    name: str
    frame_id: str


class FrameListResponse(BaseModel):
    """Response model for listing frames."""
    frames: List[FrameConfig]


class StatsResponse(BaseModel):
    """Response model for frame statistics."""
    frame_id: str
    total: int
    photos: int
    videos: int
    portrait: int
    landscape: int


class OperationResult(BaseModel):
    """Response model for operations that return counts."""
    success: bool
    message: str
    processed: int = 0
    skipped: int = 0
    failed: int = 0


class SyncRequest(BaseModel):
    """Request model for sync operation."""
    source_frame_id: str
    target_frame_id: str
    photos_only: bool = False
    videos_only: bool = False
    dry_run: bool = False


class UploadRequest(BaseModel):
    """Request model for upload configuration."""
    caption: Optional[str] = None


class CropRequest(BaseModel):
    """Request model for crop/fit operation."""
    fit_to_frame: bool = True
    rotation_cw: int = Field(default=0, ge=0, le=270)
    landscape_rect: Optional[str] = None
    portrait_rect: Optional[str] = None


class DownloadJobResponse(BaseModel):
    """Response for background download job."""
    job_id: str
    status: str
    message: str


# =============================================================================
# Global State
# =============================================================================

# Store for background job status
background_jobs: dict = {}

# AuraManager instance (initialized on startup)
aura: Optional[AuraManager] = None


# =============================================================================
# Application Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize AuraManager on startup."""
    global aura
    try:
        aura = AuraManager()
        print("AuraManager initialized successfully")
    except Exception as e:
        print(f"Warning: Failed to initialize AuraManager: {e}")
        print("API will start but most endpoints will fail until config is fixed")
        aura = None
    yield
    # Cleanup on shutdown
    aura = None


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Aura Frame Manager API",
    description="REST API for managing photos and videos on Aura digital picture frames",
    version="1.0.0",
    lifespan=lifespan,
)


def get_aura() -> AuraManager:
    """Get the AuraManager instance or raise an error."""
    if aura is None:
        raise HTTPException(
            status_code=503,
            detail="AuraManager not initialized. Check config.yaml and restart the server."
        )
    return aura


def get_frame_id(frame_id: Optional[str] = None) -> str:
    """Get frame ID, defaulting to first configured frame."""
    manager = get_aura()
    if frame_id:
        return frame_id
    if manager.config["frames"]:
        return manager.config["frames"][0]["frame_id"]
    raise HTTPException(status_code=400, detail="No frame ID provided and no frames configured")


# =============================================================================
# Frame Endpoints
# =============================================================================

@app.get("/frames", response_model=FrameListResponse, tags=["Frames"])
async def list_frames():
    """List all configured frames."""
    manager = get_aura()
    frames = [
        FrameConfig(name=f.get("name", f["frame_id"]), frame_id=f["frame_id"])
        for f in manager.config["frames"]
    ]
    return FrameListResponse(frames=frames)


@app.get("/frames/{frame_id}/info", tags=["Frames"])
async def get_frame_info(frame_id: str):
    """Get detailed information about a frame."""
    manager = get_aura()
    info = manager.get_frame_info(frame_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"Frame {frame_id} not found")
    return info


@app.get("/frames/{frame_id}/stats", response_model=StatsResponse, tags=["Frames"])
async def get_frame_stats(frame_id: str):
    """Get statistics for a frame."""
    manager = get_aura()
    stats = manager.get_asset_stats(frame_id)
    return StatsResponse(frame_id=frame_id, **stats)


# =============================================================================
# Asset Listing Endpoints
# =============================================================================

@app.get("/frames/{frame_id}/assets", response_model=AssetListResponse, tags=["Assets"])
async def list_assets(
    frame_id: str,
    photos_only: bool = Query(False, description="Only return photos"),
    videos_only: bool = Query(False, description="Only return videos"),
):
    """List all assets on a frame."""
    manager = get_aura()
    assets = manager.list_assets(frame_id)
    
    # Filter by type if requested
    if photos_only:
        assets = [a for a in assets if not a.is_video]
    elif videos_only:
        assets = [a for a in assets if a.is_video]
    
    return AssetListResponse(
        frame_id=frame_id,
        total=len(assets),
        photos=sum(1 for a in assets if not a.is_video),
        videos=sum(1 for a in assets if a.is_video),
        assets=[AssetResponse.from_asset(a) for a in assets],
    )


@app.get("/frames/{frame_id}/assets/{asset_id}", response_model=AssetResponse, tags=["Assets"])
async def get_asset(frame_id: str, asset_id: str):
    """Get a specific asset by ID."""
    manager = get_aura()
    asset = manager.get_asset_by_id(frame_id, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    return AssetResponse.from_asset(asset)


# =============================================================================
# Download Endpoints
# =============================================================================

@app.get("/frames/{frame_id}/assets/{asset_id}/download", tags=["Download"])
async def download_asset(frame_id: str, asset_id: str):
    """Download a specific asset."""
    manager = get_aura()
    asset = manager.get_asset_by_id(frame_id, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    # Download to temp directory
    temp_dir = tempfile.mkdtemp()
    try:
        file_path = manager.download_asset(asset, temp_dir)
        if file_path is None:
            raise HTTPException(status_code=500, detail="Failed to download asset")
        
        # Return file response
        filename = os.path.basename(file_path)
        media_type = "video/mp4" if asset.is_video else "image/jpeg"
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type,
            background=BackgroundTasks().add_task(shutil.rmtree, temp_dir, ignore_errors=True)
        )
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/frames/{frame_id}/download", response_model=OperationResult, tags=["Download"])
async def download_all_assets(
    frame_id: str,
    output_dir: str = Query(..., description="Directory to save files"),
    photos_only: bool = Query(False, description="Only download photos"),
    videos_only: bool = Query(False, description="Only download videos"),
):
    """Download all assets from a frame to a local directory."""
    manager = get_aura()
    
    try:
        downloaded, skipped = manager.download_all_assets(
            frame_id,
            output_dir=output_dir,
            photos_only=photos_only,
            videos_only=videos_only,
        )
        return OperationResult(
            success=True,
            message=f"Downloaded {downloaded} assets to {output_dir}",
            processed=downloaded,
            skipped=skipped,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Upload Endpoints
# =============================================================================

@app.post("/frames/{frame_id}/upload", response_model=OperationResult, tags=["Upload"])
async def upload_file(
    frame_id: str,
    file: UploadFile = File(...),
    caption: Optional[str] = Query(None, description="Caption for the file"),
):
    """Upload a single file (photo or video) to a frame."""
    manager = get_aura()
    
    # Save uploaded file to temp location
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Upload to frame
        result = manager.upload_file(frame_id, temp_path, caption=caption)
        
        if result:
            return OperationResult(
                success=True,
                message=f"Successfully uploaded {file.filename}",
                processed=1,
            )
        else:
            raise HTTPException(status_code=500, detail="Upload failed")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/frames/{frame_id}/upload/batch", response_model=OperationResult, tags=["Upload"])
async def upload_files(
    frame_id: str,
    files: List[UploadFile] = File(...),
    caption: Optional[str] = Query(None, description="Caption for the files"),
):
    """Upload multiple files to a frame."""
    manager = get_aura()
    
    temp_dir = tempfile.mkdtemp()
    uploaded = 0
    failed = 0
    
    try:
        for file in files:
            temp_path = os.path.join(temp_dir, file.filename)
            with open(temp_path, "wb") as f:
                content = await file.read()
                f.write(content)
            
            result = manager.upload_file(frame_id, temp_path, caption=caption)
            if result:
                uploaded += 1
            else:
                failed += 1
        
        return OperationResult(
            success=failed == 0,
            message=f"Uploaded {uploaded} files, {failed} failed",
            processed=uploaded,
            failed=failed,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/frames/{frame_id}/upload/directory", response_model=OperationResult, tags=["Upload"])
async def upload_directory(
    frame_id: str,
    directory: str = Query(..., description="Local directory path to upload from"),
    photos_only: bool = Query(False, description="Only upload photos"),
    videos_only: bool = Query(False, description="Only upload videos"),
):
    """Upload all media files from a local directory to a frame."""
    manager = get_aura()
    
    if not os.path.isdir(directory):
        raise HTTPException(status_code=400, detail=f"Directory not found: {directory}")
    
    try:
        uploaded, failed = manager.upload_directory(
            frame_id,
            directory,
            photos_only=photos_only,
            videos_only=videos_only,
        )
        return OperationResult(
            success=failed == 0,
            message=f"Uploaded {uploaded} files from {directory}",
            processed=uploaded,
            failed=failed,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Sync Endpoints
# =============================================================================

@app.post("/sync", response_model=OperationResult, tags=["Sync"])
async def sync_frames(request: SyncRequest):
    """Synchronize assets from source frame to target frame."""
    manager = get_aura()
    
    try:
        synced, skipped = manager.sync_frames(
            request.source_frame_id,
            request.target_frame_id,
            photos_only=request.photos_only,
            videos_only=request.videos_only,
            dry_run=request.dry_run,
        )
        
        action = "Would sync" if request.dry_run else "Synced"
        return OperationResult(
            success=True,
            message=f"{action} {synced} assets from {request.source_frame_id} to {request.target_frame_id}",
            processed=synced,
            skipped=skipped,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sync/all", response_model=OperationResult, tags=["Sync"])
async def sync_all_frames(
    photos_only: bool = Query(False, description="Only sync photos"),
    videos_only: bool = Query(False, description="Only sync videos"),
    dry_run: bool = Query(False, description="Preview without actually syncing"),
):
    """Synchronize all configured frames with each other."""
    manager = get_aura()
    
    try:
        results = manager.sync_all_frames(
            photos_only=photos_only,
            videos_only=videos_only,
            dry_run=dry_run,
        )
        
        total_synced = sum(s for s, _ in results.values())
        total_skipped = sum(sk for _, sk in results.values())
        
        action = "Would sync" if dry_run else "Synced"
        return OperationResult(
            success=True,
            message=f"{action} {total_synced} total assets across all frames",
            processed=total_synced,
            skipped=total_skipped,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Metadata Endpoints
# =============================================================================

@app.post("/frames/{frame_id}/assets/{asset_id}/crop", response_model=AssetResponse, tags=["Metadata"])
async def update_asset_crop(frame_id: str, asset_id: str, request: CropRequest):
    """Update crop/fit settings for an asset."""
    manager = get_aura()
    
    asset = manager.get_asset_by_id(frame_id, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    
    updated = manager.update_asset_crop(
        asset,
        fit_to_frame=request.fit_to_frame,
        rotation_cw=request.rotation_cw,
        landscape_rect=request.landscape_rect,
        portrait_rect=request.portrait_rect,
    )
    
    if updated is None:
        raise HTTPException(status_code=500, detail="Failed to update crop settings")
    
    return AssetResponse.from_asset(updated)


@app.post("/frames/{frame_id}/fit", response_model=OperationResult, tags=["Metadata"])
async def fit_all_assets(
    frame_id: str,
    include_landscape: bool = Query(False, description="Also fit landscape images"),
):
    """Fit all assets on a frame to show complete images (remove auto-crop)."""
    manager = get_aura()
    
    try:
        fitted, skipped = manager.fit_all_assets(
            frame_id,
            portraits_only=not include_landscape,
        )
        return OperationResult(
            success=True,
            message=f"Fitted {fitted} assets on frame {frame_id}",
            processed=fitted,
            skipped=skipped,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/frames/{frame_id}/assets/{asset_id}", response_model=OperationResult, tags=["Metadata"])
async def delete_asset(frame_id: str, asset_id: str):
    """Delete an asset from a frame."""
    manager = get_aura()
    
    success = manager.delete_asset(frame_id, asset_id)
    
    if success:
        return OperationResult(
            success=True,
            message=f"Deleted asset {asset_id}",
            processed=1,
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to delete asset")


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Check API health and AuraManager status."""
    return {
        "status": "healthy",
        "aura_initialized": aura is not None,
        "frames_configured": len(aura.config["frames"]) if aura else 0,
    }


# =============================================================================
# Run Server
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
