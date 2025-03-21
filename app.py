from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import traceback
import json
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

app = FastAPI()

# CORS config — allows frontend (e.g. GitHub Pages) to access this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict this later to ["https://kji304ts.github.io"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request schema
class ScriptRequest(BaseModel):
    script_name: str
    start_date: str
    end_date: str

# Health check route
@app.get("/")
def read_root():
    return {"message": "Script Runner API is running"}

# Run script and upload result to Google Drive
@app.post("/run-script/")
def run_script(data: ScriptRequest):
    print(f"▶️ Received request to run: {data.script_name} from {data.start_date} to {data.end_date}")

    try:
        # Step 1: Run the script
        script_path = f"scripts/{data.script_name}"
        command = f"python {script_path} {data.start_date} {data.end_date}"
        print(f"📄 Executing command: {command}")
        result_code = os.system(command)

        if result_code != 0:
            raise RuntimeError(f"Script exited with non-zero code: {result_code}")

        # Step 2: Locate the expected output file
        output_file = "wallet_conversations.xlsx"  # Change if script outputs differently
        if not os.path.exists(output_file):
            raise FileNotFoundError(f"Output file not found: {output_file}")

        # Step 3: Upload file to Google Drive
        print("📤 Uploading file to Google Drive...")
        drive_url = upload_file_to_drive(output_file)
        print(f"✅ Upload successful: {drive_url}")

        return {
            "output": f"{data.script_name} completed successfully.",
            "drive_url": drive_url,
            "status": "success"
        }

    except Exception as e:
        print("❌ Error during execution:")
        traceback.print_exc()
        return {
            "output": f"Failed to run {data.script_name}",
            "error": str(e),
            "status": "failed"
        }

# Google Drive uploader using env-based credentials
def upload_file_to_drive(file_path: str) -> str:
    print("🔐 Authenticating with Google Drive...")

    # Load credentials.json content from env
    creds_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_str:
        raise ValueError("GOOGLE_CREDENTIALS_JSON is not set")

    # Write to credentials.json file so PyDrive can use it
    with open("credentials.json", "w") as f:
        f.write(creds_str)

    # Authenticate via PyDrive
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile("credentials.json")

    if gauth.credentials is None:
        print("⚠️ No saved credentials. Launching local webserver auth...")
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        print("🔄 Refreshing expired token...")
        gauth.Refresh()
    else:
        print("✅ Credentials loaded.")
        gauth.Authorize()

    gauth.SaveCredentialsFile("credentials.json")
    drive = GoogleDrive(gauth)

    # Read Drive folder ID from env
    folder_id = os.getenv("GDRIVE_FOLDER_ID")
    if not folder_id:
        raise ValueError("GDRIVE_FOLDER_ID is not set in environment variables")

    file_name = os.path.basename(file_path)
    file = drive.CreateFile({
        "title": file_name,
        "parents": [{"id": folder_id}]
    })
    file.SetContentFile(file_path)
    file.Upload()

    # Set file to publicly viewable
    file.InsertPermission({
        'type': 'anyone',
        'value': 'anyone',
        'role': 'reader'
    })

    print(f"✅ File '{file_name}' uploaded successfully.")
    return f"https://drive.google.com/file/d/{file['id']}/view"



