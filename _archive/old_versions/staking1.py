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
    """Fetches full conversation details from Intercom"""
    url = f'https://api.intercom.io/conversations/{conversation_id}'
    response = requests.get(url, headers={"Authorization": f"Bearer {INTERCOM_PROD_KEY}"})
    if response.status_code != 200:
        print(f'Status: {response.status_code}, Problem while looking for ticket status')
        print(f'Error: {response.json()}')
        return None
    return response.json()


def get_conversation_summary(conversation):
    """Extracts conversation summary"""
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        for part in conversation_parts:
            if part.get('part_type') == 'conversation_summary':
                return remove_html_tags(part.get('body', ''))

    custom_attributes = conversation.get('custom_attributes', {})
    fallback_fields = ['Cristi GPT response', 'Conversation description', 'User Notes']
    for field in fallback_fields:
        if custom_attributes.get(field):
            return remove_html_tags(custom_attributes[field])

    return "Does not exist"


def get_conversation_transcript(conversation):
    """Extracts full conversation transcript"""
    transcript = []
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        for part in conversation_parts:
            if part.get('part_type') == 'comment':
                author = part.get('author', {}).get('type', 'Unknown')
                comment = remove_html_tags(part.get('body', ''))
                transcript.append(f"{author}: {comment}")

    custom_attributes = conversation.get('custom_attributes', {})
    fallback_fields = ['Cristi GPT response', 'Conversation description', 'User Notes']
    for field in fallback_fields:
        if custom_attributes.get(field):
            transcript.append(f"{field}: {remove_html_tags(custom_attributes[field])}")

    return "\n".join(transcript) if transcript else "Does not exist"


def search_conversations(start_date_str, end_date_str):
    """Fetches all conversations from Intercom"""
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
        "pagination": {"per_page": 150}
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


def filter_conversations_by_staking(conversations):
    """Filters conversations for the MetaMask Staking area and retrieves full conversation details"""
    filtered_conversations = []
    for conversation in conversations:
        attributes = conversation.get('custom_attributes', {})
        print(f"Custom Attributes: {attributes}")

        # Check if the conversation belongs to "Staking"
        if attributes.get('MetaMask area', '').strip().lower() == 'staking':
            full_conversation = get_intercom_conversation(conversation['id'])
            if full_conversation:
                full_conversation['Staking issue'] = attributes.get('Staking issue', 'None')
                filtered_conversations.append(full_conversation)

    return filtered_conversations


def store_conversations_to_csv(conversations, file_path):
    """Stores filtered Staking conversations into a CSV file"""
    headers = ['conversation_id', 'summary', 'transcript', 'Staking issue']

    with open(file_path, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()

        for conversation in conversations:
            conversation_id = conversation['id']
            summary = sanitize_text(get_conversation_summary(conversation))
            transcript = sanitize_text(get_conversation_transcript(conversation))
            staking_issue = conversation.get('Staking issue', 'None')

            print(f"Writing conversation: {conversation_id}, Summary: {summary}, Transcript: {transcript}")

            writer.writerow({
                'conversation_id': conversation_id,
                'summary': summary,
                'transcript': transcript,
                'Staking issue': staking_issue
            })


def main_function():
    """Main function to extract, filter, and save Staking conversations"""
    conversations = search_conversations("2024-12-15 00:00", "2024-12-15 16:00")
    if conversations:
        staking_conversations = filter_conversations_by_staking(conversations)

        print(f"Staking Conversations: {len(staking_conversations)}")

        store_conversations_to_csv(staking_conversations, '1-21-25-combined_staking_output-2.csv')
    else:
        print('No conversations found for provided timeframe')


if __name__ == "__main__":
    main_function()
