"""
Slack data scraper for collecting conversation history and analytics
Supports both real-time monitoring and historical data analysis
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import pandas as pd
import logging
from textblob import TextBlob

logger = logging.getLogger(__name__)

class SlackScraper:
    def __init__(self, token: str = None):
        """
        Initialize Slack scraper
        
        Args:
            token: Slack bot token (defaults to SLACK_BOT_TOKEN env var)
        """
        self.token = token or os.getenv("SLACK_BOT_TOKEN")
        if not self.token:
            raise ValueError("Slack bot token not provided")
        
        self.client = WebClient(token=self.token)
        self._validate_permissions()
    
    def _validate_permissions(self):
        """Validate that the bot has necessary permissions"""
        try:
            # Test basic API access
            auth_response = self.client.auth_test()
            self.bot_user_id = auth_response["user_id"]
            self.team_id = auth_response["team_id"]
            logger.info(f"Authenticated as bot user: {auth_response['user']}")
        except SlackApiError as e:
            logger.error(f"Failed to authenticate with Slack: {e}")
            raise
    
    def get_channel_history(
        self, 
        channel_id: str, 
        start_date: datetime = None, 
        end_date: datetime = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Fetch conversation history from a Slack channel
        
        Args:
            channel_id: Slack channel ID
            start_date: Start datetime (defaults to 24 hours ago)
            end_date: End datetime (defaults to now)
            limit: Maximum number of messages to fetch
            
        Returns:
            List of message dictionaries
        """
        if not start_date:
            start_date = datetime.now() - timedelta(hours=24)
        if not end_date:
            end_date = datetime.now()
        
        # Convert to Slack timestamps
        oldest = str(start_date.timestamp())
        latest = str(end_date.timestamp())
        
        messages = []
        cursor = None
        
        try:
            while len(messages) < limit:
                response = self.client.conversations_history(
                    channel=channel_id,
                    oldest=oldest,
                    latest=latest,
                    limit=min(200, limit - len(messages)),  # Slack limits to 200 per request
                    cursor=cursor
                )
                
                messages.extend(response["messages"])
                
                if not response.get("has_more", False):
                    break
                
                cursor = response.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            
            logger.info(f"Fetched {len(messages)} messages from channel {channel_id}")
            return messages[:limit]  # Ensure we don't exceed limit
            
        except SlackApiError as e:
            logger.error(f"Error fetching channel history: {e}")
            raise
    
    def get_thread_replies(self, channel_id: str, thread_ts: str) -> List[Dict]:
        """
        Fetch all replies in a thread
        
        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp
            
        Returns:
            List of reply messages
        """
        try:
            response = self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts
            )
            return response["messages"][1:]  # Exclude the parent message
        except SlackApiError as e:
            logger.error(f"Error fetching thread replies: {e}")
            return []
    
    def analyze_conversations(self, messages: List[Dict]) -> Dict:
        """
        Analyze Slack conversations for insights
        
        Args:
            messages: List of Slack message dictionaries
            
        Returns:
            Dictionary containing analysis results
        """
        df = pd.DataFrame(messages)
        
        # Basic metrics
        total_messages = len(df)
        unique_users = df['user'].nunique() if 'user' in df.columns else 0
        
        # Thread analysis
        thread_count = df['thread_ts'].notna().sum() if 'thread_ts' in df.columns else 0
        
        # Time-based analysis
        if 'ts' in df.columns:
            df['timestamp'] = pd.to_datetime(df['ts'].astype(float), unit='s')
            df['hour'] = df['timestamp'].dt.hour
            df['day_of_week'] = df['timestamp'].dt.day_name()
            
            # Peak activity times
            peak_hour = df['hour'].mode().iloc[0] if not df.empty else None
            peak_day = df['day_of_week'].mode().iloc[0] if not df.empty else None
        else:
            peak_hour = None
            peak_day = None
        
        # Sentiment analysis
        sentiments = []
        if 'text' in df.columns:
            for text in df['text'].dropna():
                try:
                    blob = TextBlob(str(text))
                    sentiments.append(blob.sentiment.polarity)
                except:
                    continue
        
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
        
        # Reaction analysis
        total_reactions = 0
        if 'reactions' in df.columns:
            for reactions in df['reactions'].dropna():
                if isinstance(reactions, list):
                    total_reactions += sum(r.get('count', 0) for r in reactions)
        
        # User engagement
        user_message_counts = df['user'].value_counts() if 'user' in df.columns else pd.Series()
        top_contributors = user_message_counts.head(5).to_dict()
        
        return {
            "total_messages": total_messages,
            "unique_users": unique_users,
            "thread_count": thread_count,
            "avg_sentiment": round(avg_sentiment, 3),
            "total_reactions": total_reactions,
            "peak_hour": peak_hour,
            "peak_day": peak_day,
            "top_contributors": top_contributors,
            "messages_per_user": round(total_messages / unique_users, 2) if unique_users > 0 else 0
        }
    
    def get_channel_info(self, channel_id: str) -> Dict:
        """
        Get information about a Slack channel
        
        Args:
            channel_id: Slack channel ID
            
        Returns:
            Channel information dictionary
        """
        try:
            response = self.client.conversations_info(channel=channel_id)
            return response["channel"]
        except SlackApiError as e:
            logger.error(f"Error fetching channel info: {e}")
            raise
    
    def generate_channel_report(
        self, 
        channel_id: str,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> Dict:
        """
        Generate a comprehensive report for a Slack channel
        
        Args:
            channel_id: Slack channel ID
            start_date: Start datetime for analysis
            end_date: End datetime for analysis
            
        Returns:
            Dictionary containing the full report
        """
        # Get channel info
        channel_info = self.get_channel_info(channel_id)
        channel_name = channel_info.get("name", "unknown")
        
        # Fetch messages
        messages = self.get_channel_history(channel_id, start_date, end_date)
        
        # Analyze conversations
        analysis = self.analyze_conversations(messages)
        
        # Extract key topics (simplified keyword extraction)
        all_text = " ".join([msg.get("text", "") for msg in messages])
        words = all_text.lower().split()
        
        # Filter common words
        stop_words = {"the", "and", "is", "in", "to", "a", "of", "for", "on", "with", "as", "it"}
        filtered_words = [w for w in words if len(w) > 3 and w not in stop_words]
        
        # Get top keywords
        word_freq = pd.Series(filtered_words).value_counts()
        top_keywords = word_freq.head(10).to_dict()
        
        # Build report
        report = {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "period": {
                "start": start_date.isoformat() if start_date else "N/A",
                "end": end_date.isoformat() if end_date else "N/A"
            },
            "metrics": analysis,
            "top_keywords": top_keywords,
            "channel_info": {
                "topic": channel_info.get("topic", {}).get("value", ""),
                "purpose": channel_info.get("purpose", {}).get("value", ""),
                "member_count": channel_info.get("num_members", 0)
            }
        }
        
        return report
    
    def format_report_for_slack(self, report: Dict) -> str:
        """
        Format a report dictionary into a Slack-friendly message
        
        Args:
            report: Report dictionary from generate_channel_report
            
        Returns:
            Formatted string for Slack posting
        """
        metrics = report["metrics"]
        
        message = f"""
*Channel Activity Report: #{report['channel_name']}*
_Period: {report['period']['start']} to {report['period']['end']}_

📊 *Key Metrics:*
• Total Messages: {metrics['total_messages']}
• Active Users: {metrics['unique_users']}
• Threads Created: {metrics['thread_count']}
• Total Reactions: {metrics['total_reactions']}
• Avg Messages/User: {metrics['messages_per_user']}

😊 *Sentiment Analysis:*
• Average Sentiment: {'Positive' if metrics['avg_sentiment'] > 0.1 else 'Negative' if metrics['avg_sentiment'] < -0.1 else 'Neutral'} ({metrics['avg_sentiment']})

⏰ *Activity Patterns:*
• Peak Hour: {metrics['peak_hour']}:00 if available
• Peak Day: {metrics['peak_day']}

💬 *Top Keywords:*
{chr(10).join(f"• {word}: {count}" for word, count in list(report['top_keywords'].items())[:5])}

👥 *Top Contributors:*
{chr(10).join(f"• <@{user}>: {count} messages" for user, count in list(metrics['top_contributors'].items())[:3])}
"""
        
        return message.strip()

# Example usage function
def scrape_and_report(channel_id: str, hours_back: int = 24) -> str:
    """
    Convenience function to scrape a channel and generate a report
    
    Args:
        channel_id: Slack channel ID
        hours_back: Number of hours to look back
        
    Returns:
        Formatted report string
    """
    scraper = SlackScraper()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=hours_back)
    
    report = scraper.generate_channel_report(channel_id, start_date, end_date)
    formatted_report = scraper.format_report_for_slack(report)
    
    return formatted_report 