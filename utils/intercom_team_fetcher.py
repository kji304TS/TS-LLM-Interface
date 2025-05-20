import requests
import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

INTERCOM_PROD_KEY = os.getenv("INTERCOM_PROD_KEY")
INTERCOM_API_BASE_URL = "https://api.intercom.io"

def get_intercom_teams():
    """
    Fetches all teams from the Intercom API and prints their ID and name.
    """
    if not INTERCOM_PROD_KEY:
        print("Error: INTERCOM_PROD_KEY not found in environment variables.")
        print("Please ensure it is set in your .env file.")
        return None

    teams_url = f"{INTERCOM_API_BASE_URL}/teams"
    headers = {
        "Authorization": f"Bearer {INTERCOM_PROD_KEY}",
        "Accept": "application/json",
        "Intercom-Version": "2.10" # Specify a recent API version
    }

    print("Fetching teams from Intercom...")

    try:
        response = requests.get(teams_url, headers=headers, timeout=30)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        
        data = response.json()
        teams_data = data.get('teams', []) # Renamed from teams to teams_data
        
        if not teams_data:
            print("No teams found or 'teams' key missing in response.")
            return {}

        # Convert to a name:id dictionary
        teams_map = {team.get('name'): team.get('id') for team in teams_data if team.get('name') and team.get('id')}
        
        # Intercom's /teams endpoint might not paginate by default for typical numbers of teams.
        # If pagination were needed, it usually involves checking a 'pages' object and 'next' link.
        # For simplicity, this example assumes all teams are fetched in the first call,
        # which is common for the /teams endpoint. If you have hundreds of teams,
        # pagination handling would need to be added here.

        print(f"Successfully fetched {len(teams_map)} teams and mapped to name:id.")
        return teams_map

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        print(f"Response content: {response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"An unexpected error occurred: {req_err}")
    except json.JSONDecodeError:
        print("Error decoding JSON response from Intercom.")
        print(f"Response content: {response.text if 'response' in locals() else 'N/A'}")
        
    return None

if __name__ == "__main__":
    print("--- Intercom Team Fetcher ---")
    teams_list = get_intercom_teams()

    if teams_list is not None: # Check if not None (could be {} if no teams)
        if teams_list:
            print("\n--- Team Name to ID Map ---")
            for name, team_id in teams_list.items():
                print(f"Team Name: {name} (ID: {team_id})")
        else:
            print("No teams were found in your Intercom workspace.")
    else:
        print("Could not retrieve team list due to an error.") 