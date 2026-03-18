from moodle.moodle_api import get_user_courses, get_all_users
from get_user_details import build_certificate_lookup, check_user, save_users_to_excel
import pandas as pd
from tqdm import tqdm
import json
import time
import os


certificate_lookup = build_certificate_lookup()


def load_progress_cache():
    """Load previously cached progress data"""
    cache_file = 'progress_cache.json'
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_progress_cache(cache):
    """Save current progress data to cache"""
    cache_file = 'progress_cache.json'
    with open(cache_file, 'w') as f:
        json.dump(cache, f, indent=2)


def get_cache_key(user_id, course_id):
    """Generate cache key for user-course combination"""
    return f"{user_id}_{course_id}"

def safe_get_user_courses(user_id, retries=3):
    for attempt in range(retries):
        try:
            return get_user_courses(user_id)
        except Exception as e:
            print(f"⚠ Retry {attempt+1}/3 for user {user_id}: {e}")
            time.sleep(3)

    print(f"❌ Failed to fetch courses for user {user_id}")
    return []


# Load previous progress cache
progress_cache = load_progress_cache()
new_cache = {}
users_with_progress_change = {}

users = get_all_users()

print("Checking for progress changes...")
for user in tqdm(users):
    if user['id'] == 1:
        continue
    
    courses = safe_get_user_courses(user['id'])
    for course in courses:
        cache_key = get_cache_key(user['id'], course['id'])
        course_name = course.get('fullname', 'UnknownCourse').strip()
        
        # Extract current progress
        current_progress = course.get('progress')
        if current_progress is None:
            current_progress = 0
        
        # Get previous progress from cache
        previous_progress = progress_cache.get(cache_key, 0)
        
        # Update new cache
        new_cache[cache_key] = current_progress
        
        # Check if progress has changed and now >= 90%
        # Decide required progress based on course
        course_lower = course_name.lower()

        if "python" in course_lower:
            required_progress = 70
        else:
            required_progress = 90

        # Check if progress crossed the required threshold
        if current_progress >= required_progress and previous_progress < required_progress:
            # Progress just crossed 90% threshold
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

# Save new cache for next run
save_progress_cache(new_cache)

# Load existing Auto_Certificates_Sent.xlsx if it exists
existing_users = {}
if os.path.exists('Auto_Certificates_Sent.xlsx'):
    xls = pd.ExcelFile('Auto_Certificates_Sent.xlsx')
    for sheet_name in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            existing_users[sheet_name] = df.to_dict('records')
        except:
            pass

# Merge new progress changes with existing data
for course, new_users_list in users_with_progress_change.items():
    if course in existing_users:
        # Get existing user IDs in this course
        existing_ids = {u['ID'] for u in existing_users[course]}
        # Only add new users who aren't already in the sheet
        for new_user in new_users_list:
            if new_user['ID'] not in existing_ids:
                existing_users[course].append(new_user)
    else:
        existing_users[course] = new_users_list

# Save updated Auto_Certificates_Sent.xlsx using the shared function
save_users_to_excel(existing_users)

# Print summary of progress changes
if users_with_progress_change:
    print(f"✓ Users with progress changes (>= 90%, no certificate):")
    for course, users_list in users_with_progress_change.items():
        if users_list:
            print(f"  - {course}: {len(users_list)} user(s)")
else:
    print("No updates needed.")