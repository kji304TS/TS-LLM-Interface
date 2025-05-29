# Intercom Conversation Analyzer & Reporter

This project provides a FastAPI backend and associated scripts to fetch, analyze, and report on Intercom conversations. It can generate Excel summaries, text-based insights, and end-of-shift reports (both global and team-specific), with options to upload these to Google Drive and send notifications to Slack.

## Features

- Fetch Intercom conversations within a specified date range or by a single conversation ID.
- Dynamically include all custom attributes from conversations in the output.
- Generate per-product-area Excel files with conversation details.
- Create text-based insight reports for each product area, including top issues, keyword analysis, and sentiment analysis.
- Generate consolidated "End of Shift" summary reports (global).
- Generate team-specific "End of Shift" reports.
- Upload generated files to a specified Google Drive folder.
- Send team-specific End of Shift reports to Slack.
- FastAPI endpoint to trigger script runs with various parameters.
- Command-line interface for direct execution and testing of the main processing script (`scripts/LLM5.py`), including options for targeted reporting and stop word suggestions.

## Prerequisites

- Python 3.10+ (Python 3.12 is actively used by some contributors and recommended).
- Pip (Python package installer).
- Access to an Intercom account with API key permissions.
- (Optional) Google Cloud Platform account with a service account key for Google Drive uploads.
- (Optional) Slack workspace and bot token for Slack notifications.

## Setup Instructions

1.  **Clone the Repository (if you haven't already):**
    ```bash
    # git clone <your-repository-url>
    # cd TS-LLM-Interface
    ```
    Ensure all subsequent commands are run from the project root directory (`TS-LLM-Interface`).

2.  **Create and Activate a Virtual Environment (Highly Recommended):**
    This isolates project dependencies.
    ```bash
    python -m venv venv
    ```
    Activate it:
    -   **Windows (PowerShell):**
        ```powershell
        .\venv\Scripts\Activate.ps1
        ```
    -   **Windows (Command Prompt):**
        ```cmd
        .\venv\Scripts\activate.bat
        ```
    -   **macOS/Linux (bash/zsh):**
        ```bash
        source venv/bin/activate
        ```
    Your command prompt should now be prefixed with `(venv)`.

3.  **Install Dependencies:**
    With the virtual environment activated, install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables:**
    Create a `.env` file in the project root directory (`TS-LLM-Interface/.env`). **This file should not be committed to version control if it contains sensitive keys.**
    Copy the example below and replace placeholder values with your actual credentials:

    ```env
    # Intercom API Key (Required)
    INTERCOM_PROD_KEY="sk_prod_your_intercom_production_api_key"

    # Google Drive Integration (Optional - for uploads)
    # Ensure the service account has permissions for Google Drive API and access to the target folder.
    GOOGLE_CREDENTIALS_JSON='{
      "type": "service_account",
      "project_id": "your-gcp-project-id",
      "private_key_id": "your-private-key-id",
      "private_key": "-----BEGIN PRIVATE KEY-----\\nYOUR_PRIVATE_KEY_CONTENT_HERE\\n-----END PRIVATE KEY-----\\n",
      "client_email": "your-service-account-email@your-gcp-project-id.iam.gserviceaccount.com",
      "client_id": "your-client-id",
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
      "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account-email%40your-gcp-project-id.iam.gserviceaccount.com"
    }'
    GDRIVE_FOLDER_ID="your_google_drive_folder_id_for_uploads"

    # Slack Integration (Optional - for notifications)
    # SLACK_BOT_TOKEN="xoxb-your-slack-bot-token"
    # SLACK_CHANNEL_ID_TEAM_X="C0XXXXXXXXX" # Example channel ID for a specific team
    # Add more SLACK_CHANNEL_ID_TEAM_Y variables as needed if using utils/slack_notifier.py
    ```
    *   `INTERCOM_PROD_KEY`: Your production API key from Intercom.
    *   `GOOGLE_CREDENTIALS_JSON`: The JSON content of your Google Cloud Service Account key. **Important:** Ensure the private key's newline characters (`\\n`) are correctly escaped or preserved within the single-quoted string when setting this variable, especially if setting it directly in an OS environment.
    *   `GDRIVE_FOLDER_ID`: The ID of the Google Drive folder where files will be uploaded. Obtain this from the folder's URL (e.g., `https://drive.google.com/drive/folders/THIS_IS_THE_ID`).
    *   `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID_...`: (If using Slack notifications) Your Slack bot token and the channel IDs where reports should be sent. The `utils/slack_notifier.py` script might require specific channel ID variable names.

## Running the Application

You can run the Intercom analysis in two main ways: via the FastAPI server or by executing the `scripts/LLM5.py` script directly.

### 1. FastAPI Server (`app.py`)

This server provides an API endpoint to trigger the conversation processing scripts.

-   **To Run:**
    Ensure your virtual environment is activated and you are in the project root directory (`TS-LLM-Interface`).
    ```bash
    uvicorn app:app --reload
    ```
    The API will typically be available at `http://127.0.0.1:8000`. You can access the auto-generated API documentation at `http://127.0.0.1:8000/docs`.

-   **Endpoint:** `POST /run-script/`
    -   **Request Body (JSON):**
        ```json
        {
            "script_name": "LLM5.py",
            "start_date": "YYYY-MM-DD HH:MM",     // e.g., "2023-10-01 00:00"
            "end_date": "YYYY-MM-DD HH:MM",       // e.g., "2023-10-07 23:59"
            "upload_to_gdrive": false,            // boolean, true to upload
            "send_to_slack": false,               // boolean, true to send Slack messages
            "target_team_name": null,             // string or null, e.g., "MetaMask TS"
            "target_product_area_name": null      // string or null, e.g., "Security"
        }
        ```
    -   This will execute the `main_function` within the specified script (`LLM5.py` is the primary one).
    -   If `start_date` and `end_date` are omitted, the script defaults to processing the previous full week.
    -   `target_team_name` and `target_product_area_name` allow for focused report generation. If both are `null` or omitted, a full suite of reports is generated.

### 2. Direct Execution of `scripts/LLM5.py`

The main processing script `scripts/LLM5.py` can also be run directly from the command line for manual processing, testing, or scheduled tasks.

-   **Prerequisites:**
    -   Ensure your virtual environment is activated.
    -   Ensure your `.env` file is configured in the project root, especially `INTERCOM_PROD_KEY`.
    -   Navigate to the project root directory (`TS-LLM-Interface`) to run the script. This is important for correct module resolution.
        ```bash
        python scripts/LLM5.py [OPTIONS]
        ```

-   **Command-Line Flags & Options:**

    *   **Date Range (Overrides Default Last Week):**
        *   `--start_date "YYYY-MM-DD HH:MM"`: Specify the start date.
        *   `--end_date "YYYY-MM-DD HH:MM"`: Specify the end date. (Must be used with `--start_date`).
            Example: `python scripts/LLM5.py --start_date "2023-05-01 00:00" --end_date "2023-05-07 23:59"`

    *   **Single Conversation Processing:**
        *   `-c CONVERSATION_ID`, `--conversation_id CONVERSATION_ID`: Fetch and process a single conversation by its Intercom ID.
            Example: `python scripts/LLM5.py -c 123456789`

    *   **Targeted Reporting:**
        *   `--target-team "TEAM_NAME"`: Specify a single team name to generate reports for (e.g., "MetaMask TS", "Card"). This will generate the team's EoS report and its product area breakdowns.
            Example: `python scripts/LLM5.py --target-team "MetaMask TS"`
        *   `--target-product-area "PRODUCT_AREA_NAME"`: Specify a single product area to generate reports for globally (e.g., "Security", "Swaps").
            Example: `python scripts/LLM5.py --target-product-area "Security"`
        *   You can combine `--target-team` and `--target-product-area` to generate files for a specific team's involvement in a specific product area.
            Example: `python scripts/LLM5.py --target-team "MetaMask TS" --target-product-area "Security"`

    *   **Output Control:**
        *   `-u`, `--upload`: Enable uploading of generated files to Google Drive (requires GDrive env vars).
            Example (single conversation with upload): `python scripts/LLM5.py -c 123456789 -u`
            Example (date range with upload): `python scripts/LLM5.py --start_date "..." --end_date "..." -u`
        *   `--send_slack`: Send generated team EoS reports to Slack (requires Slack env vars and configuration in `utils/slack_notifier.py`).
            Example: `python scripts/LLM5.py --target-team "MetaMask TS" --send_slack`

    *   **Stop Word Suggestion Utility:**
        *   `--suggest-stop-words`: Analyze conversation data from previously generated XLSX files to suggest common words that could be added to the `STOP_WORDS` list in `LLM5.py`.
        *   `--stop-words-input-dir DIRECTORY_PATH`: Specify the directory containing XLSX files to scan. Defaults to `output_files/`.
            Example: `python scripts/LLM5.py --suggest-stop-words`
            Example: `python scripts/LLM5.py --suggest-stop-words --stop-words-input-dir "path/to/your/xlsx_files"`

-   **Default Behavior (No Date/ID/Target Flags):**
    If run without `-c`, `--start_date`/`--end_date`, or any `--target-...` flags, the script will process conversations for the *previous full week* (Monday 00:00 to Sunday 23:59, typically based on EST/EDT as configured in the script) and generate a full suite of reports (all global product areas and all team EoS reports).
    Example (process last week, no upload/slack): `python scripts/LLM5.py`
    Example (process last week, with upload): `python scripts/LLM5.py -u`

## Testing Scenarios (Direct Execution of `scripts/LLM5.py`)

Here are some common scenarios for testing the script directly from your terminal (ensure you are in the `TS-LLM-Interface` root directory and your venv is active):

1.  **Fetch and Process a Single Conversation:**
    ```bash
    python scripts/LLM5.py -c "INTERCOM_CONVERSATION_ID"
    ```
    (Replace `"INTERCOM_CONVERSATION_ID"` with an actual ID).
    Check `output_files/` and `Outputs/` for files related to this conversation ID.

2.  **Process a Specific Short Date Range (e.g., yesterday):**
    Adjust dates as needed.
    ```bash
    python scripts/LLM5.py --start_date "2023-10-25 00:00" --end_date "2023-10-25 23:59"
    ```
    Check `output_files/` and `Outputs/` for generated reports for this range. This will run the full suite for the small range.

3.  **Process Default (Last Week) with Google Drive Upload:**
    (Assumes GDrive .env variables are set)
    ```bash
    python scripts/LLM5.py -u
    ```
    Check console for upload logs and your Google Drive folder.

4.  **Generate Report for a Specific Team:**
    ```bash
    python scripts/LLM5.py --target-team "MetaMask TS" 
    ```
    (Replace `"MetaMask TS"` with a team name defined in your script's logic or Intercom).
    Check `Outputs/team_reports/` for the team's EoS report and `output_files/` for `MetaMask TS_` prefixed XLSX files and `Outputs/` for `MetaMask TS_` prefixed insights.

5.  **Generate Report for a Specific Product Area (Globally):**
    ```bash
    python scripts/LLM5.py --target-product-area "Security"
    ```
    Check `output_files/` for `Security_conversations...xlsx` and `Outputs/` for `Security_insights...txt`.

6.  **Generate Report for a Specific Team AND Product Area:**
    ```bash
    python scripts/LLM5.py --target-team "MetaMask TS" --target-product-area "Security"
    ```
    Check for files prefixed like `MetaMask TS_Security_...`.

7.  **Suggest Stop Words from Existing Output:**
    (Assumes you have run the script before and have `.xlsx` files in `output_files/`)
    ```bash
    python scripts/LLM5.py --suggest-stop-words
    ```
    Review the console output for suggested words.

After running any test, check the console for detailed logs, error messages, and confirmation of file creation/upload.

## Output Files

When `scripts/LLM5.py` runs, it generates files in the following locations:

1.  **Conversation Data (Excel):**
    -   Location: `output_files/`
    -   Naming (Global Product Area): `<product_area>_conversations_<start_date_yyyymmdd>_to_<end_date_yyyymmdd>.xlsx`
    -   Naming (Team-Specific Product Area): `<TeamName>_<product_area>_conversations_<start_date_yyyymmdd>_to_<end_date_yyyymmdd>.xlsx`
    -   Naming (Single Conversation): `<product_area>_conversations_<conversation_id>_to_single.xlsx`
    -   Content: Detailed conversation data including ID, summary, transcript, and all custom attributes.

2.  **Insight Reports (Text):**
    -   Location: `Outputs/`
    -   Naming (Global Product Area): `<product_area>_insights_<start_date_yyyymmdd>_to_<end_date_yyyymmdd>.txt`
    -   Naming (Team-Specific Product Area): `<TeamName>_<product_area>_insights_<start_date_yyyymmdd>_to_<end_date_yyyymmdd>.txt`
    -   Naming (Single Conversation): `<product_area>_insights_<conversation_id>_to_single.txt`
    -   Content: Analysis including top issues, keyword frequencies, sentiment analysis, etc.

3.  **Overall End of Shift Report (Text):**
    -   Location: `Outputs/`
    -   Naming: `end_of_shift_report_<start_date_yyyymmdd>_to_<end_date_yyyymmdd>.txt`
    -   Content: A consolidated summary across all globally processed product areas. Generated when no specific team/area target is set or when running the default "last week" full process.

4.  **Team-Specific End of Shift Reports (Text):**
    -   Location: `Outputs/team_reports/`
    -   Naming: `<TeamName>_EOS_Report_<start_date_yyyymmdd>_to_<end_date_yyyymmdd>.txt`
    -   Content: An End of Shift summary specifically for the conversations handled by that team. Generated when a specific team is targeted, or for all teams during a full default run.

## Project Structure

```
TS-LLM-Interface/
├── .env                # Environment variables (create this yourself, DO NOT COMMIT SENSITIVE DATA)
├── .gitignore          # Specifies intentionally untracked files that Git should ignore
├── app.py              # FastAPI application server
├── README.md           # This file
├── requirements.txt    # Python dependencies
├── scripts/
│   ├── LLM5.py         # Main Intercom data processing and analysis script
│   └── ...             # Other utility/processing scripts (e.g., old versions, specific tasks)
├── output_files/       # Directory for generated Excel files (created automatically)
├── Outputs/            # Directory for generated global insight/report text files (created automatically)
│   └── team_reports/   # Directory for team-specific End of Shift reports (created automatically)
└── utils/              # Utility modules (e.g., gdrive_uploader.py, slack_notifier.py)
    ├── gdrive_uploader.py
    └── slack_notifier.py
    └── intercom_team_fetcher.py
```

## Future Goals (As Discussed)

-   Automate end-of-shift reports for different teams to be sent via Slack at regular intervals (e.g., every 8 hours).
    -   Requires robust scheduling mechanism (e.g., cron, systemd timers, cloud scheduler like AWS EventBridge or Google Cloud Scheduler).
    -   The current `--send_slack` flag is for on-demand sending upon script completion.

## Troubleshooting

-   **`ModuleNotFoundError: No module named 'utils'` (or similar for `scripts` sub-modules):**
    Ensure you are running Python commands (like `python scripts/LLM5.py` or `uvicorn app:app`) from the project root directory (`TS-LLM-Interface/`). The scripts and `app.py` are generally set up to handle `sys.path` adjustments assuming this execution context. If issues persist, verify your Python environment and `PYTHONPATH`.
-   **Intercom API Timeouts/Errors (`429 Too Many Requests`, `5xx Server Error`):**
    -   Double-check your `INTERCOM_PROD_KEY` in `.env`.
    -   Ensure network connectivity to `https://api.intercom.io`.
    -   The script has retry logic, but frequent `429` errors might indicate hitting API rate limits. You may need to process data in smaller chunks (shorter date ranges) or contact Intercom support if limits are a consistent issue.
    -   `5xx` errors are server-side; retries usually help, but persistent issues should be noted.
-   **Google Drive Upload Failures:**
    -   Verify `GOOGLE_CREDENTIALS_JSON` (ensure it's valid JSON and the private key has `\\n` for newlines) and `GDRIVE_FOLDER_ID` in `.env`.
    -   Ensure the Google Cloud Service Account has the "Google Drive API" enabled in its GCP project.
    -   Ensure the service account email address (from the JSON key) has been granted "Editor" (or at least "Content manager" or "Contributor" depending on specific Drive API usage) permissions on the target `GDRIVE_FOLDER_ID`.
    -   Check `app.py` or `scripts/LLM5.py` console output for detailed error messages from the Google API client.
-   **Slack Notification Failures:**
    -   Verify `SLACK_BOT_TOKEN` and relevant `SLACK_CHANNEL_ID_...` in `.env`.
    -   Ensure the Slack bot has the necessary permissions (e.g., `chat:write`) in the target channels.
    -   Test the token and channel ID with a simple Slack API call if issues persist.
-   **Incorrect Date Processing (Timezones):**
    The script uses `pytz` for timezone handling, primarily targeting `America/Chicago` (USA_PRIMARY_TIMEZONE in `LLM5.py`) for default date calculations (like "last week"). Intercom API typically uses UTC for timestamps. Ensure your date inputs and interpretations align with expectations. The script converts input date strings to timestamps for API queries.

## AWS Deployment

The application is ready for deployment on AWS using Docker and AWS CDK. See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions on:

- Local Docker testing
- AWS ECS deployment with Fargate
- Auto-scaling configuration
- S3 integration for file storage
- CloudWatch monitoring

Quick start for AWS deployment:
```bash
cd aws_deployment
pip install -r requirements.txt
cdk bootstrap
cdk deploy
```

## Slack Data Scraping

The application now includes Slack data scraping capabilities for generating channel activity reports.

### Features
- Fetch conversation history from Slack channels
- Analyze message sentiment and engagement metrics
- Identify peak activity times and top contributors
- Generate formatted reports for posting back to Slack

### API Endpoints

1. **List Available Channels**
   ```
   GET /slack/list-channels/
   ```
   Returns all Slack channels the bot has access to.

2. **Scrape Channel Data**
   ```
   POST /slack/scrape-channel/
   {
     "channel_id": "C0XXXXXXXXX",
     "hours_back": 24
   }
   ```
   Generates an activity report for the specified channel.

### Setting Up Slack Scraping

1. **Add Required Permissions**
   In your Slack app settings, add these OAuth scopes:
   - `channels:history` - Read public channel messages
   - `groups:history` - Read private channel messages
   - `channels:read` - List channels
   - `groups:read` - List private channels

2. **Invite Bot to Channels**
   The bot must be invited to channels before it can read their history:
   ```
   /invite @your-bot-name
   ```

3. **Use the Scraping Features**
   - Call the API endpoints to generate reports
   - Reports are automatically saved to storage (local or S3)
   - Formatted reports can be posted back to Slack

### Example Slack Report Output
```
📊 Channel Activity Report: #team-support
Period: 2023-10-25T10:00:00 to 2023-10-26T10:00:00

📊 Key Metrics:
• Total Messages: 127
• Active Users: 15
• Threads Created: 23
• Total Reactions: 45
• Avg Messages/User: 8.5

😊 Sentiment Analysis:
• Average Sentiment: Positive (0.234)

⏰ Activity Patterns:
• Peak Hour: 14:00
• Peak Day: Wednesday

💬 Top Keywords:
• issue: 12
• resolved: 10
• customer: 8
```