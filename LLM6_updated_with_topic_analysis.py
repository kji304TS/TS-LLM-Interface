import os
import re
import json
import time
import pytz
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.styles import Alignment
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import NMF

# ======================================
# Environment and constants
# ======================================
load_dotenv()

API_KEY = os.getenv("API_KEY")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
INTERCOM_PROD_KEY = os.getenv("INTERCOM_PROD_KEY")

CATEGORY_HEADERS = {
    "Card": [
        "MM Card Issue",
        "MM Card Partner issue",
        "Dashboard Issue",
        "KYC Issue",
        "Dashboard Issue - Subcategory",
        "KYC Issue - Subcategory",
    ],
    "Dashboard": ["Dashboard issue", "Dashboard Issue"],
    "Ramps": ["Buy or Sell", "Buy issue", "Sell issue"],
    "SDK": [],
    "Security": [],
    "Snaps": ["Snaps Category"],
    "Staking": [
        "Staking Feature",
        "Validator Staking Issue",
        "Pooled Staking Issue",
        "Liquid Staking Issue",
        "Third Party Staking",
        "Bug ID",
        "Refund amount (USD)",
        "Refund Provided",
        "Withdrawals",
        "Managing Staked Tokens",
        "User Training",
        "Failed Transaction",
        "Liquid Staking Provider",
        "Staking Token Type",
        "Staking Platform",
    ],
    "Swaps": ["Swaps issue", "Bridge Issue"],
    "Wallet": ["Wallet issue"],
    "Wallet API": [],
}

OUTPUT_DIR = "output_files"
INSIGHTS_DIR = "Outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(INSIGHTS_DIR, exist_ok=True)

STOP_WORDS = set(
    [
        "the",
        "and",
        "of",
        "to",
        "a",
        "in",
        "for",
        "on",
        "with",
        "is",
        "this",
        "that",
        "it",
        "as",
        "was",
        "but",
        "are",
        "by",
        "or",
        "be",
        "at",
        "an",
        "not",
        "can",
        "if",
        "from",
        "about",
        "we",
        "you",
        "your",
        "so",
        "which",
        "there",
        "all",
        "will",
        "what",
        "has",
        "have",
        "do",
        "does",
        "had",
        "i",
    ]
)

PREDEFINED_PROMPTS = {
    "Top Issues": [
        "What is the most frequent subcategory in the 'Bridge Issue' column?",
        "What is the most frequent subcategory in the 'MM Card Issue' column?",
        "What is the most frequent subcategory in the 'MM Card Partner issue' column?",
        "What is the most frequent subcategory in the 'Dashboard Issue' column?",
        "What is the most frequent subcategory in the 'KYC Issue' column?",
        "What is the most frequent subcategory in the 'Dashboard Issue - Subcategory' column?",
        "What is the most frequent subcategory in the 'KYC Issue - Subcategory' column?",
        "What is the most frequent subcategory in the 'Buy issue' column?",
        "What is the most frequent subcategory in the 'Sell issue' column?",
        "What is the most frequent subcategory in the 'Snaps Category' column?",
        "What is the most frequent subcategory in the 'Staking Feature' column?",
        "What is the most frequent subcategory in the 'Validator Staking Issue' column?",
        "What is the most frequent subcategory in the 'Pooled Staking Issue' column?",
        "What is the most frequent subcategory in the 'Liquid Staking Issue' column?",
        "What is the most frequent subcategory in the 'Third Party Staking' column?",
        "What is the most frequent subcategory in the 'Swaps issue' column?",
        "What is the most frequent subcategory in the 'Wallet issue' column?",
    ],
    "Trends": [
        "How many conversations occurred in each subcategory?",
        "What percentage of total issues does each subcategory represent?",
        "How have issue frequencies changed over time?",
        "What correlations exist between different issue types?",
        "Are there seasonal trends in user-reported issues?",
    ],
    "Keyword Analysis": [
        "What are the top 10 most important keywords in the summaries?",
        "What sentiment trends can be observed from the summaries?",
    ],
    "Conversation Volume": [
        "How many conversations are in each MetaMask area?",
        "Which MetaMask area has seen the highest increase in conversations?",
    ],
}

# ======================================
# Helpers
# ======================================

def get_last_week_dates():
    est_tz = pytz.timezone("America/New_York")
    now = datetime.now(est_tz)
    last_monday = now - timedelta(days=now.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    start_date = last_monday.strftime("%Y-%m-%d 00:00")
    end_date = last_sunday.strftime("%Y-%m-%d 23:59")
    week_start_str = last_monday.strftime("%Y%m%d")
    week_end_str = last_sunday.strftime("%Y%m%d")
    return start_date, end_date, week_start_str, week_end_str


def remove_html_tags(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r"<.*?>", "", text)


def sanitize_text(text: str) -> str:
    if text is None:
        return ""
    return text.replace("\u200b", "").encode("utf-8", "ignore").decode("utf-8")


def get_conversation_summary(conversation: dict) -> str:
    if "conversation_parts" in conversation:
        parts = conversation["conversation_parts"].get("conversation_parts", [])
        for part in parts:
            if part.get("part_type") == "conversation_summary":
                return remove_html_tags(part.get("body", ""))
    return "No summary available"


def get_conversation_transcript(conversation: dict) -> str:
    transcript_lines = []
    if "conversation_parts" in conversation:
        parts = conversation["conversation_parts"].get("conversation_parts", [])
        for part in parts:
            if part.get("part_type") == "comment":
                author = part.get("author", {}).get("type", "Unknown")
                comment = remove_html_tags(part.get("body", ""))
                transcript_lines.append(f"{author}: {comment}")
    return "\n".join(transcript_lines) if transcript_lines else "No transcript available"


# ======================================
# Intercom API
# ======================================

def search_conversations(start_date_str: str, end_date_str: str):
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M").timestamp()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M").timestamp()
    url = "https://api.intercom.io/conversations/search"
    headers = {
        "Authorization": f"Bearer {INTERCOM_PROD_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "query": {
            "operator": "AND",
            "value": [
                {"field": "statistics.last_close_at", "operator": ">", "value": int(start_date)},
                {"field": "statistics.last_close_at", "operator": "<", "value": int(end_date)},
            ],
        },
        "pagination": {"per_page": 100},
    }

    all_conversations = []
    retries = 3
    while True:
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            print(f"Fetched so far: {len(all_conversations)} conversations")
            if response.status_code == 200:
                data = response.json()
                all_conversations.extend(data.get("conversations", []))
                next_page_data = data.get("pages", {}).get("next", None)
                if next_page_data and "starting_after" in next_page_data:
                    payload["pagination"]["starting_after"] = next_page_data["starting_after"]
                else:
                    break
            elif response.status_code == 500:
                if retries > 0:
                    print(f"Server error. Retrying in 5 seconds... ({retries} left)")
                    time.sleep(5)
                    retries -= 1
                else:
                    print("Max retries reached. Skipping Intercom API request.")
                    break
            else:
                print(f"Error: {response.status_code} - {response.text}")
                return None
        except requests.exceptions.ReadTimeout:
            if retries > 0:
                print("Read timeout. Retrying in 10 seconds...")
                time.sleep(10)
                retries -= 1
            else:
                print("Max retries reached. Skipping due to timeout.")
                break
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return None
    return all_conversations


def get_intercom_conversation(conversation_id: str):
    url = f"https://api.intercom.io/conversations/{conversation_id}"
    retries = 3
    while retries > 0:
        try:
            response = requests.get(url, headers={"Authorization": f"Bearer {INTERCOM_PROD_KEY}"}, timeout=30)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 500:
                print(f"Server error for {conversation_id}. Retrying... ({retries} left)")
                time.sleep(5)
                retries -= 1
            else:
                print(f"Error fetching conversation {conversation_id}: {response.status_code}")
                return None
        except requests.exceptions.ReadTimeout:
            print(f"Read timeout for conversation {conversation_id}. Retrying in 10 seconds...")
            time.sleep(10)
            retries -= 1
        except requests.exceptions.RequestException as e:
            print(f"Request failed for conversation {conversation_id}: {e}")
            return None
    print(f"Max retries reached for conversation {conversation_id}. Skipping.")
    return None


def filter_conversations_by_product(conversations, product: str):
    filtered_conversations = []
    for conversation in conversations:
        attributes = conversation.get("custom_attributes", {})
        meta_mask_area = attributes.get("MetaMask area", "").strip()
        print(f"MetaMask Area: {meta_mask_area} (Expected: {product})")
        if meta_mask_area.lower() == product.lower():
            full_conversation = get_intercom_conversation(conversation["id"]) or {}
            # carry forward custom attributes into the returned object for writing later
            full_conversation["custom_attributes"] = attributes
            if full_conversation:
                filtered_conversations.append(full_conversation)
    print(f"Total Conversations for {product}: {len(filtered_conversations)}")
    return filtered_conversations


# ======================================
# Storage
# ======================================

def store_conversations_to_xlsx(conversations, meta_mask_area: str, week_start_str: str, week_end_str: str):
    file_name = f"{meta_mask_area.lower()}_conversations_{week_start_str}_to_{week_end_str}.xlsx"
    file_path = os.path.join(OUTPUT_DIR, file_name)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversations"

    headers = ["conversation_id", "summary", "transcript", "MetaMask area"] + CATEGORY_HEADERS.get(meta_mask_area, [])
    sheet.append(headers)

    for conversation in conversations:
        conversation_id = conversation.get("id", "")
        summary = sanitize_text(get_conversation_summary(conversation))
        transcript = sanitize_text(get_conversation_transcript(conversation))
        attributes = conversation.get("custom_attributes", {})

        dynamic_values = []
        for field in CATEGORY_HEADERS.get(meta_mask_area, []):
            value = conversation.get(field, attributes.get(field, "N/A"))
            dynamic_values.append(value)

        row = [conversation_id, summary, transcript, meta_mask_area] + dynamic_values
        sheet.append(row)

    for col in ["B", "C"]:  # wrap Summary and Transcript
        for cell in sheet[col]:
            cell.alignment = Alignment(wrap_text=True)

    workbook.save(file_path)
    print(f"Saved: {file_name}")
    return file_path


# ======================================
# Insight generation (with topic analysis)
# ======================================

def _human_date_range(week_start_str: str, week_end_str: str) -> str:
    try:
        start_dt = datetime.strptime(week_start_str, "%Y%m%d")
        end_dt = datetime.strptime(week_end_str, "%Y%m%d")
        return f"{start_dt.strftime('%B %d, %Y')} – {end_dt.strftime('%B %d, %Y')}"
    except Exception:
        return f"{week_start_str} – {week_end_str}"


def _pick_primary_issue_column(df: pd.DataFrame, area: str) -> str | None:
    if area == "Ramps":
        # Prefer specific columns if present
        if "Buy issue" in df.columns or "Sell issue" in df.columns:
            return "__RampsIssue__"  # synthetic combined column
    for candidate in CATEGORY_HEADERS.get(area, []):
        if candidate in df.columns and not df[candidate].dropna().empty:
            return candidate
    # common fallbacks
    for fallback in ["Wallet issue", "Swaps issue", "Bridge Issue", "Dashboard Issue", "Dashboard issue", "Snaps Category"]:
        if fallback in df.columns and not df[fallback].dropna().empty:
            return fallback
    return None


def _build_issue_series(df: pd.DataFrame, area: str, primary_col: str) -> pd.Series:
    if area == "Ramps" and primary_col == "__RampsIssue__":
        series_list = []
        if "Buy issue" in df.columns:
            series_list.append(df["Buy issue"].dropna())
        if "Sell issue" in df.columns:
            series_list.append(df["Sell issue"].dropna())
        if series_list:
            return pd.concat(series_list).astype(str)
    return df[primary_col].dropna().astype(str)


def _extract_topics(texts: list[str], n_topics: int = 5, n_top_words: int = 6) -> list[str]:
    if len(texts) < 10:  # skip low volume to avoid unstable topics
        return []
    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_df=0.95,
            min_df=5,
        )
        X = vectorizer.fit_transform(texts)
        if X.shape[0] == 0 or X.shape[1] == 0:
            return []
        model = NMF(n_components=min(n_topics, max(1, X.shape[0] // 20)), random_state=42, init="nndsvd")
        W = model.fit_transform(X)
        H = model.components_
        feature_names = vectorizer.get_feature_names_out()
        topic_phrases: list[str] = []
        for topic in H:
            indices = topic.argsort()[: -(n_top_words + 1) : -1]
            words = [feature_names[i] for i in indices]
            # basic de-dup and cosmetic title-casing
            words = [w.strip().replace("_", " ") for w in words]
            phrase = ", ".join(dict.fromkeys(words))
            if phrase:
                topic_phrases.append(phrase)
        return topic_phrases
    except Exception:
        return []


def _top_keywords_from_summaries(df: pd.DataFrame, top_k: int = 10) -> list[str]:
    if "summary" not in df.columns or df["summary"].dropna().empty:
        return []
    words = (
        df["summary"].fillna("").str.lower().str.replace(r"[^a-z0-9\s]", " ", regex=True).str.split(expand=True).stack()
    )
    filtered = words[~words.isin(STOP_WORDS)]
    if filtered.empty:
        return []
    return filtered.value_counts().head(top_k).index.tolist()


def analyze_xlsx_and_generate_insights(xlsx_file: str, meta_mask_area: str, week_start_str: str, week_end_str: str) -> str | None:
    print(f"Analyzing {xlsx_file} for {meta_mask_area}...")
    df = pd.read_excel(xlsx_file)
    df.columns = df.columns.str.strip()

    # Combine text for topic modeling
    df["combined_text"] = df.get("summary", "").fillna("") + " " + df.get("transcript", "").fillna("")

    primary_col = _pick_primary_issue_column(df, meta_mask_area)
    insights_file = os.path.join(
        INSIGHTS_DIR, f"{meta_mask_area.lower()}_insights_{week_start_str}_to_{week_end_str}.txt"
    )

    if primary_col is None:
        text = [
            f"MetaMask {meta_mask_area} Support — Focused Issue Report",
            f"Date Range: {_human_date_range(week_start_str, week_end_str)}",
            f"Conversation Volume Analyzed: {len(df):,} total",
            "",
            "No issue columns with data were found for this area."
        ]
        with open(insights_file, "w", encoding="utf-8") as f:
            f.write("\n".join(text))
        print(f"Insights file created successfully: {insights_file}")
        return insights_file

    issue_series = _build_issue_series(df, meta_mask_area, primary_col)
    if issue_series.empty:
        issue_series = pd.Series(["Unspecified" for _ in range(len(df))])

    # Top 3 issues
    value_counts = issue_series.value_counts()
    top_issues = value_counts.head(3)
    total_conversations = int(value_counts.sum()) if not value_counts.empty else len(df)

    # Build insights text
    lines: list[str] = []
    lines.append(f"MetaMask {meta_mask_area} Support — Focused Issue Report")
    lines.append(f"Date Range: {_human_date_range(week_start_str, week_end_str)}")
    lines.append(f"Conversation Volume Analyzed: {total_conversations:,} total")
    lines.append("Focus: Top 3 " + meta_mask_area + " Issues by Volume")
    lines.append("")

    # Table header
    lines.append("Top 3 Issues")
    lines.append("Issue\tConversations\t% of Total")
    for issue, count in top_issues.items():
        pct = (count / total_conversations * 100.0) if total_conversations else 0.0
        lines.append(f"{issue}\t{count}\t{pct:.1f}%")

    # Topic insights per issue
    for issue, count in top_issues.items():
        lines.append("")
        lines.append(f"{issue} ({count} conversations)")
        issue_mask = (issue_series.astype(str) == str(issue))
        issue_texts = df.loc[issue_mask, "combined_text"].fillna("").tolist()
        topics = _extract_topics(issue_texts, n_topics=5, n_top_words=6)
        if not topics:
            lines.append("- Limited volume or signal for topic extraction.")
            continue
        for topic in topics[:5]:
            # Title-case the first token for readability
            pretty = topic[:1].upper() + topic[1:]
            lines.append(f"- {pretty}")

    # Key takeaways (coarse keywords)
    lines.append("")
    lines.append("Key Takeaways")
    keywords = _top_keywords_from_summaries(df)
    if keywords:
        lines.append("- Common themes observed: " + ", ".join(keywords))
    else:
        lines.append("- Not enough signal in summaries to extract common themes.")

    # Predefined prompts (selected)
    lines.append("")
    lines.append("Predefined Prompt Analysis")
    for category, prompts in PREDEFINED_PROMPTS.items():
        for prompt in prompts:
            if "top 10 most important keywords" in prompt.lower():
                lines.append(prompt)
                lines.append(", ".join(keywords) if keywords else "No keywords available.")

    with open(insights_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Insights file created successfully: {insights_file}")
    return insights_file


# ======================================
# Google Drive (service account)
# ======================================

def upload_to_google_drive_v3(service, file_path: str) -> bool:
    file_name = os.path.basename(file_path)
    folder_id = GDRIVE_FOLDER_ID
    file_metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaFileUpload(file_path, resumable=True)
    try:
        file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        print(f"Uploaded {file_name} successfully (File ID: {file.get('id')})")
        return True
    except Exception as e:
        print(f"Error uploading {file_name} to Google Drive: {e}")
        return False


def authenticate_google_drive_via_service_account():
    try:
        env_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if env_json:
            service_account_info = json.loads(env_json)
        else:
            with open("service_account_key.json") as f:
                service_account_info = json.load(f)
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=["https://www.googleapis.com/auth/drive"]
        )
        drive_service = build("drive", "v3", credentials=credentials)
        return drive_service
    except Exception as e:
        print(f"Google Drive service account authentication failed: {e}")
        return None


# ======================================
# Main orchestrator
# ======================================

def main_function(start_date: str, end_date: str, week_start_str: str, week_end_str: str):
    print(f"Searching for conversations from {start_date} to {end_date}...")
    conversations = search_conversations(start_date, end_date)
    if conversations is None:
        print("No conversations found or API error. Exiting.")
        return

    processed_files: set[str] = set()
    insights_files: set[str] = set()

    for area in CATEGORY_HEADERS.keys():
        filtered_conversations = filter_conversations_by_product(conversations, area)
        if not filtered_conversations:
            continue
        print(f"{area} Conversations Found: {len(filtered_conversations)}")
        xlsx_file = store_conversations_to_xlsx(filtered_conversations, area, week_start_str, week_end_str)
        processed_files.add(xlsx_file)
        insights_file = analyze_xlsx_and_generate_insights(xlsx_file, area, week_start_str, week_end_str)
        if insights_file:
            insights_files.add(insights_file)

    drive_service = authenticate_google_drive_via_service_account()
    if drive_service is None:
        print("Google Drive authentication failed. Skipping uploads.")
        return

    print("Files Queued for Upload:")
    print("XLSX Files:", list(processed_files))
    print("Insights Files:", list(insights_files))

    for file in processed_files:
        upload_to_google_drive_v3(drive_service, file)
    for file in insights_files:
        upload_to_google_drive_v3(drive_service, file)

    print("All conversations and insights files uploaded successfully.")


if __name__ == "__main__":
    start_date, end_date, week_start_str, week_end_str = get_last_week_dates()
    print(f"Running script for: {start_date} to {end_date}...")
    main_function(start_date, end_date, week_start_str, week_end_str)