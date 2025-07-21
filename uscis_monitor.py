#!/usr/bin/env python3
"""
USCIS Application Monitor
Monitors USCIS case status changes and sends notifications via Home Assistant
"""

import json
import time
import hashlib
import requests
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import yaml

class USCISMonitor:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self.load_config()
        self.setup_logging()
        self.state_file = Path(self.config.get('state_file', 'uscis_state.json'))
        self.previous_states = self.load_previous_states()
        
    def load_config(self) -> dict:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self.create_sample_config()
            raise FileNotFoundError(f"Config file {self.config_path} not found. Sample created.")
    
    def create_sample_config(self):
        """Create a sample configuration file"""
        sample_config = {
            'cases': [
                {
                    'receipt_number': 'IOE0929584536',
                    'description': 'I-485 Application - John Doe'
                }
            ],
            'check_interval_hours': 6,
            'uscis_api_base': 'https://my.uscis.gov/account/case-service/api/cases/',
            'browser_cookies_file': 'uscis_cookies.txt',  # Path to exported cookies
            'home_assistant': {
                'url': 'http://homeassistant.local:8123',
                'token': 'your_long_lived_access_token_here',
                'notify_service': 'notify.mobile_app_your_device'
            },
            'state_file': 'uscis_state.json',
            'log_file': 'uscis_monitor.log',
            'log_level': 'INFO'
        }
        
        with open(self.config_path, 'w') as f:
            yaml.dump(sample_config, f, default_flow_style=False, indent=2)
        
        print(f"Sample configuration created at {self.config_path}")
        print("Please edit the configuration file with your actual values.")
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_level = getattr(logging, self.config.get('log_level', 'INFO'))
        log_file = self.config.get('log_file', 'uscis_monitor.log')
        
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_cookies_from_file(self) -> dict:
        """Load cookies from Netscape format cookie file"""
        cookies = {}
        cookie_file = self.config.get('browser_cookies_file', 'uscis_cookies.txt')
        
        try:
            with open(cookie_file, 'r') as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    
                    parts = line.strip().split('\t')
                    if len(parts) >= 7:
                        domain, _, path, secure, expires, name, value = parts[:7]
                        cookies[name] = value
                        
        except FileNotFoundError:
            self.logger.error(f"Cookie file {cookie_file} not found.")
            self.logger.info("Please export cookies from your browser:")
            self.logger.info("1. Login to my.uscis.gov in your browser")
            self.logger.info("2. Install a cookie export extension")
            self.logger.info("3. Export cookies in Netscape format")
            self.logger.info(f"4. Save as {cookie_file}")
            
        return cookies
    
    def load_previous_states(self) -> dict:
        """Load previous case states from file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        return {}
    
    def save_states(self, states: dict):
        """Save current states to file"""
        with open(self.state_file, 'w') as f:
            json.dump(states, f, indent=2, default=str)
    
    def get_case_data(self, receipt_number: str) -> Optional[dict]:
        """Fetch case data from USCIS API"""
        url = f"{self.config['uscis_api_base']}{receipt_number}"
        cookies = self.load_cookies_from_file()
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://my.uscis.gov/',
            'Accept': 'application/json, text/plain, */*'
        }
        
        try:
            response = requests.get(url, cookies=cookies, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching data for {receipt_number}: {e}")
            return None
    
    def calculate_hash(self, data: dict) -> str:
        """Calculate hash of relevant case data"""
        # Remove timestamp fields that change frequently but aren't meaningful
        filtered_data = self.filter_relevant_data(data)
        return hashlib.md5(json.dumps(filtered_data, sort_keys=True).encode()).hexdigest()
    
    def filter_relevant_data(self, data: dict) -> dict:
        """Filter out fields that change frequently but aren't status changes"""
        if 'data' not in data:
            return data
            
        case_data = data['data'].copy()
        
        # Remove fields that update frequently but don't indicate status changes
        fields_to_remove = ['updatedAtTimestamp', 'createdAtTimestamp']
        
        for field in fields_to_remove:
            case_data.pop(field, None)
            
        # For events, only keep the meaningful data
        if 'events' in case_data:
            filtered_events = []
            for event in case_data['events']:
                filtered_event = {k: v for k, v in event.items() 
                                if k not in ['createdAtTimestamp', 'updatedAtTimestamp']}
                filtered_events.append(filtered_event)
            case_data['events'] = filtered_events
            
        return {'data': case_data}
    
    def detect_changes(self, receipt_number: str, current_data: dict) -> List[str]:
        """Detect what changed between current and previous data"""
        changes = []
        
        if receipt_number not in self.previous_states:
            changes.append("Initial monitoring setup")
            return changes
        
        prev_data = self.previous_states[receipt_number]['data']
        curr_data = current_data['data']
        
        # Check for status changes in main application
        if prev_data.get('updatedAt') != curr_data.get('updatedAt'):
            changes.append(f"Case updated: {curr_data.get('updatedAt')}")
        
        # Check for new events
        prev_events = prev_data.get('events', [])
        curr_events = curr_data.get('events', [])
        
        if len(curr_events) > len(prev_events):
            new_events = len(curr_events) - len(prev_events)
            changes.append(f"{new_events} new event(s) added")
            
            # Detail the latest events
            for event in curr_events[:new_events]:
                event_code = event.get('eventCode', 'Unknown')
                event_date = event.get('eventDateTime', 'Unknown date')
                changes.append(f"New event: {event_code} on {event_date}")
        
        # Check for evidence request changes
        prev_evidence = len(prev_data.get('evidenceRequests', []))
        curr_evidence = len(curr_data.get('evidenceRequests', []))
        
        if curr_evidence > prev_evidence:
            changes.append("New evidence request received")
        
        # Check for notice changes
        prev_notices = len(prev_data.get('notices', []))
        curr_notices = len(curr_data.get('notices', []))
        
        if curr_notices > prev_notices:
            changes.append("New notice received")
        
        return changes
    
    def send_notification(self, title: str, message: str):
        """Send notification via Home Assistant"""
        ha_config = self.config.get('home_assistant', {})
        
        if not ha_config:
            self.logger.warning("Home Assistant not configured, skipping notification")
            return
        
        url = f"{ha_config['url']}/api/services/notify/{ha_config['notify_service'].split('.')[1]}"
        
        headers = {
            'Authorization': f"Bearer {ha_config['token']}",
            'Content-Type': 'application/json'
        }
        
        payload = {
            'title': title,
            'message': message
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            self.logger.info("Notification sent successfully")
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to send notification: {e}")
    
    def check_cases(self):
        """Check all configured cases for changes"""
        current_states = {}
        
        for case in self.config['cases']:
            receipt_number = case['receipt_number']
            description = case.get('description', receipt_number)
            
            self.logger.info(f"Checking case: {receipt_number}")
            
            current_data = self.get_case_data(receipt_number)
            if not current_data:
                self.logger.error(f"Failed to fetch data for {receipt_number}")
                continue
            
            current_hash = self.calculate_hash(current_data)
            previous_hash = self.previous_states.get(receipt_number, {}).get('hash')
            
            current_states[receipt_number] = {
                'hash': current_hash,
                'data': current_data,
                'last_checked': datetime.now().isoformat(),
                'description': description
            }
            
            if current_hash != previous_hash:
                changes = self.detect_changes(receipt_number, current_data)
                
                if changes:
                    self.logger.info(f"Changes detected for {receipt_number}: {changes}")
                    
                    title = f"USCIS Case Update: {description}"
                    message = f"Case {receipt_number} has been updated:\n" + "\n".join(f"• {change}" for change in changes)
                    
                    self.send_notification(title, message)
                else:
                    self.logger.info(f"Hash changed but no significant changes detected for {receipt_number}")
            else:
                self.logger.info(f"No changes for {receipt_number}")
        
        # Save current states
        self.save_states(current_states)
        self.previous_states = current_states
    
    def run_once(self):
        """Run a single check cycle"""
        self.logger.info("Starting USCIS case check")
        self.check_cases()
        self.logger.info("USCIS case check completed")
    
    def run_continuously(self):
        """Run monitoring continuously"""
        interval_hours = self.config.get('check_interval_hours', 6)
        interval_seconds = interval_hours * 3600
        
        self.logger.info(f"Starting USCIS monitor with {interval_hours} hour intervals")
        
        while True:
            try:
                self.run_once()
                self.logger.info(f"Next check in {interval_hours} hours")
                time.sleep(interval_seconds)
                
            except KeyboardInterrupt:
                self.logger.info("Monitor stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                self.logger.info(f"Retrying in {interval_hours} hours")
                time.sleep(interval_seconds)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='USCIS Application Monitor')
    parser.add_argument('--config', default='config.yaml', help='Configuration file path')
    parser.add_argument('--once', action='store_true', help='Run once instead of continuously')
    
    args = parser.parse_args()
    
    try:
        monitor = USCISMonitor(args.config)
        
        if args.once:
            monitor.run_once()
        else:
            monitor.run_continuously()
            
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please edit the configuration file and try again.")
    except KeyboardInterrupt:
        print("\nMonitor stopped.")

if __name__ == "__main__":
    main()