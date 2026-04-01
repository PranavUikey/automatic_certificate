import os
import zipfile
import smtplib
from email.message import EmailMessage
import boto3
from dotenv import load_dotenv

load_dotenv()

# =========================
# CONFIG
# =========================

BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')
EXCEL_KEY = os.getenv('EXCEL_FILE')
CACHE_KEY = os.getenv('ORIG_JSON_FILE')

EMAIL_ADDRESS = os.getenv('SMTP_USERNAME')
EMAIL_PASSWORD = os.getenv('SMTP_PASSWORD')
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT'))

ADMIN_EMAIL = os.getenv('SMTP_ADMIN_EMAIL')

# =========================
# S3 SETUP
# =========================
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION')
)

# =========================
# DOWNLOAD COURSE FOLDERS
# =========================
def download_course_folders():
    course_files = {}

    paginator = s3.get_paginator('list_objects_v2')

    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix="certificates/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]

            if not key.endswith(".pdf"):
                continue

            parts = key.split("/")
            if len(parts) < 2:
                continue

            course = parts[1]

            if course not in course_files:
                course_files[course] = []

            course_files[course].append(key)

    for course, keys in course_files.items():
        os.makedirs(course, exist_ok=True)
        print(f"\n📘 Downloading {course}")

        for key in keys:
            filename = key.split("/")[-1]
            local_path = os.path.join(course, filename)
            s3.download_file(BUCKET_NAME, key, local_path)

    return list(course_files.keys())

# =========================
# ZIP COURSE FOLDERS
# =========================
def zip_course_folders(course_list):
    zip_files = []

    for course in course_list:
        zip_name = f"{course}.zip"
        print(f"📦 Zipping {course}")

        with zipfile.ZipFile(zip_name, "w") as zipf:
            for root, _, files in os.walk(course):
                for file in files:
                    full_path = os.path.join(root, file)
                    zipf.write(full_path, file)

        zip_files.append(zip_name)

    return zip_files

# =========================
# UPLOAD + PRESIGNED URL
# =========================
def upload_and_get_link(zip_file):
    key = f"weekly_reports/{zip_file}"

    s3.upload_file(zip_file, BUCKET_NAME, key)

    url = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': BUCKET_NAME, 'Key': key},
        ExpiresIn=604800
    )

    return url

# =========================
# CLEAN LOCAL COURSE FOLDERS
# =========================
def cleanup_course_folders(course_list):
    for course in course_list:
        for root, _, files in os.walk(course):
            for file in files:
                os.remove(os.path.join(root, file))
        os.rmdir(course)

# =========================
# DOWNLOAD EXCEL + CACHE
# =========================
def download_excel_and_cache():
    excel_local = os.getenv('EXCEL_TEMP_FILE')
    cache_local = os.getenv('JSON_TEMP_FILE')

    try:
        s3.download_file(BUCKET_NAME, EXCEL_KEY, excel_local)
    except:
        pass

    try:
        s3.download_file(BUCKET_NAME, CACHE_KEY, cache_local)
    except:
        pass

    return excel_local, cache_local

# =========================
# SEND EMAIL
# =========================
def send_admin_email_links(zip_links):
    msg = EmailMessage()
    msg["Subject"] = "Weekly Certificates 📦"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ADMIN_EMAIL

    body = "Weekly Certificates Download Links (valid 7 days):\n\n"

    for name, link in zip_links.items():
        body += f"{name}: {link}\n"

    msg.set_content(body)

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

    print("📧 Email sent with links")

# =========================
# ✅ CLEAN S3 CERTIFICATES (UPDATED LOGIC)
# =========================
def clean_certificates_folder():

    paginator = s3.get_paginator('list_objects_v2')

    objects_to_delete = []

    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix="certificates/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]

            # Skip root
            if key == "certificates/":
                continue

            parts = key.split("/")

            # KEEP only: certificates/course_name/template.pdf
            if len(parts) == 3 and parts[2] == "template.pdf":
                continue

            # DELETE everything else
            objects_to_delete.append({"Key": key})

    if objects_to_delete:
        s3.delete_objects(
            Bucket=BUCKET_NAME,
            Delete={"Objects": objects_to_delete}
        )

    print("🧹 Cleaned certificates (templates preserved)")

# =========================
# CLEAN LOCAL FILES
# =========================
def cleanup_local(files):
    for f in files:
        if f and os.path.exists(f):
            os.remove(f)

# =========================
# MAIN JOB
# =========================
def weekly_job():

    print("🚀 Weekly Job Started")

    courses = download_course_folders()

    if not courses:
        print("⚠ No certificates found")
        return

    course_zips = zip_course_folders(courses)
    cleanup_course_folders(courses)

    excel_file, cache_file = download_excel_and_cache()

    zip_links = {}

    for zip_file in course_zips:
        link = upload_and_get_link(zip_file)
        zip_links[zip_file] = link

    try:
        send_admin_email_links(zip_links)
        clean_certificates_folder()

    except Exception as e:
        print(f"❌ Email failed: {e}")
        print("⚠ Skipping deletion")

    cleanup_local(course_zips + [excel_file, cache_file])

    print("🎉 Weekly job completed")

# =========================
# RUN
# =========================
if __name__ == "__main__":
    weekly_job()