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
    try:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Conversations"

        # ✅ Headers
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
            try:
                conversation_id = conversation.get('id', 'N/A')
                summary = remove_html_tags(get_conversation_summary(conversation))
                transcript = remove_html_tags(get_conversation_transcript(conversation))

                # Extract attributes with fallback
                def safe_get(key):
                    return conversation.get(key, 'None')

                row = [
                    conversation_id, summary, transcript,
                    safe_get('Staking Feature'),
                    safe_get('Validator Staking Issue'),
                    safe_get('Pooled Staking Issue'),
                    safe_get('Liquid Staking Issue'),
                    safe_get('Third Party Staking'),
                    safe_get('Bug ID'),
                    safe_get('Refund amount (USD)'),
                    safe_get('Refund Provided'),
                    safe_get('Withdrawals'),
                    safe_get('Managing Staked Tokens'),
                    safe_get('User Training'),
                    safe_get('Failed Transaction'),
                    safe_get('Liquid Staking Provider'),
                    safe_get('Staking Token Type'),
                    safe_get('Staking Platform')
                ]
                sheet.append(row)

            except Exception as row_err:
                print(f"⚠️ Skipped a row due to error: {row_err}")

        # ✅ Enable text wrapping for summary and transcript columns
        for col_letter in ["B", "C"]:  # Columns B and C
            for cell in sheet[col_letter]:
                cell.alignment = Alignment(wrap_text=True)

        # ✅ Save to disk
        print(f"💾 Saving Excel to: {file_path}")
        workbook.save(file_path)
        print("✅ Excel file saved successfully.")

    except Exception as e:
        print("❌ Error while writing Excel file:", str(e))
        import traceback
        traceback.print_exc()
        raise  # Re-raise so main_function can handle it


def standard_result(status: str, message: str, file_url: str = None):
    return {
        "status": status,
        "message": message,
        "file": file_url if file_url else None
    }

def main_function(start_date, end_date):
    try:
        print(f"🔍 Starting search: {start_date} → {end_date}")
        conversations = search_conversations(start_date, end_date)
        print(f"📦 Total conversations: {len(conversations)}")

        if not conversations:
            return standard_result("no_data", "⚠️ No conversations found for the selected timeframe.")

        staking_conversations = filter_conversations_by_staking(conversations)
        print(f"🔎 Staking-related conversations: {len(staking_conversations)}")

        if staking_conversations:
            file_path = f'staking_conversations_{start_date}_to_{end_date}.xlsx'

    try:
        store_conversations_to_xlsx(staking_conversations, file_path)
        print(f"✅ Excel saved locally: {file_path}")
    except Exception as e:
        print("❌ Failed to save Excel file:", str(e))
        return standard_result("error", "❌ Failed to save Excel file.")

    # ✅ Upload to Google Drive
    try:
        file_url = upload_file_to_drive(file_path)
        print(f"✅ File uploaded to Google Drive: {file_url}")
        return standard_result("success", "✅ File uploaded: Complete", file_url)
    except Exception as e:
        print("⚠️ Upload failed:", str(e))
        return standard_result("success", "✅ File created, but upload to Drive failed", file_path)




if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <start_date> <end_date>")
        sys.exit(1)
    start_date = sys.argv[1]
    end_date = sys.argv[2]
    print(f"Script started with start_date: {start_date} and end_date: {end_date}")
    main_function(start_date, end_date)



