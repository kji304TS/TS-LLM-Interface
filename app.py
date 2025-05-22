print("############ I AM DEFINITELY RUNNING THIS app.py - VERSION 1 ############")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import traceback
import importlib
import zipfile
import io


# --- Import GDrive uploader --- 
from utils.gdrive_uploader import upload_file_to_drive
from utils.time_utils import calculate_dates_from_preset # New import
from utils.intercom_team_fetcher import get_intercom_teams # Import for fetching teams

# --- Scheduler Imports ---
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
import asyncio # For async sleep in scheduler if needed, and for lifespan

# --- Import the specific main_function from LLM5 for the scheduled task AND direct call debugging ---
try:
    from scripts.LLM5 import main_function as llm5_main_function_direct
    print("✅✅ Successfully directly imported main_function from scripts.LLM5 as llm5_main_function_direct.")
except ImportError as e:
    llm5_main_function_direct = None
    print("❌❌ FAILED to directly import main_function from scripts.LLM5. Direct calls will fail.")
    print("ImportError details for direct import:")
    traceback.print_exc()

# --- Scheduler Setup ---
scheduler = BackgroundScheduler(timezone="UTC")

def scheduled_llm5_job():
    """Defines the job to be run by the scheduler."""
    print(f"⏰ [{datetime.now(timezone.utc)}] Running scheduled LLM5 task...")
    try:
        # Calculate date range for the last 8 hours
        end_date_dt = datetime.now(timezone.utc)
        start_date_dt = end_date_dt - timedelta(hours=8)
        
        start_date_str = start_date_dt.strftime("%Y-%m-%d %H:%M")
        end_date_str = end_date_dt.strftime("%Y-%m-%d %H:%M")

        print(f"🗓️  Scheduled task for period: {start_date_str} to {end_date_str}")

        if llm5_main_function_direct:
            # Run the LLM5 script's main function
            # We might want to make upload_to_gdrive configurable here too, e.g., via env var
            result = llm5_main_function_direct(
                start_date_str=start_date_str,
                end_date_str=end_date_str,
                upload_to_gdrive=True,  # Or False, or from config
                send_to_slack=True      # Ensure Slack notifications are enabled
            )
            print(f"✅ Scheduled LLM5 task completed. Result: {result.get('message', 'No message')}")
        else:
            print("❌ llm5_main_function_direct not available. Scheduled task cannot run.")

    except Exception as e:
        print(f"❌ Error during scheduled LLM5 task: {e}")
        traceback.print_exc()

# --- FastAPI Lifespan for Scheduler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 FastAPI app starting up...")
    if llm5_main_function_direct:
        # Add job to scheduler - runs every 8 hours
        # For testing, you might want a shorter interval initially, e.g., minutes=1
        scheduler.add_job(scheduled_llm5_job, 'interval', hours=8, id="llm5_8hr_report")
        # scheduler.add_job(scheduled_llm5_job, 'interval', minutes=1, id="llm5_test_report") # For quick testing
        print("⏳ LLM5 reporting job scheduled to run every 8 hours.")
    else:
        print("🚫 LLM5 reporting job NOT scheduled because main_function_direct could not be imported.")
    
    scheduler.start()
    print("🕒 Scheduler started.")
    try:
        yield
    finally:
        print("🛑 FastAPI app shutting down...")
        if scheduler.running:
            scheduler.shutdown()
            print("Scheduler shut down.")

# Pass lifespan to FastAPI app
app = FastAPI(lifespan=lifespan)

# Updated Data model for request
class ScriptRequest(BaseModel):
    script_name: str
    start_date: str | None = None 
    end_date: str | None = None   
    timeframe_preset: str | None = None 
    upload_to_gdrive: bool = False
    target_team: str | None = None
    target_product_area: str | None = None

class ZipRequest(BaseModel):
    filenames: list[str]

# --- VERY BASIC TEST ROUTES (TEMPORARY - CAN BE REMOVED LATER) ---
@app.get("/api/teams-test")
async def api_get_teams_test():
    print("!!!! /api/teams-test HIT !!!!")
    return {"test_team_1": "id1", "test_team_2": "id2"}

@app.post("/run-script-test/")
async def run_script_test(data: ScriptRequest):
    print("!!!! /run-script-test/ HIT !!!!")
    print(f"Test data received: {data}")
    return {"status": "test_success", "message": "Test script ran", "input_data": data.model_dump()}

# +++ NEW DIAGNOSTIC ROUTE +++
@app.post("/test-post-new/")
async def test_post_new_endpoint(data: ScriptRequest): # Can reuse ScriptRequest or a simpler model
    print("!!!! /test-post-new/ POST endpoint HIT !!!!")
    print(f"Test data for /test-post-new/: {data}")
    return {"status": "success_new_test_post", "message": "New POST endpoint is working!", "received_data": data.model_dump()}
# +++ END NEW DIAGNOSTIC ROUTE +++

# --- END OF TEST ROUTES ---

# CORS setup 
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://kji304ts.github.io", 
        "http://192.168.0.27:8080",  
        "http://localhost:8080",     
        "http://127.0.0.1:8080",   
        "http://localhost", 
        "http://127.0.0.1"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/run-script/")
def run_script(data: ScriptRequest):
    actual_start_date = data.start_date
    actual_end_date = data.end_date
    source_of_dates = "direct input" # Assume direct input initially

    if data.script_name == "LLM5.py" and data.timeframe_preset:
        print(f"⏳ Calculating dates for LLM5.py using preset: {data.timeframe_preset}")
        actual_start_date, actual_end_date = calculate_dates_from_preset(data.timeframe_preset)
        print(f"   Calculated Start (from preset): {actual_start_date}, End (from preset): {actual_end_date}")
        source_of_dates = "preset"
    
    if source_of_dates == "direct input" and actual_start_date and actual_end_date:
        try:
            current_year = datetime.now().year
            dt_start_original = datetime.strptime(actual_start_date, "%Y-%m-%d %H:%M")
            if dt_start_original.year != current_year:
                new_start_dt = dt_start_original.replace(year=current_year)
                print(f"   Overriding year for start_date. Original: {actual_start_date}, New: {new_start_dt.strftime('%Y-%m-%d %H:%M')}")
                actual_start_date = new_start_dt.strftime("%Y-%m-%d %H:%M")
            dt_end_original = datetime.strptime(actual_end_date, "%Y-%m-%d %H:%M")
            if dt_end_original.year != current_year:
                new_end_dt = dt_end_original.replace(year=current_year)
                print(f"   Overriding year for end_date. Original: {actual_end_date}, New: {new_end_dt.strftime('%Y-%m-%d %H:%M')}")
                actual_end_date = new_end_dt.strftime("%Y-%m-%d %H:%M")
        except ValueError as e:
            print(f"   Warning: Could not parse/adjust input dates to current year: {e}. Using dates as provided by user.")
    
    if not actual_start_date or not actual_end_date:
        return {"output": "Failed: Valid start and end dates could not be determined. Please check your input or preset.", "error": "Missing or invalid date parameters", "status": "failed"}

    print(f"✅ Received request to run: {data.script_name}")
    print(f"   Using effective Start Date: {actual_start_date}, End Date: {actual_end_date}")
    print(f"📁 Storage mode: {'Google Drive' if data.upload_to_gdrive else 'Local'}")
    if data.script_name == "LLM5.py":
        print(f"🎯 Targeting - Team: {data.target_team or 'All'}, Product Area: {data.target_product_area or 'All'}")

    try:
        print("🧪 Checking environment variables...")
        folder_id = os.getenv("GDRIVE_FOLDER_ID")
        print(f"🔍 GDRIVE_FOLDER_ID loaded: {folder_id if folder_id else '❌ MISSING'}")
        module_name = data.script_name.replace(".py", "")
        print(f"📦 Importing module: scripts.{module_name}")
        script_module = importlib.import_module(f"scripts.{module_name}")
        if hasattr(script_module, "main_function"):
            print("🚀 Executing main_function...")
            main_func_args = {
                "start_date_str": actual_start_date,
                "end_date_str": actual_end_date,
                "upload_to_gdrive": data.upload_to_gdrive
            }
            if data.script_name == "LLM5.py":
                main_func_args["send_to_slack"] = True
                main_func_args["target_team_name"] = data.target_team if data.target_team and data.target_team != "ALL_TEAMS" else None
                main_func_args["target_product_area_name"] = data.target_product_area if data.target_product_area and data.target_product_area != "ALL_AREAS" else None
            result = script_module.main_function(**main_func_args)
            if isinstance(result, dict):
                print(f"✅ Script completed: {result.get('message', 'No message')}")
                processed_counts = result.get("processed_counts", {})
                return {
                    "output": result.get("message", "Completed."),
                    "status": result.get("status", "success"),
                    "file": result.get("file"),
                    "local_files": result.get("local_files", []), 
                    "gdrive_urls": result.get("gdrive_urls", []),
                    "storage_mode": "gdrive" if data.upload_to_gdrive else "local",
                    "processed_counts": processed_counts
                }
            else:
                print("✅ Script completed with no structured result.")
                return {
                    "output": str(result),
                    "status": "success",
                    "storage_mode": "gdrive" if data.upload_to_gdrive else "local"
                }
        else:
            raise AttributeError(f"'main_function' not found in {data.script_name}")
    except Exception as e:
        print("❌ Error while running script:")
        traceback.print_exc()
        return {
            "output": f"Failed to run {data.script_name}", 
            "error": str(e), 
            "status": "failed"
        }

# Restored functional /api/teams endpoint
@app.get("/api/teams")
async def api_get_teams():
    print("🚀 API call received for /api/teams (functional version)")
    try:
        teams_map = get_intercom_teams() 
        if teams_map is not None:
            print(f"✅ Successfully fetched {len(teams_map)} teams for API response.")
            return teams_map 
        else:
            print("❌ Failed to fetch teams from intercom_team_fetcher for API (teams_map is None).")
            raise HTTPException(status_code=500, detail="Failed to fetch Intercom teams (teams_map is None)")
    except Exception as e:
        print(f"❌ Error in /api/teams endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error fetching teams: {str(e)}")

@app.get("/download/{filename}")
async def download_file(filename: str):
    # Sanitize filename to prevent directory traversal attacks
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    
    # --- MODIFIED: Search in multiple known output directories --- 
    possible_base_dirs = [
        "output_files", 
        "Outputs", 
        os.path.join("Outputs", "team_reports") 
    ]

    file_path_to_serve = None
    for base_dir in possible_base_dirs:
        potential_path = os.path.join(base_dir, filename)
        if os.path.exists(potential_path) and os.path.isfile(potential_path):
            file_path_to_serve = potential_path
            break # Found the file
    # --- END MODIFICATION ---

    if not file_path_to_serve:
        print(f"❌ File not found for download in any known directory: {filename}")
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    
    # if not os.path.isfile(file_path_to_serve): # This check is now implicitly handled by the loop
    #     print(f"❌ Path is not a file for download: {file_path_to_serve}")
    #     raise HTTPException(status_code=400, detail=f"Path is not a file: {filename}")

    print(f"🔽 Preparing download for: {file_path_to_serve}")
    return FileResponse(
        path=file_path_to_serve, 
        filename=filename, 
        media_type='application/octet-stream',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/download-zip/")
async def download_zip(data: ZipRequest):
    print(f"📦 Request to zip and download files: {data.filenames}")
    if not data.filenames:
        raise HTTPException(status_code=400, detail="No filenames provided to zip.")

    output_dir = "output_files"  # Consistent with /download/{filename}
    
    # Create a BytesIO buffer to hold the zip file in memory
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in data.filenames:
            # Sanitize filename
            if ".." in filename or filename.startswith("/"):
                print(f"⚠️ Invalid or potentially malicious filename skipped: {filename}")
                continue # Skip potentially malicious filenames

            file_path = os.path.join(output_dir, filename)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                zf.write(file_path, arcname=filename) # arcname ensures filename in zip is not nested
                print(f"  + Added to zip: {file_path}")
            else:
                print(f"  - File not found or not a file, skipped: {file_path}")
    
    # Check if any files were added to the zip
    if not zf.namelist():
        raise HTTPException(status_code=404, detail="None of the requested files were found or could be added to the zip.")

    # Reset buffer position to the beginning
    zip_buffer.seek(0)

    # Create a unique zip filename (optional, could also be generic)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"ibuddy_reports_{timestamp}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
    )

# Serve static files (CSS, JS) from the 'static' sub-directory
# A request to /static/style.css will serve the file static/style.css
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html at the root path
@app.get("/", response_class=FileResponse)
async def read_index_html():
    return FileResponse("index.html", media_type="text/html")
