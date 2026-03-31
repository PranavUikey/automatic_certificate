from moodle.moodle_api import get_user_courses, get_all_users
from get_user_details import build_certificate_lookup, check_user, save_users_to_excel
import pandas as pd
from tqdm import tqdm
import json
import time
import os
import yaml
import boto3
from dotenv import load_dotenv

load_dotenv()


# =========================
# CONFIG
# =========================
EXCEL_KEY = os.getenv('EXCEL_FILE')  
BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')  # S3 bucket name

LOCAL_FILE = os.getenv('EXCEL_TEMP_FILE')  # Local temp file for processing

# =========================
# S3 SETUP
# =========================
s3 = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION')
)


# =========================
# S3 FUNCTIONS
# =========================
def download_excel():
    try:
        s3.download_file(BUCKET_NAME, EXCEL_KEY, LOCAL_FILE)
        print("📥 Excel downloaded from S3")
        return True
    except Exception as e:
        print(f"⚠ No existing Excel found on S3: {e}")
        return False


def upload_excel():
    try:
        s3.upload_file(LOCAL_FILE, BUCKET_NAME, EXCEL_KEY)
        print("☁ Excel uploaded to S3")
    except Exception as e:
        print(f"❌ Upload failed: {e}")


# =========================
# CACHE FUNCTIONS
# =========================
cache_file = os.getenv('ORIG_JSON_FILE')  # S3 key for cache (e.g. certificates/progress_cache.json)
local_cache = os.getenv('JSON_TEMP_FILE')  # Local temp file for cache


def load_progress_cache():

    if os.path.exists(local_cache):
        try:
            with open(local_cache, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def download_cache():
    try:
        s3.download_file(BUCKET_NAME, cache_file, local_cache)
        print('Cache download from s3')
    except:
        print('No existing cache found(first run)')



def save_progress_cache(cache):
    with open(local_cache, 'w') as f:
        json.dump(cache, f, indent=2)

def upload_cache():
    try:
        s3.upload_file(local_cache, BUCKET_NAME, cache_file)
        print('Cache upload to s3')
    except Exception as e:
        print('Cache upload failed: {e}')




def get_cache_key(user_id, course_id):
    return f"{user_id}_{course_id}"


def safe_get_user_courses(user_id, retries=3):
    for attempt in range(retries):
        try:
            return get_user_courses(user_id)
        except Exception as e:
            print(f"⚠ Retry {attempt+1}/3 for user {user_id}: {e}")
            time.sleep(3)
    return []


# =========================
# MAIN EXECUTION
# =========================
if __name__ == "__main__":

    print("🚀 Starting Moodle → S3 Sync")

    certificate_lookup = build_certificate_lookup()

    # STEP 1: Download Excel
    file_exists = download_excel()

    existing_users = {}

    # STEP 2: Load existing Excel
    if file_exists and os.path.exists(LOCAL_FILE):
        xls = pd.ExcelFile(LOCAL_FILE)

        for sheet_name in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                existing_users[sheet_name] = df.to_dict('records')
            except:
                existing_users[sheet_name] = {}
    else:
        print("📄 Creating new Excel structure")

    # =========================
    # LOAD CACHE
    # =========================
    download_cache()
    progress_cache = load_progress_cache()
    new_cache = {}
    users_with_progress_change = {}

    users = get_all_users()

    print("🔄 Checking for progress changes...")

    for user in tqdm(users):

        if user['id'] == 1:
            continue

        courses = safe_get_user_courses(user['id'])

        for course in courses:
            cache_key = get_cache_key(user['id'], course['id'])
            course_name = course.get('fullname', 'UnknownCourse').strip()

            current_progress = course.get('progress') or 0
            previous_progress = progress_cache.get(cache_key, 0)
            new_cache[cache_key] = current_progress

            course_lower = course_name.lower()
            required_progress = 70 if "python" in course_lower else 90

            # 🔥 Only trigger when threshold crossed
            if current_progress >= required_progress and previous_progress < required_progress:

                has_certificate = check_user(user['fullname'], course_name)

                if not has_certificate:

                    if course_name not in users_with_progress_change:
                        users_with_progress_change[course_name] = []

                    users_with_progress_change[course_name].append({
                        'ID': user['id'],
                        'Name': user['fullname'],
                        'Email': user['email'],
                        'Progress': f"{current_progress}%",
                        'Previous_Progress': f"{previous_progress}%"
                    })

    # SAVE CACHE
    save_progress_cache(new_cache)
    upload_cache()

    # =========================
    # MERGE DATA
    # =========================
    for course, new_users_list in users_with_progress_change.items():

        if course in existing_users:
            existing_ids = {u['ID'] for u in existing_users[course]}

            for new_user in new_users_list:
                if new_user['ID'] not in existing_ids:
                    existing_users[course].append(new_user)

        else:
            existing_users[course] = new_users_list

    # =========================
    # SAVE + UPLOAD
    # =========================
    save_users_to_excel(existing_users, filename=LOCAL_FILE)
    upload_excel()

    # =========================
    # SUMMARY
    # =========================
    if users_with_progress_change:
        print("✓ Users with progress changes:")
        for course, users_list in users_with_progress_change.items():
            print(f"  - {course}: {len(users_list)} user(s)")
    else:
        print("No updates needed.")

    print("\n🎉 Sync completed (S3 + Moodle)")