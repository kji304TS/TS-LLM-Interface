import requests
from datetime import datetime
import csv
import re

INTERCOM_PROD_KEY = ''

def remove_html_tags(text):
    if not isinstance(text, str):
        return ''
    clean = re.sub(r'<.*?>', '', text)
    return clean

def sanitize_text(text):
    if text:
        return text.replace('\u200b', '').encode('utf-8', 'ignore').decode('utf-8')  # Remove zero-width spaces
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

    try:
        ticket = response.json()
        print(f"Debugging ticket for Conversation ID {conversation_id}: {ticket}")  # Debugging
    except requests.exceptions.JSONDecodeError:
        print("Error: Received invalid JSON response.")
        return None

    return ticket

def get_conversation_summary(conversation):
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        print(f"Debugging conversation_parts for ID {conversation.get('id')}: {conversation_parts}")  # Debugging
        for part in conversation_parts:
            if part.get('part_type') == 'conversation_summary':
                return remove_html_tags(part.get('body', ''))

    # Fallback to custom attributes or other fields
    custom_attributes = conversation.get('custom_attributes', {})
    return custom_attributes.get('Cristi GPT response', "No summary available")

def get_conversation_transcript(conversation):
    transcript = []
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        print(f"Debugging conversation_parts for ID {conversation.get('id')}: {conversation_parts}")  # Debugging
        for part in conversation_parts:
            if part.get('part_type') == 'comment':
                author = part.get('author', {}).get('type', 'Unknown')
                comment = remove_html_tags(part.get('body', ''))
                transcript.append(f"{author}: {comment}")

    return "\n".join(transcript) if transcript else "No transcript available"

def search_conversations(start_date_str, end_date_str, product):
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
                },
                {
                    "field": "custom_attributes.MetaMask area",
                    "operator": "=",
                    "value": product
                }
            ]
        },
        "pagination": {
            "per_page": 150
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

def store_conversations_to_csv(conversations, file_path):
    headers = ['conversation_id', 'summary', 'transcript', 'Snaps Category']

    with open(file_path, mode='w', newline='', encoding='utf-8') as file:  # Specify UTF-8 encoding
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()

        for conversation in conversations:
            conversation_id = conversation['id']
            summary = sanitize_text(get_conversation_summary(conversation))
            transcript = sanitize_text(get_conversation_transcript(conversation))

            # Extract Snaps Category
            attributes = conversation.get('custom_attributes', {})
            snaps_category = attributes.get('Snaps Category', 'N/A')

            # Debugging to ensure data is being extracted
            print(f"Writing conversation: {conversation_id}, Summary: {summary}, Transcript: {transcript}, Snaps Category: {snaps_category}")

            writer.writerow({
                'conversation_id': conversation_id,
                'summary': summary,
                'transcript': transcript,
                'Snaps Category': snaps_category
            })

def main_function():
    conversations = search_conversations("2024-12-15 00:00", "2024-12-18 16:00", "Snaps")
    if conversations:
        print(f"Snaps Conversations: {len(conversations)}")
        store_conversations_to_csv(conversations, 'snaps_conversations-03.csv')
    else:
        print('No conversations found for provided timeframe')

if __name__ == "__main__":
    main_function()