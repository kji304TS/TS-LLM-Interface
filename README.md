# Intercom Conversation Analyzer & Reporter

This project provides a FastAPI backend and associated scripts to fetch, analyze, and report on Intercom conversations. It can generate Excel summaries, text-based insights, and end-of-shift reports (both global and team-specific), with options to send notifications to Slack and upload files to AWS S3.

## Features

- Fetch Intercom conversations within a specified date range or by a single conversation ID.
- Dynamically include all custom attributes from conversations in the output.
- Generate per-product-area Excel files with conversation details.
- Create text-based insight reports for each product area, including top issues, keyword analysis, and sentiment analysis.
- Generate consolidated "End of Shift" summary reports (global).
- Generate team-specific "End of Shift" reports.
- Send team-specific End of Shift reports to Slack.
- FastAPI endpoint to trigger script runs with various parameters.
- Command-line interface for direct execution and testing of the main processing script (`scripts/LLM5.py`), including options for targeted reporting and stop word suggestions.
- Upload generated files to AWS S3 (for cloud deployments).

## Prerequisites

- Python 3.10+ (Python 3.12 is actively used by some contributors and recommended).
- Pip (Python package installer).
- Access to an Intercom account with API key permissions.
- (Optional) Slack workspace and bot token for Slack notifications.
- (Optional) AWS credentials for S3 uploads (for cloud deployments).

## Setup Instructions

1.  **Clone the Repository (if you haven't already):**
    ```bash
    # git clone <your-repository-url>
    # cd TS-LLM-Interface
    ```
    Ensure all subsequent commands are run from the project root directory (`TS-LLM-Interface`).

2.  **Set up your environment variables:**
    Create a `.env` file in the project root with the following variables:
    ```env
    INTERCOM_PROD_KEY=sk_prod_your_intercom_key
    # For Slack notifications (optional)
    SLACK_BOT_TOKEN=xoxb-your-bot-token
    SLACK_CHANNEL_ID_METAMASK_TS=C0XXXXXXXXX
    SLACK_CHANNEL_ID_CARD=C0XXXXXXXXX
    # Add more team channels as needed
    # For AWS S3 (optional, for cloud deployments)
    AWS_ACCESS_KEY_ID=your-access-key
    AWS_SECRET_ACCESS_KEY=your-secret-key
    AWS_DEFAULT_REGION=us-east-1
    REPORTS_BUCKET=your-s3-bucket-name
    ```
    *   `INTERCOM_PROD_KEY`: Your production API key from Intercom.
    *   `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID_...`: (If using Slack notifications) Your Slack bot token and the channel IDs where reports should be sent. The `utils/slack_notifier.py` script might require specific channel ID variable names.
    *   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `REPORTS_BUCKET`: For S3 uploads (cloud deployments).

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
        *   `--send_slack`: Send generated team EoS reports to Slack (requires Slack env vars and configuration in `utils/slack_notifier.py`).
            Example: `python scripts/LLM5.py --target-team "MetaMask TS" --send_slack`
    
    *   **Suggest Stop Words from Existing Output:**
        (Assumes you have run the script before and have `.xlsx` files in `output_files/`)
        ```bash
        python scripts/LLM5.py --suggest-stop-words
        ```
        Review the console output for suggested words.

After running any test, check the console for detailed logs, error messages, and confirmation of file creation/upload.

## Output Files

When `scripts/LLM5.py` runs, it generates files in the following locations:

- `output_files/` — Excel files for each product area and team
- `Outputs/` — Text-based insights for each product area and team
- `Outputs/team_reports/` — End-of-shift summary reports (global and team-specific)

If running in AWS/cloud mode, files are uploaded to the configured S3 bucket.

## Troubleshooting

-   **Intercom API Timeouts/Errors (`429 Too Many Requests`, `5xx Server Error`):**
    -   Double-check your `INTERCOM_PROD_KEY` in `.env`.
    -   Ensure network connectivity to `https://api.intercom.io`.
    -   The script has retry logic, but frequent `429` errors might indicate hitting API rate limits. You may need to process data in smaller chunks (shorter date ranges) or contact Intercom support if limits are a consistent issue.
    -   `5xx` errors are server-side; retries usually help, but persistent issues should be noted.
-   **Slack Notification Failures:**
    -   Verify `SLACK_BOT_TOKEN` and relevant `SLACK_CHANNEL_ID_...` in `.env`.
    -   Ensure the Slack bot has the necessary permissions (e.g., `chat:write`) in the target channels.
    -   Test the token and channel ID with a simple Slack API call if issues persist.
-   **Incorrect Date Processing (Timezones):**
    The script uses `pytz` for timezone handling, primarily targeting `America/Chicago` (USA_PRIMARY_TIMEZONE in `LLM5.py`) for default date calculations (like "last week"). Intercom API typically uses UTC for timestamps. Ensure your date inputs and interpretations align with expectations. The script converts input date strings to timestamps for API queries.

## AWS Deployment

See `DEPLOYMENT_GUIDE.md` for details on deploying to AWS ECS/EKS and configuring S3 storage.