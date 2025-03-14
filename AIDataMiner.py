import requests
from datetime import datetime
import csv
import re
import os
import time
import pandas as pd

INTERCOM_PROD_KEY = ''

CATEGORY_HEADERS = {
    "Bridges": ["Bridge Issue"],
    "Card": ["MM Card Issue", "MM Card Partner issue"],
    "Dashboard": ["Dashboard issue"],
    "Ramps": ["Buy or Sell", "Buy issue", "Sell issue"],
    "Snaps": ["Snaps Category"],
    "Staking": ["Staking issue"],
    "Swaps": ["Swaps issue"],
    "Wallet": ["Wallet issue"]
}

OUTPUT_DIR = "output_files"
INSIGHTS_DIR = "Outputs"

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(INSIGHTS_DIR, exist_ok=True)

def remove_html_tags(text):
    if not isinstance(text, str):
        return ''
    clean = re.sub(r'<.*?>', '', text)
    return clean

def sanitize_text(text):
    if text:
        return text.replace('\u200b', '').encode('utf-8', 'ignore').decode('utf-8')
    return text

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

def search_conversations(start_date_str, end_date_str):
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
                {
                    "field": "statistics.last_close_at",
                    "operator": ">",
                    "value": int(start_date)
                },
                {
                    "field": "statistics.last_close_at",
                    "operator": "<",
                    "value": int(end_date)
                }
            ]
        },
        "pagination": {
            "per_page": 100
        }
    }

    all_conversations = []
    next_page = None

    while True:
        response = requests.post(url, headers=headers, json=payload)
        print(f"Fetched so far: {len(all_conversations)} conversations")

        if response.status_code == 200:
            data = response.json()
            all_conversations.extend(data.get('conversations', []))

            pagination = data.get('pages', {})
            next_page_data = pagination.get('next', None)

            if next_page_data and 'starting_after' in next_page_data:
                next_page = next_page_data['starting_after']
                payload['pagination']['starting_after'] = next_page
            else:
                break
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None

    return all_conversations

def get_intercom_conversation(conversation_id):
    url = f'https://api.intercom.io/conversations/{conversation_id}'
    response = requests.get(url, headers={"Authorization": f"Bearer {INTERCOM_PROD_KEY}"})
    if response.status_code != 200:
        print(f"Status: {response.status_code}, Problem while looking for ticket details")
        return None
    return response.json()

def filter_conversations_by_product(conversations, product):
    filtered_conversations = []
    for conversation in conversations:
        attributes = conversation.get('custom_attributes', {})
        meta_mask_area = attributes.get('MetaMask area', '').strip()
        print(f"MetaMask Area: {meta_mask_area} (Expected: {product})")  

        if meta_mask_area.lower() == product.lower():
            full_conversation = get_intercom_conversation(conversation['id'])
            if full_conversation:
                filtered_conversations.append(full_conversation)

    print(f"Total Conversations for {product}: {len(filtered_conversations)}")
    return filtered_conversations

def store_conversations_to_csv(conversations, file_path, meta_mask_area):
    headers = ['conversation_id', 'summary', 'transcript'] + CATEGORY_HEADERS.get(meta_mask_area, [])
    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()

        for conversation in conversations:
            conversation_id = conversation['id']
            summary = sanitize_text(get_conversation_summary(conversation))
            transcript = sanitize_text(get_conversation_transcript(conversation))
            attributes = conversation.get('custom_attributes', {})

            row = {
                'conversation_id': conversation_id,
                'summary': summary,
                'transcript': transcript,
                **{field: attributes.get(field, 'N/A') for field in CATEGORY_HEADERS.get(meta_mask_area, [])}
            }
            writer.writerow(row)

def analyze_csv_and_generate_insights(csv_file, meta_mask_area):
    print(f"Uploading and analyzing {csv_file}...")

    df = pd.read_csv(csv_file, encoding='utf-8-sig')

    # Normalize column names to ensure consistency
    df.columns = df.columns.str.strip()

    # Debugging: Print available columns
    print(f"Columns in {meta_mask_area} CSV: {df.columns.tolist()}")

    # Identify the first issue category column dynamically
    issue_columns = [col for col in df.columns if col not in ['conversation_id', 'summary', 'transcript']]
    
    if not issue_columns:
        print(f"No issue category columns found for {meta_mask_area}. Skipping analysis.")
        return

    issue_col = issue_columns[0]  # Use the first detected issue category column
    print(f"Processing issue column: {issue_col}")

    # Ensure the column is not empty
    if df[issue_col].dropna().empty:
        print(f"No valid data in column: {issue_col}. Skipping analysis.")
        return

    # Analyze most frequent issue category
    most_frequent = df[issue_col].value_counts().idxmax()
    count = df[issue_col].value_counts().max()

    # Save insights to file
    insights_file = os.path.join(INSIGHTS_DIR, f"{meta_mask_area.lower()}_insights.txt")
    with open(insights_file, 'w') as f:
        f.write(f"Most Frequent {meta_mask_area} Issue: {most_frequent} (Count: {count})\n")
        f.write("\nFull Breakdown:\n")
        f.write(df[issue_col].value_counts().to_string())

    print(f"Insights saved to {insights_file}")


def main_function(start_date, end_date):
    conversations = search_conversations(start_date, end_date)
    if conversations:
        for area in CATEGORY_HEADERS.keys():
            filtered_conversations = filter_conversations_by_product(conversations, area)
            if filtered_conversations:
                print(f"{area} Conversations: {len(filtered_conversations)}")
                csv_file = os.path.join(OUTPUT_DIR, f"{area.lower()}_conversations.csv")
                store_conversations_to_csv(filtered_conversations, csv_file, area)

                # Upload and analyze automatically
                analyze_csv_and_generate_insights(csv_file, area)
    else:
        print("No conversations found for provided timeframe")

if __name__ == "__main__":
    main_function("2024-12-20 00:00", "2024-12-20 13:00")
