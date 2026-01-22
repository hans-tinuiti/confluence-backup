import os
import json
import shutil
import datetime
from atlassian import Confluence
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==========================================
# 🔐 1. CREDENTIALS
# ==========================================
CONFLUENCE_URL = 'https://tinuiti.atlassian.net/'
CONFLUENCE_EMAIL = os.environ.get('CONFLUENCE_EMAIL')
CONFLUENCE_API_TOKEN = os.environ.get('CONFLUENCE_API_TOKEN')
SPACE_KEY = "HFS"

# Destination Folder ID (Your updated one)
FOLDER_ID = '1CxzhAAlx4ekH1il9DVoJsUeKSEGpPI6K'

GCP_SA_KEY = os.environ.get('GCP_SA_KEY')
if not GCP_SA_KEY:
    raise ValueError("Missing GCP_SA_KEY (check GitHub Secrets)")

# ==========================================
# 🛠️ SERVICE SETUP
# ==========================================
def get_confluence():
    return Confluence(url=CONFLUENCE_URL, username=CONFLUENCE_EMAIL, password=CONFLUENCE_API_TOKEN)

def get_drive_service():
    print("🔑 Authenticating Service Account...")
    creds_dict = json.loads(GCP_SA_KEY)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def upload_zip(service, filepath, filename, folder_id):
    # 1. Search (Supports Shared Drives)
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(
        q=query, 
        fields="files(id)", 
        includeItemsFromAllDrives=True, 
        supportsAllDrives=True
    ).execute()
    files = results.get('files', [])

    media = MediaFileUpload(filepath, mimetype='application/zip')

    # 2. Upload/Update (Supports Shared Drives)
    if files:
        service.files().update(
            fileId=files[0]['id'], 
            media_body=media, 
            supportsAllDrives=True
        ).execute()
        print(f"      🔄 Overwrote existing backup: {filename}")
    else:
        metadata = {'name': filename, 'parents': [folder_id]}
        service.files().create(
            body=metadata, 
            media_body=media, 
            supportsAllDrives=True
        ).execute()
        print(f"      ✅ Uploaded new backup: {filename}")

# ==========================================
# 🚀 MAIN LOGIC
# ==========================================
def run_backup():
    confluence = get_confluence()
    drive = get_drive_service()
    
    # --- NAMING CHANGE HERE ---
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    backup_name = f"RSM_Confluence_Daily_Backup_{date_str}"
    
    # We create a local folder with this name first
    os.makedirs(backup_name, exist_ok=True)
    
    print(f"🚀 Starting Backup for Space: {SPACE_KEY}")

    # Loop through pages 
    start = 0
    limit = 50
    total_pages = 0
    
    while True:
        print(f"   ...downloading batch {start} - {start + limit}...")
        pages = confluence.get_all_pages_from_space(
            SPACE_KEY, start=start, limit=limit, expand='body.storage'
        )
        
        if not pages:
            break
            
        for page in pages:
            # Sanitize Title
            safe_title = "".join([c for c in page['title'] if c.isalpha() or c.isdigit() or c==' ']).rstrip()
            page_id = page['id']
            content = page['body']['storage']['value']
            
            filename = f"{page_id} - {safe_title}.html"
            file_path = os.path.join(backup_name, filename)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"\n")
                f.write(content)
            
            total_pages += 1
            
        start += limit

    print(f"📦 Downloaded {total_pages} pages.")

    # Zip the folder
    print("🗜️ Zipping files...")
    shutil.make_archive(backup_name, 'zip', backup_name)
    zip_filename = f"{backup_name}.zip"
    
    # Upload
    print(f"☁️ Uploading {zip_filename}...")
    upload_zip(drive, zip_filename, zip_filename, FOLDER_ID)
    
    print("🎉 Backup Complete.")

if __name__ == "__main__":
    run_backup()
