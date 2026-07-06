import os
import io
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from dotenv import load_dotenv

# Load settings from .env file
load_dotenv()

# File paths (make sure credentials_drive.json is placed in the same folder on Linux)
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials_drive.json")
SCOPES = ['https://www.googleapis.com/auth/drive']
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "gravacoes_baixadas")

def get_drive_service():
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"Credentials file not found at '{CREDENTIALS_FILE}'. "
            "Please copy 'credentials_drive.json' (the Service Account key) to your Linux server."
        )
    
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)

def download_all_files(folder_id=None, dest_dir=DOWNLOAD_DIR):
    """
    Lists all files in the shared Google Drive folder and downloads them to dest_dir.
    """
    os.makedirs(dest_dir, exist_ok=True)
    service = get_drive_service()
    
    # Read folder ID from .env if not provided
    if not folder_id:
        folder_id = os.getenv("GD_FOLDER_ID")
        
    if not folder_id:
        raise ValueError("GD_FOLDER_ID must be specified in the environment or passed as an argument.")
        
    print(f"Reading files from Google Drive folder: {folder_id}...")
    
    # Query files in the folder
    query = f"'{folder_id}' in parents and trashed = false"
    try:
        results = service.files().list(
            q=query,
            fields="files(id, name, size)",
            pageSize=1000
        ).execute()
        
        files = results.get('files', [])
        if not files:
            print("No files found in the Google Drive folder.")
            return
            
        print(f"Found {len(files)} files to download.")
        
        for file in files:
            file_id = file['id']
            file_name = file['name']
            file_size = int(file.get('size', 0)) / (1024.0 * 1024.0)
            
            dest_path = os.path.join(dest_dir, file_name)
            
            # Skip download if file already exists locally with same size
            if os.path.exists(dest_path):
                # Small tolerance on file size check
                if abs(os.path.getsize(dest_path) - int(file.get('size', 0))) < 1024:
                    print(f"File '{file_name}' already downloaded. Skipping.")
                    continue
            
            print(f"\nDownloading '{file_name}' ({file_size:.2f} MB)...")
            
            # Download file chunk by chunk
            request = service.files().get_media(fileId=file_id)
            fh = io.FileIO(dest_path, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    print(f"Progress: {int(status.progress() * 100)}%", end="\r")
                    
            print(f"Download complete! Saved to: {dest_path}")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # You can set the folder ID in the .env of your Linux server, or pass it directly
    # e.g., download_all_files("1PCQ_BeBs55qlDEVJcG4LnrCXjqHEhYKV")
    try:
        # We use the folder ID shared by the user
        folder_id = "1PCQ_BeBs55qlDEVJcG4LnrCXjqHEhYKV"
        download_all_files(folder_id)
    except Exception as e:
        print(f"Error: {e}")
