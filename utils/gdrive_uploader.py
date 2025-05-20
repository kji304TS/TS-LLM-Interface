import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# Load .env variables, in case this module is used somewhere that hasn't loaded them yet
# (though app.py and LLM5.py usually do)
load_dotenv()

def upload_file_to_drive(file_path: str) -> str | None:
    print("🔐 Authenticating with Google Service Account for GDrive upload...")

    try:
        creds_json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not creds_json_str:
            print("❌ GOOGLE_SERVICE_ACCOUNT_JSON is not set in .env")
            # raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not set") # Or return None
            return None 

        folder_id = os.getenv("GDRIVE_FOLDER_ID")
        if not folder_id:
            print("❌ GDRIVE_FOLDER_ID is not set in .env")
            # raise ValueError("GDRIVE_FOLDER_ID is not set") # Or return None
            return None

        try:
            creds_dict = json.loads(creds_json_str)
        except json.JSONDecodeError as e:
            print(f"❌ Error decoding GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
            return None
            
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
        )

        drive_service = build("drive", "v3", credentials=creds)

        file_metadata = {
            "name": os.path.basename(file_path),
            "parents": [folder_id]
        }

        media = MediaFileUpload(file_path, resumable=True)
        
        print(f"☁️ Uploading {os.path.basename(file_path)} to Google Drive folder ID: {folder_id}...")
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink" # Get webViewLink directly
        ).execute()

        file_url = uploaded_file.get("webViewLink") # Use webViewLink for direct browser access
        if not file_url: # Fallback if webViewLink is not present for some reason
             file_url = f"https://drive.google.com/file/d/{uploaded_file['id']}/view" 

        # Make the file publicly viewable (optional, consider your security needs)
        # If you want files to be private to specific accounts, this permission needs to be more granular
        # or removed if the service account has direct share rights to target users/groups.
        try:
            drive_service.permissions().create(
                fileId=uploaded_file["id"],
                body={"type": "anyone", "role": "reader"}
            ).execute()
            print(f"   🌍 File made publicly viewable.")
        except HttpError as perm_error:
            print(f"   ⚠️ Could not set public permissions for {file_path}: {perm_error}. File might be private.")


        print(f"✅ File uploaded: {file_url}")
        return file_url

    except HttpError as error:
        print(f"❌ Google Drive API error during upload of {file_path}: {error}")
        # raise # Or return None
        return None

    except Exception as e:
        print(f"❌ Unexpected error during upload of {file_path}: {e}")
        # raise # Or return None
        return None 