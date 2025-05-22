# Intercom Conversation Analyzer & Reporter

This project provides a FastAPI backend and associated scripts to fetch, analyze, and report on Intercom conversations. It can generate Excel summaries, text-based insights, and end-of-shift reports, with options to upload these to Google Drive.

## Features

- Fetch Intercom conversations within a specified date range or by a single conversation ID.
- Dynamically include all custom attributes from conversations in the output.
- Generate per-product-area Excel files with conversation details.
- Create text-based insight reports for each product area, including top issues and keyword analysis.
- Generate a consolidated "End of Shift" summary report.
- Upload generated files to a specified Google Drive folder.
- FastAPI endpoint to trigger script runs.
- Command-line interface for direct execution and testing of the main processing script (`scripts/LLM5.py`).

## Prerequisites

- Python 3.10+ (Recommended: Python 3.12, as seen in some user paths)
- Pip (Python package installer)

## Setup Instructions

1.  **Clone the Repository (if applicable):**
    ```bash
    # git clone <your-repository-url>
    # cd <your-repository-name>
    ```

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    ```
    Activate it:
    -   Windows:
        ```powershell
        .\venv\Scripts\Activate.ps1
        ```
    -   macOS/Linux:
        ```bash
        source venv/bin/activate
        ```

3.  **Install Dependencies:**
    Ensure you are in the project root directory (`TS-LLM-Interface`).
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables:**
    Create a `.env` file in the project root directory (`TS-LLM-Interface/.env`).
    Add the following environment variables, replacing the placeholder values with your actual credentials:

    ```env
    INTERCOM_PROD_KEY="sk_prod_your_intercom_production_api_key"
    
    # For Google Drive uploads via the FastAPI app or direct LLM5.py runs with upload enabled:
    # Ensure the service account has permissions for Google Drive API and access to the target folder.
    GOOGLE_CREDENTIALS_JSON='{
      "type": "service_account",
      "project_id": "your-gcp-project-id",
      "private_key_id": "your-private-key-id",
      "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY_CONTENT_HERE\n-----END PRIVATE KEY-----\n",
      "client_email": "your-service-account-email@your-gcp-project-id.iam.gserviceaccount.com",
      "client_id": "your-client-id",
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
      "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account-email%40your-gcp-project-id.iam.gserviceaccount.com"
    }'
    GDRIVE_FOLDER_ID="your_google_drive_folder_id_for_uploads"
    ```
    *   `INTERCOM_PROD_KEY`: Your production API key from Intercom.
    *   `GOOGLE_CREDENTIALS_JSON`: The JSON content of your Google Cloud Service Account key. Ensure the private key's newline characters (`\n`) are preserved within the single-quoted string.
    *   `GDRIVE_FOLDER_ID`: The ID of the Google Drive folder where files will be uploaded. Obtain this from the folder's URL (e.g., `https://drive.google.com/drive/folders/THIS_IS_THE_ID`).

## Running the Application

### 1. FastAPI Server (`app.py`)

This server provides an API endpoint to trigger the conversation processing scripts.

-   **To Run:**
    Navigate to the project root directory and run:
    ```bash
    uvicorn app:app --reload
    ```
    The API will typically be available at `http://127.0.0.1:8000`.

-   **Endpoint:** `POST /run-script/`
    -   **Request Body (JSON):**
        ```json
        {
            "script_name": "LLM5.py", // Or other scripts in the 'scripts/' directory
            "start_date": "YYYY-MM-DD HH:MM", // e.g., "2023-10-01 00:00"
            "end_date": "YYYY-MM-DD HH:MM",   // e.g., "2023-10-07 23:59"
            "upload_to_gdrive": false          // boolean, true to upload, false otherwise
        }
        ```
    -   This will execute the `main_function` within the specified script.

### 2. Direct Execution of `scripts/LLM5.py`

The main processing script `scripts/LLM5.py` can also be run directly from the command line for manual processing or testing.

-   **Ensure your `.env` file is configured, especially `INTERCOM_PROD_KEY`.**
-   Navigate to the project root directory (`TS-LLM-Interface`).

-   **Command-Line Flags:**
    
    *   `-c CONVERSATION_ID`, `--conversation_id CONVERSATION_ID`:
        Fetch and process a single conversation by its Intercom ID.
        Example: `python scripts/LLM5.py -c 123456789`
    
    *   `-u`, `--upload`:
        Enable uploading of generated files to Google Drive. This flag applies to both single conversation fetches and date range processing when running the script directly.
        Example (single conversation with upload): `python scripts/LLM5.py -c 123456789 -u`
        Example (date range with upload): `python scripts/LLM5.py -u`

    *   `--start_date YYYY-MM-DD HH:MM`:
        Specify the start date for fetching conversations. If `--conversation_id` is not used, and this flag (along with `--end_date`) is provided, it overrides the default "last week" logic.
        Example: `python scripts/LLM5.py --start_date "2023-09-01 00:00" --end_date "2023-09-07 23:59"`

    *   `--end_date YYYY-MM-DD HH:MM`:
        Specify the end date for fetching conversations. Must be used with `--start_date`.

-   **Default Behavior (No Flags or Only `-u`):**
    If run without `-c`, `--start_date`, or `--end_date`, the script will process conversations for the *previous full week* (Monday 00:00 to Sunday 23:59 EST).
    Example (process last week, no upload): `python scripts/LLM5.py`
    Example (process last week, with upload): `python scripts/LLM5.py -u`

## Output Files

When `scripts/LLM5.py` runs, it generates the following files:

1.  **Conversation Data (Excel):**
    -   Location: `output_files/`
    -   Naming: `<metamask_area>_conversations_<start_date_yyyymmdd>_to_<end_date_yyyymmdd>.xlsx`
    -   For single conversation test: `<metamask_area>_conversations_<conversation_id>_to_single.xlsx`
    -   Content: Detailed conversation data including ID, summary, transcript, and all custom attributes found in the conversations for that product area.

2.  **Insight Reports (Text):**
    -   Location: `Outputs/`
    -   Naming: `<metamask_area>_insights_<start_date_yyyymmdd>_to_<end_date_yyyymmdd>.txt`
    -   For single conversation test: `<metamask_area>_insights_<conversation_id>_to_single.txt`
    -   Content: Analysis including top issues, keyword frequencies from summaries, and (placeholder) answers to predefined prompts.

3.  **End of Shift Report (Text):**
    -   Location: `Outputs/`
    -   Naming: `end_of_shift_report_<start_date_yyyymmdd>_to_<end_date_yyyymmdd>.txt`
    -   Content: A consolidated summary across all processed product areas, highlighting key metrics and top issues.
    -   (Note: This report is typically generated for date range processing, not for single conversation fetches.)

## Project Structure

```
TS-LLM-Interface/
├── .env                # Environment variables (create this yourself)
├── app.py              # FastAPI application server
├── README.md           # This file
├── requirements.txt    # Python dependencies
├── scripts/
│   ├── LLM5.py         # Main Intercom data processing and analysis script
│   ├── card5.py        # Example script for card-related conversations (runnable by app.py)
│   └── ...             # Other utility/processing scripts
├── output_files/       # Directory for generated Excel files (created automatically)
└── Outputs/            # Directory for generated insight/report text files (created automatically)
```

## Future Goals (As Discussed)

-   Automate end-of-shift reports for different teams (Global, USA, User Safety, Technical Support) to be sent via Slack every 8 hours.
    -   Requires defining how conversations map to teams.
    -   Requires implementing scheduling (e.g., cron, cloud scheduler) and Slack integration.

## Troubleshooting

-   **ImportError: cannot import name 'upload_file_to_drive' from 'app'**: Ensure you are running `python scripts/LLM5.py` from the project root directory (`TS-LLM-Interface/`). The script includes a fix to adjust `sys.path` for direct execution.
-   **Intercom API Timeouts/Errors**: Double-check your `INTERCOM_PROD_KEY` in `.env`. Ensure network connectivity to `https://api.intercom.io`.
-   **Google Drive Upload Failures**: Verify `GOOGLE_CREDENTIALS_JSON` and `GDRIVE_FOLDER_ID` in `.env`. Ensure the service account has Drive API enabled and permissions to write to the folder. Check `app.py` console output for detailed error messages from the Google API client.