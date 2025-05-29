"""
Centralized utilities for Intercom API interactions.

This module consolidates common functionality that was previously 
duplicated across multiple specialized scripts in the scripts/ directory.
"""

import requests
import re
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
INTERCOM_PROD_KEY = os.getenv('INTERCOM_PROD_KEY')

def remove_html_tags(text: str) -> str:
    """Remove HTML tags from text."""
    if not isinstance(text, str):
        return ''
    return re.sub(r'<.*?>', '', text)

def sanitize_text(text: str) -> str:
    """Sanitize text by removing zero-width characters and handling encoding."""
    if text:
        return text.replace('\u200b', '').encode('utf-8', 'ignore').decode('utf-8')
    return text

def get_intercom_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single conversation from Intercom by ID.
    
    Args:
        conversation_id: The Intercom conversation ID
        
    Returns:
        Dict containing conversation data, or None if error
    """
    url = f'https://api.intercom.io/conversations/{conversation_id}'
    response = requests.get(url, headers={"Authorization": f"Bearer {INTERCOM_PROD_KEY}"})
    if response.status_code != 200:
        print(f"Error fetching conversation {conversation_id}: {response.status_code} - {response.text}")
        return None
    return response.json()

def get_conversation_summary(conversation: Dict[str, Any]) -> str:
    """Extract summary from conversation data."""
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        for part in conversation_parts:
            if part.get('part_type') == 'conversation_summary':
                return remove_html_tags(part.get('body', ''))
    
    # Fallback to custom attribute
    return conversation.get('custom_attributes', {}).get('Cristi GPT response', "No summary available")

def get_conversation_transcript(conversation: Dict[str, Any]) -> str:
    """Extract transcript from conversation data."""
    transcript = []
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', [])
        for part in conversation_parts:
            if part.get('part_type') == 'comment':
                author = part.get('author', {}).get('type', 'Unknown')
                comment = remove_html_tags(part.get('body', ''))
                transcript.append(f"{author}: {comment}")
    return "\n".join(transcript) if transcript else "No transcript available"

def search_conversations(start_date_str: str, end_date_str: str) -> List[Dict[str, Any]]:
    """
    Search for conversations within a date range.
    
    Args:
        start_date_str: Start date in "YYYY-MM-DD" or "YYYY-MM-DD HH:MM" format
        end_date_str: End date in "YYYY-MM-DD" or "YYYY-MM-DD HH:MM" format
        
    Returns:
        List of conversation dictionaries
    """
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
            payload["pagination"]["starting_after"] = next_page
        
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text}")
            return all_conversations

        data = response.json()
        conversations = data.get('conversations', [])
        all_conversations.extend(conversations)

        print(f"Fetched {len(conversations)} conversations, total: {len(all_conversations)}")

        # Handle pagination
        next_page_data = data.get('pages', {}).get('next', None)
        if next_page_data and "starting_after" in next_page_data:
            next_page = next_page_data["starting_after"]
        else:
            break

    print(f"Total conversations retrieved: {len(all_conversations)}")
    return all_conversations

def filter_conversations_by_area(conversations: List[Dict[str, Any]], area_name: str) -> List[Dict[str, Any]]:
    """
    Filter conversations by MetaMask area and retrieve full conversation details.
    
    Args:
        conversations: List of conversation summaries from search
        area_name: MetaMask area to filter by (case-insensitive)
        
    Returns:
        List of full conversation objects for the specified area
    """
    filtered_conversations = []
    area_name_lower = area_name.lower()
    
    for conversation in conversations:
        attributes = conversation.get('custom_attributes', {})
        
        if attributes.get('MetaMask area', '').strip().lower() == area_name_lower:
            full_conversation = get_intercom_conversation(conversation['id'])
            if full_conversation:
                # Copy custom attributes to the main conversation object for easier access
                for key, value in attributes.items():
                    full_conversation[key] = value
                filtered_conversations.append(full_conversation)

    return filtered_conversations

def standard_result(status: str, message: str, file_path: Optional[str] = None) -> Dict[str, Any]:
    """Standard result format for consistency across scripts."""
    return {
        "status": status,
        "message": message,
        "file": file_path if file_path else None
    } 