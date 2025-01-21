from flask import Flask, render_template, request
import subprocess
import sys
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run', methods=['POST'])
def run_script():
    script_name = request.form['script_name']
    start_date = request.form['start_date']
    end_date = request.form['end_date']

    # Path to your scripts
    script_path = f"./scripts/{script_name}"

    # Use the current Python interpreter
    python_executable = sys.executable  # Gets the full path of the current Python interpreter

    try:
        # Run the selected Python script with the provided arguments
        print(f"Running: {python_executable} {script_path} {start_date} {end_date}")
        subprocess.run([python_executable, script_path, start_date, end_date], check=True)
        return f"Successfully executed {script_name} with dates {start_date} to {end_date}."
    except FileNotFoundError as e:
        return f"Error: Script not found or invalid Python executable. Details: {e}", 500
    except subprocess.CalledProcessError as e:
        return f"Error running script {script_name}: {e}", 500

if __name__ == '__main__':
    app.run(debug=True)
