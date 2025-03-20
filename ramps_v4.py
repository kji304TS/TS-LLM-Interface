import requests
from datetime import datetime
import csv
import re
import sys

# INTERCOM_PROD_KEY = ''


def remove_html_tags(text):
    clean = re.sub(r'<.*?>', '', text)
    return clean


def get_intercom_conversation(conversation_id):
    url = f'https://api.intercom.io/conversations/{conversation_id}'
    response = requests.get(url, headers={"Authorization": f"Bearer {INTERCOM_PROD_KEY}"})
    if response.status_code != 200:
        print('Status:', response.status_code, 'Problem while looking for ticket status')
        print('Error: ', response.json())
        return None
    ticket = response.json()
    return ticket


def get_conversation_summary(conversation):
    # might be different for tickets
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', None)
        for part in conversation_parts:
            part_type = part['part_type']
            if part_type == 'conversation_summary':
                return remove_html_tags(part['body'])
    return None


def get_conversation_transcript(conversation):
    transcript = ''
    if 'conversation_parts' in conversation:
        conversation_parts = conversation['conversation_parts'].get('conversation_parts', None)
        for part in conversation_parts:
            part_type = part['part_type']
            if part_type == 'comment':
                author = part['author']['type']
                comment = remove_html_tags(part['body'])
                transcript += f"{author}: {comment}\n"
    return transcript


def get_conversation_csat_remark(conversation):
    csat = conversation.get('conversation_rating')
    if not csat:
        return None

    # csat_score = csat.get('rating')
    remark = csat.get('remark', '')
    return remark




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
            "per_page": 150
        }
    }

    all_conversations = []
    next_page = None

    while True:
        response = requests.post(url, headers=headers, json=payload)
        print(len(all_conversations))

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


def filter_conversations_by_product(conversations, product):
    filtered_conversations_buy = []
    filtered_conversations_sell = []
    for conversation in conversations:
        attributes = conversation['custom_attributes']
        if 'MetaMask area' in attributes and 'Buy or Sell' in attributes:
            if attributes['MetaMask area'] == product:
                if attributes['Buy or Sell'] == 'Sell':
                    filtered_conversations_sell.append(get_intercom_conversation(conversation['id']))
                elif attributes['Buy or Sell'] == 'Buy':
                    filtered_conversations_buy.append(get_intercom_conversation(conversation['id']))
    return filtered_conversations_buy, filtered_conversations_sell


def store_conversations_to_csv(conversations, file_path):
    #headers = ['conversation_id', 'summary', 'network', 'provider', 'transcript']
    headers = ['conversation_id', 'summary'] 

    with open(file_path, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()

        for conversation in conversations:
            conversation_id = conversation['id']
            #csat_remark = get_conversation_csat_remark(conversation)
            summary = get_conversation_summary(conversation)
            #transcript = get_conversation_transcript(conversation)
            #network = conversation['custom_attributes'].get('Network', None)
            #provider = conversation['custom_attributes'].get('Ramps provider', None)
            #date_closed = conversation['statistics'].get('last_close_at', None)

            #if date_closed:
            #    date_closed = datetime.utcfromtimestamp(date_closed).strftime('%Y-%m-%d %H:%M:%S')

            #if network == "I don't know":
            #    network = 'Unknown'

            writer.writerow({
                'conversation_id': conversation_id,
                'summary': summary
            })
            # writer.writerow({
            #     'conversation_id': conversation_id,
            #     'summary': summary,
            #     'network': network,
            #     'provider': provider,
            #     'transcript': transcript
            # })


def main_function(start_date, end_date):
    conversations = search_conversations(start_date, end_date)
    if conversations:
        filtered_conversations_buy, filtered_conversations_sell = filter_conversations_by_product(conversations, 'Ramps')
        print(len(filtered_conversations_buy))
        print(len(filtered_conversations_sell))
        store_conversations_to_csv(filtered_conversations_buy, f'onRamp_{start_date}_to_{end_date}.csv')
        store_conversations_to_csv(filtered_conversations_sell, f'offRamp_{start_date}_to_{end_date}.csv')
    else:
        print('No conversations found for provided timeframe')


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <start_date> <end_date>")
        sys.exit(1)        

start_date = sys.argv[1]
end_date = sys.argv[2]
main_function(start_date, end_date)

#ticket = get_intercom_conversation(505032)
#print(ticket['statistics']['last_close_at'])
# print(get_conversation_transcript(ticket))
# print(get_conversation_csat_remark(ticket))
# print(get_conversation_summary(ticket))
