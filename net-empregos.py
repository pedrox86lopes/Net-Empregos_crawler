"""
Enhanced Job Crawler with improved functionality
Features:
- Rate limiting and session management
- Caching system
- Multithreading for UI responsiveness
- Error handling and logging
- Auto-refresh functionality
- Export to CSV
- Search/filter functionality
- Configuration management
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import pickle
import os
import csv
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class Config:
    """Configuration management class"""

    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.default_config = {
            'refresh_interval': 300,  # 5 minutes in seconds
            'max_jobs_display': 50,
            'cache_duration': 300,  # 5 minutes in seconds
            'request_delay': 1.0,  # Minimum delay between requests
            'timeout': 10,  # Request timeout in seconds
            'auto_refresh': True
        }
        self.settings = self.load_config()
        # Save the config file after loading to ensure it exists with proper format
        self.save_config()

    def load_config(self):
        """Load configuration from file or use defaults"""
        try:
            with open(self.config_file, 'r') as f:
                content = f.read().strip()
                if not content:  # Empty file
                    return self.default_config
                loaded_config = json.loads(content)
                return {**self.default_config, **loaded_config}
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            # If file doesn't exist, is empty, or has invalid JSON, use defaults
            print(f"Config file issue ({e}), using defaults")
            return self.default_config

    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save config: {e}")


class JobCache:
    """Job caching system to reduce server load and improve performance"""

    def __init__(self, cache_file='job_cache.pkl', cache_duration=300):
        self.cache_file = cache_file
        self.cache_duration = cache_duration

    def get_cached_jobs(self):
        """Retrieve cached jobs if they're still valid"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    cache_time = cache_data.get('timestamp')
                    if cache_time and datetime.now() - cache_time < timedelta(seconds=self.cache_duration):
                        return cache_data.get('jobs', [])
            except (pickle.PickleError, KeyError, TypeError):
                # If cache is corrupted, delete it
                self.clear_cache()
        return None

    def cache_jobs(self, jobs):
        """Cache jobs with timestamp"""
        cache_data = {
            'timestamp': datetime.now(),
            'jobs': jobs
        }
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            logging.warning(f"Failed to cache jobs: {e}")

    def clear_cache(self):
        """Clear the job cache"""
        try:
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
        except Exception as e:
            logging.warning(f"Failed to clear cache: {e}")


class RateLimiter:
    """Rate limiter to control request frequency"""

    def __init__(self, min_delay=1.0):
        self.min_delay = min_delay
        self.last_request = 0
        self.lock = threading.Lock()

    def wait(self):
        """Wait if necessary to maintain minimum delay between requests"""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request
            if time_since_last < self.min_delay:
                sleep_time = self.min_delay - time_since_last
                time.sleep(sleep_time)
            self.last_request = time.time()


class JobCrawler:
    """Main job crawler class with enhanced functionality"""

    def __init__(self):
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('job_crawler.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.config = Config()
        self.cache = JobCache(cache_duration=self.config.settings['cache_duration'])
        self.rate_limiter = RateLimiter(min_delay=self.config.settings['request_delay'])

        # Website configuration
        self.url = "https://www.net-empregos.com/pesquisa-empregos.asp?page=1&categoria=0&zona=3&tipo=0"
        self.base_url = "https://www.net-empregos.com"

        # Initialize session with proper headers and retry strategy
        self.session = self._create_session()

        # UI components
        self.root = None
        self.job_frame = None
        self.status_label = None
        self.progress = None
        self.refresh_button = None
        self.search_var = None
        self.auto_refresh_job = None

        # Data storage
        self.current_jobs = []
        self.filtered_jobs = []

        # Create and start UI
        self.create_ui()
        self.initial_load()

    def _create_session(self):
        """Create a requests session with proper headers and retry strategy"""
        session = requests.Session()

        # Add realistic browser headers
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

        # Add retry strategy for robust connection handling
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def fetch_latest_jobs(self) -> List[Dict]:
        """
        Fetch jobs from the website with comprehensive error handling
        Returns: List of job dictionaries
        """
        try:
            # Apply rate limiting
            self.rate_limiter.wait()

            # Check cache first
            cached_jobs = self.cache.get_cached_jobs()
            if cached_jobs:
                self.logger.info("Using cached jobs")
                return cached_jobs

            # Make the request
            self.logger.info("Fetching jobs from website")
            response = self.session.get(
                self.url,
                timeout=self.config.settings['timeout']
            )
            response.raise_for_status()

            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            job_items = soup.find_all('div', class_='job-item')

            if not job_items:
                self.logger.warning("No job items found - website structure may have changed")
                return []

            # Parse each job item
            jobs = []
            for item in job_items:
                job = self.parse_job_item(item)
                if job:
                    jobs.append(job)

            # Cache the results
            self.cache.cache_jobs(jobs)
            self.logger.info(f"Successfully fetched {len(jobs)} jobs")
            return jobs

        except requests.RequestException as e:
            self.logger.error(f"Network error: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return []

    def parse_job_item(self, item) -> Optional[Dict]:
        """
        Parse individual job item with better error handling
        Args:
            item: BeautifulSoup element containing job data
        Returns:
            Dictionary with job data or None if parsing fails
        """
        try:
            job = {}

            # Extract job title and URL
            title_tag = item.find('h2')
            if title_tag:
                link_tag = title_tag.find('a', class_='oferta-link')
                if link_tag:
                    job['title'] = link_tag.get_text(strip=True)
                    href = link_tag.get('href', '')
                    job['url'] = self.base_url + href if href else 'N/A'
                else:
                    job['title'] = title_tag.get_text(strip=True)
                    job['url'] = 'N/A'
            else:
                return None

            # Extract other fields using helper methods
            job['date'] = self.extract_field_by_icon(item, 'flaticon-calendar')
            job['location'] = self.extract_field_by_icon(item, 'flaticon-pin')
            job['employer'] = self.extract_employer(item)

            return job

        except Exception as e:
            self.logger.warning(f"Error parsing job item: {e}")
            return None

    def extract_field_by_icon(self, item, icon_class):
        """
        Helper method to extract fields by icon class
        Args:
            item: BeautifulSoup element
            icon_class: CSS class of the icon
        Returns:
            Extracted text or 'N/A'
        """
        try:
            icon_tag = item.find('i', class_=icon_class)
            if icon_tag:
                # Find the next text node
                next_text = icon_tag.find_next(string=True)
                if next_text:
                    return next_text.strip()
                # Alternative: look for parent's text
                parent = icon_tag.parent
                if parent:
                    text = parent.get_text(strip=True)
                    return text if text else 'N/A'
        except Exception:
            pass
        return 'N/A'

    def extract_employer(self, item):
        """
        Extract employer information from job item
        Args:
            item: BeautifulSoup element
        Returns:
            Employer name or 'N/A'
        """
        try:
            # Look for bold text which usually indicates employer
            employer_tag = item.find('li', style=lambda s: s and 'font-weight:bold' in s)
            if employer_tag:
                return employer_tag.get_text(strip=True)

            # Alternative method: look for company name patterns
            company_elements = item.find_all('li')
            for elem in company_elements:
                text = elem.get_text(strip=True)
                if text and len(text) > 2:  # Basic validation
                    return text

        except Exception:
            pass
        return 'N/A'

    def create_ui(self):
        """Create the main user interface"""
        self.root = tk.Tk()
        self.root.title("Net-Empregos Job Crawler - Latest Postings")
        self.root.geometry("900x800")
        self.root.minsize(600, 400)

        # Configure grid weights for responsive design
        self.root.grid_rowconfigure(3, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Status frame
        self.create_status_frame()

        # Control buttons frame
        self.create_control_frame()

        # Search frame
        self.create_search_frame()

        # Job listings frame with scrollbar
        self.create_job_listings_frame()

        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_status_frame(self):
        """Create status bar with progress indicator"""
        status_frame = ttk.Frame(self.root)
        status_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        status_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.grid(row=0, column=0, sticky="w")

        self.progress = ttk.Progressbar(status_frame, mode='indeterminate')
        self.progress.grid(row=0, column=1, sticky="e", padx=(10, 0))

    def create_control_frame(self):
        """Create control buttons frame"""
        control_frame = ttk.Frame(self.root)
        control_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        self.refresh_button = ttk.Button(
            control_frame,
            text="Refresh Jobs",
            command=self.refresh_jobs
        )
        self.refresh_button.pack(side="left", padx=(0, 5))

        ttk.Button(
            control_frame,
            text="Export to CSV",
            command=self.export_to_csv
        ).pack(side="left", padx=(0, 5))

        ttk.Button(
            control_frame,
            text="Clear Cache",
            command=self.clear_cache
        ).pack(side="left", padx=(0, 5))

        # Auto-refresh checkbox
        self.auto_refresh_var = tk.BooleanVar(value=self.config.settings['auto_refresh'])
        ttk.Checkbutton(
            control_frame,
            text="Auto-refresh",
            variable=self.auto_refresh_var,
            command=self.toggle_auto_refresh
        ).pack(side="right")

    def create_search_frame(self):
        """Create search/filter frame"""
        search_frame = ttk.Frame(self.root)
        search_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        ttk.Label(search_frame, text="Search:").pack(side="left")

        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.filter_jobs)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side="left", padx=5)

        ttk.Button(
            search_frame,
            text="Clear",
            command=lambda: self.search_var.set("")
        ).pack(side="left", padx=5)

        # Job count label
        self.job_count_label = ttk.Label(search_frame, text="Jobs: 0")
        self.job_count_label.pack(side="right")

    def create_job_listings_frame(self):
        """Create scrollable job listings frame"""
        # Main frame for job listings
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        # Create canvas and scrollbar
        canvas = tk.Canvas(main_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        self.job_frame = ttk.Frame(canvas)

        # Configure scrolling
        self.job_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.job_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Grid canvas and scrollbar
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Bind mousewheel to canvas
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def update_status(self, message):
        """Update status label safely from any thread"""
        if self.root:
            self.root.after(0, lambda: self.status_label.config(text=message))

    def show_progress(self, show=True):
        """Show or hide progress bar"""
        if self.root:
            if show:
                self.root.after(0, self.progress.start)
            else:
                self.root.after(0, self.progress.stop)

    def refresh_jobs(self):
        """Refresh jobs in a separate thread to avoid blocking UI"""

        def worker():
            try:
                self.update_status("Refreshing jobs...")
                self.show_progress(True)

                # Disable refresh button during operation
                self.root.after(0, lambda: self.refresh_button.config(state="disabled"))

                # Fetch jobs
                jobs = self.fetch_latest_jobs()

                # Update UI from main thread
                self.root.after(0, self.update_ui_with_jobs, jobs)

            except Exception as e:
                self.logger.error(f"Error in refresh worker: {e}")
                self.root.after(0, lambda: self.update_status(f"Error: {str(e)}"))
            finally:
                self.show_progress(False)
                self.root.after(0, lambda: self.refresh_button.config(state="normal"))

        # Start worker thread
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def update_ui_with_jobs(self, jobs):
        """Update UI with fetched jobs (must be called from main thread)"""
        self.current_jobs = jobs
        self.apply_filters()
        self.update_status(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")

    def apply_filters(self):
        """Apply search filter to jobs"""
        search_term = self.search_var.get().lower() if self.search_var else ""

        if search_term:
            self.filtered_jobs = [
                job for job in self.current_jobs
                if search_term in job.get('title', '').lower() or
                   search_term in job.get('location', '').lower() or
                   search_term in job.get('employer', '').lower()
            ]
        else:
            self.filtered_jobs = self.current_jobs.copy()

        self.display_jobs()

    def filter_jobs(self, *args):
        """Filter jobs based on search term (callback for StringVar)"""
        self.apply_filters()

    def display_jobs(self):
        """Display filtered jobs in the UI"""
        # Clear existing job widgets
        for widget in self.job_frame.winfo_children():
            widget.destroy()

        # Update job count
        self.job_count_label.config(text=f"Jobs: {len(self.filtered_jobs)}")

        if not self.filtered_jobs:
            ttk.Label(
                self.job_frame,
                text="No jobs found matching your criteria.",
                font=("Arial", 12)
            ).pack(pady=20)
            return

        # Display jobs
        for idx, job in enumerate(self.filtered_jobs, start=1):
            self.create_job_widget(job, idx)

    def create_job_widget(self, job, index):
        """Create a widget for displaying a single job"""
        # Create job frame with border
        job_widget = ttk.Frame(self.job_frame, relief="solid", borderwidth=1)
        job_widget.pack(fill="x", padx=5, pady=5)

        # Job title (larger, bold)
        title_label = ttk.Label(
            job_widget,
            text=f"{index}. {job.get('title', 'N/A')}",
            font=("Arial", 12, "bold"),
            foreground="blue"
        )
        title_label.pack(anchor="w", padx=10, pady=(10, 5))

        # Job details frame
        details_frame = ttk.Frame(job_widget)
        details_frame.pack(fill="x", padx=10, pady=(0, 10))

        # Create detail labels
        details = [
            ("Date:", job.get('date', 'N/A')),
            ("Location:", job.get('location', 'N/A')),
            ("Employer:", job.get('employer', 'N/A'))
        ]

        for label_text, value in details:
            detail_frame = ttk.Frame(details_frame)
            detail_frame.pack(fill="x", pady=2)

            ttk.Label(detail_frame, text=label_text, font=("Arial", 9, "bold")).pack(side="left")
            ttk.Label(detail_frame, text=value, font=("Arial", 9)).pack(side="left", padx=(5, 0))

        # URL (clickable if available)
        if job.get('url') and job['url'] != 'N/A':
            url_label = ttk.Label(
                details_frame,
                text=f"URL: {job['url']}",
                font=("Arial", 9),
                foreground="blue",
                cursor="hand2"
            )
            url_label.pack(anchor="w", pady=2)
            url_label.bind("<Button-1>", lambda e, url=job['url']: self.open_url(url))

    def open_url(self, url):
        """Open URL in default web browser"""
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:
            self.logger.error(f"Error opening URL: {e}")
            messagebox.showerror("Error", f"Could not open URL: {e}")

    def export_to_csv(self):
        """Export jobs to CSV file"""
        if not self.filtered_jobs:
            messagebox.showwarning("No Data", "No jobs to export")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Jobs to CSV"
        )

        if filename:
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['title', 'date', 'location', 'employer', 'url']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(self.filtered_jobs)

                messagebox.showinfo("Success", f"Jobs exported to {filename}")
                self.logger.info(f"Exported {len(self.filtered_jobs)} jobs to {filename}")

            except Exception as e:
                error_msg = f"Failed to export: {e}"
                messagebox.showerror("Error", error_msg)
                self.logger.error(error_msg)

    def clear_cache(self):
        """Clear job cache"""
        self.cache.clear_cache()
        self.update_status("Cache cleared")
        messagebox.showinfo("Success", "Cache cleared successfully")

    def toggle_auto_refresh(self):
        """Toggle auto-refresh functionality"""
        self.config.settings['auto_refresh'] = self.auto_refresh_var.get()
        self.config.save_config()

        if self.config.settings['auto_refresh']:
            self.setup_auto_refresh()
        else:
            self.cancel_auto_refresh()

    def setup_auto_refresh(self):
        """Set up automatic refresh"""
        if not self.config.settings['auto_refresh']:
            return

        self.cancel_auto_refresh()  # Cancel any existing auto-refresh

        interval = self.config.settings['refresh_interval'] * 1000  # Convert to milliseconds
        self.auto_refresh_job = self.root.after(interval, self.auto_refresh)

    def cancel_auto_refresh(self):
        """Cancel automatic refresh"""
        if hasattr(self, 'auto_refresh_job') and self.auto_refresh_job:
            self.root.after_cancel(self.auto_refresh_job)
            self.auto_refresh_job = None

    def auto_refresh(self):
        """Automatically refresh jobs"""
        self.logger.info("Auto-refreshing jobs")
        self.refresh_jobs()
        self.setup_auto_refresh()  # Schedule next refresh

    def initial_load(self):
        """Load jobs when application starts"""
        self.update_status("Loading jobs...")
        self.refresh_jobs()

        # Set up auto-refresh if enabled
        if self.config.settings['auto_refresh']:
            self.setup_auto_refresh()

    def on_closing(self):
        """Handle application closing"""
        self.logger.info("Application closing")
        self.cancel_auto_refresh()

        # Save configuration
        self.config.save_config()

        # Close session
        if hasattr(self, 'session'):
            self.session.close()

        # Destroy window
        self.root.destroy()

    def run(self):
        """Start the application"""
        self.logger.info("Starting Job Crawler application")
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.logger.info("Application interrupted by user")
        except Exception as e:
            self.logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.on_closing()


def main():
    """Main entry point"""
    try:
        app = JobCrawler()
        app.run()
    except Exception as e:
        logging.error(f"Failed to start application: {e}")
        print(f"Error: {e}")


if __name__ == "__main__":
    main()