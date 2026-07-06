import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

# Load settings from .env file
load_dotenv()

# File paths
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")

# Google Drive API Scopes (Read/Write access)
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive']

def get_drive_service():
    """
    Initializes and returns the Google Drive API service using OAuth 2.0 User credentials.
    Performs interactive login on first run and saves a refresh token in token.json.
    """
    creds = None
    
    # Check if we already have a saved token
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            print(f"Warning: Could not read token file: {e}. Re-authenticating.")
            
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing Google Drive access token...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Failed to refresh token: {e}. Full login required.")
                creds = None
                
        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Credentials file not found at '{CREDENTIALS_FILE}'. "
                    "Please download the OAuth 2.0 Client credentials JSON file from Google Cloud Console "
                    "and save it in the project root as 'credentials.json'."
                )
            print("\n" + "=" * 60)
            print("ACTION REQUIRED: A browser window will open to authenticate your Google Account.")
            print("Please sign in and verify the app (even if it says 'unverified' - click Advanced -> Go to DVR Downloader).")
            print("=" * 60 + "\n")
            
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            print(f"Saved authentication token to: {TOKEN_FILE}")
            
    return build('drive', 'v3', credentials=creds)

def upload_file_to_drive(file_path, folder_id=None):
    """
    Uploads a file to a specific folder in Google Drive.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Local file to upload not found: '{file_path}'")
        
    service = get_drive_service()
    
    # If no folder_id is provided, read it from .env
    if not folder_id:
        folder_id = os.getenv("GD_FOLDER_ID")
        
    file_name = os.path.basename(file_path)
    print(f"Uploading '{file_name}' to Google Drive...")
    
    # Metadata for Google Drive upload
    file_metadata = {
        'name': file_name
    }
    
    # If a folder ID is defined, upload inside it
    if folder_id:
        file_metadata['parents'] = [folder_id]
        print(f"Destination Google Drive Folder ID: {folder_id}")
    else:
        print("Warning: No GD_FOLDER_ID specified. File will be uploaded to the root of your Google Drive.")
        
    media = MediaFileUpload(file_path, resumable=True)
    
    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        file_id = file.get('id')
        print(f"Upload SUCCESS! Google Drive File ID: {file_id}")
        return file_id
    except Exception as e:
        print(f"Failed to upload to Google Drive: {e}")
        raise e
