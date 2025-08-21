import os
import re
import json
import time
import pytz
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from collections import Counter
from typing import Optional, List, Set
from openpyxl import Workbook
from openpyxl.styles import Alignment
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# Load environment variables early
load_dotenv()

API_KEY = os.getenv("API_KEY")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
INTERCOM_PROD_KEY = os.getenv("INTERCOM_PROD_KEY")


# MetaMask Areas and their related subcategory columns captured in the XLSX output
CATEGORY_HEADERS = {
    "Card": [
        "MM Card Issue",
        "MM Card Partner issue",
        "Dashboard Issue",
        "KYC Issue",
        "Dashboard Issue - Subcategory",
        "KYC Issue - Subcategory",
    ],
    "Dashboard": ["Dashboard issue"],
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
    "Swaps": ["Swaps issue"],
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
        "im",
        "ive",
        "amp",
    ]
)


def get_last_week_dates():
    """Return start and end strings for last week (Mon 00:00 to Sun 23:59) and YYYYMMDD tokens."""
    est_zone = pytz.timezone("America/New_York")
    now = datetime.now(est_zone)

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
    if text:
        return text.replace("\u200b", "").encode("utf-8", "ignore").decode("utf-8")
    return ""


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


def search_conversations(start_date_str: str, end_date_str: str):
    """Fetch all conversations from Intercom within the time window, with basic retry on errors."""
    start_timestamp = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M").timestamp()
    end_timestamp = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M").timestamp()

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
                {"field": "statistics.last_close_at", "operator": ">", "value": int(start_timestamp)},
                {"field": "statistics.last_close_at", "operator": "<", "value": int(end_timestamp)},
            ],
        },
        "pagination": {"per_page": 100},
    }

    all_conversations = []
    retries = 3

    while True:
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                all_conversations.extend(data.get("conversations", []))

                pages = data.get("pages", {})
                next_info = pages.get("next")
                if next_info and "starting_after" in next_info:
                    payload["pagination"]["starting_after"] = next_info["starting_after"]
                else:
                    break
            elif response.status_code == 500:
                if retries > 0:
                    time.sleep(5)
                    retries -= 1
                    continue
                break
            else:
                print(f"Error: {response.status_code} - {response.text}")
                return None
        except requests.exceptions.ReadTimeout:
            if retries > 0:
                time.sleep(10)
                retries -= 1
                continue
            break
        except requests.exceptions.RequestException as ex:
            print(f"Request failed: {ex}")
            return None

    return all_conversations


def get_intercom_conversation(conversation_id: str):
    url = f"https://api.intercom.io/conversations/{conversation_id}"
    retries = 3
    headers = {"Authorization": f"Bearer {INTERCOM_PROD_KEY}"}

    while retries > 0:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 500:
                retries -= 1
                time.sleep(5)
                continue
            print(f"Error fetching conversation {conversation_id}: {response.status_code}")
            return None
        except requests.exceptions.ReadTimeout:
            retries -= 1
            time.sleep(10)
        except requests.exceptions.RequestException as ex:
            print(f"Request failed for conversation {conversation_id}: {ex}")
            return None
    return None


def filter_conversations_by_product(conversations, product: str):
    filtered = []
    for conv in conversations:
        attributes = conv.get("custom_attributes", {})
        meta_mask_area = (attributes.get("MetaMask area", "") or "").strip()
        if meta_mask_area.lower() == product.lower():
            full = get_intercom_conversation(conv["id"])  # enrich with parts
            if full:
                # Carry through the custom attributes we care about for this area
                full_attrs = full.get("custom_attributes", {}) or {}
                for col in CATEGORY_HEADERS.get(product, []):
                    full_attrs[col] = attributes.get(col, "None")
                full["custom_attributes"] = full_attrs
                filtered.append(full)
    return filtered


def store_conversations_to_xlsx(conversations, meta_mask_area: str, week_start_str: str, week_end_str: str) -> str:
    file_name = f"{meta_mask_area.lower()}_conversations_{week_start_str}_to_{week_end_str}.xlsx"
    file_path = os.path.join(OUTPUT_DIR, file_name)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversations"

    headers = ["conversation_id", "summary", "transcript"] + CATEGORY_HEADERS.get(meta_mask_area, [])
    sheet.append(headers)

    for conv in conversations:
        conv_id = conv.get("id")
        summary = sanitize_text(get_conversation_summary(conv))
        transcript = sanitize_text(get_conversation_transcript(conv))
        attributes = conv.get("custom_attributes", {})

        row_values = [conv_id, summary, transcript]
        for field in CATEGORY_HEADERS.get(meta_mask_area, []):
            row_values.append(attributes.get(field, "N/A"))
        sheet.append(row_values)

    # Wrap long text columns
    for col in ["B", "C"]:
        for cell in sheet[col]:
            cell.alignment = Alignment(wrap_text=True)

    workbook.save(file_path)
    print(f"Saved: {file_path}")
    return file_path


# --------------------------
# Insight generation helpers
# --------------------------

def _pick_primary_issue_column(df: pd.DataFrame, area: str) -> Optional[str]:
    """Pick the most useful issue column for an area based on non-null volume."""
    candidates = [c for c in CATEGORY_HEADERS.get(area, []) if c in df.columns]
    if not candidates:
        return None
    best_col = None
    best_non_null = -1
    for c in candidates:
        non_null = df[c].replace({"N/A": None, "None": None, "": None}).dropna().shape[0]
        if non_null > best_non_null:
            best_non_null = non_null
            best_col = c
    return best_col


def _format_human_date_range(week_start_str: str, week_end_str: str) -> str:
    try:
        s = datetime.strptime(week_start_str, "%Y%m%d")
        e = datetime.strptime(week_end_str, "%Y%m%d")
        return f"{s.strftime('%B %-d')} – {e.strftime('%B %-d, %Y')}"
    except Exception:
        # Fallback without platform-specific day formatting
        s = datetime.strptime(week_start_str, "%Y%m%d")
        e = datetime.strptime(week_end_str, "%Y%m%d")
        return f"{s.strftime('%B %d')} – {e.strftime('%B %d, %Y')}"


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9']+", text)
    return [t for t in tokens if t not in STOP_WORDS]


def _top_phrases(texts: List[str], max_phrases: int = 5) -> List[str]:
    """Return up to max_phrases of the most frequent bigrams/trigrams from texts."""
    bigram_counts: Counter = Counter()
    trigram_counts: Counter = Counter()

    for txt in texts:
        tokens = _tokenize(txt or "")
        if not tokens:
            continue
        # bigrams
        for i in range(len(tokens) - 1):
            bigram = (tokens[i], tokens[i + 1])
            if all(t not in STOP_WORDS for t in bigram):
                bigram_counts[bigram] += 1
        # trigrams
        for i in range(len(tokens) - 2):
            trigram = (tokens[i], tokens[i + 1], tokens[i + 2])
            if all(t not in STOP_WORDS for t in trigram):
                trigram_counts[trigram] += 1

    # Combine and pick top
    combined = []
    combined.extend(list(bigram_counts.items()))
    combined.extend(list(trigram_counts.items()))
    combined.sort(key=lambda kv: kv[1], reverse=True)

    phrases = []
    for ngram, _cnt in combined[: max_phrases * 2]:
        phrase = ", ".join(ngram) if len(ngram) > 2 else " ".join(ngram)
        if phrase not in phrases:
            phrases.append(phrase)
        if len(phrases) >= max_phrases:
            break
    return phrases


def analyze_xlsx_and_generate_insights(
    xlsx_file: str, meta_mask_area: str, week_start_str: str, week_end_str: str
) -> str:
    print(f"Analyzing {xlsx_file} for {meta_mask_area}…")
    df = pd.read_excel(xlsx_file)
    df.columns = df.columns.str.strip()

    # Determine which column to treat as the primary issue taxonomy
    issue_col = _pick_primary_issue_column(df, meta_mask_area)

    insights_file = os.path.join(
        INSIGHTS_DIR,
        f"{meta_mask_area.lower()}_insights_{week_start_str}_to_{week_end_str}.txt",
    )

    if issue_col is None:
        with open(insights_file, "w", encoding="utf-8") as f:
            f.write(
                f"MetaMask {meta_mask_area} Support — Focused Issue Report\n"
                f"Date Range: {_format_human_date_range(week_start_str, week_end_str)}\n"
                f"Conversation Volume Analyzed: {len(df)} total\n\n"
                f"No issue taxonomy found for this area."
            )
        return insights_file

    # Ensure combined_text column exists
    if "combined_text" not in df.columns:
        if "summary" in df.columns:
            summary_series = df["summary"].astype(str)
        else:
            summary_series = pd.Series([""] * len(df))
        if "transcript" in df.columns:
            transcript_series = df["transcript"].astype(str)
        else:
            transcript_series = pd.Series([""] * len(df))
        df["combined_text"] = summary_series.fillna("") + " " + transcript_series.fillna("")

    # Normalize and filter the issue column
    issues_series = (
        df[issue_col]
        .astype(str)
        .str.strip()
        .replace({"nan": None, "None": None, "N/A": None, "": None})
        .dropna()
    )

    total_area_rows = len(df)
    top_counts = issues_series.value_counts().head(3)

    # Precompute combined text for later topical analysis
    df["combined_text"] = df["summary"].fillna("") + " " + df["transcript"].fillna("")

    # Build report
    human_range = _format_human_date_range(week_start_str, week_end_str)
    lines = []
    lines.append(f"MetaMask {meta_mask_area} Support — Focused Issue Report")
    lines.append(f"Date Range: {human_range}")
    lines.append(f"Conversation Volume Analyzed: {len(df)} total")
    lines.append(f"Focus: Top 3 {meta_mask_area} Issues by Volume")
    lines.append("")

    lines.append("\U0001F4CA Top 3 " + f"{meta_mask_area} Issues")
    lines.append("Issue\tConversations\t% of Total")
    for issue, cnt in top_counts.items():
        pct = (cnt / total_area_rows * 100.0) if total_area_rows else 0.0
        lines.append(f"{issue}\t{cnt}\t{pct:.1f}%")

    # Deep dives per issue with dynamic topical phrases
    for issue, cnt in top_counts.items():
        lines.append("")
        lines.append(f"\U0001F501 {issue} ({cnt} conversations)")

        # Build a boolean mask aligned to df.index
        issue_mask = df[issue_col].astype(str).str.strip().eq(str(issue))
        issue_mask = issue_mask.reindex(df.index, fill_value=False)
        issue_texts_series = df.loc[issue_mask, "combined_text"]
        issue_texts = issue_texts_series.astype(str).fillna("").tolist()

        # Extract top phrases as proxy for "why" themes
        phrases = _top_phrases(issue_texts, max_phrases=5)
        if phrases:
            for p in phrases:
                lines.append(f"- {p}")
        else:
            lines.append("- No dominant topical phrases detected.")

    # Optional: global keyword trend from summaries
    if "summary" in df.columns and not df["summary"].dropna().empty:
        words = (
            df["summary"].astype(str).str.lower().str.split(expand=True).stack().dropna()
        )
        words = words[~words.isin(STOP_WORDS)]
        if not words.empty:
            top_words = words.value_counts().head(10)
            lines.append("")
            lines.append("Top keywords across summaries:")
            lines.append(", ".join(list(top_words.index)))

    with open(insights_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Insights written: {insights_file}")
    return insights_file


def upload_to_google_drive_v3(service, file_path: str) -> bool:
    file_name = os.path.basename(file_path)
    folder_id = GDRIVE_FOLDER_ID

    file_metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaFileUpload(file_path, resumable=True)

    try:
        created = (
            service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        )
        print(f"Uploaded {file_name} (File ID: {created.get('id')})")
        return True
    except Exception as ex:
        print(f"Upload failed for {file_name}: {ex}")
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
    except Exception as ex:
        print(f"Google Drive auth failed: {ex}")
        return None


def main_function(start_date: str, end_date: str, week_start_str: str, week_end_str: str):
    print(f"Searching for conversations from {start_date} to {end_date}…")
    conversations = search_conversations(start_date, end_date)
    if not conversations:
        print("No conversations found in the selected time window.")
        return

    generated_xlsx: Set[str] = set()
    generated_insights: Set[str] = set()

    for area in CATEGORY_HEADERS.keys():
        filtered = filter_conversations_by_product(conversations, area)
        if not filtered:
            continue

        xlsx_path = store_conversations_to_xlsx(filtered, area, week_start_str, week_end_str)
        generated_xlsx.add(xlsx_path)

        insights_path = analyze_xlsx_and_generate_insights(
            xlsx_path, area, week_start_str, week_end_str
        )
        if insights_path:
            generated_insights.add(insights_path)

    drive_service = authenticate_google_drive_via_service_account()
    if drive_service is None:
        print("Skipping uploads due to Drive auth failure.")
        return

    print("Uploading generated files…")
    for fpath in sorted(generated_xlsx):
        upload_to_google_drive_v3(drive_service, fpath)
    for fpath in sorted(generated_insights):
        upload_to_google_drive_v3(drive_service, fpath)
    print("All files uploaded.")


if __name__ == "__main__":
    s, e, ws, we = get_last_week_dates()
    print(f"Running script for: {s} to {e}…")
    main_function(s, e, ws, we)

