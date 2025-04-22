import tkinter as tk
from tkinter import messagebox, ttk, filedialog
from tkinter.scrolledtext import ScrolledText
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.widgets import Entry, Button, Label, Frame, Checkbutton, Notebook
import threading
import random
import time
import os
import sys
import webbrowser
import json
import re
import requests
from datetime import datetime, timedelta
# === License System with Supabase ===
import os
import uuid
import socket
import hashlib
import base64
import json
import time
import threading
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

class LicenseSystem:
    def __init__(self):
        # Supabase credentials
        self.supabase_url = "https://xifdmmpexgiodpzvgifl.supabase.co"
        self.supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhpZmRtbXBleGdpb2RwenZnaWZsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyODQzOTUsImV4cCI6MjA2MDg2MDM5NX0.h2Z3Fosh0IEfLbSglCwoNeuKLutY0rph-Wuj9Q7IGCU"
        
        # Initialize Supabase client
        try:
            self.supabase = create_client(self.supabase_url, self.supabase_key)
            self.online_db_available = True
        except Exception as e:
            print(f"Failed to initialize Supabase: {str(e)}")
            self.online_db_available = False
            
        self.hardware_id = self.get_hardware_id()
        self.is_licensed = False
        self.license_info = {}
        
        # Initialize cache directory
        self.cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".license_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
    def get_hardware_id(self):
        """Generate a unique hardware ID based on machine details"""
        mac = uuid.getnode()
        hostname = socket.gethostname()
        cpu_id = self.get_cpu_id()
        
        # Combine hardware details and hash them
        combined = f"{mac}-{hostname}-{cpu_id}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def get_cpu_id(self):
        """Get CPU ID (simplified version)"""
        if os.name == 'nt':  # Windows
            try:
                import wmi
                c = wmi.WMI()
                for processor in c.Win32_Processor():
                    return processor.ProcessorId.strip()
            except:
                pass
        # Fallback to a portion of the uuid based on host ID
        return str(uuid.uuid1())[:8]
    
    def check_license(self, license_key):
        """Verify if the license is valid"""
        if not license_key:
            return False, "No license key provided"
        
        # Try online validation first
        if self.online_db_available:
            try:
                result, message, success = self.online_validation(license_key)
                if success:
                    return result, message
            except Exception as e:
                print(f"Online validation error: {str(e)}")
                # Fall back to offline validation
        
        # Try offline validation as fallback
        return self.offline_validation(license_key)
    
    def online_validation(self, license_key):
        """Perform online validation with Supabase database"""
        if not license_key:
            return False, "No license key provided", True
        
        try:
            # Fetch the license from Supabase
            response = self.supabase.table('licenses').select('*').eq('license_key', license_key).execute()
            
            # Check if license exists
            if not response.data:
                return False, "Invalid license key", True
                
            license_data = response.data[0]
            
            # Check if license is still active
            if not license_data.get('is_active', False):
                return False, "License has been revoked", True
                
            # Check if license has expired
            expires_at = license_data.get('expires_at')
            if expires_at:
                try:
                    # Parse with timezone awareness
                    exp_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    if now > exp_date:
                        return False, "License has expired", True
                except Exception as e:
                    print(f"Date parsing error: {str(e)}")
            
            # Check hardware binding if it exists
            hardware_id = license_data.get('hardware_id')
            if hardware_id and hardware_id != self.hardware_id:
                # License is bound to a different machine
                activation_count = license_data.get('activation_count', 0)
                max_activations = license_data.get('max_activations', 1) 
                if activation_count >= max_activations:
                    return False, "License already activated on another machine", True
            
            # Update license with hardware ID if not set and log activation
            try:
                if not hardware_id:
                    self.supabase.table('licenses').update({
                        'hardware_id': self.hardware_id, 
                        'activation_count': 1,
                        'last_checked': datetime.now(timezone.utc).isoformat()
                    }).eq('license_key', license_key).execute()
                else:
                    # Increment activation count if on different hardware
                    if hardware_id != self.hardware_id:
                        self.supabase.table('licenses').update({
                            'activation_count': activation_count + 1,
                            'last_checked': datetime.now(timezone.utc).isoformat()
                        }).eq('license_key', license_key).execute()
                    else:
                        # Just update last checked time
                        self.supabase.table('licenses').update({
                            'last_checked': datetime.now(timezone.utc).isoformat()
                        }).eq('license_key', license_key).execute()
                
                # Log this activation
                self.supabase.table('activations').insert({
                    'license_key': license_key,
                    'hardware_id': self.hardware_id,
                    'activation_time': datetime.now(timezone.utc).isoformat()
                }).execute()
            except Exception as e:
                print(f"Error updating license: {str(e)}")
            
            # Save license info for future reference
            self.license_info = {
                'key': license_data.get('license_key'),
                'name': license_data.get('name'),
                'email': license_data.get('email'),
                'expires_at': license_data.get('expires_at')
            }
            
            # Cache the license locally for offline usage
            self.cache_license(license_key, license_data)
            
            self.is_licensed = True
            return True, "License validated successfully", True
            
        except Exception as e:
            # Return false but indicate the online check failed so we can try offline
            return False, f"Online validation failed: {str(e)}", False
    
    def offline_validation(self, license_key):
        """Validate license using cached data when offline"""
        if not license_key:
            return False, "No license key provided"
            
        cached_license = self.get_cached_license(license_key)
        if not cached_license:
            return False, "License not found in cache"
        
        # Check if license is active in cache
        if not cached_license.get('is_active', False):
            return False, "Cached license has been revoked"
            
        # Check expiration
        expires_at = cached_license.get('expires_at')
        if expires_at:
            try:
                # Parse with timezone awareness
                exp_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                if now > exp_date:
                    return False, "Cached license has expired"
            except Exception as e:
                print(f"Cache date parsing error: {str(e)}")
        
        # Check hardware binding
        hw_id = cached_license.get('hardware_id')
        if hw_id and hw_id != self.hardware_id:
            return False, "License is bound to another machine"
        
        # Set the license info from cache
        self.license_info = {
            'key': cached_license.get('license_key'),
            'name': cached_license.get('name'),
            'email': cached_license.get('email'),
            'expires_at': cached_license.get('expires_at')
        }
        
        self.is_licensed = True
        return True, "License validated from cache"
    
    def cache_license(self, license_key, license_data):
        """Save license data to local cache"""
        if not license_key or not license_data:
            return
            
        cache_file = os.path.join(self.cache_dir, hashlib.md5(license_key.encode()).hexdigest() + ".json")
        
        try:
            with open(cache_file, "w") as f:
                # Create a cleaned version of the license data for caching
                cache_data = {
                    'license_key': license_data.get('license_key'),
                    'hardware_id': license_data.get('hardware_id'),
                    'name': license_data.get('name'),
                    'email': license_data.get('email'),
                    'expires_at': license_data.get('expires_at'),
                    'is_active': license_data.get('is_active', True),
                    'cached_at': datetime.now(timezone.utc).isoformat(),
                    'max_activations': license_data.get('max_activations', 1)
                }
                json.dump(cache_data, f, indent=4)
        except Exception as e:
            print(f"Failed to cache license: {str(e)}")
    
    def get_cached_license(self, license_key):
        """Get license data from local cache"""
        if not license_key:
            return None
            
        cache_file = os.path.join(self.cache_dir, hashlib.md5(license_key.encode()).hexdigest() + ".json")
        
        if not os.path.exists(cache_file):
            return None
            
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except:
            return None
    
    def save_license_to_config(self, license_key):
        """Save the license key to config file"""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "license_config.json")
        
        # Simple encryption of the license key
        encoded_key = base64.b64encode(license_key.encode()).decode()
        
        config = {
            "license": encoded_key,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)
    
    def load_license_from_config(self):
        """Load license key from config if available"""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "license_config.json")
        
        if not os.path.exists(config_path):
            return None
            
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                
            encoded_key = config.get("license", "")
            license_key = base64.b64decode(encoded_key).decode()
            return license_key
        except:
            return None
    
    def activate_license(self, license_key):
        """Activate the license and save it"""
        is_valid, message = self.check_license(license_key)
        
        if is_valid:
            self.is_licensed = True
            self.save_license_to_config(license_key)
        
        return is_valid, message
    
    def validate_license_format(self, license_key):
        """Check if the license key format is valid"""
        # License format: XXXX-XXXX-XXXX-XXXX or XXXXXXXXXXXXXXXX
        license_key = license_key.strip()
        
        # Remove any hyphens
        clean_key = license_key.replace("-", "")
        
        # Check if it's 16 characters and alphanumeric
        if len(clean_key) != 16 or not clean_key.isalnum():
            return False
            
        return True
    
    def start_stronger_periodic_check(self, callback=None, check_interval=300):
        """
        Start a more frequent periodic license check in the background
    
        Args:
            callback: Function to call when license becomes invalid
            check_interval: Time in seconds between checks (default 5 minutes)
        """
        def check_thread():
            while True:
                # Sleep for the specified interval
                time.sleep(check_interval)
            
                # Only check if we're licensed
                if not self.is_licensed:
                        continue
                
                # Get current license key
                license_key = self.license_info.get('key')
                if not license_key:
                    continue
                
                print(f"[LICENSE] Performing periodic license validation check")
            
                # Always try online validation first
                try:
                    # Do a fresh check directly against the database
                    response = self.supabase.table('licenses').select('*').eq('license_key', license_key).execute()
                
                    if not response.data:
                        # License has been completely removed
                        self.is_licensed = False
                        print("[LICENSE] License no longer exists in database")
                        if callback:
                            callback("License has been revoked")
                        continue
                    
                    license_data = response.data[0]
                
                    # Check if license is still active
                    if not license_data.get('is_active', False):
                        self.is_licensed = False
                        print("[LICENSE] License has been revoked")
                    
                        # Also update the cache to reflect the revoked status
                        cached_license = self.get_cached_license(license_key)
                        if cached_license:
                            cached_license['is_active'] = False
                            self.cache_license(license_key, cached_license)
                    
                        if callback:
                            callback("License has been revoked")
                        continue
                
                    # Check if license has expired
                    expires_at = license_data.get('expires_at')
                    if expires_at:
                        try:
                            exp_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                            now = datetime.now(timezone.utc)
                            if now > exp_date:
                                self.is_licensed = False
                                print("[LICENSE] License has expired")
                                if callback:
                                    callback("License has expired")
                                continue
                        except Exception as e:
                            print(f"[LICENSE] Error parsing date: {str(e)}")
                
                    # License is still valid, update last checked time
                    try:
                        self.supabase.table('licenses').update({
                            'last_checked': datetime.now(timezone.utc).isoformat()
                        }).eq('license_key', license_key).execute()
                    
                        # Update the cached license data
                        self.cache_license(license_key, license_data)
                    except Exception as e:
                        print(f"[LICENSE] Error updating last check: {str(e)}")
                
                except Exception as e:
                    print(f"[LICENSE] Periodic check error: {str(e)}")
                    # If we can't reach the server, we'll just continue using the current license status
                    # Don't change self.is_licensed here as we don't know if the license is truly invalid
    
        # Start the thread
        threading.Thread(target=check_thread, daemon=True).start()

# Try to import selenium components, with fallback message
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# === Temporary Email Service Integration ===
class TempMailService:
    def __init__(self):
        self.session = requests.Session()
        self.current_email = None
        self.email_id = None
        self.domain = "1secmail.com"  # Using 1secmail API as it's free and doesn't require an API key
        
    def create_email(self):
        """Generate a new temporary email address"""
        username = self._generate_username()
        email = f"{username}@{self.domain}"
        self.current_email = email
        return email
    
    def _generate_username(self):
        """Generate a random username for the email"""
        letters = 'abcdefghijklmnopqrstuvwxyz'
        username = ''.join(random.choice(letters) for _ in range(10))
        return username
    
    def get_inbox(self, max_wait=60, check_interval=5):
        """Check inbox for new emails, with timeout"""
        if not self.current_email:
            return None
            
        username, domain = self.current_email.split('@')
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={username}&domain={domain}"
                response = self.session.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if data:  # If we have emails
                        return data
            except Exception as e:
                print(f"Error checking inbox: {str(e)}")
            
            time.sleep(check_interval)
        
        return None
    
    def get_message(self, message_id):
        """Get the content of a specific email"""
        if not self.current_email:
            return None
            
        username, domain = self.current_email.split('@')
        
        try:
            url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={username}&domain={domain}&id={message_id}"
            response = self.session.get(url)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error getting message: {str(e)}")
        
        return None
    
    def extract_confirmation_link(self, message_content):
        """Extract confirmation/verification links from email content"""
        # First try to extract from HTML body
        if 'htmlBody' in message_content and message_content['htmlBody']:
            # Look for href links that contain typical confirmation keywords
            html_body = message_content['htmlBody']
            urls = re.findall(r'href=[\'"]?([^\'" >]+)', html_body)
            
            # Filter for links that look like confirmation links
            confirm_keywords = ['confirm', 'verify', 'activate', 'validation', 'validate']
            for url in urls:
                if any(keyword in url.lower() for keyword in confirm_keywords):
                    return url
            
            # If no specific confirmation link found, try to find any link
            if urls:
                return urls[0]
        
        # Try to extract from text body as fallback
        if 'textBody' in message_content and message_content['textBody']:
            text_body = message_content['textBody']
            urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', text_body)
            if urls:
                return urls[0]
        
        return None

# Predefined list of common user agents
user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36", 
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.76",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0"
]

# === UI and Progress ===
class RefStormApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RefStorm")
        self.root.geometry("850x700")  # Slightly wider for better layout
        self.running = False
        self.paused = False  # New flag for pause/continue functionality
        self.theme_mode = "dark"

        # Initialize license system
        self.license_system = LicenseSystem()

        # Initialize log storage
        self.logs = []
    
        # Bot settings
        self.run_type = "count"  # "count" or "time"
        self.referral_urls = []  # List to store multiple referral URLs
        self.current_url_index = 0
    
        # Set app icon
        try:
            self.root.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "refstorm.ico"))
        except:
            pass  # Icon not found, continue without it
        
        # Initialize style with a custom theme
        self.style = tb.Style(theme="darkly")
        
        # Apply custom styles
        self.apply_custom_styles()
    
        # Create main container with padding
        self.container = Frame(self.root, padding=20)
        self.container.pack(fill="both", expand=True)
    
        # Create header with logo and theme toggle
        self.create_header()
    
        # Create logs tab first to avoid issues with add_log
        self.tabs = Notebook(self.container)
        self.tabs.pack(fill="both", expand=True, pady=(15, 0))
    
        # Create other tabs
        self.create_bot_tab()
        self.create_logs_tab()
        self.create_settings_tab()
        self.create_license_tab()
        self.create_about_tab()
        
        # Create status bar
        self.create_status_bar()
    
        # Check for saved license
        if self.check_saved_license():
            self.status_text.set("Licensed")
            # Start the periodic license check
            self.initialize_license_system()
        else:
            self.status_text.set("Unlicensed - Please activate")

    def apply_custom_styles(self):
        """Apply custom styling to make the UI more modern"""
        # Create custom button styles
        self.style.configure('primary.TButton', font=("Segoe UI", 10), borderwidth=0)
        self.style.configure('secondary.TButton', font=("Segoe UI", 10), borderwidth=0)
        self.style.configure('success.TButton', font=("Segoe UI", 10, "bold"), borderwidth=0)
        self.style.configure('danger.TButton', font=("Segoe UI", 10), borderwidth=0)
        
        # Create custom entry styles
        self.style.configure('TEntry', font=("Segoe UI", 10), padding=5)
        
        # Create custom label styles
        self.style.configure('header.TLabel', font=("Segoe UI", 22, "bold"))
        self.style.configure('subheader.TLabel', font=("Segoe UI", 14, "bold"))
        self.style.configure('normal.TLabel', font=("Segoe UI", 10))
        
        # Style for tab headers
        self.style.configure('TNotebook.Tab', padding=[12, 5], font=("Segoe UI", 10))
        
        # Custom frame styles
        self.style.configure('card.TFrame', borderwidth=1, relief='solid', padding=15)
        
    def create_header(self):
        header_frame = Frame(self.container, bootstyle="secondary")
        header_frame.pack(fill="x", pady=(0, 15))
        
        # Add a gradient background effect to the header
        header_bg = tk.Frame(header_frame, background="#1e0d30")
        header_bg.place(x=0, y=0, relwidth=1, relheight=1)
        
        # Create logo with improved styling
        logo_label = Label(header_frame, text="RefStorm", 
                          font=("Segoe UI", 24, "bold"), 
                          bootstyle="light")
        logo_label.pack(side="left", padx=15, pady=15)
        
        # Version label with improved styling
        version_label = Label(header_frame, text="v2.0", 
                             font=("Segoe UI", 12), 
                             bootstyle="light")
        version_label.pack(side="left", padx=(0, 15), pady=(15, 0))
        
        # Create a container for right-side controls
        right_controls = Frame(header_frame, bootstyle="secondary")
        right_controls.pack(side="right", padx=15, pady=10)
        
        # Theme toggle button with improved styling
        self.theme_btn = Button(right_controls, 
                              text="☀️", 
                              command=self.toggle_theme,
                              bootstyle="outline-light",
                              width=3)
        self.theme_btn.pack(side="right", padx=5)
        
        # Add a status indicator for license
        self.license_indicator = Label(right_controls,
                                    text="🔒 Licensed",
                                    font=("Segoe UI", 10),
                                    bootstyle="light")
        self.license_indicator.pack(side="right", padx=10)
        
        # Update the license indicator based on current status
        if not self.license_system.is_licensed:
            self.license_indicator.config(text="🔓 Unlicensed")
            
    def create_bot_tab(self):
        bot_frame = Frame(self.tabs, padding=20)
        self.tabs.add(bot_frame, text="🤖 Bot")
        
        # Create a 2-column layout
        left_column = Frame(bot_frame)
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        right_column = Frame(bot_frame)
        right_column.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        # === LEFT COLUMN: URL Management ===
        # Create a card-like container for URL management
        url_card = Frame(left_column, bootstyle="secondary", padding=15)
        url_card.pack(fill="x", expand=False, pady=(0, 15))
        
        # Card header
        Label(url_card, text="Referral URLs", 
             font=("Segoe UI", 16, "bold"),
             bootstyle="info").pack(anchor="w", pady=(0, 10))
        
        # URL entry with add button
        url_frame = Frame(url_card)
        url_frame.pack(fill="x", pady=10)
        
        self.url_entry = Entry(url_frame, font=("Segoe UI", 10), padding=8)
        self.url_entry.pack(side="left", fill="x", expand=True)
        
        add_url_btn = Button(url_frame, 
                           text="➕ Add URL", 
                           bootstyle="success",
                           command=self.add_referral_url)
        add_url_btn.pack(side="right", padx=(5, 0))
        
        # URL list display
        Label(url_card, text="Added URLs:", 
             font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 0))
        
        self.url_list_frame = Frame(url_card)
        self.url_list_frame.pack(fill="x", pady=5)
        
        self.url_list = ScrolledText(self.url_list_frame, 
                                    height=6, 
                                    wrap="word", 
                                    font=("Consolas", 10))
        self.url_list.pack(fill="x")
        self.url_list.config(state="disabled")
        
        # Clear URLs button with improved styling
        clear_urls_btn = Button(url_card,
                              text="🗑️ Clear All URLs",
                              bootstyle="danger",
                              command=self.clear_referral_urls)
        clear_urls_btn.pack(anchor="e", pady=(5, 0))
        
        # === LEFT COLUMN: Run Settings ===
        settings_card = Frame(left_column, bootstyle="secondary", padding=15)
        settings_card.pack(fill="x", expand=False)
        
        # Card header
        Label(settings_card, text="Run Configuration", 
             font=("Segoe UI", 16, "bold"),
             bootstyle="info").pack(anchor="w", pady=(0, 10))
        
        # Run Type Radio Buttons with improved styling
        self.run_type_var = tk.StringVar(value="count")
        
        run_type_frame = Frame(settings_card)
        run_type_frame.pack(fill="x", pady=5)
        
        count_radio = ttk.Radiobutton(run_type_frame, 
                                    text="Number of Referrals", 
                                    variable=self.run_type_var, 
                                    value="count",
                                    command=self.toggle_run_type,
                                    style="TRadiobutton")
        count_radio.pack(anchor="w", pady=5)
        
        time_radio = ttk.Radiobutton(run_type_frame, 
                                   text="Time Duration (Hours)", 
                                   variable=self.run_type_var, 
                                   value="time",
                                   command=self.toggle_run_type,
                                   style="TRadiobutton")
        time_radio.pack(anchor="w", pady=5)
        
        # Count/Time Input Frame with improved styling
        input_frame = Frame(settings_card)
        input_frame.pack(fill="x", pady=10)
        
        # Number of Referrals
        count_frame = Frame(input_frame)
        count_frame.pack(fill="x", pady=5)
        
        self.count_label = Label(count_frame, text="Number of Referrals:", font=("Segoe UI", 10))
        self.count_label.pack(side="left")
        
        self.count_entry = Entry(count_frame, width=10, font=("Segoe UI", 10), padding=5)
        self.count_entry.pack(side="right")
        self.count_entry.insert(0, "10")
        
        # Time Duration
        time_frame = Frame(input_frame)
        time_frame.pack(fill="x", pady=5)
        
        self.time_label = Label(time_frame, text="Duration (Hours):", font=("Segoe UI", 10))
        self.time_label.pack(side="left")
        
        self.time_entry = Entry(time_frame, width=10, state="disabled", font=("Segoe UI", 10), padding=5)
        self.time_entry.pack(side="right")
        self.time_entry.insert(0, "24")
        
        # === RIGHT COLUMN: Progress Display ===
        progress_card = Frame(right_column, bootstyle="secondary", padding=15)
        progress_card.pack(fill="both", expand=True)
        
        # Card header
        Label(progress_card, text="Progress", 
             font=("Segoe UI", 16, "bold"),
             bootstyle="info").pack(anchor="w", pady=(0, 10))
        
        # Create a modern circular progress indicator
        self.create_modern_progress_circle(progress_card)
        
        # Control buttons with improved styling
        control_frame = Frame(progress_card)
        control_frame.pack(fill="x", expand=False, pady=15)
        
        # Use grid for better alignment
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)
        control_frame.columnconfigure(2, weight=1)
        
        self.start_btn = Button(control_frame, 
                              text="▶️ Start", 
                              bootstyle="success", 
                              width=12,
                              command=self.start_bot)
        self.start_btn.grid(row=0, column=0, padx=5, pady=5)
        
        self.pause_btn = Button(control_frame, 
                              text="⏸ Pause", 
                              bootstyle="warning", 
                              width=12, 
                              command=self.toggle_pause,
                              state="disabled")
        self.pause_btn.grid(row=0, column=1, padx=5, pady=5)
        
        self.stop_btn = Button(control_frame, 
                             text="⏹ Stop", 
                             bootstyle="danger", 
                             width=12, 
                             command=self.stop_bot)
        self.stop_btn.grid(row=0, column=2, padx=5, pady=5)
        
        # Status box with improved styling
        status_frame = Frame(progress_card)
        status_frame.pack(fill="both", expand=True, pady=(10, 0))
        
        Label(status_frame, text="Status Log:", 
             font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        
        self.status_box = ScrolledText(status_frame, 
                                     height=10, 
                                     wrap="word", 
                                     font=("Consolas", 10))
        self.status_box.pack(fill="both", expand=True)
        
    def create_modern_progress_circle(self, parent):
        """Create a more modern and visually appealing progress indicator"""
        self.progress_frame = Frame(parent)
        self.progress_frame.pack(pady=10, anchor="center")
        
        # Use a consistent size for the progress indicator
        circle_size = 200
        self.progress_canvas = tk.Canvas(self.progress_frame, 
                                      width=circle_size, 
                                      height=circle_size, 
                                      highlightthickness=0,
                                      bg="#1f1f1f")  # Match background color
        self.progress_canvas.pack()
        
        # Calculate center and radius
        center = circle_size / 2
        radius = circle_size / 2 - 15  # Leave some margin
        
        # Create background circle (lighter shade)
        self.progress_canvas.create_oval(
            center - radius, center - radius, 
            center + radius, center + radius, 
            outline="#444444", width=10, fill="#1f1f1f"
        )
        
        # Create progress arc (initially empty)
        self.arc = self.progress_canvas.create_arc(
            center - radius, center - radius, 
            center + radius, center + radius, 
            start=90, extent=0, 
            style="arc", outline="#ff1f5a", width=10
        )
        
        # Create inner circle for cleaner look
        self.progress_canvas.create_oval(
            center - radius + 15, center - radius + 15, 
            center + radius - 15, center + radius - 15, 
            outline="", fill="#1f1f1f"
        )
        
        # Create text for percentage with shadow effect for depth
        # Shadow text (slightly offset)
        self.progress_canvas.create_text(
            center + 2, center + 2, 
            text="0%", fill="#101010",
            font=("Segoe UI", 30, "bold")
        )
        
        # Main percentage text
        self.progress_text = self.progress_canvas.create_text(
            center, center, text="0%", 
            fill="#ff1f5a", font=("Segoe UI", 30, "bold")
        )
        
        # Create text for count or time remaining
        self.count_text = self.progress_canvas.create_text(
            center, center + 40, text="0/0", 
            fill="#ffffff", font=("Segoe UI", 14)
        )
        
        # Add additional status text field
        self.status_text_display = self.progress_canvas.create_text(
            center, center + 70, text="Ready",
            fill="#88ff88", font=("Segoe UI", 12)
        )

    def update_license_status(self, is_valid, message):
        """Update the license status display based on validation result"""
        if is_valid:
            self.license_status_var.set("✅ Licensed")
            self.display_license_info()
            self.add_log("License validated successfully")
        else:
            self.license_status_var.set("⚠️ Unlicensed")
            self.add_log(f"License validation failed: {message}")
            
    def initialize_license_system(self):
        """Initialize the license system and start periodic checks"""
        # Start periodic check with a callback
        self.license_system.start_stronger_periodic_check(
            callback=self.handle_license_revocation,
            check_interval=300  # Check every 5 minutes
        )
        self.add_log("Started periodic license validation")
    
    def handle_license_revocation(self, message):
        """Handle license revocation or expiration during runtime"""
        # This runs in a background thread, so we need to use after() to update the UI
        self.root.after(0, lambda: self.show_license_revoked_dialog(message))
    
    def show_license_revoked_dialog(self, message):
        """Show a dialog indicating the license has been revoked and force the user to re-license"""
        messagebox.showerror("License Revoked", 
                           f"Your license is no longer valid: {message}\n\n"
                           f"The application will now close.")
    
        # Disable all functionality
        self.disable_all_features()
    
        # Force the user to close and restart the application
        self.root.quit()
    
    def disable_all_features(self):
        """Disable all interactive features of the application"""
        # Disable all buttons and inputs
        for widget in self.root.winfo_children():
            if isinstance(widget, (Button, Entry, Checkbutton)):
                widget.config(state="disabled")
        
        # Set status to indicate disabled state
        self.status_text.set("License revoked - Application disabled")
        self.license_status_var.set("❌ License Revoked")
    
    def activate_license(self):
        license_key = self.license_key_var.get().strip()
    
        if not license_key:
            messagebox.showerror("License Error", "Please enter a license key.")
            return
    
        # Validate license format
        if not self.license_system.validate_license_format(license_key):
            messagebox.showerror("License Error", "Invalid license key format. Please enter a valid license key.")
            return
    
        self.status_text.set("Activating license...")
    
        # Run activation in a separate thread
        def activation_thread():
            is_valid, message = self.license_system.activate_license(license_key)
        
            if is_valid:
                # Update UI
                self.root.after(0, lambda: self.license_status_var.set("✅ Licensed"))
                self.root.after(0, lambda: self.display_license_info())
                self.root.after(0, lambda: messagebox.showinfo("License Activated", "License successfully activated!"))
                self.root.after(0, lambda: self.add_log("License successfully activated"))
                self.root.after(0, lambda: self.status_text.set("Licensed"))
                # Start periodic check
                self.root.after(0, self.initialize_license_system)
            else:
                self.root.after(0, lambda: messagebox.showerror("License Error", message))
                self.root.after(0, lambda: self.add_log(f"License activation failed: {message}"))
                self.root.after(0, lambda: self.status_text.set("Unlicensed"))
    
        threading.Thread(target=activation_thread).start()

    def check_saved_license(self):
        """Check if there's a saved license and validate it"""
        license_key = self.license_system.load_license_from_config()
    
        if not license_key:
            return False
    
        is_valid, message = self.license_system.check_license(license_key)
    
        if is_valid:
            self.license_status_var.set("✅ Licensed")
            self.license_system.is_licensed = True
            self.display_license_info()
            self.add_log("License validated successfully")
            return True
        else:
            self.add_log(f"Saved license validation failed: {message}")
            return False
        
    def create_header(self):
        header_frame = Frame(self.container)
        header_frame.pack(fill="x", pady=(0, 10))
        
        # Create logo
        logo_label = Label(header_frame, text="RefStorm", 
                          font=("Segoe UI", 20, "bold"), 
                          bootstyle="danger")
        logo_label.pack(side="left")
        
        # Version label
        version_label = Label(header_frame, text="v2.0", 
                             font=("Segoe UI", 10), 
                             bootstyle="secondary")
        version_label.pack(side="left", padx=(5, 0), pady=(10, 0))
        
        # Theme toggle button
        self.theme_btn = Button(header_frame, 
                              text="☀️", 
                              command=self.toggle_theme,
                              bootstyle="link-outline",
                              width=3)
        self.theme_btn.pack(side="right")

    def create_license_tab(self):
        license_frame = Frame(self.tabs, padding=15)
        self.tabs.add(license_frame, text="🔑 License")
    
        # License status frame
        status_frame = Frame(license_frame, padding=10)
        status_frame.pack(fill="x", pady=10)
    
        # License status
        self.license_status_var = tk.StringVar(value="⚠️ Unlicensed")
        self.license_status_color = tk.StringVar(value="danger")
    
        license_title = Label(status_frame, text="License Status:", font=("Segoe UI", 14, "bold"))
        license_title.pack(anchor="w")
    
        license_status = Label(status_frame, textvariable=self.license_status_var, 
                       font=("Segoe UI", 12), bootstyle="danger")
        license_status.pack(anchor="w", pady=5)
    
        # License details frame (initially hidden)
        self.license_details_frame = Frame(license_frame)
    
        # License activation frame
        activation_frame = Frame(license_frame, padding=10)
        activation_frame.pack(fill="x", pady=10)
    
        Label(activation_frame, text="Enter License Key:", font=("Segoe UI", 12)).pack(anchor="w", pady=(10, 5))
    
        key_frame = Frame(activation_frame)
        key_frame.pack(fill="x", pady=5)
    
        self.license_key_var = tk.StringVar()
        license_key_entry = Entry(key_frame, textvariable=self.license_key_var, font=("Segoe UI", 11))
        license_key_entry.pack(side="left", fill="x", expand=True)
    
        activate_btn = Button(key_frame, text="Activate License", bootstyle="success", 
                          command=self.activate_license)
        activate_btn.pack(side="right", padx=(5, 0))
    
        # License information
        help_frame = Frame(license_frame, padding=10)
        help_frame.pack(fill="x", pady=10)
    
        Label(help_frame, text="License Information:", font=("Segoe UI", 12, "bold")).pack(anchor="w")
    
        info_text = """
    • A valid license key is required to use RefStorm
    • License is bound to your hardware after activation
    • Contact support if you need to transfer your license
    • Your license includes free updates for the duration of your subscription
        """
    
        info_label = Label(help_frame, text=info_text, font=("Segoe UI", 10), 
                   justify="left", wraplength=500)
        info_label.pack(anchor="w", pady=5)
    
        # Purchase button
        purchase_frame = Frame(license_frame)
        purchase_frame.pack(fill="x", pady=20)
    
        purchase_btn = Button(purchase_frame, text="Purchase a License", bootstyle="primary-outline", 
                     command=self.open_purchase_page)
        purchase_btn.pack(anchor="center")

    def activate_license(self):
        license_key = self.license_key_var.get().strip()
    
        if not license_key:
            messagebox.showerror("License Error", "Please enter a license key.")
            return
    
        # Validate license format
        if not self.license_system.validate_license_format(license_key):
            messagebox.showerror("License Error", "Invalid license key format. Please enter a valid license key.")
            return
    
        self.status_text.set("Activating license...")
    
        # Run activation in a separate thread
        def activation_thread():
            is_valid, message = self.license_system.activate_license(license_key)
        
            if is_valid:
                # Update UI
                self.root.after(0, lambda: self.license_status_var.set("✅ Licensed"))
                self.root.after(0, lambda: self.display_license_info())
                self.root.after(0, lambda: messagebox.showinfo("License Activated", "License successfully activated!"))
                self.root.after(0, lambda: self.add_log("License successfully activated"))
                self.root.after(0, lambda: self.status_text.set("Licensed"))
            else:
                self.root.after(0, lambda: messagebox.showerror("License Error", message))
                self.root.after(0, lambda: self.add_log(f"License activation failed: {message}"))
                self.root.after(0, lambda: self.status_text.set("Unlicensed"))
    
        threading.Thread(target=activation_thread).start()

    def display_license_info(self):
        # Get license info
        license_info = self.license_system.license_info
    
        if not license_info:
            return
    
        # Show license details frame
        self.license_details_frame.pack(fill="x", pady=10, before=self.tabs.index("end"))
    
        # Clear previous widgets
        for widget in self.license_details_frame.winfo_children():
            widget.destroy()
    
        # Add license details
        Label(self.license_details_frame, text="License Details:", 
          font=("Segoe UI", 12, "bold")).pack(anchor="w")
    
        if license_info.get("name"):
            Label(self.license_details_frame, text=f"Licensed to: {license_info['name']}", 
              font=("Segoe UI", 10)).pack(anchor="w", pady=2)
    
        if license_info.get("email"):
            Label(self.license_details_frame, text=f"Email: {license_info['email']}", 
              font=("Segoe UI", 10)).pack(anchor="w", pady=2)
    
        if license_info.get("expires_at"):
            expiry_date = datetime.fromisoformat(license_info['expires_at'])
            expiry_str = expiry_date.strftime("%Y-%m-%d")
            days_left = (expiry_date - datetime.now()).days
        
            expiry_text = f"Expires: {expiry_str} ({days_left} days left)"
            Label(self.license_details_frame, text=expiry_text, 
              font=("Segoe UI", 10)).pack(anchor="w", pady=2)

    def open_purchase_page(self):
        webbrowser.open("https://discord.gg/eupVTtC2Xp")  # Replace with your actual purchase URL
        self.add_log("Opening license purchase page")

    def check_saved_license(self):
        """Check if there's a saved license and validate it"""
        license_key = self.license_system.load_license_from_config()
    
        if not license_key:
            return False
    
        is_valid, message = self.license_system.check_license(license_key)
    
        if is_valid:
            self.license_status_var.set("✅ Licensed")
            self.license_system.is_licensed = True
            self.display_license_info()
            self.add_log("License validated successfully")
            return True
        else:
            self.add_log(f"Saved license validation failed: {message}")
            return False
    
    def create_bot_tab(self):
        bot_frame = Frame(self.tabs, padding=15)
        self.tabs.add(bot_frame, text="🤖 Bot")
        
        # Input fields
        form_frame = Frame(bot_frame)
        form_frame.pack(fill="x", expand=False)
        
        # Referral Link - Modified to support multiple URLs
        Label(form_frame, text="Referral Link(s):", 
             font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(10, 0))
        
        # URL entry with add button
        url_frame = Frame(form_frame)
        url_frame.pack(fill="x", pady=5)
        
        self.url_entry = Entry(url_frame)
        self.url_entry.pack(side="left", fill="x", expand=True)
        
        add_url_btn = Button(url_frame, 
                           text="Add URL", 
                           bootstyle="primary-outline",
                           command=self.add_referral_url)
        add_url_btn.pack(side="right", padx=(5, 0))
        
        # URL list display
        self.url_list_frame = Frame(form_frame)
        self.url_list_frame.pack(fill="x", pady=5)
        
        self.url_list = ScrolledText(self.url_list_frame, 
                                    height=3, 
                                    wrap="word", 
                                    font=("Consolas", 9))
        self.url_list.pack(fill="x")
        self.url_list.config(state="disabled")
        
        # Clear URLs button
        clear_urls_btn = Button(self.url_list_frame,
                              text="Clear URLs",
                              bootstyle="danger-outline",
                              command=self.clear_referral_urls)
        clear_urls_btn.pack(anchor="e", pady=(5, 0))
        
        # Run Type Selection Frame
        run_type_frame = Frame(form_frame)
        run_type_frame.pack(fill="x", pady=10)
        
        # Run Type Radio Buttons
        self.run_type_var = tk.StringVar(value="count")
        Label(run_type_frame, text="Run Mode:", 
             font=("Segoe UI", 13, "bold")).pack(anchor="w")
        
        count_radio = ttk.Radiobutton(run_type_frame, 
                                    text="Number of Referrals", 
                                    variable=self.run_type_var, 
                                    value="count",
                                    command=self.toggle_run_type)
        count_radio.pack(anchor="w", pady=2)
        
        time_radio = ttk.Radiobutton(run_type_frame, 
                                   text="Time Duration (Hours)", 
                                   variable=self.run_type_var, 
                                   value="time",
                                   command=self.toggle_run_type)
        time_radio.pack(anchor="w", pady=2)
        
        # Count/Time Input Frame
        count_time_frame = Frame(form_frame)
        count_time_frame.pack(fill="x", pady=5)
        
        # Number of Referrals
        self.count_label = Label(count_time_frame, text="Number of Referrals:")
        self.count_label.grid(row=0, column=0, sticky="w")
        
        self.count_entry = Entry(count_time_frame, width=10)
        self.count_entry.grid(row=0, column=1, sticky="w", padx=5)
        self.count_entry.insert(0, "10")
        
        # Time Duration
        self.time_label = Label(count_time_frame, text="Duration (Hours):")
        self.time_label.grid(row=1, column=0, sticky="w")
        
        self.time_entry = Entry(count_time_frame, width=10, state="disabled")
        self.time_entry.grid(row=1, column=1, sticky="w", padx=5)
        self.time_entry.insert(0, "24")
        
        # Progress section
        progress_frame = Frame(bot_frame)
        progress_frame.pack(fill="x", expand=False, pady=15)
        
        # Create circular progress
        self.create_progress_circle(progress_frame)
        
        # Control buttons
        control_frame = Frame(bot_frame)
        control_frame.pack(fill="x", expand=False, pady=10)
        
        # Use grid for better alignment
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)
        control_frame.columnconfigure(2, weight=1)
        
        self.start_btn = Button(control_frame, 
                              text="🚀 Start Bot", 
                              bootstyle="success", 
                              width=15, 
                              command=self.start_bot)
        self.start_btn.grid(row=0, column=0, padx=2, pady=5)
        
        self.pause_btn = Button(control_frame, 
                              text="⏸ Pause", 
                              bootstyle="warning", 
                              width=15, 
                              command=self.toggle_pause,
                              state="disabled")
        self.pause_btn.grid(row=0, column=1, padx=2, pady=5)
        
        self.stop_btn = Button(control_frame, 
                             text="🛑 Stop Bot", 
                             bootstyle="danger", 
                             width=15, 
                             command=self.stop_bot)
        self.stop_btn.grid(row=0, column=2, padx=2, pady=5)
        
        # Status box
        status_frame = Frame(bot_frame)
        status_frame.pack(fill="both", expand=True, pady=10)
        
        Label(status_frame, text="Status:", 
             font=("Segoe UI", 12)).pack(anchor="w", pady=(0, 5))
        
        self.status_box = ScrolledText(status_frame, 
                                     height=8, 
                                     wrap="word", 
                                     font=("Consolas", 9))
        self.status_box.pack(fill="both", expand=True)
        
    def create_settings_tab(self):
        settings_frame = Frame(self.tabs, padding=15)
        self.tabs.add(settings_frame, text="⚙️ Settings")
        
        # Create a notebook for settings categories
        settings_notebook = ttk.Notebook(settings_frame)
        settings_notebook.pack(fill="both", expand=True)
        
        # === Browser Settings Tab ===
        browser_frame = Frame(settings_notebook, padding=10)
        settings_notebook.add(browser_frame, text="Browser")
        
        # Chrome path settings
        Label(browser_frame, text="Chrome Path:", 
             font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 5))
        
        self.chrome_path_var = tk.StringVar()
        self.chrome_path_var.set(self.check_chrome_installed() or "")
        
        chrome_path_frame = Frame(browser_frame)
        chrome_path_frame.pack(fill="x", pady=5)
        
        chrome_path_entry = Entry(chrome_path_frame, textvariable=self.chrome_path_var)
        chrome_path_entry.pack(side="left", fill="x", expand=True)
        
        browse_btn = Button(chrome_path_frame, 
                          text="Browse", 
                          bootstyle="secondary", 
                          command=self.browse_chrome)
        browse_btn.pack(side="right", padx=(5, 0))
        
        # Headless mode option
        self.headless_mode_var = tk.BooleanVar(value=False)
        headless_check = Checkbutton(browser_frame, 
                                   text="Run Chrome in headless mode (invisible browser)", 
                                   variable=self.headless_mode_var, 
                                   bootstyle="round-toggle")
        headless_check.pack(anchor="w", pady=10)
        
        # User agent settings
        Label(browser_frame, text="User Agent", 
             font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(15, 5))
        
        self.custom_ua_var = tk.BooleanVar(value=False)
        custom_ua_check = Checkbutton(browser_frame, 
                                    text="Use custom user agent", 
                                    variable=self.custom_ua_var, 
                                    bootstyle="round-toggle",
                                    command=self.toggle_ua_entry)
        custom_ua_check.pack(anchor="w", pady=5)
        
        self.ua_entry = Entry(browser_frame, state="disabled")
        self.ua_entry.pack(fill="x", pady=5)
        
        # === Email Settings Tab ===
        email_frame = Frame(settings_notebook, padding=10)
        settings_notebook.add(email_frame, text="Email")
        
        # Email options
        Label(email_frame, text="Email Settings", 
             font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 10))
        
        self.check_confirm_var = tk.BooleanVar(value=True)
        confirm_check = Checkbutton(email_frame, 
                                  text="Check for confirmation emails", 
                                  variable=self.check_confirm_var, 
                                  bootstyle="round-toggle")
        confirm_check.pack(anchor="w", pady=5)
        
        # Email timeout setting
        timeout_frame = Frame(email_frame)
        timeout_frame.pack(fill="x", pady=10)
        
        Label(timeout_frame, text="Email confirmation timeout (seconds):").pack(side="left")
        self.timeout_var = tk.IntVar(value=60)
        timeout_spinbox = tb.Spinbox(timeout_frame, 
                                   from_=10, 
                                   to=300, 
                                   increment=5, 
                                   textvariable=self.timeout_var,
                                   width=10)
        timeout_spinbox.pack(side="right")
        
        # === Timing Settings Tab ===
        timing_frame = Frame(settings_notebook, padding=10)
        settings_notebook.add(timing_frame, text="Timing")
        
        # Timing settings
        Label(timing_frame, text="Timing Settings", 
             font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 10))
        
        delay_frame = Frame(timing_frame)
        delay_frame.pack(fill="x", pady=10)
        
        Label(delay_frame, text="Delay between referrals (seconds):").pack(side="left")
        self.delay_var = tk.DoubleVar(value=3.0)
        delay_spinbox = tb.Spinbox(delay_frame, 
                                 from_=1.0, 
                                 to=30.0, 
                                 increment=0.5, 
                                 textvariable=self.delay_var,
                                 width=10)
        delay_spinbox.pack(side="right")
        
        # === Webhook Settings Tab ===
        webhook_frame = Frame(settings_notebook, padding=10)
        settings_notebook.add(webhook_frame, text="Webhook")
        
        # Discord webhook settings
        Label(webhook_frame, text="Discord Webhook Settings", 
             font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(5, 10))
        
        self.use_webhook_var = tk.BooleanVar(value=True)
        webhook_check = Checkbutton(webhook_frame, 
                                  text="Send notifications to Discord webhook", 
                                  variable=self.use_webhook_var, 
                                  bootstyle="round-toggle",
                                  command=self.toggle_webhook_entry)
        webhook_check.pack(anchor="w", pady=5)
        
        # Webhook URL
        Label(webhook_frame, text="Discord Webhook URL:").pack(anchor="w", pady=(10, 5))
        self.webhook_url_var = tk.StringVar()
        self.webhook_url_entry = Entry(webhook_frame, textvariable=self.webhook_url_var)
        self.webhook_url_entry.pack(fill="x", pady=5)
        
        # Test webhook button
        test_webhook_btn = Button(webhook_frame, 
                                text="Test Webhook", 
                                bootstyle="info-outline", 
                                command=self.test_webhook)
        test_webhook_btn.pack(anchor="w", pady=10)
        
        # Save settings button at the bottom
        save_btn = Button(settings_frame, 
                        text="Save Settings", 
                        bootstyle="primary", 
                        command=self.save_settings)
        save_btn.pack(anchor="e", pady=15)
        
        # Load settings
        self.load_settings()
        
    def create_logs_tab(self):
        logs_frame = Frame(self.tabs, padding=15)
        self.tabs.add(logs_frame, text="📋 Logs")
        
        # Controls
        controls_frame = Frame(logs_frame)
        controls_frame.pack(fill="x", pady=(0, 10))
        
        clear_btn = Button(controls_frame, 
                         text="Clear Logs", 
                         bootstyle="warning-outline", 
                         command=self.clear_logs)
        clear_btn.pack(side="left")
        
        export_btn = Button(controls_frame, 
                          text="Export Logs", 
                          bootstyle="info-outline", 
                          command=self.export_logs)
        export_btn.pack(side="left", padx=(5, 0))
        
        # Log display
        self.log_box = ScrolledText(logs_frame, 
                                  height=20, 
                                  wrap="word", 
                                  font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True, pady=5)
        self.log_box.config(state="disabled")
        
        # Add initial log entry
        self.add_log("RefStorm v2.0 started")
    
    def create_about_tab(self):
        about_frame = Frame(self.tabs, padding=15)
        self.tabs.add(about_frame, text="ℹ️ About")
        
        # Create scrollable content
        about_content = ScrolledText(about_frame, 
                                   wrap="word", 
                                   font=("Segoe UI", 10),
                                   height=25)
        about_content.pack(fill="both", expand=True)
        
        # Set about content
        about_text = """
# 🌪️ RefStorm v2.0

RefStorm is a powerful automated referral tool designed to help you maximize your referral rewards.

## 🚀 Features

- **Automated Referrals**: Generate multiple referrals with just a few clicks
- **Temporary Email Integration**: Uses real temporary email addresses
- **Email Confirmation**: Automatically confirms verification emails
- **Time-Based Running**: Set duration in hours instead of counting referrals
- **Pause/Resume**: Pause and continue your referral campaigns
- **Multiple Referral URLs**: Rotate through different referral links
- **Headless Mode**: Run Chrome invisibly in the background
- **Custom Discord Webhooks**: Get notifications on your own Discord server
- **User Agent Rotation**: Randomizes user agents to avoid detection
- **Modern UI**: Clean, intuitive interface with dark/light mode
- **Detailed Logging**: Track all actions taken by the bot

## 🔧 How to Use

1. Enter your referral link(s) in the Bot tab
2. Choose between referral count or time-based running
3. Configure any additional settings in the Settings tab
4. Click "Start Bot" and let RefStorm do the work

## 🔒 Safety & Privacy

RefStorm is designed to be used responsibly and ethically. Always ensure you are complying with the terms of service of any website or platform you are using.

## 🌟 Credits

Made by GhostHax

Join our Discord community for updates and support!

## 📜 Disclaimer

This tool is provided for educational purposes only. Users are responsible for their own actions and any consequences that may arise from the use of this software.
"""
        about_content.insert("1.0", about_text)
        about_content.config(state="disabled")
        
        # Discord button
        discord_btn = Button(about_frame, 
                           text="Join our Discord", 
                           bootstyle="info", 
                           command=self.open_discord)
        discord_btn.pack(anchor="center", pady=10)
        
        # Version info
        version_frame = Frame(about_frame)
        version_frame.pack(fill="x", pady=5)
        
        version_label = Label(version_frame, 
                            text="RefStorm v2.0 | Build Date: April 2025", 
                            font=("Segoe UI", 8))
        version_label.pack(side="left")
        
        made_by_label = Label(version_frame, 
                            text="Made by GhostHax", 
                            font=("Segoe UI", 8, "italic"), 
                            bootstyle="danger")
        made_by_label.pack(side="right")
    
    def create_status_bar(self):
        status_bar = Frame(self.root)
        status_bar.pack(fill="x", side="bottom")
        
        self.status_text = tk.StringVar()
        self.status_text.set("Ready")
        
        status_label = Label(status_bar, textvariable=self.status_text)
        status_label.pack(side="left", padx=5)
        
        # Add selenium status indicator
        selenium_status = "✅ Selenium Loaded" if SELENIUM_AVAILABLE else "❌ Selenium Not Found"
        selenium_label = Label(status_bar, 
                             text=selenium_status, 
                             bootstyle="success" if SELENIUM_AVAILABLE else "danger")
        selenium_label.pack(side="right", padx=5)
    
    def create_progress_circle(self, parent):
        self.progress_frame = Frame(parent)
        self.progress_frame.pack(pady=10)
        
        self.progress_canvas = tk.Canvas(self.progress_frame, width=180, height=180, highlightthickness=0)
        self.progress_canvas.pack()
        
        # Create outer circle
        self.progress_canvas.create_oval(10, 10, 170, 170, outline="#ff0033", width=2)
        
        # Create progress arc (initially empty)
        self.arc = self.progress_canvas.create_arc(10, 10, 170, 170, 
                                                 start=90, extent=0, 
                                                 style="arc", 
                                                 outline="#ff0033", width=14)
        
        # Create text for percentage
        self.progress_text = self.progress_canvas.create_text(90, 90, 
                                                          text="0%", 
                                                          fill="#ff0033", 
                                                          font=("Segoe UI", 18, "bold"))
        
        # Create text for count or time remaining
        self.count_text = self.progress_canvas.create_text(90, 120, 
                                                        text="0/0", 
                                                        fill="#ff0033", 
                                                        font=("Segoe UI", 12))
        
        # Add additional status text field
        self.status_text_display = self.progress_canvas.create_text(90, 150,
                                                               text="Ready",
                                                               fill="#ff0033",
                                                               font=("Segoe UI", 9))
    
    def update_progress(self, current, total, status_text=None):
        target_percent = int((current / total) * 100) if total > 0 else 0
        current_extent = abs(float(self.progress_canvas.itemcget(self.arc, "extent")))
        target_extent = (target_percent / 100) * 360
        
        # Update count/time text immediately
        if self.run_type == "count":
            self.progress_canvas.itemconfig(self.count_text, text=f"{current}/{total}")
        else:
            # Format remaining time
            remaining = total - current if total >= current else 0
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            self.progress_canvas.itemconfig(self.count_text, text=f"{hours}h {minutes}m left")
        
        # Update status text if provided
        if status_text:
            self.progress_canvas.itemconfig(self.status_text_display, text=status_text)

        def animate():
            nonlocal current_extent
            while abs(current_extent - target_extent) > 1:
                current_extent += (target_extent - current_extent) / 6
                self.progress_canvas.itemconfig(self.arc, extent=-current_extent)
                self.progress_canvas.itemconfig(self.progress_text, text=f"{int((current_extent / 360) * 100)}%")
                time.sleep(0.016)

        threading.Thread(target=animate, daemon=True).start()
    
    def update_status(self, message):
        self.status_box.insert(tk.END, f"[{self.get_timestamp()}] {message}\n")
        self.status_box.see(tk.END)
        # Also add to logs
        self.add_log(message)

    def get_timestamp(self):
        return datetime.now().strftime("%H:%M:%S")
    
    def add_log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        
        # Update log display
        if hasattr(self, 'log_box'):  # Check if log_box exists
            self.log_box.config(state="normal")
            self.log_box.insert(tk.END, log_entry + "\n")
            self.log_box.see(tk.END)
            self.log_box.config(state="disabled")
    
    def clear_logs(self):
        self.logs = []
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state="disabled")
        self.add_log("Logs cleared")
    
    def export_logs(self):
        if not self.logs:
            messagebox.showinfo("Export Logs", "No logs to export.")
            return
        
        try:
            # Create logs directory if it doesn't exist
            logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            os.makedirs(logs_dir, exist_ok=True)
            
            # Create log file with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = os.path.join(logs_dir, f"refstorm_log_{timestamp}.txt")
            
            with open(log_file, "w") as f:
                f.write("RefStorm Bot Logs\n")
                f.write("=" * 50 + "\n\n")
                for log in self.logs:
                    f.write(log + "\n")
            
            self.add_log(f"Logs exported to {log_file}")
            messagebox.showinfo("Export Logs", f"Logs successfully exported to:\n{log_file}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export logs: {str(e)}")
    
    def toggle_theme(self):
        if self.theme_mode == "dark":
            self.style.theme_use("flatly")  # Light theme
            self.theme_btn.config(text="🌙")
            self.theme_mode = "light"
        else:
            self.style.theme_use("darkly")  # Dark theme
            self.theme_btn.config(text="☀️")
            self.theme_mode = "dark"
            
        # Update progress circle colors based on theme
        if self.theme_mode == "dark":
            fill_color = "#ff0033"  # Red for dark mode
        else:
            fill_color = "#dc3545"  # Bootstrap danger color for light mode
            
        self.progress_canvas.itemconfig(self.arc, outline=fill_color)
        self.progress_canvas.itemconfig(self.progress_text, fill=fill_color)
        self.progress_canvas.itemconfig(self.count_text, fill=fill_color)
        self.progress_canvas.itemconfig(self.status_text_display, fill=fill_color)
    
    def toggle_ua_entry(self):
        if self.custom_ua_var.get():
            self.ua_entry.config(state="normal")
        else:
            self.ua_entry.config(state="disabled")
    
    def toggle_webhook_entry(self):
        if self.use_webhook_var.get():
            self.webhook_url_entry.config(state="normal")
        else:
            self.webhook_url_entry.config(state="disabled")
    
    def toggle_run_type(self):
        if self.run_type_var.get() == "count":
            self.count_entry.config(state="normal")
            self.time_entry.config(state="disabled")
        else:
            self.count_entry.config(state="disabled")
            self.time_entry.config(state="normal")
    
    def add_referral_url(self):
        url = self.url_entry.get().strip()
        
        if not url:
            return
        
        if not url.startswith("http"):
            messagebox.showerror("Invalid URL", "The URL must start with http:// or https://")
            return
            
        # Add to list
        self.referral_urls.append(url)
        
        # Clear entry
        self.url_entry.delete(0, tk.END)
        
        # Update URL list display
        self.update_url_list_display()
    
    def clear_referral_urls(self):
        self.referral_urls = []
        self.update_url_list_display()
    
    def update_url_list_display(self):
        self.url_list.config(state="normal")
        self.url_list.delete("1.0", tk.END)
        
        if self.referral_urls:
            for i, url in enumerate(self.referral_urls, 1):
                self.url_list.insert(tk.END, f"{i}. {url}\n")
        else:
            self.url_list.insert(tk.END, "No URLs added. Add at least one referral URL.")
            
        self.url_list.config(state="disabled")
    
    def browse_chrome(self):
        chrome_path = filedialog.askopenfilename(
            title="Select Chrome Executable",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if chrome_path:
            self.chrome_path_var.set(chrome_path)
    
    def test_webhook(self):
        webhook_url = self.webhook_url_var.get().strip()
        
        if not webhook_url:
            messagebox.showerror("Webhook Error", "Please enter a webhook URL first.")
            return
        
        try:
            data = {
                "embeds": [{
                    "title": "RefStorm Webhook Test",
                    "description": "If you can see this message, your webhook is configured correctly!",
                    "color": 3447003,  # Blue color
                    "footer": {
                        "text": "RefStorm v2.0"
                    },
                    "timestamp": datetime.now().isoformat()
                }]
            }
            
            headers = {"Content-Type": "application/json"}
            response = requests.post(webhook_url, json=data, headers=headers)
            
            if response.status_code in (200, 204):
                messagebox.showinfo("Webhook Test", "Webhook test successful! Check your Discord server.")
                self.add_log("Webhook test successful")
            else:
                messagebox.showerror("Webhook Error", f"Failed to send webhook: Status code {response.status_code}")
                self.add_log(f"Webhook test failed: Status code {response.status_code}")
                
        except Exception as e:
            messagebox.showerror("Webhook Error", f"Error testing webhook: {str(e)}")
            self.add_log(f"Webhook test error: {str(e)}")

    def initialize_license_system(self):
        """Initialize the license system and start periodic checks"""
        self.license_system = LicenseSystem()
    
    # Load saved license if available
        saved_license = self.license_system.load_license_from_config()
        if saved_license:
            is_valid, message = self.license_system.check_license(saved_license)
            if is_valid:
                self.update_license_status(True, message)
                # Start periodic check with a callback
                self.license_system.start_stronger_periodic_check(
                    callback=self.handle_license_revocation,
                    check_interval=300  # Check every 5 minutes
                )
            else:
                self.update_license_status(False, message)

    def handle_license_revocation(self, message):
        """Handle license revocation or expiration during runtime"""
        # This runs in a background thread, so we need to use after() to update the UI
        self.root.after(0, lambda: self.show_license_revoked_dialog(message))

    def show_license_revoked_dialog(self, message):
        """Show a dialog indicating the license has been revoked and force the user to re-license"""
        import tkinter.messagebox as messagebox
    
        messagebox.showerror("License Revoked", 
                           f"Your license is no longer valid: {message}\n\n"
                           f"The application will now close.")
    
        # Disable all functionality
        self.disable_all_features()
    
        # Force the user to close and restart the application
        self.root.quit()
    
    def save_settings(self):
        settings = {
            "chrome_path": self.chrome_path_var.get(),
            "use_custom_ua": self.custom_ua_var.get(),
            "custom_ua": self.ua_entry.get(),
            "delay": self.delay_var.get(),
            "timeout": self.timeout_var.get(),
            "theme": self.theme_mode,
            "headless_mode": self.headless_mode_var.get(),
            "check_confirmation": self.check_confirm_var.get(),
            "use_webhook": self.use_webhook_var.get(),
            "webhook_url": self.webhook_url_var.get()
        }
        
        try:
            settings_dir = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(settings_dir, "refstorm_settings.json"), "w") as f:
                json.dump(settings, f, indent=4)
            
            self.add_log("Settings saved successfully")
            self.status_text.set("Settings saved")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save settings: {str(e)}")
    
    def load_settings(self):
        try:
            settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "refstorm_settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    settings = json.load(f)
                
                # Apply settings
                if "chrome_path" in settings:
                    self.chrome_path_var.set(settings["chrome_path"])
                
                if "use_custom_ua" in settings:
                    self.custom_ua_var.set(settings["use_custom_ua"])
                    
                if "custom_ua" in settings:
                    self.ua_entry.delete(0, tk.END)
                    self.ua_entry.insert(0, settings["custom_ua"])
                
                if "delay" in settings:
                    self.delay_var.set(settings["delay"])
                
                if "timeout" in settings:
                    self.timeout_var.set(settings["timeout"])
                
                if "headless_mode" in settings:
                    self.headless_mode_var.set(settings["headless_mode"])
                
                if "check_confirmation" in settings:
                    self.check_confirm_var.set(settings["check_confirmation"])
                
                if "use_webhook" in settings:
                    self.use_webhook_var.set(settings["use_webhook"])
                
                if "webhook_url" in settings:
                    self.webhook_url_var.set(settings["webhook_url"])
                
                if "theme" in settings and settings["theme"] != self.theme_mode:
                    self.toggle_theme()  # This will switch the theme if needed
                
                # Toggle UI states based on settings
                self.toggle_ua_entry()
                self.toggle_webhook_entry()
                
                self.add_log("Settings loaded successfully")
        except Exception as e:
            self.add_log(f"Failed to load settings: {str(e)}")
    
    def check_chrome_installed(self):
        """Check if Chrome is installed on the system"""
        try:
            # Common Chrome installation paths
            possible_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expanduser("~") + r"\AppData\Local\Google\Chrome\Application\chrome.exe",
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    return path
                    
            # Try to find Chrome using registry on Windows
            if os.name == 'nt':
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                        chrome_path = winreg.QueryValue(key, None)
                        if os.path.exists(chrome_path):
                            return chrome_path
                except:
                    pass
        except:
            pass
        
        return None
    
    def open_discord(self):
        webbrowser.open("https://discord.gg/eupVTtC2Xp")
    
    def send_discord_webhook(self, content, title=None, color=None):
        """Send a message to Discord webhook"""
        if not self.use_webhook_var.get():
            return False
            
        webhook_url = self.webhook_url_var.get().strip()
        if not webhook_url:
            return False
            
        try:
            data = {
                "content": content
            }
            
            # If title and color are provided, use an embed
            if title:
                embed = {
                    "title": title,
                    "description": content,
                    "color": color or 3447003,  # Blue if no color specified
                    "footer": {
                        "text": f"RefStorm v2.0 • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                }
                data = {"embeds": [embed]}
                
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.post(webhook_url, json=data, headers=headers)
            return response.status_code in (200, 204)
        except Exception as e:
            print(f"Failed to send Discord webhook: {str(e)}")
            return False
    
    def handle_email_confirmation(self, driver, temp_mail, wait_time=60):
        """Check for confirmation emails and handle them"""
        self.update_status("Checking for confirmation emails...")
        inbox = temp_mail.get_inbox(max_wait=wait_time)
        
        if not inbox:
            self.update_status("No confirmation emails received.")
            return False
        
        # Get the newest email
        newest_email = max(inbox, key=lambda x: x['id'])
        message_id = newest_email['id']
        
        self.update_status(f"Confirmation email received from: {newest_email.get('from', 'Unknown')}")
        
        # Get the full message content
        message = temp_mail.get_message(message_id)
        if not message:
            self.update_status("Failed to fetch email content.")
            return False
        
        # Extract confirmation link
        confirm_link = temp_mail.extract_confirmation_link(message)
        if not confirm_link:
            self.update_status("No confirmation link found in the email.")
            return False
        
        self.update_status(f"Confirmation link found! Opening link...")
        
        # Open the confirmation link
        try:
            driver.get(confirm_link)
            self.update_status("✅ Confirmation link visited successfully!")
            return True
        except Exception as e:
            self.update_status(f"Failed to open confirmation link: {str(e)}")
            return False
    
    def toggle_pause(self):
        if not self.running:
            return
        
        if self.paused:
            # Resume the bot
            self.paused = False
            self.pause_btn.config(text="⏸ Pause", bootstyle="warning")
            self.update_status("▶️ Bot resumed")
            self.send_discord_webhook("▶️ **Bot resumed**", "RefStorm Bot Resumed", 16776960)  # Yellow color
        else:
            # Pause the bot
            self.paused = True
            self.pause_btn.config(text="▶️ Resume", bootstyle="success")
            self.update_status("⏸ Bot paused")
            self.send_discord_webhook("⏸ **Bot paused**", "RefStorm Bot Paused", 16776960)  # Yellow color
    
    def start_bot(self):       
        if self.running:
            return
    
        # Check license
        if not self.license_system.is_licensed:
            messagebox.showerror("License Required", "Please activate your license to use RefStorm.")
            # Switch to license tab
            self.tabs.select(2)  # Assuming it's the 3rd tab (index 2)
            return
    
        # Check if we have any URLs - Fix for the bug: only check referral_urls list, not the entry field
        if not self.referral_urls:
            messagebox.showerror("Missing URLs", "Please add at least one referral URL using the 'Add URL' button.")
            return
    
        # Get run parameters
        if self.run_type_var.get() == "count":
            count = self.count_entry.get().strip()
            if not count.isdigit() or int(count) <= 0:
                messagebox.showerror("Invalid Number", "Please enter a positive number of referrals.")
                return
        else:
            hours = self.time_entry.get().strip()
            try:
                hours_float = float(hours)
                if hours_float <= 0:
                    raise ValueError("Hours must be positive")
            except:
                messagebox.showerror("Invalid Time", "Please enter a valid number of hours.")
                return
    
        # Check if Selenium is available
        if not SELENIUM_AVAILABLE:
            messagebox.showerror("Missing Dependency", 
                              "Selenium is not installed. Please install it using:\n\npip install selenium")
            return
    
        # Clear status box
        self.status_box.delete("1.0", tk.END)
    
        # Update button states
        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal")
    
        # Reset current URL index
        self.current_url_index = 0
    
        # Start bot in a separate thread
        threading.Thread(target=self.run_bot, daemon=True).start()
    
        # Update status
        self.status_text.set("Bot running...")
    
    def stop_bot(self):
        if self.running:
            self.running = False
            self.paused = False
            self.status_text.set("Stopping bot...")
            self.update_status("🛑 Stopping bot...")
            
            # Reset button states
            self.start_btn.config(state="normal")
            self.pause_btn.config(state="disabled")
            self.pause_btn.config(text="⏸ Pause", bootstyle="warning")
    
    def run_bot(self):
        self.running = True
        
        # Determine run type and parameters
        is_time_based = self.run_type_var.get() == "time"
        
        if is_time_based:
            hours = float(self.time_entry.get())
            duration_seconds = hours * 3600
            end_time = time.time() + duration_seconds
            total_time = duration_seconds
        else:
            repeat_count = int(self.count_entry.get())
        
        # Send Discord webhook notification for bot start
        if is_time_based:
            self.send_discord_webhook(
                f"✅ **Bot started**\nTarget: {len(self.referral_urls)} referral URLs\nRunning for: {hours} hours" +
                f"\nChecking confirmation emails: {'Yes' if self.check_confirm_var.get() else 'No'}",
                "RefStorm Bot Started", 65280  # Green color
            )
        else:
            self.send_discord_webhook(
                f"✅ **Bot started**\nTarget: {len(self.referral_urls)} referral URLs\nPlanned referrals: {repeat_count}" +
                f"\nChecking confirmation emails: {'Yes' if self.check_confirm_var.get() else 'No'}",
                "RefStorm Bot Started", 65280  # Green color
            )
        
        # Check if Chrome is installed or use custom path
        chrome_path = self.chrome_path_var.get() or self.check_chrome_installed()
        if not chrome_path or not os.path.exists(chrome_path):
            self.update_status("❌ Chrome not found! Please set the correct path in Settings.")
            self.running = False
            self.status_text.set("Ready")
            self.start_btn.config(state="normal")
            self.pause_btn.config(state="disabled")
            return
        
        # Initialize temp mail service
        temp_mail = TempMailService()
        
        submitted_count = 0
        confirmed_count = 0
        start_time = time.time()
        
        # Main bot loop
        counter = 0
        while self.running:
            # Handle pause state
            while self.paused and self.running:
                self.progress_canvas.itemconfig(self.status_text_display, text="Paused")
                time.sleep(0.5)
                
            if not self.running:
                break
                
            # Update progress
            if is_time_based:
                current_time = time.time()
                if current_time >= end_time:
                    # Time's up
                    self.update_progress(total_time, total_time, "Time completed")
                    break
                    
                elapsed = current_time - start_time
                self.update_progress(elapsed, total_time, f"Completed: {submitted_count}")
            else:
                if counter >= repeat_count:
                    # Reached desired count
                    self.update_progress(repeat_count, repeat_count, "Count completed")
                    break
                    
                self.update_progress(counter, repeat_count, f"URL #{self.current_url_index+1}")
            
            # Get next URL in rotation
            if not self.referral_urls:
                self.update_status("No referral URLs available!")
                break
                
            current_url = self.referral_urls[self.current_url_index]
            self.current_url_index = (self.current_url_index + 1) % len(self.referral_urls)
            
            try:
                # Use our predefined user agents or custom one
                if self.custom_ua_var.get() and self.ua_entry.get().strip():
                    user_agent = self.ua_entry.get().strip()
                else:
                    user_agent = random.choice(user_agents)
                    
                options = Options()
                options.add_argument(f"--user-agent={user_agent}")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--incognito")
                
                # Add headless mode if enabled
                if self.headless_mode_var.get():
                    options.add_argument("--headless=new")
                else:
                    options.add_argument("--start-maximized")
                    
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
                options.binary_location = chrome_path
                
                # Use the newer approach for Chrome
                driver = webdriver.Chrome(options=options)
                wait = WebDriverWait(driver, 10)
                
                # Generate email with temp mail
                email = temp_mail.create_email()
                self.update_status(f"[URL #{self.current_url_index}/{len(self.referral_urls)}] Created temp email: {email}")
    
                # Visit referral URL
                driver.get(current_url)
                possible_inputs = driver.find_elements(By.XPATH, "//input[not(@type='hidden')]")
                email_input = None
                
                # Find email input field
                for input_field in possible_inputs:
                    attr_type = input_field.get_attribute("type") or ""
                    attr_name = input_field.get_attribute("name") or ""
                    attr_id = input_field.get_attribute("id") or ""
                    attr_placeholder = input_field.get_attribute("placeholder") or ""
                    if any(k in attr_type.lower() for k in ["email"]) or \
                       any(k in attr_name.lower() for k in ["email", "mail"]) or \
                       any(k in attr_id.lower() for k in ["email", "mail"]) or \
                       any(k in attr_placeholder.lower() for k in ["email", "e-mail", "your email"]):
                        email_input = input_field
                        break
    
                if email_input is None:
                    self.update_status("❌ Could not find email input field!")
                    driver.quit()
                    continue
    
                # Enter email with realistic typing behavior
                driver.execute_script("arguments[0].focus();", email_input)
                for char in email:
                    email_input.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.12))
    
                # Find submit button
                button_keywords = ["start", "submit", "continue", "quest", "join", "go", "enter", "Access", "get", "access"]
                quest_button = None
                buttons = driver.find_elements(By.XPATH, "//*[self::button or (self::a and @role='button') or (self::input and (@type='submit' or @type='button'))]")
    
                for btn in buttons:
                    try:
                        text_parts = [btn.text or "", btn.get_attribute("value") or "", btn.get_attribute("aria-label") or "", btn.get_attribute("id") or "", btn.get_attribute("name") or ""]
                        combined_text = " ".join(text_parts).lower()
                        if any(k in combined_text for k in button_keywords):
                            quest_button = btn
                            break
                    except:
                        continue
    
                if quest_button:
                    driver.execute_script("arguments[0].click();", quest_button)
                    self.update_status("✅ Form submitted!")
                    submitted_count += 1
                    counter += 1
                    
                    # Send Discord webhook notification for each referral
                    self.send_discord_webhook(
                        f"📩 **Referral submitted** #{submitted_count}" +
                        (f"/{repeat_count}" if not is_time_based else "") +
                        f"\nEmail: {email}\nURL: {current_url}",
                        "RefStorm Referral Submitted", 3447003  # Blue color
                    )
                    
                    # Handle confirmation if needed
                    if self.check_confirm_var.get():
                        confirmation_success = self.handle_email_confirmation(
                            driver, temp_mail, wait_time=self.timeout_var.get()
                        )
                        if confirmation_success:
                            confirmed_count += 1
                            self.send_discord_webhook(
                                f"✅ **Email confirmed** #{confirmed_count}/{submitted_count}\nEmail: {email}",
                                "RefStorm Email Confirmed", 7340032  # Green color
                            )
                else:
                    self.update_status("❌ Could not find submission button!")
    
                time.sleep(random.uniform(2.0, 3.5))
    
            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                self.update_status(f"❌ Error: {str(e)}")
            
            try:
                driver.delete_all_cookies()
                driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
            except:
                pass
            
            try:
                driver.quit()
            except:
                pass
                
            # Use the delay from settings
            time.sleep(random.uniform(self.delay_var.get() * 0.8, self.delay_var.get() * 1.2))
    
        # Final update
        if is_time_based:
            self.update_progress(total_time, total_time, f"Completed: {submitted_count}")
        else:
            self.update_progress(counter, repeat_count, f"Completed: {submitted_count}")
        
        if self.running:
            # Send Discord webhook notification for bot finished
            self.send_discord_webhook(
                f"🎉 **Bot finished**\nSuccessfully submitted: {submitted_count}" +
                (f"/{repeat_count}" if not is_time_based else f" in {hours} hours") +
                (f"\nConfirmed emails: {confirmed_count}/{submitted_count}" if self.check_confirm_var.get() else ""),
                "RefStorm Bot Finished", 10181046  # Purple color
            )
            self.update_status("🎉 Done! Thank you for using RefStorm!")
            
        self.running = False
        self.paused = False
        self.status_text.set("Ready")
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled")
        self.pause_btn.config(text="⏸ Pause", bootstyle="warning")

# Main application
def main():
    root = tb.Window(themename="darkly")
    app = RefStormApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()