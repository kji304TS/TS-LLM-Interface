"""
Comprehensive End-of-Shift Report Generator
Combines Intercom conversation data with bug tracking and trend analysis
"""

import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import pandas as pd
from collections import Counter
import json
import logging

from utils.slack_notifier import send_slack_report
from utils.storage_handler import storage

logger = logging.getLogger(__name__)

class ShiftReportGenerator:
    def __init__(self):
        self.bug_pattern = re.compile(r'MMBUGS-(\d+)', re.IGNORECASE)
        
    def extract_bug_tickets(self, conversation_data: Dict) -> List[str]:
        """
        Extract bug ticket IDs from conversation links
        
        Args:
            conversation_data: Intercom conversation dictionary
            
        Returns:
            List of bug ticket IDs (e.g., ['MMBUGS-123', 'MMBUGS-456'])
        """
        bug_tickets = []
        
        # Check conversation parts for links
        if 'conversation_parts' in conversation_data:
            parts = conversation_data.get('conversation_parts', {}).get('conversation_parts', [])
            for part in parts:
                # Check body for bug references
                body = part.get('body', '')
                bug_tickets.extend(self.bug_pattern.findall(str(body)))
                
                # Check for links in custom attributes or attachments
                # (Intercom structure may vary, adjust as needed)
                
        # Also check custom attributes for tracker tickets
        custom_attrs = conversation_data.get('custom_attributes', {})
        for key, value in custom_attrs.items():
            if 'tracker' in key.lower() or 'bug' in key.lower():
                if isinstance(value, str):
                    bug_tickets.extend(self.bug_pattern.findall(value))
                    
        # Return unique bug tickets with full ID
        return [f"MMBUGS-{ticket}" for ticket in set(bug_tickets)]
    
    def analyze_case_types(self, conversations: List[Dict]) -> Dict:
        """
        Analyze and categorize case types from conversations
        
        Returns dictionary with:
        - top_issues: Most frequent issues with counts
        - categories: Breakdown by category
        - bug_tickets: Most referenced bug tickets
        """
        issue_counter = Counter()
        category_counter = Counter()
        bug_counter = Counter()
        
        for conv in conversations:
            attrs = conv.get('custom_attributes', {})
            
            # Count product areas
            product_area = attrs.get('MetaMask area', 'Unknown')
            if product_area and product_area != 'Unknown':
                category_counter[product_area] += 1
            
            # Count specific issues based on various fields
            # This is flexible to handle different issue categorizations
            issue_fields = [
                'MM Card Issue', 'Bridge Issue', 'Swaps issue', 
                'Wallet issue', 'scam vector', 'Funds missing',
                'Snaps Category', 'Buy issue', 'Sell issue'
            ]
            
            for field in issue_fields:
                if field in attrs and attrs[field]:
                    issue_value = attrs[field]
                    if isinstance(issue_value, list):
                        issue_value = issue_value[0] if issue_value else None
                    if issue_value and issue_value not in ['None', 'N/A', '']:
                        issue_counter[f"{field}: {issue_value}"] += 1
            
            # Extract bug tickets
            bug_tickets = self.extract_bug_tickets(conv)
            for bug in bug_tickets:
                bug_counter[bug] += 1
        
        return {
            'top_issues': dict(issue_counter.most_common(10)),
            'categories': dict(category_counter),
            'bug_tickets': dict(bug_counter.most_common(5))
        }
    
    def identify_trends(self, current_data: Dict, previous_data: Dict = None) -> Dict:
        """
        Identify trends by comparing current shift data with previous shift
        
        Returns dictionary with:
        - volume_change: Percentage change in conversation volume
        - emerging_issues: New issues that appeared
        - resolved_issues: Issues that disappeared
        - trending_up: Issues increasing in frequency
        - trending_down: Issues decreasing in frequency
        """
        if not previous_data:
            return {
                'volume_change': 0,
                'emerging_issues': [],
                'resolved_issues': [],
                'trending_up': [],
                'trending_down': [],
                'no_comparison': True
            }
        
        current_issues = current_data.get('top_issues', {})
        previous_issues = previous_data.get('top_issues', {})
        
        # Calculate volume change
        current_volume = sum(current_issues.values())
        previous_volume = sum(previous_issues.values())
        volume_change = ((current_volume - previous_volume) / previous_volume * 100) if previous_volume > 0 else 0
        
        # Find emerging and resolved issues
        current_keys = set(current_issues.keys())
        previous_keys = set(previous_issues.keys())
        
        emerging = current_keys - previous_keys
        resolved = previous_keys - current_keys
        
        # Find trending issues
        trending_up = []
        trending_down = []
        
        for issue in current_keys & previous_keys:  # Issues in both periods
            current_count = current_issues[issue]
            previous_count = previous_issues[issue]
            change_pct = ((current_count - previous_count) / previous_count * 100) if previous_count > 0 else 0
            
            if change_pct > 20:  # More than 20% increase
                trending_up.append({
                    'issue': issue,
                    'current': current_count,
                    'previous': previous_count,
                    'change_pct': round(change_pct, 1)
                })
            elif change_pct < -20:  # More than 20% decrease
                trending_down.append({
                    'issue': issue,
                    'current': current_count,
                    'previous': previous_count,
                    'change_pct': round(change_pct, 1)
                })
        
        # Sort by change percentage
        trending_up.sort(key=lambda x: x['change_pct'], reverse=True)
        trending_down.sort(key=lambda x: x['change_pct'])
        
        return {
            'volume_change': round(volume_change, 1),
            'emerging_issues': list(emerging)[:5],  # Top 5 new issues
            'resolved_issues': list(resolved)[:5],  # Top 5 resolved
            'trending_up': trending_up[:5],  # Top 5 trending up
            'trending_down': trending_down[:5],  # Top 5 trending down
            'no_comparison': False
        }
    
    def extract_learnings(self, conversations: List[Dict], analysis: Dict) -> List[str]:
        """
        Extract quick wins and learnings from shift data
        
        This is a simplified version - could be enhanced with ML/NLP
        """
        learnings = []
        
        # Learning from bug patterns
        if analysis.get('bug_tickets'):
            top_bug = list(analysis['bug_tickets'].keys())[0]
            count = analysis['bug_tickets'][top_bug]
            learnings.append(f"🐛 {top_bug} was reported {count} times - may need priority attention")
        
        # Learning from category distribution
        categories = analysis.get('categories', {})
        if categories:
            total = sum(categories.values())
            top_category = max(categories, key=categories.get)
            pct = (categories[top_category] / total * 100) if total > 0 else 0
            learnings.append(f"📊 {round(pct, 1)}% of issues were in {top_category} - consider focused support")
        
        # Learning from issue resolution (if we track resolution times)
        # This would require additional data tracking
        
        return learnings[:3]  # Return top 3 learnings
    
    def generate_shift_report(
        self, 
        conversations: List[Dict],
        shift_start: datetime,
        shift_end: datetime,
        previous_report_path: Optional[str] = None
    ) -> Tuple[Dict, str]:
        """
        Generate comprehensive end-of-shift report
        
        Returns:
            Tuple of (report_data_dict, formatted_slack_message)
        """
        # Analyze current shift
        current_analysis = self.analyze_case_types(conversations)
        
        # Load previous report for comparison
        previous_data = None
        if previous_report_path:
            try:
                previous_json = storage.read_file(previous_report_path)
                previous_data = json.loads(previous_json)
                previous_analysis = previous_data.get('analysis', {})
            except Exception as e:
                logger.warning(f"Could not load previous report: {e}")
                previous_analysis = None
        else:
            previous_analysis = None
        
        # Identify trends
        trends = self.identify_trends(current_analysis, previous_analysis)
        
        # Extract learnings
        learnings = self.extract_learnings(conversations, current_analysis)
        
        # Build report data
        report_data = {
            'shift_period': {
                'start': shift_start.isoformat(),
                'end': shift_end.isoformat()
            },
            'total_conversations': len(conversations),
            'analysis': current_analysis,
            'trends': trends,
            'learnings': learnings,
            'generated_at': datetime.now().isoformat()
        }
        
        # Format for Slack
        slack_message = self.format_slack_report(report_data)
        
        return report_data, slack_message
    
    def format_slack_report(self, report_data: Dict) -> str:
        """
        Format report data into a beautiful Slack message
        """
        analysis = report_data['analysis']
        trends = report_data['trends']
        learnings = report_data['learnings']
        
        # Header
        shift_start = datetime.fromisoformat(report_data['shift_period']['start'])
        shift_end = datetime.fromisoformat(report_data['shift_period']['end'])
        
        message = f"""
🌟 *End of Shift Report*
📅 _{shift_start.strftime('%B %d, %Y %I:%M %p')} - {shift_end.strftime('%I:%M %p')}_
📊 *Total Conversations: {report_data['total_conversations']}*

"""
        
        # Question 1: Recurrent case types and biggest issues
        message += "❓ *What were today's recurrent case types or biggest issues?*\n"
        
        top_issues = analysis.get('top_issues', {})
        if top_issues:
            for i, (issue, count) in enumerate(list(top_issues.items())[:5], 1):
                message += f"   {i}. {issue}: *{count}* cases\n"
        else:
            message += "   _No specific issues tracked_\n"
        
        # Bug tickets section
        bug_tickets = analysis.get('bug_tickets', {})
        if bug_tickets:
            message += "\n🐛 *Most Reported Bugs:*\n"
            for bug, count in bug_tickets.items():
                message += f"   • {bug}: *{count}* reports\n"
        
        message += "\n"
        
        # Question 2: Trends
        message += "📈 *Were there any trends experienced?*\n"
        
        if trends.get('no_comparison'):
            message += "   _No previous shift data for comparison_\n"
        else:
            # Volume trend
            volume_change = trends['volume_change']
            if volume_change > 0:
                message += f"   📈 Volume increased by *{volume_change}%* from previous shift\n"
            elif volume_change < 0:
                message += f"   📉 Volume decreased by *{abs(volume_change)}%* from previous shift\n"
            else:
                message += f"   ➡️ Volume remained stable\n"
            
            # Emerging issues
            if trends['emerging_issues']:
                message += "\n   🆕 *New Issues:*\n"
                for issue in trends['emerging_issues']:
                    message += f"      • {issue}\n"
            
            # Trending up
            if trends['trending_up']:
                message += "\n   ⬆️ *Increasing:*\n"
                for item in trends['trending_up'][:3]:
                    message += f"      • {item['issue']} (+{item['change_pct']}%)\n"
            
            # Trending down
            if trends['trending_down']:
                message += "\n   ⬇️ *Decreasing:*\n"
                for item in trends['trending_down'][:3]:
                    message += f"      • {item['issue']} ({item['change_pct']}%)\n"
        
        message += "\n"
        
        # Question 3: Quick wins and learnings
        message += "💡 *What's a quick win or learning from today?*\n"
        
        if learnings:
            for learning in learnings:
                message += f"   • {learning}\n"
        else:
            message += "   _Analysis in progress_\n"
        
        # Footer with actionable items
        message += "\n---\n"
        message += "_💬 Reply in thread with any additional context or follow-up actions_"
        
        return message.strip()
    
    def save_report(self, report_data: Dict, team_name: str) -> str:
        """
        Save report data to storage for future comparison
        
        Returns:
            Path to saved report
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"shift_reports/{team_name}_{timestamp}.json"
        
        storage.save_file(
            json.dumps(report_data, indent=2),
            filename
        )
        
        return filename
    
    def get_previous_report_path(self, team_name: str) -> Optional[str]:
        """
        Find the most recent previous report for comparison
        
        Returns:
            Path to previous report or None
        """
        try:
            # List all reports for this team
            all_files = storage.list_files(f"shift_reports/{team_name}_")
            
            if not all_files:
                return None
            
            # Sort by filename (which includes timestamp)
            all_files.sort(reverse=True)
            
            # Return the most recent (first after sort)
            return all_files[0] if all_files else None
            
        except Exception as e:
            logger.warning(f"Could not find previous report: {e}")
            return None

# Global instance
shift_reporter = ShiftReportGenerator() 