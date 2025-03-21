from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import traceback
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

app = FastAPI()

# CORS setup — allows requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict this to ["https://kji304ts.github.io"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Model for incoming POST data
class ScriptRequest(BaseModel):
    script_name: str
    start_date: str
    end_date: str

# Root route for sanity check
@app.get("/")
def read_root():
    return {"message": "Script Runner API is running"}

# Main POST route
@app.post("/run-script/")
def run_script(data: ScriptRequest):
    print(f"▶️ Received request to run {data.script_name} from {data.start_date} to {data.end_date}")

    try:
        # Step 1: Run the script
        script_path = f"scripts/{data.script_name}"
        command = f"python {script_path} {data.start_date} {data.end_date}"
        print(f"📄 Running command: {command}")
        result_code = os.system(command)

        if result_code != 0:
            raise RuntimeError(f"Script exited with non-zero code: {result_code}")

        # Step 2: Define the expected output file (adjust as needed)
        output_file = "wallet_conversations.xlsx"
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
        print("❌ An error occurred:")
        traceback.print_exc()
        return {
            "output": f"Failed to run {data.script_name}",
            "error": str(e),
            "status": "failed"
        }

# Google Drive uploader
def upload_file_to_drive(file_path: str) -> str:
    print("🔐 Authenticating with Google Drive...")

    gauth = GoogleAuth()
    gauth.LoadCredentialsFile("credentials.json")

    if gauth.credentials is None:
        print("⚠️ No saved credentials found. Attempting webserver auth...")
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        print("🔄 Access token expired. Refreshing...")
        gauth.Refresh()
    else:
        print("✅ Credentials loaded.")
        gauth.Authorize()

    gauth.SaveCredentialsFile("credentials.json")

    drive = GoogleDrive(gauth)

    folder_id = os.getenv("GDRIVE_FOLDER_ID")
    if not folder_id:
        raise ValueError("GDRIVE_FOLDER_ID environment variable is not set.")

    file_name = os.path.basename(file_path)
    file = drive.CreateFile({
        "title": file_name,
        "parents": [{"id": folder_id}]
    })
    file.SetContentFile(file_path)
    file.Upload()

    print(f"✅ File '{file_name}' uploaded to Google Drive folder '{folder_id}'.")

    # Make file publicly viewable
    file.InsertPermission({
        'type': 'anyone',
        'value': 'anyone',
        'role': 'reader'
    })

    return f"https://drive.google.com/file/d/{file['id']}/view"



