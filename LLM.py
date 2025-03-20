import requests
from datetime import datetime
import re
import os
from dotenv import load_dotenv  # ✅ Import dotenv
import time
import pandas as pd
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import pytz
from datetime import datetime, timedelta

# ✅ Load .env variables
load_dotenv()  # <-- This must be called BEFORE using os.getenv()

# ✅ Get values from .env
API_KEY = os.getenv("API_KEY")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
INTERCOM_PROD_KEY = os.getenv("INTERCOM_PROD_KEY")

CATEGORY_HEADERS = {
    "Bridges": ["Bridge Issue"],
    "Dashboard": ["Dashboard issue"],
    "Ramps": ["Buy or Sell", "Buy issue", "Sell issue"],
    "SDK": [],
    "Security": [],
    "Snaps": ["Snaps Category"],
    "Swaps": ["Swaps issue"],
    "Wallet": ["Wallet issue"],
    "Wallet API": []
}

OUTPUT_DIR = "output_files"
INSIGHTS_DIR = "Outputs"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(INSIGHTS_DIR, exist_ok=True)

# ✅ Define stop words to exclude common words from keyword analysis
STOP_WORDS = set([
    "the", "and", "of", "to", "a", "in", "for", "on", "with", "is", "this",
    "that", "it", "as", "was", "but", "are", "by", "or", "be", "at", "an",
    "not", "can", "if", "from", "about", "we", "you", "your", "so", "which",
    "there", "all", "will", "what", "has", "have", "do", "does", "had", "i"
])

# ✅ Predefined Prompts
PREDEFINED_PROMPTS = {
    "Top Issues": [
        "What is the most frequent subcategory in the 'Bridge Issue' column?",
        "What is the most frequent subcategory in the 'MM Card Issue' column?",
        "What is the most frequent subcategory in the 'MM Card Partner issue' column?",
        "What is the most frequent subcategory in the 'Swaps issue' column?",
        "What is the most frequent subcategory in the 'Wallet issue' column?"
    ],
    "Trends": [
        "How many conversations occurred in each subcategory?",
        "What percentage of total issues does each subcategory represent?",
        "How have issue frequencies changed over time?",
        "What correlations exist between different issue types?",
        "Are there seasonal trends in user-reported issues?"
    ],
    "Keyword Analysis": [
        "What are the top 10 most important keywords in the summaries?",
        "What sentiment trends can be observed from the summaries?"
    ],
    "Conversation Volume": [
        "How many conversations are in each MetaMask area?",
        "Which MetaMask area has seen the highest increase in conversations?"
    ]
}

def get_last_week_dates():
    """Returns the start (last Monday 00:00) and end (last Sunday 23:59) dates."""
    EST = pytz.timezone("America/New_York")
    now = datetime.now(EST)

    # Find last Monday
    last_monday = now - timedelta(days=now.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)

    # Format dates
    start_date = last_monday.strftime("%Y-%m-%d 00:00")
    end_date = last_sunday.strftime("%Y-%m-%d 23:59")
    
    # Generate filenames based on the processed week's date range
    week_start_str = last_monday.strftime("%Y%m%d")  # Example: 20250303
    week_end_str = last_sunday.strftime("%Y%m%d")  # Example: 20250309

    return start_date, end_date, week_start_str, week_end_str


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
def search_conversations(start_date_str, end_date_str):
    """Fetches all conversations from Intercom with retry logic for timeouts."""
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M").timestamp()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M").timestamp()

    url = "https://api.intercom.io/conversations/search"
    headers = {
        "Authorization": f"Bearer {INTERCOM_PROD_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    payload = {
        "query": {
            "operator": "AND",
            "value": [
                {"field": "statistics.last_close_at", "operator": ">", "value": int(start_date)},
                {"field": "statistics.last_close_at", "operator": "<", "value": int(end_date)}
            ]
        },
        "pagination": {"per_page": 100}
    }

    all_conversations = []
    retries = 3  # Number of retries allowed for timeouts

    while True:
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)  # ⏳ Set 30-second timeout
            print(f"Fetched so far: {len(all_conversations)} conversations")

            if response.status_code == 200:
                data = response.json()
                all_conversations.extend(data.get('conversations', []))

                pagination = data.get('pages', {})
                next_page_data = pagination.get('next', None)

                if next_page_data and 'starting_after' in next_page_data:
                    payload['pagination']['starting_after'] = next_page_data['starting_after']
                else:
                    break

            elif response.status_code == 500:
                if retries > 0:
                    print(f"⚠️ Server error encountered. Retrying in 5 seconds... ({retries} retries left)")
                    time.sleep(5)
                    retries -= 1
                else:
                    print("❌ Max retries reached. Skipping Intercom API request.")
                    break

            else:
                print(f"❌ Error: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.ReadTimeout:
            if retries > 0:
                print("⚠️ Read timeout. Retrying in 10 seconds...")
                time.sleep(10)
                retries -= 1
            else:
                print("❌ Max retries reached. Skipping due to timeout.")
                break

        except requests.exceptions.RequestException as e:
            print(f"❌ Request failed: {e}")
            return None

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
    print(f"Total Conversations for {product}: {len(filtered_conversations)}")
    return filtered_conversations

# ✅ Store extracted data into a CSV file
    if 'summary' in df.columns and not df['summary'].dropna().empty:
        word_series = df['summary'].str.lower().str.split(expand=True).stack()
        filtered_words = word_series[~word_series.isin(STOP_WORDS)]
        if not filtered_words.empty:
            top_words = filtered_words.value_counts().head(10)

    # ✅ Answer Predefined Prompts
    analysis_text.append("\n🔹 **Predefined Prompt Analysis:**")
    for category, prompts in PREDEFINED_PROMPTS.items():
        if category in ["Keyword Analysis", "Trends", "Conversation Volume"] or meta_mask_area in PREDEFINED_PROMPTS:
            for prompt in prompts:
                if "top 10 most important keywords" in prompt:
                    analysis_text.append(f"\n**{prompt}**")
                    analysis_text.append("\n".join(top_words.index.tolist()) if not top_words.empty else "No keywords available.")


def upload_to_google_drive(drive, file_path):
    """Uploads a file to a specific Google Drive folder with retry handling."""
    file_name = os.path.basename(file_path)
    retries = 3  # Number of retries allowed

    for attempt in range(retries):
        try:
            print(f"📤 Uploading {file_name} to Google Drive (Attempt {attempt+1})...")
            file = drive.CreateFile({'title': file_name, 'parents': [{'id': GDRIVE_FOLDER_ID}]})
            file.SetContentFile(file_path)
            file.Upload()
            print(f"✅ Successfully uploaded {file_name} to Google Drive.")
            return True  # Return success
        except Exception as e:
            print(f"❌ Error uploading {file_name}: {e}")
            if attempt < retries - 1:
                print("Retrying in 10 seconds...")
                time.sleep(10)
            else:
                print("❌ Max retries reached. Skipping upload.")
                return False  # Return failure if all retries fail


def authenticate_google_drive():
    """Authenticates Google Drive using stored credentials for automatic login."""
    gauth = GoogleAuth()

    try:
        # ✅ Try to load existing credentials
        gauth.LoadCredentialsFile("credentials.json")

        if gauth.credentials is None:
            # If no saved credentials exist, authenticate manually
            print("🔑 No saved credentials found. Performing manual authentication...")
            gauth.LocalWebserverAuth()
        elif gauth.access_token_expired:
            # If the token expired, refresh it automatically
            print("🔄 Access token expired. Refreshing...")
            gauth.Refresh()
        else:
            # ✅ If credentials exist and are valid, authorize without prompting the user
            print("✅ Using existing credentials.")
            gauth.Authorize()

        # ✅ Save credentials for future use (prevents login prompts)
        gauth.SaveCredentialsFile("credentials.json")

        print("🔗 Google Drive authentication successful!")
        return GoogleDrive(gauth)

    except Exception as e:
        print(f"❌ Google Drive authentication failed: {e}")
        return None  # Return None if authentication fails


    print(f"🔍 Searching for conversations from {start_date} to {end_date}...")

    conversations = search_conversations(start_date, end_date)
    if not conversations:
        print("⚠️ No conversations found. The script will still continue processing.")
        return  

    insights_files = set()   # Store unique insights files

    for area in CATEGORY_HEADERS.keys():
        filtered_conversations = filter_conversations_by_product(conversations, area)
        if filtered_conversations:
            print(f"✅ {area} Conversations Found: {len(filtered_conversations)}"
            if insights_file:
                insights_files.add(insights_file)  # ✅ Use a set to ensure uniqueness
            else:
                print(f"⚠️ Insights file missing for {area}. Skipping upload.")

    # ✅ Authenticate Google Drive **before** uploads
    drive = authenticate_google_drive()
    
    if drive is None:
        print("❌ Google Drive authentication failed. Skipping uploads.")
        return

    # ✅ Debugging Step: Print Files Queued for Upload
    print("📤 Files Queued for Upload:")

    for file in processed_files:
        upload_to_google_drive(drive, file)

    # ✅ Upload insights files **only once**
    for file in insights_files:
        upload_to_google_drive(drive, file)

    print("✅ All conversations and insights files uploaded successfully.")


if __name__ == "__main__":
    # ✅ Automatically determine correct date range for last week
    start_date, end_date, week_start_str, week_end_str = get_last_week_dates()

    print(f"🚀 Running script for: {start_date} to {end_date}...")

    main_function(start_date, end_date, week_start_str, week_end_str)
