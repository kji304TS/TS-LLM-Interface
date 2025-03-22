from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import traceback
import importlib
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError


app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://kji304ts.github.io"],  # ✅ YOUR GitHub Pages origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data model for request
class ScriptRequest(BaseModel):
    script_name: str
    start_date: str
    end_date: str

@app.get("/")
def read_root():
    return {"message": "Script Runner API is running"}

@app.post("/run-script/")
def run_script(data: ScriptRequest):
    print(f"✅ Received request to run: {data.script_name} from {data.start_date} to {data.end_date}")

    try:
        # Log environment variable status
        print("🧪 Checking environment variables...")
        creds = os.getenv("GOOGLE_CREDENTIALS_JSON")
        folder_id = os.getenv("GDRIVE_FOLDER_ID")
        print(f"🔍 GOOGLE_CREDENTIALS_JSON loaded: {'✅' if creds else '❌ MISSING'}")
        print(f"🔍 GDRIVE_FOLDER_ID loaded: {folder_id if folder_id else '❌ MISSING'}")

        # Import script module dynamically
        module_name = data.script_name.replace(".py", "")
        print(f"📦 Importing module: scripts.{module_name}")
        script_module = importlib.import_module(f"scripts.{module_name}")

        # Run the script's main_function
        if hasattr(script_module, "main_function"):
            print("🚀 Executing main_function...")
            result = script_module.main_function(data.start_date, data.end_date)
            print(f"✅ Script completed: {result if result else 'No return value'}")
        else:
            raise AttributeError(f"'main_function' not found in {data.script_name}")

        return {
            "output": f"{data.script_name} completed successfully.",
            "status": "success"
        }

    except Exception as e:
        print("❌ Error while running script:")
        traceback.print_exc()
        return {
            "output": f"Failed to run {data.script_name}",
            "error": str(e),
            "status": "failed"
        }

# Upload file to Google Drive
def upload_file_to_drive(file_path: str) -> str:
    print("🔐 Authenticating with Google Service Account...")

    try:
        creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not creds_json:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is not set")

        creds_dict = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
        )

        drive_service = build("drive", "v3", credentials=creds)

        folder_id = os.getenv("GDRIVE_FOLDER_ID")
        if not folder_id:
            raise ValueError("GDRIVE_FOLDER_ID is not set")

        file_metadata = {
            "name": os.path.basename(file_path),
            "parents": [folder_id]
        }

        media = MediaFileUpload(file_path, resumable=True)
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        # Make the file publicly viewable
        drive_service.permissions().create(
            fileId=uploaded_file["id"],
            body={"type": "anyone", "role": "reader"}
        ).execute()

        file_url = f"https://drive.google.com/file/d/{uploaded_file['id']}/view"
        print(f"✅ File uploaded: {file_url}")
        return file_url

    except HttpError as error:
        print(f"❌ Google Drive API error: {error}")
        raise

    except Exception as e:
        print(f"❌ Unexpected error during upload: {e}")
        raise



