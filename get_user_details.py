from moodle.moodle_api import get_user_courses, get_all_users
import pandas as pd
from tqdm import tqdm
import time
import re
import os
import yaml
import boto3
from dotenv import load_dotenv

load_dotenv()

# =========================
# CONFIG
# =========================


EXCEL_KEY = os.getenv('EXCEL_KEY')  # S3 key (e.g. certificates/Auto_Certificates.xlsx)
BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')  # S3 bucket name

LOCAL_FILE = os.getenv('EXCEL_TEMP_FILE')  # Local temp file for processing

CERTIFICATE_SHEET = os.getenv('EXCEL_CERTIFICATES_SHEET')  # Local path to certificates Excel (for lookup)

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
        print(f"❌ Download failed: {e}")
        return False


def upload_excel():
    try:
        s3.upload_file(LOCAL_FILE, BUCKET_NAME, EXCEL_KEY)
        print("☁ Excel uploaded to S3")
    except Exception as e:
        print(f"❌ Upload failed: {e}")


# =====================================
# CLEAN NAME FUNCTION
# =====================================
def clean_name(name):
    if not isinstance(name, str):
        return ""

    name = re.sub(r'[^\w\s]', '', name)
    name = name.strip()
    parts = name.split()

    if len(parts) == 0:
        return ""

    if len(parts) == 1:
        return parts[0].lower()

    return parts[0].lower() + parts[-1].lower()


# =====================================
# BUILD CERTIFICATE LOOKUP
# =====================================
def build_certificate_lookup():
    if not os.path.exists(CERTIFICATE_SHEET):
        return {}

    xls = pd.ExcelFile(CERTIFICATE_SHEET)
    name_to_sheet = {}

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)

        for _, row in df.iterrows():
            if "Name" not in row or pd.isna(row["Name"]):
                continue

            normalized = clean_name(row["Name"])
            if not normalized:
                continue

            if normalized not in name_to_sheet:
                name_to_sheet[normalized] = []

            name_to_sheet[normalized].append(sheet_name.strip())

    return name_to_sheet


certificate_lookup = build_certificate_lookup()


# =====================================
# CHECK IF USER ALREADY HAS CERTIFICATE
# =====================================
def check_user(used_name: str, course_name: str):
    normalized = clean_name(used_name)
    sheets = certificate_lookup.get(normalized, [])

    course_lower = course_name.lower()

    for sheet in sheets:
        if sheet.lower() in course_lower or course_lower in sheet.lower():
            return True

    return False


# =====================================
# SAVE TO EXCEL (LOCAL TEMP)
# =====================================
def save_users_to_excel(course_to_users,filename = LOCAL_FILE):
    with pd.ExcelWriter(filename) as writer:
        for course, users_list in course_to_users.items():
            df = pd.DataFrame(users_list)

            if "Certificate_Issued" not in df.columns:
                df["Certificate_Issued"] = 0

            df.to_excel(writer, sheet_name=course[:31], index=False)

    print("💾 Excel updated locally")


def safe_get_user_courses(user_id, retries=3):
    for attempt in range(retries):
        try:
            return get_user_courses(user_id)
        except Exception as e:
            print(f"⚠ Retry {attempt+1}/3 for user {user_id}: {e}")
            time.sleep(3)

    print(f"❌ Failed to fetch courses for user {user_id}")
    return []


# =====================================
# MAIN EXECUTION
# =====================================
if __name__ == "__main__":

    print("🚀 Starting Moodle → S3 Sync")

    # STEP 1: Download Excel
    if not download_excel():
        print("No previous Excel found. Creating new.")
        existing_users = {}
    else:
        existing_users = {}

    final_output = {}

    # ---------------------------------
    # LOAD EXISTING EXCEL
    # ---------------------------------
    if os.path.exists(LOCAL_FILE):
        xls_existing = pd.ExcelFile(LOCAL_FILE)

        for sheet in xls_existing.sheet_names:
            df_existing = pd.read_excel(xls_existing, sheet_name=sheet)

            if not df_existing.empty:
                if "Certificate_Issued" not in df_existing.columns:
                    df_existing["Certificate_Issued"] = 0

                final_output[sheet] = df_existing.to_dict("records")
                existing_users[sheet] = set(df_existing["ID"].astype(int).tolist())
            else:
                final_output[sheet] = []
                existing_users[sheet] = set()

    # ---------------------------------
    # SCAN MOODLE
    # ---------------------------------
    print("🔄 Scanning Moodle users...")
    users = get_all_users()

    for user in tqdm(users):

        if user["id"] == 1:
            continue

        courses = safe_get_user_courses(user["id"])

        for course in courses:
            course_name = course.get("fullname", "UnknownCourse").strip()

            has_certificate = check_user(user["fullname"], course_name)

            course_progress = course.get("progress", 0) or 0

            course_lower = course_name.lower()
            required_progress = 70 if "python" in course_lower else 90

            if not has_certificate and course_progress >= required_progress:

                if course_name in existing_users and user["id"] in existing_users[course_name]:
                    continue

                if course_name not in final_output:
                    final_output[course_name] = []
                    existing_users[course_name] = set()

                final_output[course_name].append({
                    "ID": user["id"],
                    "Name": user["fullname"],
                    "Email": user["email"],
                    "Progress": f"{course_progress:.2f}%",
                    "Certificate_Issued": 0
                })

                existing_users[course_name].add(user["id"])

    # ---------------------------------
    # SAVE + UPLOAD
    # ---------------------------------
    save_users_to_excel(final_output)
    upload_excel()

    print("✅ Sheet updated successfully in S3.")