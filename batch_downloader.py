import os
import sys
import json
import time
import shutil
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv
from dvr_api import IntelbrasDVR, NET_RECORDFILE_INFO
from static_ffmpeg import run as static_ffmpeg_run

# Optional import for Google Drive API
try:
    from google_drive_uploader import upload_file_to_drive
    HAS_DRIVE_API = True
except ImportError:
    HAS_DRIVE_API = False

# Target Cameras Configuration
TARGET_CAMERAS = [
    # DVR 1 (Cam1 - MHDX 3116-C)
    {"dvr": 1, "channel": 2, "name": "Externa Doc 1"},
    {"dvr": 1, "channel": 4, "name": "Externa Doc 3"},
    {"dvr": 1, "channel": 5, "name": "Externa Doc 4"},
    {"dvr": 1, "channel": 6, "name": "Externa Doc 2"},
    {"dvr": 1, "channel": 15, "name": "Ext Doc 5"},
    
    # DVR 2 (CAM2 - MHDX 1116-C)
    {"dvr": 2, "channel": 0, "name": "Int Doca 5"},
    {"dvr": 2, "channel": 1, "name": "Int Doca 6"},
    {"dvr": 2, "channel": 2, "name": "Int Doca 4"},
    {"dvr": 2, "channel": 3, "name": "Inte Doc 3"},
    {"dvr": 2, "channel": 4, "name": "Int Doc 1"},
    {"dvr": 2, "channel": 5, "name": "Int Doc 2"},
    {"dvr": 2, "channel": 11, "name": "Interna Escritorio"},
    {"dvr": 2, "channel": 7, "name": "Ext Doca 6"}
]

PROGRESS_FILE = "download_progress.json"

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not read progress file: {e}. Starting fresh.")
    return {"completed": []}

def save_progress(progress):
    temp_file = PROGRESS_FILE + ".tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(progress, f, indent=4)
        os.replace(temp_file, PROGRESS_FILE)
    except Exception as e:
        print(f"Error saving progress: {e}")

def get_dates(start_date_str, end_date_str):
    start = datetime.strptime(start_date_str, "%Y-%m-%d")
    end = datetime.strptime(end_date_str, "%Y-%m-%d")
    delta = timedelta(days=1)
    
    dates = []
    curr = start
    while curr <= end:
        dates.append(curr.strftime("%Y-%m-%d"))
        curr += delta
    return dates

def convert_to_mp4(dav_path, mp4_path):
    print(f"Converting '{os.path.basename(dav_path)}' to fMP4...")
    ffmpeg_path, _ = static_ffmpeg_run.get_or_fetch_platform_executables_else_raise()
    cmd = [
        ffmpeg_path, "-y",
        "-i", dav_path,
        "-codec", "copy",
        "-movflags", "frag_keyframe+empty_moov",
        mp4_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode == 0, res.stderr

def main():
    load_dotenv()
    progress = load_progress()
    
    host = os.getenv("HOST", "127.0.0.1")
    user = os.getenv("Usuario", "admin")
    password = os.getenv("Senha", "transbocayuva123")
    local_gd_path = os.getenv("LOCAL_GD_PATH", "")
    
    # Target date range
    start_date = "2026-06-21"
    end_date = "2026-07-04"
    dates = get_dates(start_date, end_date)
    
    print("=" * 60)
    print("      Intelbras NVR Batch Downloader & Cloud Uploader")
    print("=" * 60)
    print(f"Target Range: {start_date} to {end_date} ({len(dates)} days)")
    print(f"Total Cameras configured: {len(TARGET_CAMERAS)}")
    print(f"Loaded progress: {len(progress['completed'])} files already uploaded.")
    
    if local_gd_path:
        print(f"Upload Mode: Google Drive Desktop App (Base Folder: {local_gd_path})")
    else:
        print("Upload Mode: Google Drive API (via credentials.json)")
        
    print("=" * 60)
    
    # Loop through each day
    for date_idx, date in enumerate(dates):
        print(f"\n[DAY {date_idx+1}/{len(dates)}] Processing date: {date}...")
        
        # Loop through each camera
        for cam in TARGET_CAMERAS:
            dvr_id = cam["dvr"]
            channel = cam["channel"]
            cam_name = cam["name"]
            
            # Map port
            port = int(os.getenv(f"DVR{dvr_id}_PORT", "8487" if dvr_id == 1 else "32286"))
            
            print(f"\n-> Camera: {cam_name} (DVR {dvr_id}, Ch {channel}) on localhost:{port}")
            
            # Attempt to login with retry loop if DVR/SIM Next is offline
            dvr = None
            login_success = False
            retry_count = 0
            
            while not login_success:
                try:
                    dvr = IntelbrasDVR()
                    dvr.login(host, port, user, password)
                    login_success = True
                except Exception as e:
                    retry_count += 1
                    print(f"Connection failed: {e}. Retry #{retry_count} in 30 seconds...")
                    if dvr:
                        try:
                            dvr.close()
                        except Exception:
                            pass
                    time.sleep(30.0)
            
            try:
                # Search recordings for the entire day (00:00:00 to 23:59:59)
                start_dt = f"{date} 00:00:00"
                end_dt = f"{date} 23:59:59"
                
                files = dvr.search_recordings(channel, start_dt, end_dt, record_type=0)
                
                if not files:
                    print("   No recordings found on this date.")
                    continue
                    
                print(f"   Found {len(files)} record blocks.")
                
                for idx, file_info in enumerate(files):
                    # We create a unique progress key
                    start_time_clean = file_info["starttime"].replace(" ", "_").replace(":", "-")
                    progress_key = f"dvr{dvr_id}_ch{channel}_{start_time_clean}"
                    
                    if progress_key in progress["completed"]:
                        # Already uploaded, skip!
                        continue
                        
                    print(f"\n   [File {idx+1}/{len(files)}] Processing block starting at: {file_info['starttime']}")
                    
                    # File names
                    clean_cam_name = cam_name.replace(" ", "_").replace("/", "-")
                    time_range = start_time_clean + "_to_" + file_info["endtime"].split(" ")[1].replace(":", "-")
                    
                    # File naming: in structured folders, we can keep the filename clean (just the time range)
                    # Ex: "12-00-00_to_12-30-00.mp4"
                    short_time_range = start_time_clean.split("_")[1] + "_to_" + file_info["endtime"].split(" ")[1].replace(":", "-")
                    dav_filename = f"{clean_cam_name}_{time_range}.dav"
                    mp4_filename = f"{short_time_range}.mp4"
                    
                    dav_path = os.path.join(os.getcwd(), dav_filename)
                    mp4_path = os.path.join(os.getcwd(), mp4_filename)
                    
                    # 1. Download
                    try:
                        dvr.download_file(file_info, dav_path)
                    except Exception as e:
                        print(f"   ERROR downloading file: {e}. Skipping block.")
                        if os.path.exists(dav_path):
                            os.remove(dav_path)
                        continue
                        
                    # 2. Convert to fMP4
                    success, err_msg = convert_to_mp4(dav_path, mp4_path)
                    
                    # Clean up raw .dav file right after conversion
                    if os.path.exists(dav_path):
                        try:
                            os.remove(dav_path)
                        except Exception:
                            pass
                            
                    if not success:
                        print(f"   ERROR converting to MP4: {err_msg}. Skipping block.")
                        if os.path.exists(mp4_path):
                            os.remove(mp4_path)
                        continue
                        
                    # 3. Upload to Google Drive (Desktop Folder Copy or API Upload)
                    upload_success = False
                    
                    # Method A: Google Drive Desktop App (structured local folders copy)
                    if local_gd_path:
                        # Target structure: LOCAL_GD_PATH / Camera_Name / Date / File
                        target_dir = os.path.join(local_gd_path, clean_cam_name, date)
                        dest_path = os.path.join(target_dir, mp4_filename)
                        
                        try:
                            os.makedirs(target_dir, exist_ok=True)
                            print(f"   Copying converted MP4 to structured path: {dest_path}")
                            shutil.move(mp4_path, dest_path)
                            upload_success = True
                            print("   Successfully saved to Google Drive local folder (syncing in background).")
                        except Exception as e:
                            print(f"   ERROR copying to local Google Drive: {e}")
                    # Method B: Google Drive API (flat list or basic folder)
                    else:
                        if HAS_DRIVE_API:
                            try:
                                # Standard upload to GD_FOLDER_ID
                                upload_file_to_drive(mp4_path)
                                upload_success = True
                            except Exception as e:
                                print(f"   ERROR uploading to Google Drive API: {e}")
                        else:
                            print("   ERROR: No local Google Drive path specified and Google Drive API libraries are not available.")
                            
                    if upload_success:
                        # Record progress
                        progress["completed"].append(progress_key)
                        save_progress(progress)
                        print(f"   SUCCESS: Saved progress for {progress_key}")
                        
                        # Clean up local mp4 if it was not moved
                        if os.path.exists(mp4_path):
                            try:
                                os.remove(mp4_path)
                            except Exception:
                                pass
                    else:
                        print("   Upload failed. Keeping MP4 file locally to retry on next run.")
                        
                    # Pause briefly between blocks to let NVR/network breathe
                    time.sleep(2.0)
                    
            finally:
                if dvr:
                    dvr.close()
                    
            # Pause briefly between cameras
            time.sleep(5.0)

if __name__ == "__main__":
    main()
