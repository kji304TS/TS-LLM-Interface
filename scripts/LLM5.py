import requests
from datetime import datetime, timedelta
import re
import os
from dotenv import load_dotenv  # ✅ Import dotenv
import time
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment
import openpyxl.utils
import argparse # Add argparse
import sys
import pytz # For timezone handling
import json # Make sure this is at the top with other imports
from textblob import TextBlob # <<< ADD THIS IMPORT

from utils.gdrive_uploader import upload_file_to_drive as app_upload_file_to_drive
from utils.slack_notifier import send_slack_report
from utils.intercom_team_fetcher import get_intercom_teams # Added import

# ✅ Load .env variables
load_dotenv()  # <-- This must be called BEFORE using os.getenv()

# ✅ Get values from .env
# API_KEY = os.getenv("API_KEY") # Handled by app.py's GDrive upload
# GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID") # Handled by app.py's GDrive upload
INTERCOM_PROD_KEY = os.getenv("INTERCOM_PROD_KEY") # Still needed for Intercom calls

# --- CONFIGURABLE TEAM IDENTIFICATION --- 
# !!! IMPORTANT: Update this placeholder with the actual Intercom custom attribute key 
# that indicates a conversation was elevated or handled by Technical Support.
# You can find this key by inspecting the Excel output from a single conversation test (-c flag).
ELEVATED_BY_FIELD_NAME_PLACEHOLDER = "elevated_by" # Actual field name
USA_PRIMARY_TIMEZONE = "America/Chicago"
# --- END CONFIGURABLE TEAM IDENTIFICATION ---

CATEGORY_HEADERS = {
    "Bridges": ["Bridge Issue"],
    "Card": ["MM Card Issue", "MM Card Partner issue", "Dashboard Issue", "KYC Issue", "Dashboard Issue - Subcategory", "KYC Issue - Subcategory"],
    "Dashboard": ["Dashboard issue"],
    "Ramps": ["Buy or Sell", "Buy issue", "Sell issue"],
    "SDK": [],
    "Security": ["scam vector", "Phishing Method", "Funds missing", "Compromise Method"], # Added "Compromise Method"
    "Snaps": ["Snaps Category"],
    "Staking": ["Staking Feature", "Validator Staking Issue", "Pooled Staking Issue", "Liquid Staking Issue", "Third Party Staking", "Bug ID", "Refund amount (USD)", "Refund Provided", "Withdrawals", "Managing Staked Tokens", "User Training", "Failed Transaction", "Liquid Staking Provider", "Staking Token Type", "Staking Platform"],
    "Swaps": ["Swaps issue"],
    "Wallet": ["Wallet issue"],
    "Wallet API": [],
    "Portfolio": [], 
    "Solana": []     
}

OUTPUT_DIR = "output_files"
INSIGHTS_DIR = "Outputs"
TEAM_REPORTS_DIR = os.path.join(INSIGHTS_DIR, "team_reports") # New directory for team reports

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(INSIGHTS_DIR, exist_ok=True)
os.makedirs(TEAM_REPORTS_DIR, exist_ok=True) # Create team_reports directory

# ✅ Define stop words to exclude common words from keyword analysis
STOP_WORDS = set([
    "the", "and", "of", "to", "a", "in", "for", "on", "with", "is", "this",
    "that", "it", "as", "was", "but", "are", "by", "or", "be", "at", "an",
    "not", "can", "if", "from", "about", "we", "you", "your", "so", "which",
    "there", "all", "will", "what", "has", "have", "do", "does", "had", "i",
    "summary", "available"
])

# ✅ Predefined Prompts - Restructured
PREDEFINED_PROMPTS = {
    "GLOBAL": { # Prompts applicable to most/all reports
        "Trends": [
            "How many conversations occurred in each subcategory?", # This might need to be more generic or context-aware
            "What percentage of total issues does each subcategory represent?", # Ditto
            "How have issue frequencies changed over time?",
            "What correlations exist between different issue types?",
            "Are there seasonal trends in user-reported issues?"
        ],
        "Keyword Analysis": [
            "What are the top 10 most important keywords?", # Removed 'in the summaries' for generality
            "What sentiment trends can be observed?" # Removed 'from the summaries'
        ],
        "Conversation Volume": [
            "How many conversations are in each MetaMask area?", # This is specific, might move or rephrase
            "Which MetaMask area has seen the highest increase in conversations?" # Ditto
        ]
    },
    "Security": { # Prompts specific to the Security product area
        "Scam Vector Analysis": [
            "What is the most frequent value in the 'scam vector' field?",
            "What are the counts for each 'scam vector' value (e.g., Address Poisoning, Airdrop Claim, etc.)?",
            "What percentage of Security conversations does each 'scam vector' represent?",
            "Are there any notable keywords or summaries associated with high-frequency 'scam vector' types?"
        ],
        "Phishing Method Analysis": [ # New category for Phishing Method
            "What is the most frequent value in the 'Phishing Method' field?",
            "What are the counts for each 'Phishing Method' value (e.g., Angler phishing, Email phishing, etc.)?",
            "What percentage of Security conversations does each 'Phishing Method' represent?",
            "Are there any notable keywords or summaries associated with high-frequency 'Phishing Method' types?"
        ],
        "Funds Missing Analysis": [
            "What is the most frequent reason in the 'Funds missing' field (e.g., SRP/PKcompromised, User error, Report scam, No funds lost)?",
            "What are the counts for each 'Funds missing' reason (e.g., SRP/PKcompromised, Unintended contract interaction, User error, Ecosystem exploit, No information, No funds lost, Unknown, Blockaid false positive, eth-phishing-detect false positive, Law enforcement / legal inquiry, Report scam, Request for update on prior ticket, Security questions)?",
            "What percentage of Security conversations does each 'Funds missing' reason represent?",
            "Are there notable keywords or summaries associated with high-frequency 'Funds missing' reasons, especially for actual loss categories vs. 'No funds lost' categories?"
        ],
        "Compromise Method Analysis": [ # New category for SRP/PK Compromise Methods
            "If 'Funds missing' is 'SRP/PKcompromised', what is the most frequent value in the 'Compromise Method' field (e.g., Malware, Rotten Seed)?",
            "What are the counts for each 'Compromise Method' (e.g., Malware, Rotten Seed, SRP Digitally Stolen, SRP Phished Directly, SRP Physically Stolen)?",
            "What percentage of SRP/PK compromised conversations does each 'Compromise Method' represent?",
            "Are there specific keywords or summary patterns associated with different 'Compromise Method' types like 'Malware' or 'Rotten Seed'?"
        ],
        "Top Issues": [ # Security might still have other general issue columns, if applicable
            # Add prompts here if Security uses other columns from CATEGORY_HEADERS like "Security Issue Subcategory"
        ]
    },
    "Card": {
        "Top Issues": [
            "What is the most frequent subcategory in the 'MM Card Issue' column?",
            "What is the most frequent subcategory in the 'MM Card Partner issue' column?",
            "What is the most frequent subcategory in the 'Dashboard Issue' column (related to Card)?",
            "What is the most frequent subcategory in the 'KYC Issue' column (related to Card)?"
        ]
    },
    "Bridges": {
        "Top Issues": ["What is the most frequent subcategory in the 'Bridge Issue' column?"]
    },
    "Ramps": {
        "Top Issues": [
            "What is the most frequent subcategory in the 'Buy issue' column?",
            "What is the most frequent subcategory in the 'Sell issue' column?"
        ]
    },
    "Snaps": {
        "Top Issues": ["What is the most frequent subcategory in the 'Snaps Category' column?"]
    },
    "Staking": {
        "Top Issues": [
            "What is the most frequent subcategory in the 'Staking Feature' column?",
            "What is the most frequent subcategory in the 'Validator Staking Issue' column?",
            "What is the most frequent subcategory in the 'Pooled Staking Issue' column?",
            "What is the most frequent subcategory in the 'Liquid Staking Issue' column?",
            "What is the most frequent subcategory in the 'Third Party Staking' column?"
        ]
    },
    "Swaps": {
        "Top Issues": ["What is the most frequent subcategory in the 'Swaps issue' column?"]
    },
    "Wallet": {
        "Top Issues": ["What is the most frequent subcategory in the 'Wallet issue' column?"]
    }
    # Add other product areas (Dashboard, SDK, Wallet API, Portfolio, Solana) if they have specific columns/prompts
}

# Removed get_last_week_dates() - dates will be passed from app.py
# Helper function to format dates for file naming
def get_yyyymmdd_date_strings(date_str_from_app):
    # Assumes date_str_from_app is "YYYY-MM-DD HH:MM"
    dt_obj = datetime.strptime(date_str_from_app.split(" ")[0], "%Y-%m-%d")
    return dt_obj.strftime("%Y%m%d")

# ✅ Extract and clean text
def remove_html_tags(text):
    if not isinstance(text, str):
        return ''
    clean = re.sub(r'<.*?>', '', text)
    return clean

def sanitize_text(text):
    if text:
        return text.replace('\u200b', '').encode('utf-8', 'ignore').decode('utf-8')
    return text

# ✅ Fetch summaries and transcripts
def get_conversation_summary(conversation):
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        for part in conversation_parts:
            if part.get('part_type') == 'conversation_summary':
                return remove_html_tags(part.get('body', ''))
    return "No summary available"

def get_conversation_transcript(conversation):
    transcript = []
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        for part in conversation_parts:
            if part.get('part_type') == 'comment':
                author = part.get('author', {}).get('type', 'Unknown')
                comment = remove_html_tags(part.get('body', ''))
                transcript.append(f"{author}: {comment}")
    return "\n".join(transcript) if transcript else "No transcript available"

# ✅ Fetch conversations from Intercom
def search_conversations(
    start_date_str: str, 
    end_date_str: str, 
    product_area_filter_value: str | None = None,
    team_filter_details: dict | None = None # New parameter for team filter
):
    """Fetches all conversations from Intercom with retry logic for timeouts."""
    start_timestamp = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M").timestamp()
    end_timestamp = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M").timestamp()

    url = "https://api.intercom.io/conversations/search"
    headers = {
        "Authorization": f"Bearer {INTERCOM_PROD_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    query_filters = [
        {"field": "statistics.last_close_at", "operator": ">", "value": int(start_timestamp)},
        {"field": "statistics.last_close_at", "operator": "<", "value": int(end_timestamp)}
    ]

    # --- Corrected and Uncommmented Product Area Filtering ---
    # Assuming the actual custom attribute name is "metamask_area". 
    # If it's different (e.g., "MetaMask area" with a space), this needs to be adjusted.
    ACTUAL_PRODUCT_AREA_CUSTOM_ATTRIBUTE_NAME = "MetaMask area" # UPDATED: Was "metamask_area"

    if product_area_filter_value:
        # --- ADD PRINT HERE ---
        print(f"👉 VERIFY: Using product area filter: custom_attribute.{ACTUAL_PRODUCT_AREA_CUSTOM_ATTRIBUTE_NAME} = '{product_area_filter_value}'. Ensure attribute name and value EXACTLY match Intercom.")
        # --- END ADD PRINT ---
        api_product_area_field = f"custom_attribute.{ACTUAL_PRODUCT_AREA_CUSTOM_ATTRIBUTE_NAME}" 
        query_filters.append({
            "field": api_product_area_field,
            "operator": "=", 
            "value": product_area_filter_value
        })
        print(f"   Adding API product area filter: '{api_product_area_field}' = '{product_area_filter_value}'")
        # print(f"   Product area filter ('{product_area_filter_value}') specified, but API-level filtering for product area is currently disabled. Filtering will occur post-fetch.") # Removed this line
    # --- End Corrected Product Area Filtering ---

    if team_filter_details: # Add team filter if provided
        query_filters.append(team_filter_details)
        # api_product_area_field = "custom_attribute.metamask_area" 
        # query_filters.append({
        #     "field": api_product_area_field,
        #     "operator": "=", 
        #     "value": product_area_filter_value
        # })
        # print(f"   Adding API product area filter: '{api_product_area_field}' = '{product_area_filter_value}'")
        print(f"   Product area filter ('{product_area_filter_value}') specified, but API-level filtering for product area is currently disabled. Filtering will occur post-fetch.")

    if team_filter_details: # Add team filter if provided
        query_filters.append(team_filter_details)
        print(f"   Adding API team filter: {team_filter_details}")

    # Initial payload
    payload = {
        "query": {
            "operator": "AND",
            "value": query_filters
        },
        "pagination": {"per_page": 100}
    }

    all_conversations = []
    retries = 3
    initial_timeout = 35 # MODIFIED from 45
    retry_timeout = 50   # MODIFIED from 60

    print(f"🔍 Intercom Search: Attempting to fetch conversations from {start_date_str} to {end_date_str}")
    # print(f"   Initial Payload: {json.dumps(payload)}") # Log the initial payload (json.dumps for pretty print)

    page_count = 0
    while True:
        page_count += 1
        print(f"   Fetching page {page_count}...")
        # --- Add detailed logging of the exact payload for each request ---
        print(f"   DEBUG: Sending payload to Intercom for page {page_count}: {json.dumps(payload, indent=2)}")
        # --- End detailed logging ---
        current_timeout = retry_timeout if page_count > 1 else initial_timeout
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=current_timeout)
            print(f"   Page {page_count} - Status Code: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                fetched_conversations = data.get('conversations', [])

                # If no conversations are returned on a page, assume it's the end.
                if not fetched_conversations:
                    print(f"   Page {page_count} - Fetched 0 conversations. Assuming end of results.")
                    break

                all_conversations.extend(fetched_conversations)
                print(f"   Page {page_count} - Fetched {len(fetched_conversations)} conversations. Total so far: {len(all_conversations)}")

                pagination = data.get('pages', {})
                next_page_data = pagination.get('next', None)

                if next_page_data and 'starting_after' in next_page_data:
                    payload['pagination']['starting_after'] = next_page_data['starting_after']
                    print(f"   Next page cursor: {next_page_data['starting_after']}")
                else:
                    print("   No more pages found.")
                    break
                retries = 3 # Reset retries on successful page fetch

            elif response.status_code == 429: # Explicitly handle rate limiting
                print(f"   ⚠️ Rate limit hit (429). Waiting for 60 seconds before retrying page {page_count}...")
                time.sleep(60)
                # No retry decrement here, just wait and retry the same page
                continue 
            elif response.status_code >= 500: # Server-side errors
                print(f"   ⚠️ Server error ({response.status_code}) on page {page_count}. Content: {response.text[:200]}")
                if retries > 0:
                    print(f"      Retrying page {page_count} in 15 seconds... ({retries} retries left)")
                    time.sleep(15)
                    retries -= 1
                else:
                    print(f"      ❌ Max retries reached for page {page_count} due to server error. Aborting search.")
                    break
            else: # Other client-side errors (400, 401, 403, etc.)
                print(f"   ❌ Client Error: {response.status_code} - {response.text[:500]}") # Log more of the error
                print(f"      Payload sent: {json.dumps(payload)}")
                return None # Abort on other client errors like auth issues

        except requests.exceptions.ReadTimeout:
            print(f"   ⚠️ Read timeout ({current_timeout}s) while fetching page {page_count}.")
            if retries > 0:
                print(f"      Retrying page {page_count} in 20 seconds... ({retries} retries left)")
                time.sleep(20)
                retries -= 1
            else:
                print(f"      ❌ Max retries reached for page {page_count} due to read timeout. Aborting search.")
                break
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Request failed for page {page_count}: {e}")
            return None # Abort on other request exceptions

    print(f"✅ Intercom Search: Finished. Total conversations fetched: {len(all_conversations)}")
    return all_conversations


# ✅ Fetch full conversation details
def get_intercom_conversation(conversation_id):
    url = f'https://api.intercom.io/conversations/{conversation_id}'
    retries = 3  # Number of retries allowed

    while retries > 0:
        try:
            response = requests.get(url, headers={"Authorization": f"Bearer {INTERCOM_PROD_KEY}"}, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 500:
                print(f"⚠️ Server error. Retrying... ({retries} retries left)")
                time.sleep(5)
                retries -= 1
            else:
                print(f"❌ Error fetching conversation {conversation_id}: {response.status_code}")
                return None

        except requests.exceptions.ReadTimeout:
            print(f"⚠️ Read timeout for conversation {conversation_id}. Retrying in 10 seconds...")
            time.sleep(10)
            retries -= 1

        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed for conversation {conversation_id}: {e}")
            return None

    print(f"❌ Max retries reached for conversation {conversation_id}. Skipping.")
    return None


def filter_conversations_by_product(conversations, product):
    filtered_conversations = []
    for conversation in conversations:
        attributes = conversation.get('custom_attributes', {})
        meta_mask_area = attributes.get('MetaMask area', '').strip()
        print(f"MetaMask Area: {meta_mask_area} (Expected: {product})")  

        if meta_mask_area.lower() == product.lower():
            full_conversation = get_intercom_conversation(conversation['id'])
            if full_conversation:
                # ✅ Extract all relevant attributes dynamically
                for category in CATEGORY_HEADERS.get(product, []):
                    full_conversation[category] = attributes.get(category, 'None')
                filtered_conversations.append(full_conversation)
    
    print(f"Total Conversations for {product}: {len(filtered_conversations)}")
    return filtered_conversations

# ✅ Store extracted data into a CSV file
# ✅ Store extracted data into an XLSX file
def store_conversations_to_xlsx(conversations, meta_mask_area, week_start_str_for_files, week_end_str_for_files):
    """Stores conversations in a dynamically named Excel file, including all custom attributes."""
    if not conversations:
        print(f"No conversations to store for {meta_mask_area}.")
        return None

    file_name = f"{meta_mask_area.lower()}_conversations_{week_start_str_for_files}_to_{week_end_str_for_files}.xlsx"
    file_path = os.path.join(OUTPUT_DIR, file_name)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversations"

    # Dynamically determine headers
    standard_headers = ['conversation_id', 'summary', 'transcript']
    all_custom_attribute_keys = set()
    for conv in conversations:
        if conv and isinstance(conv.get('custom_attributes'), dict):
            all_custom_attribute_keys.update(conv['custom_attributes'].keys())
    
    # Sort custom attribute keys for consistent column order, though order might still vary if new keys appear
    sorted_custom_attribute_keys = sorted(list(all_custom_attribute_keys))
    headers = standard_headers + sorted_custom_attribute_keys
    sheet.append(headers)

    for conversation in conversations:
        conversation_id = conversation.get('id', 'N/A') # Use .get for safety
        summary = sanitize_text(get_conversation_summary(conversation))
        transcript = sanitize_text(get_conversation_transcript(conversation))
        attributes = conversation.get('custom_attributes', {}) if isinstance(conversation.get('custom_attributes'), dict) else {}

        row_data = {
            'conversation_id': conversation_id,
            'summary': summary,
            'transcript': transcript
        }
        # Add all custom attributes found for this conversation
        for key in sorted_custom_attribute_keys:
            row_data[key] = attributes.get(key, 'N/A') # Default to 'N/A' if key not in this specific conversation
        
        current_row_for_excel = []
        for header in headers:
            value = row_data.get(header, 'N/A')
            processed_value = value

            if isinstance(value, list):
                if value:  # If list is not empty
                    processed_value = value[0]  # Take the first element
                else:  # If list is empty
                    processed_value = 'N/A'
            
            # Check again if the processed_value (e.g. from list[0]) or original value is a dict
            if isinstance(processed_value, dict):
                processed_value = str(processed_value) # Convert dict to string representation
            
            current_row_for_excel.append(processed_value)
        sheet.append(current_row_for_excel)

    # Auto-size columns for better readability
    for col_idx, column_cells in enumerate(sheet.columns):
        max_length = 0
        column = column_cells[0].column_letter
        for cell in column_cells:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        sheet.column_dimensions[column].width = adjusted_width

    for col_letter in ['B', 'C']:  # Summary and Transcript columns (adjust if needed based on dynamic headers)
        # This part might need to be smarter if B and C are no longer fixed due to many custom attributes
        # For now, let's assume summary and transcript remain prominent and relatively early columns.
        try:
            summary_col_letter = openpyxl.utils.get_column_letter(headers.index('summary') + 1)
            transcript_col_letter = openpyxl.utils.get_column_letter(headers.index('transcript') + 1)
            for col_letter_to_wrap in [summary_col_letter, transcript_col_letter]:
                for cell in sheet[col_letter_to_wrap]:
                    cell.alignment = Alignment(wrap_text=True)
        except ValueError:
            print("Warning: 'summary' or 'transcript' column not found for text wrapping.")
        except ImportError:
            print("Warning: openpyxl.utils not available, cannot dynamically find columns for wrapping. Skipping.")

    workbook.save(file_path)
    print(f"✅ File saved: {file_path}")
    return file_path


# --- Helper function for Sentiment Analysis (moved to global scope) ---
def get_text_sentiment_tuple(text_input):
    if pd.isna(text_input) or not isinstance(text_input, str) or not text_input.strip():
        return 0.0, 0.0 
    try:
        blob = TextBlob(str(text_input)) 
        return blob.sentiment.polarity, blob.sentiment.subjectivity
    except Exception as e:
        # print(f"Warning: Could not process text for sentiment: '{str(text_input)[:50]}...'. Error: {e}")
        return 0.0, 0.0 

# ✅ Analyze XLSX and generate insights
def analyze_xlsx_and_generate_insights(xlsx_file, meta_mask_area, week_start_str_for_files, week_end_str_for_files):
    """Analyzes the Excel file, generates structured insights based on PREDEFINED_PROMPTS."""
    if not xlsx_file or not os.path.exists(xlsx_file):
        print(f"Skipping analysis for {meta_mask_area}: XLSX file not found or not provided ({xlsx_file})")
        return None
    
    print(f"📊 Analyzing {xlsx_file} for {meta_mask_area}...")
    df = pd.read_excel(xlsx_file)
    df.columns = df.columns.str.strip() # Clean column names
    
    insights_file_name = f"{meta_mask_area.lower()}_insights_{week_start_str_for_files}_to_{week_end_str_for_files}.txt"
    insights_file_path = os.path.join(INSIGHTS_DIR, insights_file_name)
    
    if not os.path.exists(INSIGHTS_DIR):
        os.makedirs(INSIGHTS_DIR)
    
    analysis_text = [f"🚀 **Analysis for {meta_mask_area} ({week_start_str_for_files} to {week_end_str_for_files})**\n", "=" * 60, "\n\n"]
    
    # --- Helper function to generate frequency analysis for a column ---
    def generate_frequency_analysis(column_name, df_subset=None, conditional_column=None, conditional_value=None):
        if df_subset is None:
            df_subset = df # Use the full dataframe if no subset is provided
        
        text_lines = []
        if column_name not in df_subset.columns:
            text_lines.append(f"    Column '{column_name}' not found in the data for this section.")
            return text_lines

        # If conditional, filter the subset further
        if conditional_column and conditional_value:
            if conditional_column not in df_subset.columns:
                text_lines.append(f"    Conditional column '{conditional_column}' not found.")
                return text_lines
            df_subset = df_subset[df_subset[conditional_column] == conditional_value]
            if df_subset.empty:
                text_lines.append(f"    No data where '{conditional_column}' is '{conditional_value}' to analyze '{column_name}'.")
                return text_lines
            text_lines.append(f"    (Analysis for '{column_name}' where '{conditional_column}' = '{conditional_value}')")

        cleaned_series = df_subset[column_name].dropna().astype(str) # Ensure string type and drop NAs
        if cleaned_series.empty:
            text_lines.append(f"    No data available in '{column_name}' for frequency analysis.")
            return text_lines

        value_counts = cleaned_series.value_counts()
        total_count = value_counts.sum()
        percentages = (value_counts / total_count * 100).round(2)

        if not value_counts.empty:
            most_frequent = value_counts.index[0]
            count = value_counts.iloc[0]
            text_lines.append(f"    Most frequent value: **{most_frequent}** (Count: {count}, {percentages.iloc[0]:.2f}% of relevant entries)")
            text_lines.append(f"\n    Full Breakdown for '{column_name}':")
            text_lines.append(f"      {str(most_frequent):<40}{'Count':<10}{'Percentage':<12}")
            text_lines.append(f"      {'-'*39}{'-'*9}{'-'*11}")
            rank = 1
            for item, num in value_counts.items():
                percent = percentages.get(item, 0.0)
                text_lines.append(f"      {rank}. {str(item):<37}{num:<10}{percent:>10.2f}%")
                rank +=1
        else:
            text_lines.append(f"    No countable values found in '{column_name}'.")
        return text_lines

    # --- Determine text source for keywords and sentiment ---
    text_source_column = None
    keyword_source_message = "" 
    if 'summary' in df.columns and not df['summary'].dropna().empty:
        valid_summaries = df['summary'][
            df['summary'].notna() & \
            ~df['summary'].str.strip().str.lower().isin(['', 'no summary available', 'n/a'])
        ]
        if not valid_summaries.empty:
            text_source_column = 'summary'
            keyword_source_message = " (from summaries)"

    if text_source_column is None and 'transcript' in df.columns and not df['transcript'].dropna().empty:
        valid_transcripts = df['transcript'][
            df['transcript'].notna() & \
            ~df['transcript'].str.strip().str.lower().isin(['', 'no transcript available', 'n/a'])
        ]
        if not valid_transcripts.empty:
            text_source_column = 'transcript'
            keyword_source_message = " (from transcripts - summaries were unavailable/empty)"
    
    # --- Combine Global and Area-Specific Prompts ---
    prompts_to_process = {}
    global_prompts = PREDEFINED_PROMPTS.get("GLOBAL", {})
    area_specific_prompts = PREDEFINED_PROMPTS.get(meta_mask_area, {})

    for category, cat_prompts in global_prompts.items():
        if category not in prompts_to_process: prompts_to_process[category] = []
        prompts_to_process[category].extend(cat_prompts)
    for category, cat_prompts in area_specific_prompts.items():
        if category not in prompts_to_process: prompts_to_process[category] = []
        prompts_to_process[category].extend(cat_prompts)

    # --- Process Prompts ---
    for category_title, individual_prompts in prompts_to_process.items():
        analysis_text.append(f"\n🔹 **{category_title.replace('_', ' ')}**") # Nicer category titles
        
        for prompt_text in individual_prompts:
            analysis_text.append(f"\n  *Prompt: {prompt_text}*")
            answered = False

            # Keyword Analysis (GLOBAL)
            if category_title == "Keyword Analysis" and "top 10 most important keywords" in prompt_text:
                if text_source_column:
                    text_for_keywords_series = df[text_source_column][df[text_source_column].notna()].astype(str)
                    if not text_for_keywords_series.empty:
                        word_series = text_for_keywords_series.str.lower().str.split(expand=True).stack()
                        word_series = word_series.str.replace(r'^[^\w\s]+|[^\w\s]+$', '', regex=True) 
                        word_series = word_series[word_series != ''] 
                        filtered_words = word_series[~word_series.isin(STOP_WORDS) & (word_series.str.len() > 2)]
                        if not filtered_words.empty:
                            top_words_counts = filtered_words.value_counts().head(10)
                            if not top_words_counts.empty:
                                analysis_text.append("\n  Top Keywords:")
                                for kw, count in top_words_counts.items(): analysis_text.append(f"    - {kw} ({count})")
                            else: analysis_text.append("    No significant keywords found after filtering.")
                        else: analysis_text.append("    No words left after filtering for stop words and length.")
                    else: analysis_text.append(f"    No valid text in '{text_source_column}' for keyword extraction.")
                else: analysis_text.append("    No text source (summary/transcript) available for keyword extraction.")
                answered = True
            # Sentiment Analysis (GLOBAL)
            elif category_title == "Keyword Analysis" and "sentiment trends can be observed" in prompt_text:
                if text_source_column and 'sentiment_polarity' not in df.columns: # Calculate if not already done
                    sentiments = df[text_source_column].apply(get_text_sentiment_tuple) 
                    df['sentiment_polarity'] = sentiments.apply(lambda x: x[0] if isinstance(x, tuple) else 0.0)
                    df['sentiment_subjectivity'] = sentiments.apply(lambda x: x[1] if isinstance(x, tuple) else 0.0)
                # ... (add positive/negative/neutral counts as before if desired)
                if text_source_column and 'sentiment_polarity' in df.columns and df['sentiment_polarity'].notna().any():
                    valid_sentiment_df = df[df['sentiment_polarity'].notna()] # Ensure we only use valid scores

                    avg_polarity = valid_sentiment_df['sentiment_polarity'].mean()
                    avg_subjectivity = valid_sentiment_df['sentiment_subjectivity'].mean()
                    analysis_text.append(f"Source Text for Sentiment: {text_source_column.capitalize()}{keyword_source_message}")
                    analysis_text.append(f"Average Sentiment Polarity: {avg_polarity:.2f} (Range: -1 Negative to +1 Positive)")
                    analysis_text.append(f"Average Sentiment Subjectivity: {avg_subjectivity:.2f} (Range: 0 Objective to 1 Subjective)")
                    # ... (add positive/negative/neutral counts as before if desired)
                else: analysis_text.append("    Sentiment analysis not performed or no valid scores.")
                answered = True

            # Security Specific Analyses
            elif meta_mask_area == "Security":
                if category_title == "Scam Vector Analysis":
                    analysis_text.extend(generate_frequency_analysis("scam vector"))
                    answered = True
                elif category_title == "Phishing Method Analysis":
                    analysis_text.extend(generate_frequency_analysis("Phishing Method"))
                    answered = True
                elif category_title == "Funds Missing Analysis":
                    # This prompt has multiple parts usually covered by generate_frequency_analysis for "Funds missing"
                    analysis_text.extend(generate_frequency_analysis("Funds missing"))
                    # Specific prompt for keywords related to loss could be added here if needed
                    answered = True
                elif category_title == "Compromise Method Analysis":
                    # Conditional analysis: only if "Funds missing" is "SRP/PKcompromised"
                    # The prompt phrasing implies this, so the helper handles it.
                    analysis_text.extend(generate_frequency_analysis("Compromise Method", conditional_column="Funds missing", conditional_value="SRP/PKcompromised"))
                    answered = True

            # Top Issues (Area-Specific)
            # This logic now finds the column name from the prompt itself.
            elif category_title == "Top Issues" and "most frequent subcategory in the '" in prompt_text:
                match = re.search(r"in the '([^\']+)' column", prompt_text)
                if match:
                    issue_column_from_prompt = match.group(1)
                    analysis_text.extend(generate_frequency_analysis(issue_column_from_prompt))
                    answered = True
                else:
                    analysis_text.append("    Could not parse column name from 'Top Issues' prompt.")
                    answered = True # Mark as answered to avoid "Not specifically answered"

            # Fallback for Trends and Conversation Volume or other complex prompts
            if not answered and category_title in ["Trends", "Conversation Volume"]:
                analysis_text.append("    Detailed analysis for this trend/volume prompt is not yet implemented.")
                answered = True # Mark as handled for now
            
            if not answered:
                analysis_text.append("    This specific prompt is not automatically answered by current logic.")

    # --- Save insights file ---
    with open(insights_file_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(analysis_text))
    
    print(f"✅ Insights saved: {insights_file_path}")
    return insights_file_path

# Removed authenticate_google_drive and upload_to_google_drive functions

def _generate_scoped_product_area_files(
    conversations_for_scope: list, # List of 'thin' conversation objects for the current scope
    product_area_name: str,
    scope_identifier: str, # e.g., "TeamName" or "GLOBAL". Used for file naming.
    week_start_str_for_files: str,
    week_end_str_for_files: str,
    all_generated_files_list: list # List to append generated file paths to
) -> pd.DataFrame | None:
    """
    Filters conversations for a specific product area within a given scope,
    then generates and stores XLSX and insights files.

    Args:
        conversations_for_scope: List of conversation dicts (can be 'thin' from search).
        product_area_name: The name of the product area to filter for.
        scope_identifier: A string identifying the scope (e.g., team name or "GLOBAL").
        week_start_str_for_files: Date string for file naming.
        week_end_str_for_files: Date string for file naming.
        all_generated_files_list: List to which paths of generated files will be appended.

    Returns:
        A pandas DataFrame containing the data for the generated XLSX file, or None if no data.
    """
    print(f"  Filtering for product area '{product_area_name}' within scope '{scope_identifier}'...")
    # filter_conversations_by_product fetches full details if needed
    area_specific_conversations = filter_conversations_by_product(conversations_for_scope, product_area_name)

    if not area_specific_conversations:
        print(f"    No conversations found for product area '{product_area_name}' in scope '{scope_identifier}'.")
        return None

    file_label = f"{scope_identifier}_{product_area_name}" if scope_identifier != "GLOBAL" else product_area_name
    
    print(f"    Storing {len(area_specific_conversations)} conversations for '{file_label}'...")
    xlsx_file_path = store_conversations_to_xlsx(
        area_specific_conversations,
        file_label.replace(" ", "_"), # Ensure clean file name
        week_start_str_for_files,
        week_end_str_for_files
    )

    dataframe_for_report = None
    if xlsx_file_path:
        all_generated_files_list.append(xlsx_file_path)
        print(f"    Analyzing '{file_label}'...")
        insights_file_path = analyze_xlsx_and_generate_insights(
            xlsx_file_path,
            file_label.replace(" ", "_"), # Ensure clean context name
            week_start_str_for_files,
            week_end_str_for_files
        )
        if insights_file_path:
            all_generated_files_list.append(insights_file_path)
        
        try:
            dataframe_for_report = pd.read_excel(xlsx_file_path)
        except Exception as e:
            print(f"    Error reading {xlsx_file_path} back into DataFrame: {e}")
            dataframe_for_report = pd.DataFrame() # Return empty df on error
    
    return dataframe_for_report


def generate_end_of_shift_report(all_product_data, week_start_str_for_files, week_end_str_for_files):
    report_content = f"End of Shift Report ({week_start_str_for_files} to {week_end_str_for_files})\n\n"
    grand_total_conversations = 0
    all_issues_summary = {}

    for product_area, data in all_product_data.items():
        df = data['dataframe']
        if df is None or df.empty:
            report_content += f"No data processed for {product_area}.\n"
            continue

        num_conversations = len(df)
        grand_total_conversations += num_conversations
        report_content += f"Product Area: {product_area} ({num_conversations} conversations)\n"
        
        issue_columns = CATEGORY_HEADERS.get(product_area, [])
        primary_issue_col = issue_columns[0] if issue_columns else None

        if primary_issue_col and primary_issue_col in df.columns and not df[primary_issue_col].dropna().empty:
            top_issue = df[primary_issue_col].mode()[0] # Get the most frequent
            top_issue_count = df[primary_issue_col].value_counts().iloc[0]
            report_content += f"  - Biggest Issue: {top_issue} ({top_issue_count} occurrences)\n"
            
            # Aggregate for overall summary
            for issue, count in df[primary_issue_col].value_counts().items():
                all_issues_summary[f"{product_area} - {issue}"] = all_issues_summary.get(f"{product_area} - {issue}", 0) + count
        else:
            report_content += f"  - No primary issue data to report for {product_area}.\n"
        report_content += "---\n"

    report_content += f"\nOverall Summary:\n"
    report_content += f"Grand Total Conversations Processed: {grand_total_conversations}\n"
    
    if all_issues_summary:
        sorted_overall_issues = sorted(all_issues_summary.items(), key=lambda item: item[1], reverse=True)
        report_content += "Top 3 Issues Across All Products:\n"
        for i, (issue, count) in enumerate(sorted_overall_issues[:3]):
            report_content += f"  {i+1}. {issue}: {count} occurrences\n"
    else:
        report_content += "No specific issue data aggregated across products.\n"

    report_file_name = f"end_of_shift_report_{week_start_str_for_files}_to_{week_end_str_for_files}.txt"
    report_file_path = os.path.join(INSIGHTS_DIR, report_file_name)
    with open(report_file_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    print(f"✅ End of Shift Report saved: {report_file_path}")
    return report_file_path

def determine_conversation_team(conversation_data):
    """Determines the team for a single conversation based on predefined logic."""
    attributes = conversation_data.get('custom_attributes', {})
    elevated_value = attributes.get(ELEVATED_BY_FIELD_NAME_PLACEHOLDER)
    is_elevated = True if elevated_value not in [None, "", "N/A", "None"] else False
    meta_mask_area = attributes.get('MetaMask area', '').strip().lower()

    if is_elevated:
        return "MetaMask TS"
    
    # Specific product area teams (ensure these product area names are lowercased for comparison)
    if meta_mask_area == 'card':
        return "Card"
    if meta_mask_area == 'portfolio':
        return "Portfolio"
    if meta_mask_area == 'solana':
        return "Solana"
    if meta_mask_area == 'security': # Assuming "Security" product area maps to MetaMask UST team
        return "MetaMask HD UST"
    
    # Fallback for other conversations
    return "MetaMask HD General"

def generate_team_end_of_shift_report(team_name, team_conversations, week_start_str_for_files, week_end_str_for_files):
    """Generates an End of Shift report specifically for a given team's conversations."""
    report_content = f"Team End of Shift Report: {team_name} ({week_start_str_for_files} to {week_end_str_for_files})\n"
    report_content += "=" * (len(report_content) -1) + "\n\n"

    if not team_conversations:
        report_content += "No conversations found for this team in this period.\n"
        # Save and return even if empty for consistency
        report_file_name = f"{team_name.replace(' ', '_')}_EOS_Report_{week_start_str_for_files}_to_{week_end_str_for_files}.txt"
        report_file_path = os.path.join(TEAM_REPORTS_DIR, report_file_name)
        with open(report_file_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        print(f"✅ Empty Team End of Shift Report saved: {report_file_path}")
        return report_file_path, report_content

    # Convert list of conversations to DataFrame for analysis similar to existing report
    # We need to extract relevant fields: custom attributes for issues, summaries.
    data_for_df = []
    for conv in team_conversations:
        attrs = conv.get('custom_attributes', {})
        summary = get_conversation_summary(conv) # Assuming this function is defined elsewhere
        row = {'summary': summary, **attrs} # Include all custom attributes
        data_for_df.append(row)
    df = pd.DataFrame(data_for_df)

    num_conversations = len(df)
    report_content += f"Total Conversations for Team: {num_conversations}\n\n"

    # Simplified: Aggregate top issues from all relevant CATEGORY_HEADERS for this team's conversations
    # This part needs careful thought: which columns define "issues" for a team?
    # For now, let's try to find most common values in *any* of the known issue columns present in this team's data.
    team_issues_summary = {}
    all_known_issue_columns = [col for cols in CATEGORY_HEADERS.values() for col in cols]
    
    for col_name in df.columns:
        if col_name in all_known_issue_columns and not df[col_name].dropna().empty:
            for issue, count in df[col_name].value_counts().items():
                if issue not in [None, "", "N/A", "None"]:
                    team_issues_summary[f"{col_name} - {issue}"] = team_issues_summary.get(f"{col_name} - {issue}", 0) + count
    
    if team_issues_summary:
        sorted_team_issues = sorted(team_issues_summary.items(), key=lambda item: item[1], reverse=True)
        report_content += "Top Issues/Custom Attributes Reported for Team:\n"
        for i, (issue, count) in enumerate(sorted_team_issues[:5]): # Top 5 overall for the team
            report_content += f"  {i+1}. {issue}: {count} occurrences\n"
    else:
        report_content += "No specific issue data aggregated for this team (check CATEGORY_HEADERS and data).\n"
    report_content += "---\n"
    
    # Top keywords from summaries for this team
    if 'summary' in df.columns and not df['summary'].dropna().empty:
        all_summaries = " ".join(df['summary'].dropna().astype(str).tolist()).lower()
        words = re.findall(r'\b\w+\b', all_summaries)
        filtered_words = [word for word in words if word not in STOP_WORDS and len(word) > 2]
        word_counts = pd.Series(filtered_words).value_counts().nlargest(5)
        
        report_content += "\nTop 5 Keywords from Summaries for Team:\n"
        for keyword, count in word_counts.items():
            report_content += f"- {keyword}: {count}\n"
    else:
        report_content += "\nNo summary data available for keyword analysis for this team.\n"

    # --- Team Sentiment Analysis ---
    # Ensure get_text_sentiment_tuple is accessible here or redefine if necessary
    # For this edit, assuming it's defined locally or accessible (e.g., moved to utils)
    # If not, you'd need to redefine the get_text_sentiment_tuple helper here too.
    
    team_text_source_column = None
    if 'summary' in df.columns and not df['summary'].dropna().empty:
        valid_summaries = df['summary'][df['summary'].notna() & ~df['summary'].str.strip().str.lower().isin(['', 'no summary available', 'n/a'])]
        if not valid_summaries.empty:
            team_text_source_column = 'summary'
    if team_text_source_column is None and 'transcript' in df.columns and not df['transcript'].dropna().empty:
        valid_transcripts = df['transcript'][df['transcript'].notna() & ~df['transcript'].str.strip().str.lower().isin(['', 'no transcript available', 'n/a'])]
        if not valid_transcripts.empty:
            team_text_source_column = 'transcript'

    if team_text_source_column:
        print(f"Calculating sentiment for team '{team_name}' from '{team_text_source_column}' column...")
        try:
            # Now calls the global get_text_sentiment_tuple
            team_sentiments = df[team_text_source_column].apply(get_text_sentiment_tuple) 
            df['sentiment_polarity'] = team_sentiments.apply(lambda x: x[0] if isinstance(x, tuple) else 0.0)
            df['sentiment_subjectivity'] = team_sentiments.apply(lambda x: x[1] if isinstance(x, tuple) else 0.0)

            avg_polarity = df['sentiment_polarity'].mean()
            avg_subjectivity = df['sentiment_subjectivity'].mean()
            
            report_content += f"\nSentiment Analysis (from {team_text_source_column}): \n"
            report_content += f"  - Average Polarity: {avg_polarity:.2f} \n"
            report_content += f"  - Average Subjectivity: {avg_subjectivity:.2f} \n"

            positive_threshold = 0.05
            negative_threshold = -0.05
            positive_count = df[df['sentiment_polarity'] > positive_threshold].shape[0]
            negative_count = df[df['sentiment_polarity'] < negative_threshold].shape[0]
            neutral_count = df[(df['sentiment_polarity'] >= negative_threshold) & (df['sentiment_polarity'] <= positive_threshold)].shape[0]
            total_sentiments = positive_count + negative_count + neutral_count

            if total_sentiments > 0:
                report_content += "  Distribution: \n"
                report_content += f"    - Positive: {positive_count} ({positive_count/total_sentiments:.1%}) \n"
                report_content += f"    - Neutral:  {neutral_count} ({neutral_count/total_sentiments:.1%}) \n"
                report_content += f"    - Negative: {negative_count} ({negative_count/total_sentiments:.1%}) \n"
            else:
                report_content += "  No sentiment scores available for distribution for this team. \n"
        except Exception as e:
            report_content += f"\nError during team sentiment analysis: {e} \n"
            print(f"Error in team sentiment for {team_name}: {e}")
    else:
        report_content += "\nSentiment analysis not performed for team (no suitable text source found). \n"
    report_content += "---\n"
    
    # ... (rest of team report generation, including keyword analysis if any, and saving the file) ...

    report_file_name = f"{team_name.replace(' ', '_')}_EOS_Report_{week_start_str_for_files}_to_{week_end_str_for_files}.txt"
    report_file_path = os.path.join(TEAM_REPORTS_DIR, report_file_name)
    with open(report_file_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    print(f"✅ Team End of Shift Report saved: {report_file_path}")
    return report_file_path, report_content

def main_function(
    start_date_str: str, 
    end_date_str: str, 
    upload_to_gdrive: bool = False, 
    send_to_slack: bool = False,
    target_team_name: str | None = None,
    target_product_area_name: str | None = None
):
    """Main function to fetch, process, and analyze Intercom conversations, with targeted reporting."""
    print(f"🚀 LLM5.py: main_function started for {start_date_str} to {end_date_str}")
    print(f"⚙️ Targets - Team: {target_team_name or 'All'}, Product Area: {target_product_area_name or 'All'}")
    print(f"☁️ Upload to Google Drive: {upload_to_gdrive}")
    print(f"📢 Send to Slack: {send_to_slack}")

    try:
        week_start_str_for_files = get_yyyymmdd_date_strings(start_date_str)
        week_end_str_for_files = get_yyyymmdd_date_strings(end_date_str)
    except ValueError as e:
        print(f"❌ Error parsing input dates for file naming: {e}")
        return {"status": "failed", "message": f"Error parsing input dates: {e}", "local_files": [], "gdrive_urls": [], "processed_counts": {}}

    # Initialize API filter variables
    product_area_api_filter_value = None
    team_api_filter_details = None

    # Fetch all team names and IDs from Intercom
    # This is done once, regardless of targeting, in case it's needed for some logic
    # or if we want to validate target_team_name against actual team names.
    print("⚙️ Fetching Intercom team list for potential ID-based filtering...")
    available_intercom_teams = get_intercom_teams() # Returns a name:id dict or None
    if available_intercom_teams is None:
        print("⚠️ Could not fetch Intercom teams. ID-based API filtering for teams will be skipped.")
        available_intercom_teams = {} # Ensure it's an empty dict to avoid errors
    else:
        print(f"  Found {len(available_intercom_teams)} teams in Intercom: {list(available_intercom_teams.keys())}") # Log fetched team names

    # Priority: Use team_assignee_id if target_team_name matches a fetched team name
    if target_team_name and target_team_name in available_intercom_teams:
        team_id_for_filter = available_intercom_teams[target_team_name]
        team_api_filter_details = {"field": "team_assignee_id", "operator": "=", "value": team_id_for_filter}
        print(f"ℹ️ Will attempt to filter initial Intercom search by Team ID: {team_id_for_filter} for Team Name: '{target_team_name}'")
    # Fallback to custom attribute based filtering for specific, predefined team names if no ID match or if logic dictates
    elif target_team_name == "MetaMask TS": 
        team_api_filter_details = {"field": f"custom_attribute.{ELEVATED_BY_FIELD_NAME_PLACEHOLDER}", "operator": "EXISTS"}
        print(f"ℹ️ (Fallback) Will attempt to filter initial Intercom search for Team: MetaMask TS (using {ELEVATED_BY_FIELD_NAME_PLACEHOLDER} EXISTS)")
    elif target_team_name == "Card": 
        team_api_filter_details = {"field": "custom_attribute.metamask_area", "operator": "=", "value": "Card"}
        print(f"ℹ️ (Fallback) Will attempt to filter initial Intercom search for Team: Card (metamask_area = Card)")
    elif target_team_name == "Portfolio": 
        team_api_filter_details = {"field": "custom_attribute.metamask_area", "operator": "=", "value": "Portfolio"}
        print(f"ℹ️ (Fallback) Will attempt to filter initial Intercom search for Team: Portfolio (metamask_area = Portfolio)")
    elif target_team_name == "Solana": 
        team_api_filter_details = {"field": "custom_attribute.metamask_area", "operator": "=", "value": "Solana"}
        print(f"ℹ️ (Fallback) Will attempt to filter initial Intercom search for Team: Solana (metamask_area = Solana)")
    elif target_team_name: # This will include "Phosphor TS" if not caught by ID check
        # If target_team_name was provided but didn't match any ID or specific fallback logic
        print(f"⚠️ Target team '{target_team_name}' not found in fetched Intercom teams or specific fallbacks. API-level team filtering may not be applied for this team. Python-side filtering will still occur if possible.")
        # team_api_filter_details remains None for this specific target_team_name
        
    # Product area filter is applied if target_product_area_name is set (and not ALL_AREAS or empty string)
    # An empty string for target_product_area_name means no PA filter (e.g., for Phosphor TS)
    # Note: app.py converts empty string from UI to None before calling this function.
    if target_product_area_name and target_product_area_name != "ALL_AREAS": # `None` will not satisfy this condition
        product_area_api_filter_value = target_product_area_name
        print(f"ℹ️ Will attempt to filter initial Intercom search by Product Area: {product_area_api_filter_value}")
    else:
        # If target_product_area_name is None (from empty string in UI), "ALL_AREAS", no specific product area API filter is applied.
        print(f"ℹ️ No specific product area API filter will be applied (target_product_area_name from app.py: '{target_product_area_name}').")
        # product_area_api_filter_value remains None here by default if not set above

    print(f"🔎 Pre-Safety Check Filter Status:")
    print(f"   - target_team_name: '{target_team_name}'")
    print(f"   - team_api_filter_details: {team_api_filter_details}")
    print(f"   - target_product_area_name (from app.py): '{target_product_area_name}'")
    print(f"   - product_area_api_filter_value (used for search): '{product_area_api_filter_value}'")

    # --- Safety check for overly broad queries ---
    if target_team_name and not team_api_filter_details and \
       (not product_area_api_filter_value or product_area_api_filter_value == "ALL_AREAS"):
        message = f"Configuration for team '{target_team_name}' does not allow for specific API-level filtering, and no specific product area was selected to narrow the search. Query would be too broad and is not permitted. Please ensure '{target_team_name}' is an exact match to an Intercom team name with an ID, or define a custom attribute filter for it."
        print(f"❌ SAFETY CHECK TRIGGERED: {message}")
        return {"status": "failed", "message": message, "local_files": [], "gdrive_urls": [], "processed_counts": {}}

    print("✅ Safety check passed or not applicable.")
    conversations = search_conversations(
        start_date_str, 
        end_date_str, 
        product_area_filter_value=product_area_api_filter_value,
        team_filter_details=team_api_filter_details
    )
    
    if conversations is None:
        print("❌ Failed to fetch conversations from Intercom.")
        return {"status": "failed", "message": "Failed to fetch Intercom conversations.", "local_files": [], "gdrive_urls": [], "processed_counts": {}}

    if not conversations:
        print("🤷 No conversations found for the selected timeframe.")
        return {"status": "no_data", "message": "No conversations found.", "local_files": [], "gdrive_urls": [], "processed_counts": {}}

    all_generated_files = []
    uploaded_file_urls = []
    # Initialize new detailed counters
    processed_counts = {
        "total_conversations_fetched": len(conversations),
        "targeted_team_product_area_files": 0, # For Team X + Area Y combo
        "team_eos_reports_generated": 0,
        "team_specific_product_area_files": 0, # Files generated when a team is targeted (for all its areas)
        "global_product_area_files": 0,        # Files generated when an area is targeted (globally)
        "overall_eos_report_generated": 0,
        "unclassified_team_skipped": False
    }

    team_grouped_conversations = {
        "MetaMask TS": [],
        "MetaMask HD UST": [],
        "Card": [],
        "Portfolio": [],
        "Solana": [],
        "MetaMask HD General": [],
        "Unclassified": [] # Keep Unclassified for any edge cases or if determine_conversation_team returns it.
    }
    for conv_data in conversations:
        if isinstance(conv_data, dict):
            team = determine_conversation_team(conv_data)
            team_grouped_conversations.get(team, team_grouped_conversations["Unclassified"]).append(conv_data)
        else:
            print(f"Warning: Found non-dictionary item in conversations: {type(conv_data)}")

    # --- Conditional Report Generation ---

    if target_team_name and target_product_area_name:
        print(f"\n--- Generating report for specific Team '{target_team_name}' AND Product Area '{target_product_area_name}' ---")
        if target_team_name not in team_grouped_conversations or not team_grouped_conversations[target_team_name]:
            print(f"  Specified team '{target_team_name}' not found or has no conversations. Skipping.")
        elif target_product_area_name not in CATEGORY_HEADERS:
            print(f"  Specified product area '{target_product_area_name}' is invalid. Skipping.")
        else:
            team_convs_for_target = team_grouped_conversations[target_team_name]
            # _generate_scoped_product_area_files handles filtering by area internally
            df_generated = _generate_scoped_product_area_files(
                conversations_for_scope=team_convs_for_target,
                product_area_name=target_product_area_name,
                scope_identifier=target_team_name, # File prefix will be TeamName_AreaName
                week_start_str_for_files=week_start_str_for_files,
                week_end_str_for_files=week_end_str_for_files,
                all_generated_files_list=all_generated_files
            )
            if df_generated is not None:
                processed_counts["targeted_team_product_area_files"] += 1 # Counts pairs of (XLSX, TXT) as 1 logical unit

    elif target_team_name: # Specific team, all its product areas + its EoS
        print(f"\n--- Generating reports for Target Team: {target_team_name} ---")
        if target_team_name not in team_grouped_conversations or not team_grouped_conversations[target_team_name]:
            print(f"  Specified team '{target_team_name}' not found or has no conversations. Skipping.")
        else:
            team_convs_for_target = team_grouped_conversations[target_team_name]
            
            # 1. Generate Team EoS Report
            print(f"  Generating End of Shift Report for team: {target_team_name}...")
            team_report_path, team_report_content = generate_team_end_of_shift_report(
                target_team_name, team_convs_for_target, week_start_str_for_files, week_end_str_for_files
            )
            if team_report_path:
                all_generated_files.append(team_report_path)
                processed_counts["team_eos_reports_generated"] += 1
                if send_to_slack and team_report_content:
                    print(f"    Attempting to send EoS report for {target_team_name} to Slack...")
                    send_slack_report(target_team_name, team_report_content)

            # 2. Generate product area files for this team
            print(f"  Generating product area files for team: {target_team_name}...")
            for area_name in CATEGORY_HEADERS.keys():
                df_generated = _generate_scoped_product_area_files(
                    conversations_for_scope=team_convs_for_target,
                    product_area_name=area_name,
                    scope_identifier=target_team_name,
                    week_start_str_for_files=week_start_str_for_files,
                    week_end_str_for_files=week_end_str_for_files,
                    all_generated_files_list=all_generated_files
                )
                if df_generated is not None:
                     processed_counts["team_specific_product_area_files"] += 1
    
    elif target_product_area_name: # Specific product area, global context
        print(f"\n--- Generating reports for Target Product Area (Global): {target_product_area_name} ---")
        if target_product_area_name not in CATEGORY_HEADERS:
            print(f"  Specified product area '{target_product_area_name}' is invalid. Skipping.")
        else:
            # Generate files for this product area using ALL conversations
            _generate_scoped_product_area_files(
                conversations_for_scope=conversations, # All conversations
                product_area_name=target_product_area_name,
                scope_identifier="GLOBAL", # Results in "GLOBAL_AreaName" or just "AreaName" files
                week_start_str_for_files=week_start_str_for_files,
                week_end_str_for_files=week_end_str_for_files,
                all_generated_files_list=all_generated_files
            )
            # The helper appends to all_generated_files; count based on successful generation if needed more finely
            # For simplicity, we'll assume if called, it's an attempt. Actual file count is len(all_generated_files)
            # This path doesn't generate an EoS report currently, just the area files.
            # Incrementing a counter if any files are made for this global area.
            # The number of files generated by the helper is 2 (xlsx, txt) if successful.
            # Let's count "sets" of product area files.
            # The helper returns a df if successful, so we can count that.
            if any(target_product_area_name in f for f in all_generated_files): # crude check
                 processed_counts["global_product_area_files"] += 1


    else: # No specific targets - run full original process
        print("\n--- Generating Full Suite of Reports (All Product Areas & All Teams) ---")
        
        # 1. Global Product Area Files and Overall EoS Report
        all_product_data_for_overall_report = {}
        print("  Processing all product areas globally...")
        for area in CATEGORY_HEADERS.keys():
            df_global_area = _generate_scoped_product_area_files(
                conversations_for_scope=conversations,
                product_area_name=area,
                scope_identifier="GLOBAL",
                week_start_str_for_files=week_start_str_for_files,
                week_end_str_for_files=week_end_str_for_files,
                all_generated_files_list=all_generated_files
            )
            if df_global_area is not None:
                all_product_data_for_overall_report[area] = {'dataframe': df_global_area}
                processed_counts["global_product_area_files"] += 1
            else: # Ensure key exists even if no data, for generate_end_of_shift_report
                all_product_data_for_overall_report[area] = {'dataframe': pd.DataFrame()}

        if any(not data['dataframe'].empty for data in all_product_data_for_overall_report.values()):
            print("  Generating Overall End of Shift Report...")
            overall_eos_report_path = generate_end_of_shift_report(all_product_data_for_overall_report, week_start_str_for_files, week_end_str_for_files)
            if overall_eos_report_path:
                all_generated_files.append(overall_eos_report_path)
                processed_counts["overall_eos_report_generated"] += 1
        else:
            print("  No data from global product areas for overall report. Skipping.")

        # 2. All Team-Specific End of Shift Reports
        print("  Generating all team-specific End of Shift reports...")
        for team_name_iter, team_convs_iter in team_grouped_conversations.items():
            if team_name_iter == "Unclassified" and not team_convs_iter:
                processed_counts["unclassified_team_skipped"] = True
                continue
            if not team_convs_iter:
                 print(f"    Skipping EoS report for team '{team_name_iter}' as it has no conversations.")
                 continue

            print(f"    Generating EoS report for Team: {team_name_iter} ({len(team_convs_iter)} conversations)")
            team_report_path, team_report_content = generate_team_end_of_shift_report(
                team_name_iter, team_convs_iter, week_start_str_for_files, week_end_str_for_files
            )
            if team_report_path:
                all_generated_files.append(team_report_path)
                processed_counts["team_eos_reports_generated"] += 1
                if send_to_slack and team_report_content: # also consider send_to_slack for specific team if targeted
                    print(f"      Attempting to send EoS report for {team_name_iter} to Slack...")
                    send_slack_report(team_name_iter, team_report_content)
    
    # --- Uploading and Finalizing ---
    if upload_to_gdrive and all_generated_files:
        print("\n☁️ Uploading files to Google Drive...")
        for file_path in all_generated_files:
            if file_path and os.path.exists(file_path): # Make sure file exists
                try:
                    print(f"  Uploading {file_path}...")
                    file_url = app_upload_file_to_drive(file_path) # Ensure this uses the correct uploader
                    if file_url:
                        uploaded_file_urls.append(file_url)
                        print(f"    ✅ Successfully uploaded to: {file_url}")
                    else:
                        print(f"    ⚠️ Upload attempt for {file_path} did not return a URL.")
                except Exception as e:
                    print(f"    ❌ Error uploading {file_path}: {e}")
            else:
                print(f"  Skipping upload for non-existent or None file: {file_path}")
    
    final_message = f"Processing complete for {start_date_str} to {end_date_str}. {len(all_generated_files)} distinct files generated."
    if not all_generated_files and (target_team_name or target_product_area_name):
        final_message = f"Processing complete for {start_date_str} to {end_date_str}. No files generated for the specified targets."
    elif not all_generated_files:
         final_message = f"Processing complete for {start_date_str} to {end_date_str}. No files generated (no data or no reports run)."


    if upload_to_gdrive:
        final_message += f" {len(uploaded_file_urls)} files uploaded to Google Drive."

    print(f"\n✅ {final_message}")
    return {
        "status": "success" if len(all_generated_files) > 0 or not (target_team_name or target_product_area_name) else "no_files_for_target", 
        "message": final_message,
        "local_files": all_generated_files, 
        "gdrive_urls": uploaded_file_urls,
        "processed_counts": processed_counts
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and analyze Intercom conversations.")
    parser.add_argument("-c", "--conversation_id", type=str, help="Fetch a single conversation by ID (generates its area files).")
    parser.add_argument("-u", "--upload", action="store_true", help="Upload generated files to Google Drive.")
    parser.add_argument("--start_date", type=str, help="Start date (YYYY-MM-DD HH:MM).")
    parser.add_argument("--end_date", type=str, help="End date (YYYY-MM-DD HH:MM).")
    parser.add_argument("--send_slack", action="store_true", help="Send generated team reports to Slack.")
    
    # New arguments for targeted reporting
    parser.add_argument("--target-team", type=str, help="Specify a single team name to generate reports for.")
    parser.add_argument("--target-product-area", type=str, help="Specify a single product area to generate reports for.")
    # New argument for suggesting stop words
    parser.add_argument("--suggest-stop-words", action="store_true", help="Analyze conversation data from a previous run to suggest stop words.")
    parser.add_argument("--stop-words-input-dir", type=str, default=OUTPUT_DIR, help="Directory containing XLSX files to scan for stop word suggestion.")


    args = parser.parse_args()

    if not INTERCOM_PROD_KEY:
        print("🛑 INTERCOM_PROD_KEY not found in .env. Please set it.")
        sys.exit(1)

    if args.suggest_stop_words:
        print(f"Analyzing files in '{args.stop_words_input_dir}' to suggest stop words...")
        all_text_for_stopwords = []
        if not os.path.isdir(args.stop_words_input_dir):
            print(f"Error: Input directory for stop words '{args.stop_words_input_dir}' not found.")
            sys.exit(1)

        for filename in os.listdir(args.stop_words_input_dir):
            if filename.endswith(".xlsx"):
                file_path = os.path.join(args.stop_words_input_dir, filename)
                try:
                    print(f"  Reading {file_path}...")
                    df = pd.read_excel(file_path)
                    if 'transcript' in df.columns:
                        all_text_for_stopwords.extend(df['transcript'].dropna().astype(str).tolist())
                    if 'summary' in df.columns: # Also consider summaries
                        all_text_for_stopwords.extend(df['summary'].dropna().astype(str).tolist())
                except Exception as e:
                    print(f"  Could not read or process {file_path}: {e}")
        
        if not all_text_for_stopwords:
            print("No text data found in XLSX files in the specified directory.")
            sys.exit(0)

        print(f"Collected text from {len(all_text_for_stopwords)} entries. Processing for stop word suggestions...")
        word_counts = {}
        for text_entry in all_text_for_stopwords:
            # Basic cleaning: lowercase, split by non-alphanumeric but keep words
            words = re.findall(r'[a-z0-9\']+', text_entry.lower()) # Find alphanumeric words, allows internal apostrophes
            for word in words:
                if len(word) > 1 and word not in STOP_WORDS: # Exclude current stop words and single letters
                    word_counts[word] = word_counts.get(word, 0) + 1
        
        # Sort by frequency
        sorted_word_counts = sorted(word_counts.items(), key=lambda item: item[1], reverse=True)
        
        print("\nTop 100 most frequent words (excluding current stop words, min length 2):")
        print("Consider adding common bot/macro/template words from this list to your STOP_WORDS set in LLM5.py.")
        print("Format: word (count)")
        for i, (word, count) in enumerate(sorted_word_counts[:100]):
            print(f"{i+1}. {word} ({count})")
        
        sys.exit(0) # End execution after suggesting stop words


    if args.conversation_id:
        print(f"Fetching single conversation ID: {args.conversation_id}")
        conversation_data = get_intercom_conversation(args.conversation_id)
        all_generated_files_single = []
        uploaded_file_urls_single = []

        if conversation_data:
            attributes = conversation_data.get('custom_attributes', {})
            meta_mask_area_single = attributes.get('MetaMask area', 'Unknown_Area').strip()
            if not meta_mask_area_single: meta_mask_area_single = "Unknown_Area"
            
            print(f"  Conversation belongs to MetaMask Area: {meta_mask_area_single}")
            file_timestamp_str = args.conversation_id

            # Use _generate_scoped_product_area_files for consistency if desired,
            # or keep the specialized store/analyze calls for single conv.
            # For now, keeping specialized single logic.
            print(f"  Storing conversation {args.conversation_id} for area {meta_mask_area_single}...")
            xlsx_file_path_single = store_conversations_to_xlsx(
                [conversation_data], meta_mask_area_single, 
                file_timestamp_str, "single"
            )
            if xlsx_file_path_single:
                all_generated_files_single.append(xlsx_file_path_single)
                print(f"  Analyzing {xlsx_file_path_single}...")
                insights_file_path_single = analyze_xlsx_and_generate_insights(
                    xlsx_file_path_single, meta_mask_area_single, 
                    file_timestamp_str, "single"
                )
                if insights_file_path_single:
                    all_generated_files_single.append(insights_file_path_single)
            
            if args.upload and all_generated_files_single:
                print(f"  Uploading {len(all_generated_files_single)} file(s)...")
                for file_path in all_generated_files_single:
                    if file_path and os.path.exists(file_path):
                        try:
                            print(f"    Uploading {file_path}...")
                            file_url = app_upload_file_to_drive(file_path)
                            if file_url:
                                uploaded_file_urls_single.append(file_url)
                                print(f"      ✅ Successfully uploaded to: {file_url}")
                        except Exception as e:
                            print(f"      ❌ Error uploading {file_path}: {e}")
            
            print("\n--- Single Conversation Test Run Summary ---")
            print(f"Processed Conversation ID: {args.conversation_id}")
            print("Local files generated:")
            for f in all_generated_files_single:
                print(f"  - {f}")
            if uploaded_file_urls_single:
                print("Google Drive URLs:")
                for url in uploaded_file_urls_single:
                    print(f"  - {url}")
        else:
            print(f"❌ Could not fetch conversation ID: {args.conversation_id}")
    
    else: # Batch processing (date range) using new targeted logic or full run
        if args.start_date and args.end_date:
            run_start_date = args.start_date
            run_end_date = args.end_date
        else: # Default to last week if no dates given
            today = datetime.now()
            from datetime import timedelta 
            last_monday_actual = today - timedelta(days=today.weekday() + 7)
            last_sunday_actual = last_monday_actual + timedelta(days=6)
            run_start_date = last_monday_actual.strftime("%Y-%m-%d 00:00")
            run_end_date = last_sunday_actual.strftime("%Y-%m-%d 23:59")
        
        print(f"Running LLM5.py for date range: {run_start_date} to {run_end_date}")
        if args.target_team: print(f"Targeting Team: {args.target_team}")
        if args.target_product_area: print(f"Targeting Product Area: {args.target_product_area}")

        result = main_function(
            run_start_date, 
            run_end_date, 
            upload_to_gdrive=args.upload, 
            send_to_slack=args.send_slack,
            target_team_name=args.target_team,
            target_product_area_name=args.target_product_area
        ) 
        
        print("\n--- Batch Run Summary ---")
        print(f"Status: {result.get('status')}")
        print(f"Message: {result.get('message')}")
        print("Local files generated:")
        for f in result.get('local_files', []): print(f"  - {f}")
        if result.get('gdrive_urls'):
            print("Google Drive URLs:")
            for url in result.get('gdrive_urls', []): print(f"  - {url}")
        print("Processed Counts:")
        for k, v in result.get('processed_counts', {}).items(): print(f"  - {k}: {v}")
