from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import traceback
import importlib
import json
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict to ["https://kji304ts.github.io"]
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
    print("🔐 Authenticating with Google Drive...")

    creds_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_str:
        raise ValueError("GOOGLE_CREDENTIALS_JSON is not set")

    with open("credentials.json", "w") as f:
        f.write(creds_str)

    gauth = GoogleAuth()
    gauth.LoadCredentialsFile("credentials.json")

    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()

    gauth.SaveCredentialsFile("credentials.json")
    drive = GoogleDrive(gauth)

    folder_id = os.getenv("GDRIVE_FOLDER_ID")
    if not folder_id:
        raise ValueError("GDRIVE_FOLDER_ID is not set")

    file_name = os.path.basename(file_path)
    file = drive.CreateFile({
        "title": file_name,
        "parents": [{"id": folder_id}]
    })
    file.SetContentFile(file_path)
    file.Upload()

    file.InsertPermission({
        'type': 'anyone',
        'value': 'anyone',
        'role': 'reader'
    })

    print(f"✅ File '{file_name}' uploaded to Google Drive.")
    return f"https://drive.google.com/file/d/{file['id']}/view"



