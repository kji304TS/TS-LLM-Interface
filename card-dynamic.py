import requests
from datetime import datetime
import csv
import re
import os
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

INTERCOM_PROD_KEY = ''
GDRIVE_FOLDER_NAME = "DataAndInsights"

# ✅ Authenticate and initialize Google Drive API
def authenticate_google_drive():
    gauth = GoogleAuth()
    gauth.LocalWebserverAuth()  # Opens a browser for authentication
    return GoogleDrive(gauth)

# ✅ Upload file to Google Drive folder
def upload_to_google_drive(drive, file_path, folder_name):
    file_name = os.path.basename(file_path)

    # Search for the folder ID by name
    folder_id = None
    file_list = drive.ListFile({'q': "mimeType='application/vnd.google-apps.folder'"}).GetList()
    for folder in file_list:
        if folder['title'] == folder_name:
            folder_id = folder['id']
            break

    # Create the folder if it doesn’t exist
    if folder_id is None:
        folder_metadata = {'title': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
        folder = drive.CreateFile(folder_metadata)
        folder.Upload()
        folder_id = folder['id']

    # Upload the file
    file = drive.CreateFile({'title': file_name, 'parents': [{'id': folder_id}]})
    file.SetContentFile(file_path)
    file.Upload()
    print(f"✅ Uploaded {file_name} to Google Drive folder: {folder_name}")

# ✅ Generate dynamic filenames based on UI input
def generate_dynamic_filename(base_name, start_date, end_date, extension):
    formatted_start = datetime.strptime(start_date, "%Y-%m-%d %H:%M").strftime("%m-%d-%Y")
    formatted_end = datetime.strptime(end_date, "%Y-%m-%d %H:%M").strftime("%m-%d-%Y")
    return f"{base_name}_{formatted_start}_to_{formatted_end}.{extension}"

def store_conversations_to_csv(conversations, start_date, end_date):
    """Stores filtered Card conversations into a dynamically named CSV file"""
    headers = ['conversation_id', 'summary', 'transcript', 'MM Card Issue', 'MM Card Partner issue']

    # Generate filename based on search date range
    file_name = generate_dynamic_filename("mmcard_output", start_date, end_date, "csv")
    file_path = os.path.join(os.getcwd(), file_name)

    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()

        for conversation in conversations:
            conversation_id = conversation['id']
            summary = sanitize_text(get_conversation_summary(conversation))
            transcript = sanitize_text(get_conversation_transcript(conversation))
            mm_card_issue = conversation.get('MM Card Issue', 'None')
            mm_card_partner_issue = conversation.get('MM Card Partner issue', 'None')

            print(f"Writing conversation: {conversation_id}, Summary: {summary}, Transcript: {transcript}")

            writer.writerow({
                'conversation_id': conversation_id,
                'summary': summary,
                'transcript': transcript,
                'MM Card Issue': mm_card_issue,
                'MM Card Partner issue': mm_card_partner_issue
            })

    print(f"✅ CSV saved as {file_name}")
    return file_path  # Return the dynamically generated file path

def main_function(start_date, end_date):
    """Main function to extract, filter, save, and upload Card conversations"""
    drive = authenticate_google_drive()
    conversations = search_conversations(start_date, end_date)

    if conversations:
        file_path = store_conversations_to_csv(conversations, start_date, end_date)
        upload_to_google_drive(drive, file_path, GDRIVE_FOLDER_NAME)
    else:
        print('⚠️ No conversations found for provided timeframe')

# ✅ User enters date range dynamically (UI Integration)
if __name__ == "__main__":
    start_date = input("Enter start date (YYYY-MM-DD HH:MM): ").strip()
    end_date = input("Enter end date (YYYY-MM-DD HH:MM): ").strip()

    main_function(start_date, end_date)
