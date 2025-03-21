from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# Define a Pydantic model for the request body
class ScriptRequest(BaseModel):
    script_name: str
    start_date: str
    end_date: str

@app.post("/run-script/")
def run_script(data: ScriptRequest):
    return {"output": f"Running {data.script_name} from {data.start_date} to {data.end_date}"}


