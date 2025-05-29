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
import logging
from logging.handlers import RotatingFileHandler
import asyncio
from utils.s3_uploader import upload_file_to_s3


# --- Import GDrive uploader ---
# Removed: from utils.gdrive_uploader import upload_file_to_drive
from utils.time_utils import calculate_dates_from_preset # New import
from utils.intercom_team_fetcher import get_intercom_teams # Import for fetching teams

# --- Scheduler Imports ---
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

# --- Helper function for date ranges ---
def get_date_range_from_preset(timeframe_preset: str):
    """Calculate start and end dates based on a timeframe preset."""
    return calculate_dates_from_preset(timeframe_preset)

def get_date_range(start_date: str | None, end_date: str | None):
    """Return start and end dates, ensuring they are not None."""
    if start_date and end_date:
        return start_date, end_date
    now = datetime.now(timezone.utc)
    if not start_date:
        start_date = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    if not end_date:
        end_date = now.strftime("%Y-%m-%d %H:%M")
    return start_date, end_date

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
        end_date_dt = datetime.now(timezone.utc)
        start_date_dt = end_date_dt - timedelta(hours=8)
        
        start_date_str = start_date_dt.strftime("%Y-%m-%d %H:%M")
        end_date_str = end_date_dt.strftime("%Y-%m-%d %H:%M")

        print(f"🗓️  Scheduled task for period: {start_date_str} to {end_date_str}")

        if llm5_main_function_direct:
            try:
                result = asyncio.run(llm5_main_function_direct(
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                    # upload_to_gdrive=True, # Removed GDrive functionality
                    send_to_slack=True,
                    target_team_name=None, 
                    target_product_area_name=None
                ))
                print(f"✅ Scheduled LLM5 task completed. Result: {result.get('message', 'No message')}")
            except RuntimeError as e:
                if "cannot be called from a running event loop" in str(e):
                    print(f"❌ Error in scheduled LLM5 task: Attempted to call asyncio.run from within a running loop. Details: {e}")
                    print("   Investigate if llm5_main_function or its sub-calls are mismanaging asyncio loops.")
                else:
                    print(f"❌ Runtime Error during scheduled LLM5 task: {e}")
                    traceback.print_exc()
            except Exception as e:
                print(f"❌ General Error during scheduled LLM5 task: {e}")
                traceback.print_exc()
        else:
            print("❌ llm5_main_function_direct not available. Scheduled task cannot run.")

    except Exception as e:
        print(f"❌ Error during scheduled LLM5 task: {e}") # Outer exception for date calculation etc.
        traceback.print_exc()

# --- FastAPI Lifespan for Scheduler ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 FastAPI app starting up...")
    if llm5_main_function_direct:
        scheduler.add_job(scheduled_llm5_job, 'interval', hours=8, id="llm5_8hr_report")
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

app = FastAPI(lifespan=lifespan)

class ScriptRequest(BaseModel):
    script_name: str
    start_date: str | None = None 
    end_date: str | None = None   
    timeframe_preset: str | None = None 
    # upload_to_gdrive: bool = False # Removed GDrive functionality
    target_team: str | None = None
    target_product_area: str | None = None

class ZipRequest(BaseModel):
    filenames: list[str]

class SlackScraperRequest(BaseModel):
    channel_id: str
    hours_back: int = 24

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

# Default allowed origins for development
DEFAULT_ALLOWED_ORIGINS = [
    "https://blhafner.github.io",
    "http://192.168.0.27:8080",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://08dd-184-97-144-83.ngrok-free.app",  # TODO: Remove after AWS deployment
    # "https://your-aws-url.amazonaws.com",  # TODO: Add your AWS URL here after deployment
]

# Get allowed origins from environment variable or use defaults
allowed_origins = os.getenv('ALLOWED_ORIGINS', '').split(',')
allowed_origins = [origin.strip() for origin in allowed_origins if origin.strip()]  # Clean empty strings
if not allowed_origins:  # If no origins specified in env, use defaults
    allowed_origins = DEFAULT_ALLOWED_ORIGINS

# CORS setup with both security and development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=['GET', 'POST'],  # Restrict to only needed methods
    allow_headers=['Content-Type', 'Authorization'],  # Restrict to only needed headers
)

@app.post("/run-script/")
async def run_script(data: ScriptRequest):
    """Run a script with the provided parameters."""
    print(f"🚀 Received request to run {data.script_name}")
    
    # Get actual dates based on timeframe preset or provided dates
    actual_start_date, actual_end_date = get_date_range(data.start_date, data.end_date)
    if data.timeframe_preset:
        actual_start_date, actual_end_date = get_date_range_from_preset(data.timeframe_preset)
        print(f"📅 Using preset timeframe: {data.timeframe_preset}")
        print(f"   Start: {actual_start_date}")
        print(f"   End: {actual_end_date}")
    else:
        print(f"📅 Using provided dates:")
        print(f"   Start: {actual_start_date}")
        print(f"   End: {actual_end_date}")

    if data.target_team or data.target_product_area:
        print(f"🎯 Targeting - Team: {data.target_team or 'All'}, Product Area: {data.target_product_area or 'All'}")

    try:
        print("🧪 Checking environment variables...")
        # folder_id = os.getenv("GDRIVE_FOLDER_ID") # Removed GDrive functionality
        # print(f"🔍 GDRIVE_FOLDER_ID loaded: {folder_id if folder_id else '❌ MISSING'}") # Removed GDrive functionality
        module_name = data.script_name.replace(".py", "")
        print(f"📦 Importing module: scripts.{module_name}")
        script_module = importlib.import_module(f"scripts.{module_name}")
        if hasattr(script_module, "main_function"):
            print("🚀 Executing main_function...")
            main_func_args = {
                "start_date_str": actual_start_date,
                "end_date_str": actual_end_date
                # "upload_to_gdrive": data.upload_to_gdrive # Removed GDrive functionality
            }
            if data.script_name == "LLM5.py":
                main_func_args["send_to_slack"] = True
                main_func_args["target_team_name"] = data.target_team if data.target_team and data.target_team != "ALL_TEAMS" else None
                main_func_args["target_product_area_name"] = data.target_product_area if data.target_product_area and data.target_product_area != "ALL_AREAS" else None
            
            print(f"🔧 Calling main_function with args: {main_func_args}")
            result = await script_module.main_function(**main_func_args)
            
            print(f"🎁 Result from main_function: {result}")

            if isinstance(result, dict):
                print(f"✅ Script completed: {result.get('message', 'No message')}")
                processed_counts = result.get("processed_counts", {})
                response_data = {
                    "output": result.get("message", "Completed."),
                    "status": result.get("status", "success"),
                    "file": result.get("file"),
                    "local_files": result.get("local_files", []), 
                    # "gdrive_urls": result.get("gdrive_urls", []), # Removed GDrive functionality
                    "storage_mode": "local", # Defaulting to local
                    "processed_counts": processed_counts
                }
                print(f"📬 Sending response data (dict): {response_data}")
                return response_data
            else:
                print("✅ Script completed with no structured result.")
                response_data = {
                    "output": str(result),
                    "status": "success",
                    "storage_mode": "local" # Defaulting to local
                }
                print(f"📬 Sending response data (non-dict): {response_data}")
                return response_data
        else:
            raise AttributeError(f"'main_function' not found in {data.script_name}")
    except Exception as e:
        logger.error(f"Error running script: {repr(e)}", exc_info=True) 
        print(f"💥🚨 CAUGHT EXCEPTION IN /run-script/ 🚨💥")
        import traceback
        traceback.print_exc() 
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred while trying to run {data.script_name}. Check server logs for details."
        )

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
    # Normalize and validate path
    safe_filename = os.path.normpath(filename)
    if safe_filename.startswith('..') or safe_filename.startswith('/'):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # Whitelist of allowed directories
    allowed_dirs = {
        "output_files": "output_files",
        "Outputs": "Outputs",
        "team_reports": os.path.join("Outputs", "team_reports")
    }
    
    file_path = None
    for dir_name, dir_path in allowed_dirs.items():
        potential_path = os.path.join(dir_path, safe_filename)
        if os.path.exists(potential_path) and os.path.isfile(potential_path):
            file_path = potential_path
            break

    if not file_path:
        logger.warning(f"File not found: {filename}")
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type='application/octet-stream',
        headers={"Content-Disposition": f"attachment; filename={safe_filename}"}
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

@app.post("/slack/scrape-channel/")
async def scrape_slack_channel(data: SlackScraperRequest):
    """Scrape a Slack channel and generate an activity report"""
    print(f"📊 Slack scraping request for channel: {data.channel_id}")
    
    try:
        from utils.slack_scraper import SlackScraper
        
        scraper = SlackScraper()
        end_date = datetime.now()
        start_date = end_date - timedelta(hours=data.hours_back)
        
        # Generate report
        report = scraper.generate_channel_report(data.channel_id, start_date, end_date)
        
        # Save report as JSON
        from utils.storage_handler import storage
        import json
        
        report_filename = f"slack_reports/channel_{data.channel_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        storage.save_file(
            json.dumps(report, indent=2), 
            report_filename
        )
        
        # Format for Slack
        formatted_report = scraper.format_report_for_slack(report)
        
        return {
            "status": "success",
            "report": report,
            "formatted_message": formatted_report,
            "report_file": report_filename
        }
        
    except Exception as e:
        print(f"❌ Error scraping Slack channel: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to scrape Slack channel: {str(e)}")

@app.get("/slack/list-channels/")
async def list_slack_channels():
    """List all available Slack channels the bot can access"""
    try:
        from utils.slack_scraper import SlackScraper
        
        scraper = SlackScraper()
        response = scraper.client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True
        )
        
        channels = []
        for channel in response["channels"]:
            if channel.get("is_member", False):  # Only channels the bot is in
                channels.append({
                    "id": channel["id"],
                    "name": channel["name"],
                    "is_private": channel.get("is_private", False),
                    "num_members": channel.get("num_members", 0)
                })
        
        return {
            "status": "success",
            "channels": channels,
            "total": len(channels)
        }
        
    except Exception as e:
        print(f"❌ Error listing Slack channels: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list Slack channels: {str(e)}")

# Serve static files (CSS, JS) from the 'static' sub-directory
# A request to /static/style.css will serve the file static/style.css
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve index.html at the root path
@app.get("/", response_class=FileResponse)
async def read_index_html():
    return FileResponse("index.html", media_type="text/html")

# 1. Add proper logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('app.log', maxBytes=10000000, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@app.post("/upload-to-s3/")
async def upload_to_s3_endpoint(filename: str):
    s3_key = f"uploads/{filename}"
    file_path = f"output_files/{filename}"
    s3_url = await upload_file_to_s3(file_path, s3_key)
    if s3_url:
        return {"status": "success", "s3_url": s3_url}
    else:
        raise HTTPException(status_code=500, detail="Failed to upload to S3")
