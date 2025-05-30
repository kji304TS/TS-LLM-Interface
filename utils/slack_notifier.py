import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load .env variables if not already loaded by the main app
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
DEFAULT_SLACK_CHANNEL = "#general-reports" # Placeholder - update as needed

def send_slack_report(team_name: str, report_content: str, slack_channel: str = None):
    """
    Sends a formatted report to a Slack channel.

    Args:
        team_name (str): The name of the team the report is for.
        report_content (str): The full text content of the report.
        slack_channel (str, optional): The specific Slack channel to send to. 
                                       Defaults to DEFAULT_SLACK_CHANNEL.
    
    Returns:
        bool: True if the message was sent successfully, False otherwise.
    """
    if not SLACK_BOT_TOKEN:
        print("❌ Slack Bot Token not found. Please set SLACK_BOT_TOKEN in your .env file.")
        return False

    client = WebClient(token=SLACK_BOT_TOKEN)
    channel_to_send = slack_channel if slack_channel else DEFAULT_SLACK_CHANNEL

    # Friendly end-of-day message format
    # Since the report_content is already a pre-formatted string,
    # we will send it as the main text.
    # We can enhance this by parsing the report_content if it has a very specific Q&A structure.
    
    friendly_header = f"🔔 *End of Shift Report for {team_name}* 🔔\n\n"
    message_text = friendly_header + report_content

    try:
        response = client.chat_postMessage(
            channel=channel_to_send,
            text=message_text,
            mrkdwn=True  # Ensure markdown is enabled for formatting like bold
        )
        print(f"✅ Slack message sent successfully to {channel_to_send} for team {team_name}!")
        return True
    except SlackApiError as e:
        print(f"❌ Error sending Slack message to {channel_to_send} for {team_name}: {e.response['error']}")
        return False

if __name__ == '__main__':
    # Example usage (for testing this module directly)
    # Make sure SLACK_BOT_TOKEN is in your .env and you have a #testing channel (or similar)
    print("Attempting to send a test Slack message...")
    if SLACK_BOT_TOKEN:
        test_team = "Test Team"
        test_report = (
            "Summary of Activities:\n"
            "- Top Issue: Login failures (5 instances)\n"
            "- Keywords: login, password, stuck\n"
            "Details:\n"
            "  Question: What was the primary concern?\n"
            "  Answer: Users reported being unable to log in after the recent update.\n"
            "  Question: Any emerging trends?\n"
            "  Answer: A slight increase in password reset requests noted."
        )
        # Replace with a real channel ID or name you have access to for testing
        test_channel = "#general-reports" # Or your personal DM, or a test channel
        
        # You might need to invite your bot to the channel first.
        # To send to a user by ID, use their Member ID (e.g., "U0xxxxxxxxx")
        
        success = send_slack_report(test_team, test_report, slack_channel=test_channel)
        if success:
            print("Test message sent. Check Slack.")
        else:
            print("Test message failed. Check token, channel, and bot permissions.")
    else:
        print("SLACK_BOT_TOKEN not found in .env. Cannot run test.") 