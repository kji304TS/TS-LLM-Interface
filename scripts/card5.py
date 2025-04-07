import requests
from datetime import datetime
import re
import os
import sys
from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.styles import Alignment
from app import upload_file_to_drive

# Load environment variables
load_dotenv()
API_KEY = os.getenv("API_KEY")
INTERCOM_PROD_KEY = os.getenv('INTERCOM_PROD_KEY')
GDRIVE_FOLDER_ID = os.getenv('GDRIVE_FOLDER_ID')

def remove_html_tags(text):
    if not isinstance(text, str):
        return ''
    return re.sub(r'<.*?>', '', text)

def sanitize_text(text):
    if text:
        return text.replace('\u200b', '').encode('utf-8', 'ignore').decode('utf-8')
    return text

def get_intercom_conversation(conversation_id):
    url = f'https://api.intercom.io/conversations/{conversation_id}'
    response = requests.get(url, headers={"Authorization": f"Bearer {INTERCOM_PROD_KEY}"})
    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}")
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
    try:
        # Handle both "YYYY-MM-DD" and "YYYY-MM-DD HH:MM" formats
        if " " in start_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M").timestamp()
        else:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").timestamp()

        if " " in end_date_str:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M").timestamp()
        else:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").timestamp()

    except ValueError as e:
        print(f"Error parsing dates: {e}")
        return []

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


def filter_conversations_by_card(conversations):
    """Filters conversations for the MetaMask Card area and retrieves full conversation details"""
    filtered_conversations = []
    
    for conversation in conversations:
        attributes = conversation.get('custom_attributes', {})
        print(f"Custom Attributes: {attributes}")  # Debugging
        
        # Check if the conversation belongs to "Card"
        if attributes.get('MetaMask area', '').strip().lower() == 'card':
            full_conversation = get_intercom_conversation(conversation['id'])
            if full_conversation:
                # ✅ Extract new subcategories
                full_conversation['MM Card Issue'] = attributes.get('MM Card Issue', 'None')
                full_conversation['MM Card Partner issue'] = attributes.get('MM Card Partner issue', 'None')
                full_conversation['Dashboard Issue'] = attributes.get('Dashboard Issue', 'None')
                full_conversation['KYC Issue'] = attributes.get('KYC Issue', 'None')

                # ✅ Capture new subcategories (if they exist)
                full_conversation['Dashboard Subcategory'] = attributes.get('Dashboard Issue - Subcategory', 'None')
                full_conversation['KYC Subcategory'] = attributes.get('KYC Issue - Subcategory', 'None')

                filtered_conversations.append(full_conversation)

    return filtered_conversations



def store_conversations_to_xlsx(conversations, file_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversations"

    # ✅ Define the headers (including new subcategories)
    headers = [
        'conversation_id', 'summary', 'transcript', 
        'MM Card Issue', 'MM Card Partner issue',
        'Dashboard Issue', 'Dashboard Subcategory', 
        'KYC Issue', 'KYC Subcategory'
    ]
    sheet.append(headers)

    for conversation in conversations:
        conversation_id = conversation['id']
        summary = sanitize_text(get_conversation_summary(conversation))
        transcript = sanitize_text(get_conversation_transcript(conversation))

        # ✅ Extract new categories & subcategories
        mm_card_issue = conversation.get('MM Card Issue', 'None')
        mm_card_partner_issue = conversation.get('MM Card Partner issue', 'None')
        dashboard_issue = conversation.get('Dashboard Issue', 'None')
        dashboard_subcategory = conversation.get('Dashboard Subcategory', 'None')
        kyc_issue = conversation.get('KYC Issue', 'None')
        kyc_subcategory = conversation.get('KYC Subcategory', 'None')

        # ✅ Append the data as a row in the sheet
        sheet.append([
            conversation_id, summary, transcript, 
            mm_card_issue, mm_card_partner_issue, 
            dashboard_issue, dashboard_subcategory, 
            kyc_issue, kyc_subcategory
        ])

    # ✅ Apply text wrapping for better readability
    for col in ["B", "C"]:  # Column B = Summary, Column C = Transcript
        for cell in sheet[col]:
            cell.alignment = Alignment(wrap_text=True)

    workbook.save(file_path)
    print(f"File {file_path} saved successfully.")

def standard_result(status: str, message: str, file_url: str = None):
    return {
        "status": status,
        "message": message,
        "file": file_url if file_url else None
    }

def main_function(start_date, end_date):
    conversations = search_conversations(start_date, end_date)
    if not conversations:
        return standard_result("no_data", "⚠️ No conversations found for the selected timeframe.")

    card_conversations = filter_conversations_by_card(conversations)
    print(f"Card Conversations Found: {len(card_conversations)}")

    if card_conversations:
        file_path = f'card_conversations_{start_date}_to_{end_date}.xlsx'
        store_conversations_to_xlsx(card_conversations, file_path)
        
        file_url = upload_file_to_drive(file_path)
        print(f"File uploaded to Google Drive: {file_url}")

        # ✅ Only show simple message in output
        return standard_result("success", "✅ File uploaded: Complete")

    else:
        return standard_result("no_data", "🤷 No card-related conversations found.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <start_date> <end_date>")
        sys.exit(1)
    start_date = sys.argv[1]
    end_date = sys.argv[2]
    print(f"Script started with start_date: {start_date} and end_date: {end_date}")
    main_function(start_date, end_date)
