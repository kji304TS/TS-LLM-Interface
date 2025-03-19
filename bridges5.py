import requests
from datetime import datetime
import csv
import re
import os
import sys
from dotenv import load_dotenv
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from openpyxl import Workbook
from openpyxl.styles import Alignment


# Load environment variables
load_dotenv()
API_KEY = os.getenv("API_KEY")
INTERCOM_PROD_KEY = os.getenv('INTERCOM_PROD_KEY')
GDRIVE_FOLDER_ID = os.getenv('GDRIVE_FOLDER_ID')

def remove_html_tags(text):
    if not isinstance(text, str):
        return ''
    clean = re.sub(r'<.*?>', '', text)
    return clean

def sanitize_text(text):
    if text:
        return text.replace('\u200b', '').encode('utf-8', 'ignore').decode('utf-8')
    return text

def get_intercom_conversation(conversation_id):
    url = f'https://api.intercom.io/conversations/{conversation_id}'
    response = requests.get(url, headers={"Authorization": f"Bearer {INTERCOM_PROD_KEY}"})
    if response.status_code != 200:
        print(f"Status: {response.status_code}, Problem while looking for ticket status")
        try:
            print(f"Error: {response.json()}")
        except requests.exceptions.JSONDecodeError:
            print("Error: Unable to parse JSON response.")
        return None
    return response.json()

def get_conversation_summary(conversation):
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        for part in conversation_parts:
            if part.get('part_type') == 'conversation_summary':
                return remove_html_tags(part.get('body', ''))
    return conversation.get('custom_attributes', {}).get('Cristi GPT response', "No summary available")

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
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").timestamp()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").timestamp()
    
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
        "pagination": {"per_page": 150}
    }

    all_conversations = []
    next_page = None

    while True:
        if next_page:
            payload["pagination"]["starting_after"] = next_page  # Add pagination cursor

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text}")
            return all_conversations  # Return whatever was retrieved so far

        data = response.json()
        conversations = data.get('conversations', [])
        all_conversations.extend(conversations)  # Append new conversations

        print(f"Fetched {len(conversations)} conversations, total: {len(all_conversations)}")  # Debugging output

        # Handle pagination
        next_page_data = data.get('pages', {}).get('next', None)
        if next_page_data and "starting_after" in next_page_data:
            next_page = next_page_data["starting_after"]
        else:
            break  # No more pages to fetch

    print(f"Total conversations retrieved: {len(all_conversations)}")  # Final count
    return all_conversations


def filter_conversations_by_product(conversations, product):
    filtered_conversations = []
    for conversation in conversations:
        conversation = get_intercom_conversation(conversation['id'])  # Fetch full conversation details
        if not conversation:
            continue

        attributes = conversation.get('custom_attributes', {})
        print(f"Custom Attributes for Conversation ID {conversation.get('id')}: {attributes}")  # Debugging

        # Check if MetaMask area matches the product
        if attributes.get('MetaMask area', '').strip().lower() == product.lower():
            filtered_conversations.append(conversation)

    print(f"Total Conversations Matching '{product}': {len(filtered_conversations)}")
    return filtered_conversations

def store_conversations_to_xlsx(conversations, file_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversations"

    headers = ['conversation_id', 'summary', 'transcript', 'Bridge Issue']
    sheet.append(headers)

    for conversation in conversations:
        conversation_id = conversation['id']
        summary = sanitize_text(get_conversation_summary(conversation))

        # ✅ Ensure line breaks are properly formatted for Excel/Google Sheets
        transcript = sanitize_text(get_conversation_transcript(conversation))

        bridge_issue = conversation.get('custom_attributes', {}).get('Bridge Issue', 'N/A')

        # ✅ Append data correctly into separate columns
        sheet.append([conversation_id, summary, transcript, bridge_issue])

    # ✅ Apply text wrapping to the Transcript & Summary columns
    for col in ["B", "C"]:  # Column B = Summary, Column C = Transcript
        for cell in sheet[col]:
            cell.alignment = Alignment(wrap_text=True)

    workbook.save(file_path)
    print(f"File {file_path} saved successfully.")

def upload_to_drive(file_path):
    gauth = GoogleAuth()

    # Try to load saved client credentials
    gauth.LoadCredentialsFile("credentials.json")

    if gauth.credentials is None:
        gauth.LocalWebserverAuth()  # Authenticate if no credentials found
    elif gauth.access_token_expired:
        gauth.Refresh()  # Refresh credentials if expired
    else:
        gauth.Authorize()  # Just authorize if valid credentials exist

    # Save the credentials for future use
    gauth.SaveCredentialsFile("credentials.json")

    drive = GoogleDrive(gauth)
    file = drive.CreateFile({"title": os.path.basename(file_path), "parents": [{"id": GDRIVE_FOLDER_ID}]})
    file.SetContentFile(file_path)
    file.Upload()
    print(f"File {file_path} uploaded successfully to Google Drive.")


def main_function(start_date, end_date):
    conversations = search_conversations(start_date, end_date)

    if conversations:
        bridges_conversations = filter_conversations_by_product(conversations, 'Bridges')  # ✅ Apply filter
        print(f"Bridges Conversations: {len(bridges_conversations)}")  # Debugging

        file_path = f'bridges_conversations_{start_date}_to_{end_date}.xlsx'

        # ✅ Call the function with the correct data (filtered conversations)
        store_conversations_to_xlsx(bridges_conversations, file_path)

        # ✅ Upload the generated file to Google Drive
        upload_to_drive(file_path)

    else:
        print('No conversations found for provided timeframe')



if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <start_date> <end_date>")
        sys.exit(1)

    start_date = sys.argv[1]
    end_date = sys.argv[2]

    print(f"Script started with start_date: {start_date} and end_date: {end_date}")
    main_function(start_date, end_date)
