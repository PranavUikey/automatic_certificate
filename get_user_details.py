from moodle.moodle_api import get_user_courses, get_all_users
import pandas as pd
from tqdm import tqdm
import time
import re
import os


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
    if not os.path.exists("Certificates.xlsx"):
        return {}

    xls = pd.ExcelFile("Certificates.xlsx")
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
# SAVE TO EXCEL
# =====================================
def save_users_to_excel(course_to_users, filename="Auto_Certificates_Sent.xlsx"):
    with pd.ExcelWriter(filename) as writer:
        for course, users_list in course_to_users.items():
            df = pd.DataFrame(users_list)

            # Ensure Certificate_Issued column exists
            if "Certificate_Issued" not in df.columns:
                df["Certificate_Issued"] = 0

            df.to_excel(writer, sheet_name=course[:31], index=False)

    print(f"✓ Excel updated: {filename}")


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

    print("🔍 Loading existing sheet...")

    existing_users = {}
    final_output = {}

    # ---------------------------------
    # LOAD EXISTING EXCEL
    # ---------------------------------
    if os.path.exists("Auto_Certificates_Sent.xlsx"):
        xls_existing = pd.ExcelFile("Auto_Certificates_Sent.xlsx")

        for sheet in xls_existing.sheet_names:
            df_existing = pd.read_excel(xls_existing, sheet_name=sheet)

            if not df_existing.empty:
                # Ensure column exists
                if "Certificate_Issued" not in df_existing.columns:
                    df_existing["Certificate_Issued"] = 0

                final_output[sheet] = df_existing.to_dict("records")
                existing_users[sheet] = set(df_existing["ID"].astype(int).tolist())
            else:
                final_output[sheet] = []
                existing_users[sheet] = set()
    else:
        print("No previous Excel found. Creating new.")

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

            course_progress = course.get("progress", 0)
            if course_progress is None:
                course_progress = 0
            # Set progress threshold
            course_lower = course_name.lower()

            if "python" in course_lower:
                required_progress = 70
            else:
                required_progress = 90

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
                    "Certificate_Issued": 0  # 🔥 Always 0 for NEW entries
                })

                existing_users[course_name].add(user["id"])

    # ---------------------------------
    # SAVE UPDATED FILE
    # ---------------------------------
    save_users_to_excel(final_output)

    print("✅ Sheet updated successfully.")





