import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import ttk

# Function to fetch jobs
def fetch_latest_jobs():
    url = "https://www.net-empregos.com/pesquisa-empregos.asp?page=1&categoria=0&zona=3&tipo=0"
    base_url = "https://www.net-empregos.com"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        job_items = soup.find_all('div', class_='job-item')

        jobs = []
        for item in job_items:
            try:
                job = {}
                title_tag = item.find('h2').find('a', class_='oferta-link')
                job['title'] = title_tag.get_text(strip=True) if title_tag else 'N/A'
                job['url'] = base_url + title_tag['href'] if title_tag else 'N/A'

                date_tag = item.find('i', class_='flaticon-calendar')
                job['date'] = date_tag.find_next(string=True).strip() if date_tag else 'N/A'

                location_tag = item.find('i', class_='flaticon-pin')
                job['location'] = location_tag.find_next(string=True).strip() if location_tag else 'N/A'

                employer_tag = item.find('li', style=lambda s: s and 'font-weight:bold' in s)
                job['employer'] = employer_tag.get_text(strip=True) if employer_tag else 'N/A'

                jobs.append(job)
            except AttributeError:
                continue
        return jobs
    except Exception as e:
        print(f"Error fetching jobs: {e}")
        return []

# Function to update the UI
def update_jobs():
    jobs = fetch_latest_jobs()
    # Clear existing job postings
    for widget in job_frame.winfo_children():
        widget.destroy()
    
    # Add job postings to the UI
    if jobs:
        for idx, job in enumerate(jobs, start=1):
            job_text = (
                f"Title: {job['title']}\n"
                f"Date: {job['date']}\n"
                f"Location: {job['location']}\n"
                f"Employer: {job['employer']}\n"
                f"URL: {job['url']}\n"
            )
            ttk.Label(job_frame, text=job_text, justify="left", anchor="w", wraplength=500).pack(
                fill="x", padx=5, pady=5, anchor="w"
            )
    else:
        ttk.Label(job_frame, text="No jobs available.").pack()

# Tkinter UI setup
root = tk.Tk()
root.title("Latest Job Postings")
root.geometry("600x600")

# Add a refresh button
refresh_button = ttk.Button(root, text="Refresh Page", command=update_jobs)
refresh_button.pack(pady=10)

# Create a frame for the job postings
main_frame = ttk.Frame(root, padding=10)
main_frame.pack(fill="both", expand=True)

# Add a scrollable canvas
canvas = tk.Canvas(main_frame)
scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
job_frame = ttk.Frame(canvas)

job_frame.bind(
    "<Configure>",
    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
)
canvas.create_window((0, 0), window=job_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)

# Pack canvas and scrollbar
canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

# Initial loading of jobs
update_jobs()

# Run the Tkinter main loop
root.mainloop()
