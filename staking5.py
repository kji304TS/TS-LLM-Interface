import requests
from datetime import datetime
import re
import os
import sys
from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.styles import Alignment
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

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

def filter_conversations_by_staking(conversations):
    """Filters conversations for the MetaMask Staking area and retrieves full conversation details"""
    filtered_conversations = []
    
    for conversation in conversations:
        attributes = conversation.get('custom_attributes', {})
        print(f"Custom Attributes: {attributes}")  # Debugging
        
        # Check if the conversation belongs to "Staking"
        if attributes.get('MetaMask area', '').strip().lower() == 'staking':
            full_conversation = get_intercom_conversation(conversation['id'])
            if full_conversation:
                # ✅ Extract new subcategories
                full_conversation['Staking Feature'] = attributes.get('Staking Feature', 'None')
                full_conversation['Validator Staking Issue'] = attributes.get('Validator Staking Issue', 'None')
                full_conversation['Pooled Staking Issue'] = attributes.get('Pooled Staking Issue', 'None')
                full_conversation['Liquid Staking Issue'] = attributes.get('Liquid Staking Issue', 'None')
                full_conversation['Third Party Staking'] = attributes.get('Third Party Staking', 'None')
                full_conversation['Bug ID'] = attributes.get('Bug ID', 'None')
                full_conversation['Refund amount (USD)'] = attributes.get('Refund amount (USD)', 'None')
                full_conversation['Refund Provided'] = attributes.get('Refund Provided', 'None')

                # ✅ Capture subcategories (if they exist)
                full_conversation['Withdrawals'] = attributes.get('Withdrawals', 'None')
                full_conversation['Managing Staked Tokens'] = attributes.get('Managing Staked Tokens', 'None')
                full_conversation['User Training'] = attributes.get('User Training', 'None')
                full_conversation['Failed Transaction'] = attributes.get('Failed Transaction', 'None')
                full_conversation['Liquid Staking Provider'] = attributes.get('Liquid Staking Provider', 'None')
                full_conversation['Staking Token Type'] = attributes.get('Staking Token Type', 'None')
                full_conversation['Staking Platform'] = attributes.get('Staking Platform', 'None')
                
                filtered_conversations.append(full_conversation)

    return filtered_conversations

def store_conversations_to_xlsx(conversations, file_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Conversations"

    # ✅ Define the headers (including new subcategories for Staking)
    headers = [
        'conversation_id', 'summary', 'transcript', 
        'Staking Feature', 'Validator Staking Issue', 'Pooled Staking Issue', 
        'Liquid Staking Issue', 'Third Party Staking', 'Bug ID', 
        'Refund amount (USD)', 'Refund Provided', 'Withdrawals', 
        'Managing Staked Tokens', 'User Training', 'Failed Transaction',
        'Liquid Staking Provider', 'Staking Token Type', 'Staking Platform'
    ]
    sheet.append(headers)

    for conversation in conversations:
        conversation_id = conversation['id']
        summary = remove_html_tags(get_conversation_summary(conversation))
        transcript = remove_html_tags(get_conversation_transcript(conversation))

        # ✅ Extract new staking categories & subcategories
        staking_feature = conversation.get('Staking Feature', 'None')
        validator_staking_issue = conversation.get('Validator Staking Issue', 'None')
        pooled_staking_issue = conversation.get('Pooled Staking Issue', 'None')
        liquid_staking_issue = conversation.get('Liquid Staking Issue', 'None')
        third_party_staking = conversation.get('Third Party Staking', 'None')
        bug_id = conversation.get('Bug ID', 'None')
        refund_amount = conversation.get('Refund amount (USD)', 'None')
        refund_provided = conversation.get('Refund Provided', 'None')
        withdrawals = conversation.get('Withdrawals', 'None')
        managing_staked_tokens = conversation.get('Managing Staked Tokens', 'None')
        user_training = conversation.get('User Training', 'None')
        failed_transaction = conversation.get('Failed Transaction', 'None')
        liquid_staking_provider = conversation.get('Liquid Staking Provider', 'None')
        staking_token_type = conversation.get('Staking Token Type', 'None')
        staking_platform = conversation.get('Staking Platform', 'None')

        # ✅ Append the data as a row in the sheet
        sheet.append([
            conversation_id, summary, transcript, 
            staking_feature, validator_staking_issue, pooled_staking_issue, 
            liquid_staking_issue, third_party_staking, bug_id, 
            refund_amount, refund_provided, withdrawals, 
            managing_staked_tokens, user_training, failed_transaction,
            liquid_staking_provider, staking_token_type, staking_platform
        ])

    # ✅ Apply text wrapping for better readability
    for col in ["B", "C"]:  # Column B = Summary, Column C = Transcript
        for cell in sheet[col]:
            cell.alignment = Alignment(wrap_text=True)

    workbook.save(file_path)
    print(f"File {file_path} saved successfully.")


def upload_to_drive(file_path):
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile("credentials.json")
    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()
    gauth.SaveCredentialsFile("credentials.json")
    
    drive = GoogleDrive(gauth)
    file = drive.CreateFile({"title": os.path.basename(file_path), "parents": [{"id": GDRIVE_FOLDER_ID}]})
    file.SetContentFile(file_path)
    file.Upload()
    print(f"File {file_path} uploaded successfully to Google Drive.")

def main_function(start_date, end_date):
    conversations = search_conversations(start_date, end_date)
    if conversations:
        staking_conversations = filter_conversations_by_staking(conversations)
        print(f"Staking Conversations: {len(staking_conversations)}")
        file_path = f'staking_conversations_{start_date}_to_{end_date}.xlsx'
        store_conversations_to_xlsx(staking_conversations, file_path)
        upload_to_drive(file_path)
    else:
        print("No conversations found for provided timeframe")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <start_date> <end_date>")
        sys.exit(1)
    start_date = sys.argv[1]
    end_date = sys.argv[2]
    print(f"Script started with start_date: {start_date} and end_date: {end_date}")
    main_function(start_date, end_date)

