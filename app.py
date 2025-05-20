from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import traceback
import importlib
# import json # No longer needed here directly
# from google.oauth2 import service_account # No longer needed here directly
# from googleapiclient.discovery import build # No longer needed here directly
# from googleapiclient.http import MediaFileUpload # No longer needed here directly
# from googleapiclient.errors import HttpError # No longer needed here directly

# --- Import GDrive uploader --- 
from utils.gdrive_uploader import upload_file_to_drive
from utils.time_utils import calculate_dates_from_preset # New import
from utils.intercom_team_fetcher import get_intercom_teams # Import for fetching teams

# --- Scheduler Imports ---
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
import asyncio # For async sleep in scheduler if needed, and for lifespan

# --- Import the specific main_function from LLM5 for the scheduled task ---
# This assumes LLM5.py is in a 'scripts' directory relative to app.py
try:
    from scripts.LLM5 import main_function as llm5_main_function
    print("✅ Successfully imported main_function from scripts.LLM5.") # Add success message
except ImportError as e: # Capture the exception instance as 'e'
    llm5_main_function = None
    print("❌ FAILED to import main_function from scripts.LLM5. Scheduled tasks will NOT run.")
    print("ImportError details:")
    traceback.print_exc() # Print the full traceback for the ImportError


# --- Scheduler Setup ---
scheduler = BackgroundScheduler(timezone="UTC") # Use UTC for consistency

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

        if llm5_main_function:
            # Run the LLM5 script's main function
            # We might want to make upload_to_gdrive configurable here too, e.g., via env var
            result = llm5_main_function(
                start_date_str=start_date_str,
                end_date_str=end_date_str,
                upload_to_gdrive=True,  # Or False, or from config
                send_to_slack=True      # Ensure Slack notifications are enabled
            )
            print(f"✅ Scheduled LLM5 task completed. Result: {result.get('message', 'No message')}")
        else:
            print("❌ llm5_main_function not available. Scheduled task cannot run.")

    except Exception as e:
        print(f"❌ Error during scheduled LLM5 task: {e}")
        traceback.print_exc()

# --- FastAPI Lifespan for Scheduler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 FastAPI app starting up...")
    if llm5_main_function:
        # Add job to scheduler - runs every 8 hours
        # For testing, you might want a shorter interval initially, e.g., minutes=1
        scheduler.add_job(scheduled_llm5_job, 'interval', hours=8, id="llm5_8hr_report")
        # scheduler.add_job(scheduled_llm5_job, 'interval', minutes=1, id="llm5_test_report") # For quick testing
        print("⏳ LLM5 reporting job scheduled to run every 8 hours.")
    else:
        print("🚫 LLM5 reporting job NOT scheduled because main_function could not be imported.")
    
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
    target_team: str | None = None  # New field for targeted team
    target_product_area: str | None = None  # New field for targeted product area

# --- VERY BASIC TEST ROUTES (TEMPORARY) ---
@app.get("/api/teams-test")
async def api_get_teams_test():
    print("!!!! /api/teams-test HIT !!!!")
    return {"test_team_1": "id1", "test_team_2": "id2"}

@app.post("/run-script-test/")
async def run_script_test(data: ScriptRequest):
    print("!!!! /run-script-test/ HIT !!!!")
    print(f"Test data received: {data}")
    return {"status": "test_success", "message": "Test script ran", "input_data": data.model_dump()}
# --- END OF TEST ROUTES ---

# CORS setup - Placed before StaticFiles mounting to ensure CORS headers apply to static files too.
app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://kji304ts.github.io", 
            "http://192.168.0.27:8080",  
            "http://localhost:8080",     
            "http://127.0.0.1:8080",   
            "http://localhost", # For cases where port is omitted but resolved by browser
            "http://127.0.0.1"  # Same as above
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# API routes should be defined before broad StaticFiles mounts if they share common path prefixes.

@app.post("/run-script/")
def run_script(data: ScriptRequest):
    actual_start_date = data.start_date
    actual_end_date = data.end_date
    source_of_dates = "direct input" # Assume direct input initially

    # If LLM5.py is called and a preset is given, calculate dates from preset
    if data.script_name == "LLM5.py" and data.timeframe_preset:
        print(f"⏳ Calculating dates for LLM5.py using preset: {data.timeframe_preset}")
        actual_start_date, actual_end_date = calculate_dates_from_preset(data.timeframe_preset)
        print(f"   Calculated Start (from preset): {actual_start_date}, End (from preset): {actual_end_date}")
        source_of_dates = "preset"
    
    # If dates came from direct user input (not a preset), override their year with the current year.
    if source_of_dates == "direct input" and actual_start_date and actual_end_date:
        try:
            current_year = datetime.now().year # Get current year from system
            
            # Process start_date
            dt_start_original = datetime.strptime(actual_start_date, "%Y-%m-%d %H:%M")
            if dt_start_original.year != current_year:
                new_start_dt = dt_start_original.replace(year=current_year)
                print(f"   Overriding year for start_date. Original: {actual_start_date}, New: {new_start_dt.strftime('%Y-%m-%d %H:%M')}")
                actual_start_date = new_start_dt.strftime("%Y-%m-%d %H:%M")

            # Process end_date
            dt_end_original = datetime.strptime(actual_end_date, "%Y-%m-%d %H:%M")
            if dt_end_original.year != current_year:
                new_end_dt = dt_end_original.replace(year=current_year)
                print(f"   Overriding year for end_date. Original: {actual_end_date}, New: {new_end_dt.strftime('%Y-%m-%d %H:%M')}")
                actual_end_date = new_end_dt.strftime("%Y-%m-%d %H:%M")
        except ValueError as e:
            print(f"   Warning: Could not parse/adjust input dates to current year: {e}. Using dates as provided by user.")
            # Fallback to original dates from input if parsing/adjustment fails.
    
    if not actual_start_date or not actual_end_date:
        # This condition means valid dates were not obtained either from preset or direct input (after potential adjustment)
        return {"output": "Failed: Valid start and end dates could not be determined. Please check your input or preset.", "error": "Missing or invalid date parameters", "status": "failed"}


    print(f"✅ Received request to run: {data.script_name}")
    # Log the final effective dates being used
    print(f"   Using effective Start Date: {actual_start_date}, End Date: {actual_end_date}")
    # The individual print statements for preset vs explicit dates earlier are now covered by the "effective" date logging.
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
            
            # Prepare arguments for main_function
            main_func_args = {
                "start_date_str": actual_start_date,
                "end_date_str": actual_end_date,
                "upload_to_gdrive": data.upload_to_gdrive
            }
            
            # Add targeted parameters only if the script is LLM5.py
            if data.script_name == "LLM5.py":
                main_func_args["send_to_slack"] = True # Assuming Slack is desired for UI runs of LLM5
                main_func_args["target_team_name"] = data.target_team if data.target_team and data.target_team != "ALL_TEAMS" else None
                main_func_args["target_product_area_name"] = data.target_product_area if data.target_product_area and data.target_product_area != "ALL_AREAS" else None

            result = script_module.main_function(**main_func_args)

            if isinstance(result, dict):
                print(f"✅ Script completed: {result.get('message', 'No message')}")
                return {
                    "output": result.get("message", "Completed."),
                    "status": result.get("status", "success"),
                    "file": result.get("file"),
                    "local_files": result.get("local_files", []),
                    "gdrive_urls": result.get("gdrive_urls", []),
                    "storage_mode": "gdrive" if data.upload_to_gdrive else "local"
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

@app.get("/api/teams")
async def api_get_teams():
    """API endpoint to fetch the list of Intercom teams."""
    print("🚀 API call received for /api/teams")
    try:
        teams_map = get_intercom_teams() # Returns a name:id dict or None
        if teams_map is not None:
            # Convert to a list of objects for easier frontend iteration if needed,
            # or just return the map. Let's return a list of {'name': name, 'id': id} objects.
            # Or, if the JS will populate a select where value=name, map is fine.
            # For simplicity, let's return the name:id map directly. Client can use Object.keys() and values.
            print(f"✅ Successfully fetched {len(teams_map)} teams for API response.")
            return teams_map 
        else:
            print("❌ Failed to fetch teams from intercom_team_fetcher for API.")
            raise HTTPException(status_code=500, detail="Failed to fetch Intercom teams")
    except Exception as e:
        print(f"❌ Error in /api/teams endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error fetching teams: {str(e)}")

# Endpoint to download generated files
@app.get("/download/{filename}")
async def download_file(filename: str):
    # Sanitize filename to prevent directory traversal attacks
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    
    # Define the base directory for output files
    # This should be consistent with where LLM5.py saves files
    output_dir = "output_files"
    file_path = os.path.join(output_dir, filename)

    if not os.path.exists(file_path):
        print(f"❌ File not found for download: {file_path}")
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    
    if not os.path.isfile(file_path):
        print(f"❌ Path is not a file for download: {file_path}")
        raise HTTPException(status_code=400, detail=f"Path is not a file: {filename}")

    print(f"🔽 Preparing download for: {file_path}")
    return FileResponse(
        path=file_path, 
        filename=filename, 
        media_type='application/octet-stream',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# Serve static files (CSS, JS) from the 'static' sub-directory
# A request to /static/style.css will serve the file static/style.css
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html at the root path
@app.get("/", response_class=FileResponse)
async def read_index_html():
    return FileResponse("index.html", media_type="text/html")

# Mount static files (CSS, JS, images) to serve from the root directory
# html=True means it will try to serve index.html for "/" if no other route matches "/" first.
# Placing this last makes it a fallback for any paths not matched by API routes.
# app.mount("/static_assets", StaticFiles(directory="."), name="static_assets") # Removed this line

# The User's original structure had index.html, script.js and style.css in the root.
# The most robust way to handle this with FastAPI is to:
# 1. Serve API routes (e.g. /run-script/)
# 2. Serve the main HTML page (e.g. index.html for "/")
# 3. Serve other static assets (CSS, JS) from their paths.

# Let's ensure /run-script is defined, then index.html for /, then other static files.
# (The previous edit had StaticFiles at root first, which was the likely cause of 405)

# Final re-ordering attempt for app.py:
# Lifespan, CORS
# API routes (@app.post("/run-script/"), etc.)
# Root HTML route (@app.get("/", response_class=FileResponse) async def read_index()...)
# Static files mount for other assets (app.mount("/", StaticFiles(directory="."), name="static_assets_root"))
# This ensures that /run-script is hit, then / is hit for index.html, then StaticFiles serves style.css and script.js

# The code block below reflects moving StaticFiles to the end AFTER all other routes.
# It will serve index.html from root due to html=True if no specific "/" GET route is matched first.
# And it will serve other files like style.css and script.js from the root.




