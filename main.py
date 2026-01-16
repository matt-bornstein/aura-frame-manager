#!/usr/bin/env python3
"""
Aura Frame Manager - CLI Interface

A command-line tool for managing photos and videos on Aura digital picture frames.

Usage:
    python main.py <command> [options]

Commands:
    list        List assets on a frame
    download    Download assets from a frame
    upload      Upload assets to a frame
    sync        Synchronize assets between frames
    fit         Fit images to show complete picture (remove auto-crop)
    stats       Show statistics for a frame
    frames      List all available frames
    
Run 'python main.py <command> --help' for more information on a specific command.
"""

import argparse
import sys
from auramanager import AuraManager


def cmd_list(args, aura: AuraManager):
    """List assets on a frame."""
    frame_id = args.frame_id or aura.config["frames"][0]["frame_id"]
    
    if args.all:
        assets = aura.list_all_assets(write_to_file=args.save)
        for frame_id, frame_assets in assets.items():
            print(f"\n{frame_id}: {len(frame_assets)} assets")
    else:
        assets = aura.list_assets(frame_id, write_to_file=args.save)
        
        if args.verbose:
            for asset in assets:
                asset_type = "VIDEO" if asset.is_video else "PHOTO"
                print(f"  [{asset_type}] {asset.id} - {asset.file_name} ({asset.width}x{asset.height})")


def cmd_download(args, aura: AuraManager):
    """Download assets from a frame."""
    if args.all:
        results = aura.download_from_all_frames(
            photos_only=args.photos_only,
            videos_only=args.videos_only
        )
        print("\n" + "="*60)
        print("Summary:")
        for frame_id, (downloaded, skipped) in results.items():
            print(f"  {frame_id}: {downloaded} downloaded, {skipped} skipped")
    else:
        frame_id = args.frame_id or aura.config["frames"][0]["frame_id"]
        aura.download_all_assets(
            frame_id,
            output_dir=args.output,
            photos_only=args.photos_only,
            videos_only=args.videos_only,
            delay=args.delay
        )


def cmd_upload(args, aura: AuraManager):
    """Upload assets to a frame."""
    frame_id = args.frame_id or aura.config["frames"][0]["frame_id"]
    
    if args.file:
        # Upload single file
        result = aura.upload_file(frame_id, args.file, caption=args.caption)
        if result:
            print("Upload successful!")
        else:
            print("Upload failed.")
            sys.exit(1)
    elif args.directory:
        # Upload directory
        uploaded, failed = aura.upload_directory(
            frame_id,
            args.directory,
            photos_only=args.photos_only,
            videos_only=args.videos_only,
            delay=args.delay
        )
        if failed > 0:
            sys.exit(1)
    else:
        print("Error: Must specify --file or --directory")
        sys.exit(1)


def cmd_sync(args, aura: AuraManager):
    """Synchronize assets between frames."""
    if args.all:
        results = aura.sync_all_frames(
            photos_only=args.photos_only,
            videos_only=args.videos_only,
            dry_run=args.dry_run
        )
        print("\n" + "="*60)
        print("Summary:")
        for key, (synced, skipped) in results.items():
            print(f"  {key}: {synced} synced, {skipped} skipped")
    else:
        if not args.source or not args.target:
            print("Error: Must specify --source and --target frame IDs, or use --all")
            sys.exit(1)
        
        aura.sync_frames(
            args.source,
            args.target,
            photos_only=args.photos_only,
            videos_only=args.videos_only,
            dry_run=args.dry_run
        )


def cmd_fit(args, aura: AuraManager):
    """Fit images to show complete picture (remove auto-crop)."""
    if args.all:
        for frame in aura.config["frames"]:
            frame_id = frame["frame_id"]
            frame_name = frame.get("name", frame_id)
            print(f"\n{'='*60}")
            print(f"Processing: {frame_name}")
            print(f"{'='*60}")
            aura.fit_all_assets(frame_id, portraits_only=not args.include_landscape)
    else:
        frame_id = args.frame_id or aura.config["frames"][0]["frame_id"]
        aura.fit_all_assets(frame_id, portraits_only=not args.include_landscape)


def cmd_stats(args, aura: AuraManager):
    """Show statistics for a frame."""
    if args.all:
        for frame in aura.config["frames"]:
            frame_id = frame["frame_id"]
            frame_name = frame.get("name", frame_id)
            stats = aura.get_asset_stats(frame_id)
            print(f"\n{frame_name} ({frame_id}):")
            print(f"  Total assets: {stats['total']}")
            print(f"  Photos: {stats['photos']}")
            print(f"  Videos: {stats['videos']}")
            print(f"  Portrait: {stats['portrait']}")
            print(f"  Landscape: {stats['landscape']}")
    else:
        frame_id = args.frame_id or aura.config["frames"][0]["frame_id"]
        stats = aura.get_asset_stats(frame_id)
        print(f"Frame: {frame_id}")
        print(f"  Total assets: {stats['total']}")
        print(f"  Photos: {stats['photos']}")
        print(f"  Videos: {stats['videos']}")
        print(f"  Portrait: {stats['portrait']}")
        print(f"  Landscape: {stats['landscape']}")


def cmd_frames(args, aura: AuraManager):
    """List all available frames."""
    print("Configured frames:")
    for frame in aura.config["frames"]:
        frame_id = frame["frame_id"]
        frame_name = frame.get("name", frame_id)
        print(f"  {frame_name}: {frame_id}")
    
    print("\nFrames from account:")
    frames = aura.list_frames()
    for frame in frames:
        print(f"  {frame.get('name', 'Unknown')}: {frame.get('id', 'N/A')}")


def cmd_delete(args, aura: AuraManager):
    """Delete an asset from a frame."""
    frame_id = args.frame_id or aura.config["frames"][0]["frame_id"]
    
    if not args.asset_id:
        print("Error: Must specify --asset-id")
        sys.exit(1)
    
    if not args.force:
        confirm = input(f"Are you sure you want to delete asset {args.asset_id}? [y/N] ")
        if confirm.lower() != 'y':
            print("Cancelled.")
            return
    
    success = aura.delete_asset(frame_id, args.asset_id)
    if not success:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Aura Frame Manager - Manage photos and videos on Aura digital picture frames",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--config", 
        default="config.yaml", 
        help="Path to config file (default: config.yaml)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List assets on a frame")
    list_parser.add_argument("--frame-id", "-f", help="Frame ID to list assets from")
    list_parser.add_argument("--all", "-a", action="store_true", help="List assets from all frames")
    list_parser.add_argument("--save", "-s", action="store_true", help="Save asset data to debug file")
    list_parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed asset info")

    # Download command
    download_parser = subparsers.add_parser("download", help="Download assets from a frame")
    download_parser.add_argument("--frame-id", "-f", help="Frame ID to download from")
    download_parser.add_argument("--all", "-a", action="store_true", help="Download from all frames")
    download_parser.add_argument("--output", "-o", help="Output directory")
    download_parser.add_argument("--photos-only", action="store_true", help="Only download photos")
    download_parser.add_argument("--videos-only", action="store_true", help="Only download videos")
    download_parser.add_argument("--delay", type=float, default=0, help="Delay between downloads (seconds)")

    # Upload command
    upload_parser = subparsers.add_parser("upload", help="Upload assets to a frame")
    upload_parser.add_argument("--frame-id", "-f", help="Frame ID to upload to")
    upload_parser.add_argument("--file", help="Single file to upload")
    upload_parser.add_argument("--directory", "-d", help="Directory of files to upload")
    upload_parser.add_argument("--caption", "-c", help="Caption for uploaded file(s)")
    upload_parser.add_argument("--photos-only", action="store_true", help="Only upload photos")
    upload_parser.add_argument("--videos-only", action="store_true", help="Only upload videos")
    upload_parser.add_argument("--delay", type=float, default=2.0, help="Delay between uploads (seconds)")

    # Sync command
    sync_parser = subparsers.add_parser("sync", help="Synchronize assets between frames")
    sync_parser.add_argument("--source", "-s", help="Source frame ID")
    sync_parser.add_argument("--target", "-t", help="Target frame ID")
    sync_parser.add_argument("--all", "-a", action="store_true", help="Sync all frames with each other")
    sync_parser.add_argument("--photos-only", action="store_true", help="Only sync photos")
    sync_parser.add_argument("--videos-only", action="store_true", help="Only sync videos")
    sync_parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without doing it")

    # Fit command
    fit_parser = subparsers.add_parser("fit", help="Fit images to show complete picture")
    fit_parser.add_argument("--frame-id", "-f", help="Frame ID to process")
    fit_parser.add_argument("--all", "-a", action="store_true", help="Process all frames")
    fit_parser.add_argument("--include-landscape", action="store_true", help="Also fit landscape images")

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show statistics for a frame")
    stats_parser.add_argument("--frame-id", "-f", help="Frame ID to get stats for")
    stats_parser.add_argument("--all", "-a", action="store_true", help="Show stats for all frames")

    # Frames command
    subparsers.add_parser("frames", help="List all available frames")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete an asset from a frame")
    delete_parser.add_argument("--frame-id", "-f", help="Frame ID")
    delete_parser.add_argument("--asset-id", "-i", required=True, help="Asset ID to delete")
    delete_parser.add_argument("--force", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Initialize manager
    try:
        aura = AuraManager(config_path=args.config)
    except Exception as e:
        print(f"Error initializing AuraManager: {e}")
        sys.exit(1)

    # Dispatch to command handler
    commands = {
        "list": cmd_list,
        "download": cmd_download,
        "upload": cmd_upload,
        "sync": cmd_sync,
        "fit": cmd_fit,
        "stats": cmd_stats,
        "frames": cmd_frames,
        "delete": cmd_delete,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            handler(args, aura)
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            sys.exit(130)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
