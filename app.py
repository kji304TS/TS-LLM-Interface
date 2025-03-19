from fastapi import FastAPI
import subprocess

app = FastAPI()

# Health check
@app.get("/")
def home():
    return {"message": "Script Runner API is running"}

# Run scripts
@app.post("/run-script/")
def run_script(script_name: str, start_date: str, end_date: str):
    try:
        # Replace with your actual script path
        result = subprocess.run(["python", f"./scripts/{script_name}.py", start_date, end_date], capture_output=True, text=True)
        
        return {"status": "success", "output": result.stdout}
    except Exception as e:
        return {"status": "error", "message": str(e)}
