from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Add CORS middleware to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Optional: Replace "*" with ["https://kji304ts.github.io"] for tighter security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define request model
class ScriptRequest(BaseModel):
    script_name: str
    start_date: str
    end_date: str

# Root route (optional for testing)
@app.get("/")
def read_root():
    return {"message": "Script Runner API is running"}

# POST route that accepts JSON data from the frontend
@app.post("/run-script/")
def run_script(data: ScriptRequest):
    # Process the data (you can expand this later)
    return {
        "output": f"Running {data.script_name} from {data.start_date} to {data.end_date}"
    }



