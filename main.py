import os
import argparse
import shutil
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv
from dvr_api import IntelbrasDVR
from static_ffmpeg import run as static_ffmpeg_run

# Optional import for Google Drive uploader
try:
    from google_drive_uploader import upload_file_to_drive
    HAS_DRIVE_API = True
except ImportError:
    HAS_DRIVE_API = False

def main():
    # Load settings from .env file
    load_dotenv()
    
    # Defaults from .env or fallback
    default_host = os.getenv("HOST", "127.0.0.1")
    default_user = os.getenv("Usuario", "admin")
    default_pass = os.getenv("Senha", "transbocayuva123")
    
    parser = argparse.ArgumentParser(description="Intelbras NVR/DVR Recordings Downloader")
    parser.add_argument("--dvr", type=int, choices=[1, 2], default=2, help="Target DVR (1 for Cam1, 2 for Transbocayuva; default: 2)")
    parser.add_argument("--host", default=default_host, help="DVR Hostname or IP address (default: localhost)")
    parser.add_argument("--port", type=int, default=0, help="DVR NetSDK port (overrides --dvr port selection)")
    parser.add_argument("--user", default=default_user, help="DVR username (default: admin)")
    parser.add_argument("--password", default=default_pass, help="DVR password")
    parser.add_argument("--channel", type=int, default=0, help="Channel number (0 to 15, default: 0)")
    
    # Date/time settings
    parser.add_argument("--date", default="2026-07-05", help="Date to search (YYYY-MM-DD, default: 2026-07-05)")
    parser.add_argument("--start-time", default="12:00:00", help="Start time (HH:MM:SS, default: 12:00:00)")
    parser.add_argument("--end-time", default="12:05:00", help="End time (HH:MM:SS, default: 12:05:00)")
    
    parser.add_argument("--output", default="", help="Output path for downloaded file")
    parser.add_argument("--search-only", action="store_true", help="Only list files, do not download")
    parser.add_argument("--download-full-file", action="store_true", help="Download the full 30-minute block containing the timeframe")
    parser.add_argument("--convert", action="store_true", help="Automatically convert downloaded .dav to fragmented .mp4 (fMP4)")
    parser.add_argument("--upload", action="store_true", help="Automatically upload converted .mp4 to Google Drive and clean up locally")
    
    args = parser.parse_args()
    
    # If upload is requested, auto-enable convert
    if args.upload:
        args.convert = True
            
    # Port selection logic
    if args.port == 0:
        if args.dvr == 1:
            args.port = int(os.getenv("DVR1_PORT", "8487"))
        else:
            args.port = int(os.getenv("DVR2_PORT", "32286"))
            
    dvr_name = os.getenv(f"DVR{args.dvr}_NAME", f"DVR {args.dvr}")
    
    print("=" * 60)
    print("      Intelbras NVR/DVR Recordings Downloader")
    print("=" * 60)
    print(f"Target: {args.host}:{args.port} ({dvr_name})")
    print(f"User: {args.user}")
    print(f"Channel: {args.channel}")
    print(f"Target Date/Time: {args.date} {args.start_time} to {args.end_time}")
    print("=" * 60)
    
    # Make sure output path is valid
    start_dt = f"{args.date} {args.start_time}"
    end_dt = f"{args.date} {args.end_time}"
    
    if not args.output:
        # Default filename based on channel and timeframe
        safe_start = start_dt.replace(" ", "_").replace(":", "-")
        safe_end = args.end_time.replace(":", "-")
        args.output = os.path.join(os.getcwd(), f"clip_dvr{args.dvr}_ch{args.channel}_{safe_start}_to_{safe_end}.dav")
        
    # Check if SIM Next is running
    if args.host in ["127.0.0.1", "localhost"]:
        print("NOTE: Connecting via localhost. Please make sure the 'SIM Next' app is running")
        print("      so it can bridge the connection to your remote NVR.")
        print("-" * 60)
        
    try:
        # Initialize DVR connection
        dvr = IntelbrasDVR()
        
        # Connect
        dev_info = dvr.login(args.host, args.port, args.user, args.password)
        
        # Search files matching the timeframe
        files = dvr.search_recordings(args.channel, start_dt, end_dt, record_type=0)
        
        if not files:
            print("\nNo recording files found for the specified timeframe.")
            print("Try checking if the camera is online or if it has recordings on other hours.")
            dvr.close()
            return
            
        print("\n=== RECORDINGS FOUND ===")
        for idx, f in enumerate(files):
            print(f"[{idx}] {f['filename']} ({f['size_mb']:.2f} MB)")
            print(f"    Start: {f['starttime']} | End: {f['endtime']}")
            
        if args.search_only:
            print("\nSearch-only mode enabled. Skipping download.")
            dvr.close()
            return
            
        # Download
        print("-" * 60)
        if args.download_full_file:
            # Download the first matching file block entirely
            first_file = files[0]
            print(f"Downloading the entire block containing the timeframe:")
            print(f"File: {first_file['filename']} ({first_file['size_mb']:.2f} MB)")
            dvr.download_file(first_file, args.output)
            print(f"\nDownload finished successfully! Saved to: {args.output}")
        else:
            # Download the exact timeframe requested
            print(f"Downloading clip of exact timeframe: {start_dt} to {end_dt}...")
            dvr.download_by_time(args.channel, start_dt, end_dt, args.output, record_type=0)
            
            if os.path.exists(args.output):
                size_kb = os.path.getsize(args.output) / 1024.0
                print(f"\nDownload finished! Saved to: {args.output} (Size: {size_kb:.2f} KB)")
                if size_kb < 100:
                    print("Note: The clip is very small. If the DVR is set to motion-only,")
                    print("      this indicates there was no motion on this camera during this period.")
                    
        # Close connection
        dvr.close()
        
        # Post-download conversion if requested
        mp4_output = None
        if args.convert and os.path.exists(args.output):
            print("\n" + "=" * 60)
            print("Converting .dav to fragmented .mp4 (fMP4)...")
            try:
                # Get static ffmpeg path
                ffmpeg_path, _ = static_ffmpeg_run.get_or_fetch_platform_executables_else_raise()
                mp4_output = args.output.rsplit(".", 1)[0] + ".mp4"
                
                cmd = [
                    ffmpeg_path, "-y",
                    "-i", args.output,
                    "-codec", "copy",
                    "-movflags", "frag_keyframe+empty_moov",
                    mp4_output
                ]
                
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if res.returncode == 0:
                    print(f"Conversion SUCCESS! fMP4 file saved to: {mp4_output}")
                    print(f"fMP4 Size: {os.path.getsize(mp4_output) / (1024.0 * 1024.0):.2f} MB")
                    # Delete original .dav file
                    try:
                        os.remove(args.output)
                        print("Cleaned up original .dav file.")
                    except Exception as e:
                        print(f"Could not remove original .dav: {e}")
                else:
                    print("Conversion failed. FFmpeg output:")
                    print(res.stderr)
                    mp4_output = None
            except Exception as e:
                print(f"Failed to convert: {e}")
                mp4_output = None
                
        # Google Drive Upload
        if args.upload and mp4_output and os.path.exists(mp4_output):
            print("\n" + "=" * 60)
            print("Uploading fMP4 file to Google Drive...")
            
            local_gd_path = os.getenv("LOCAL_GD_PATH", "")
            
            # Method A: Google Drive Desktop App (local copy)
            if local_gd_path:
                dest_path = os.path.join(local_gd_path, os.path.basename(mp4_output))
                print(f"Copying fMP4 to Google Drive Desktop folder: {dest_path}")
                try:
                    os.makedirs(local_gd_path, exist_ok=True)
                    shutil.move(mp4_output, dest_path)
                    print("SUCCESS! File saved to Google Drive Desktop folder (syncing in background).")
                except Exception as e:
                    print(f"Failed to copy to Google Drive local folder: {e}")
            # Method B: Google Drive API
            else:
                if HAS_DRIVE_API:
                    try:
                        drive_file_id = upload_file_to_drive(mp4_output)
                        if drive_file_id:
                            try:
                                os.remove(mp4_output)
                                print("Cleaned up local fMP4 file after successful upload.")
                            except Exception as e:
                                print(f"Could not remove local fMP4: {e}")
                    except Exception as e:
                        print(f"Failed to upload to Google Drive API: {e}")
                else:
                    print("ERROR: Google Drive API libraries are not available and LOCAL_GD_PATH is not set in .env")
                
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        
if __name__ == "__main__":
    main()
