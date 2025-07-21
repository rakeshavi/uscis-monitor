# USCIS Application Monitor Setup

This guide will help you set up automated monitoring of your USCIS applications on a Raspberry Pi.

## Prerequisites

- Raspberry Pi with Python 3.7+
- Access to Home Assistant
- USCIS account with cases to monitor

## Installation

1. **Install required packages:**
```bash
pip3 install requests pyyaml
```

2. **Download the monitor script:**
Save the Python script as `uscis_monitor.py` and make it executable:
```bash
chmod +x uscis_monitor.py
```

3. **Create initial configuration:**
Run the script once to generate a sample config:
```bash
python3 uscis_monitor.py
```

## Configuration

### 1. Edit config.yaml

The script will create a `config.yaml` file. Edit it with your details:

```yaml
cases:
  - receipt_number: 'IOE0929584536'
    description: 'I-485 Application - John Doe'
  - receipt_number: 'IOE1234567890'
    description: 'I-765 Work Authorization - Jane Doe'

check_interval_hours: 6

uscis_api_base: 'https://my.uscis.gov/account/case-service/api/cases/'

browser_cookies_file: 'uscis_cookies.txt'

home_assistant:
  url: 'http://homeassistant.local:8123'
  token: 'your_long_lived_access_token_here'
  notify_service: 'notify.mobile_app_your_device'

state_file: 'uscis_state.json'
log_file: 'uscis_monitor.log'
log_level: 'INFO'
```

### 2. Export Browser Cookies

Since the USCIS API requires authentication, you need to export cookies from your browser:

#### Option A: Using Browser Extension (Recommended)
1. Install a cookie export extension like "Get cookies.txt LOCALLY"
2. Login to https://my.uscis.gov
3. Navigate to your case status page
4. Export cookies in Netscape format
5. Save as `uscis_cookies.txt` in the same directory

#### Option B: Manual Cookie Extraction
1. Login to https://my.uscis.gov
2. Open Developer Tools (F12)
3. Go to Application/Storage → Cookies
4. Copy relevant cookies to `uscis_cookies.txt` in Netscape format:
```
# Netscape HTTP Cookie File
my.uscis.gov	FALSE	/	TRUE	1234567890	session_cookie	cookie_value
my.uscis.gov	FALSE	/	FALSE	1234567890	csrf_token	token_value
```

### 3. Setup Home Assistant Integration

#### Create Long-Lived Access Token:
1. Go to Home Assistant → Profile → Long-Lived Access Tokens
2. Click "Create Token"
3. Name it "USCIS Monitor"
4. Copy the token to your config.yaml

#### Find Your Notification Service:
1. Go to Developer Tools → Services
2. Look for `notify.mobile_app_yourphone` or similar
3. Update the `notify_service` in config.yaml

## Usage

### Run Once (Testing)
```bash
python3 uscis_monitor.py --once
```

### Run Continuously
```bash
python3 uscis_monitor.py
```

### Run with Custom Config
```bash
python3 uscis_monitor.py --config /path/to/custom_config.yaml
```

## Setting Up as a Service

### Create systemd service (recommended):

1. **Create service file:**
```bash
sudo nano /etc/systemd/system/uscis-monitor.service
```

2. **Add service configuration:**
```ini
[Unit]
Description=USCIS Application Monitor
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/uscis-monitor
ExecStart=/usr/bin/python3 /home/pi/uscis-monitor/uscis_monitor.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

3. **Enable and start service:**
```bash
sudo systemctl enable uscis-monitor.service
sudo systemctl start uscis-monitor.service
```

4. **Check service status:**
```bash
sudo systemctl status uscis-monitor.service
```

## Monitoring and Troubleshooting

### View Logs
```bash
# Service logs
sudo journalctl -u uscis-monitor.service -f

# Application logs
tail -f uscis_monitor.log
```

### Common Issues

1. **Authentication Errors:**
   - Cookies may have expired
   - Re-export cookies from browser
   - Ensure you're logged into USCIS portal

2. **Network Errors:**
   - Check internet connectivity
   - Verify USCIS site is accessible
   - Check if API endpoint has changed

3. **Home Assistant Notifications Not Working:**
   - Verify HA URL and token
   - Check notification service name
   - Test notification manually in HA

### Manual Testing

Test individual components:

```bash
# Test configuration loading
python3 -c "from uscis_monitor import USCISMonitor; m = USCISMonitor(); print('Config loaded')"

# Test Home Assistant notification
python3 -c "from uscis_monitor import USCISMonitor; m = USCISMonitor(); m.send_notification('Test', 'Hello from USCIS Monitor')"
```

## Security Considerations

- Store sensitive files in a secure location
- Regularly rotate Home Assistant tokens
- Monitor for unauthorized access to your USCIS account
- Keep cookies file permissions restricted: `chmod 600 uscis_cookies.txt`

## File Structure

```
uscis-monitor/
├── uscis_monitor.py       # Main script
├── config.yaml            # Configuration file
├── uscis_cookies.txt       # Browser cookies (sensitive)
├── uscis_state.json        # Previous states (auto-generated)
└── uscis_monitor.log       # Log file (auto-generated)
```

## What Gets Monitored

The monitor detects changes in:
- Case update timestamps
- New events (with event codes and dates)
- Evidence requests
- Notices and appointments
- Any other significant case data changes

## Customization

You can modify the `filter_relevant_data()` method to focus on specific fields or add custom change detection logic in the `detect_changes()` method.