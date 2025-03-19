import requests
from datetime import datetime


def remove_html_tags(text):
    if not isinstance(text, str):
        return ''

    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        for part in conversation_parts:
            if part.get('part_type') == 'conversation_summary':
                return remove_html_tags(part.get('body', ''))

    transcript = []
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        for part in conversation_parts:
            if part.get('part_type') == 'comment':
                author = part.get('author', {}).get('type', 'Unknown')
                comment = remove_html_tags(part.get('body', ''))
                transcript.append(f"{author}: {comment}")


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

    return all_conversations


def filter_conversations_by_security(conversations):
    """Filters conversations for the MetaMask Security area and retrieves full conversation details"""
    filtered_conversations = []
    for conversation in conversations:
        attributes = conversation.get('custom_attributes', {})
        print(f"Custom Attributes: {attributes}")

        # Check if the conversation belongs to "Security"
        if attributes.get('MetaMask area', '').strip().lower() == 'security':
            full_conversation = get_intercom_conversation(conversation['id'])
            if full_conversation:
                filtered_conversations.append(full_conversation)

    return filtered_conversations



