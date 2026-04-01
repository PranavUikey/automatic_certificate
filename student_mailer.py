import pandas as pd
import smtplib
import os
import time
from email.message import EmailMessage
from tqdm import tqdm
import yaml
import boto3
from dotenv import load_dotenv


load_dotenv()

# =========================
# CONFIG
# =========================


EXCEL_KEY = os.getenv('EXCEL_FILE')
EMAIL_ADDRESS = os.getenv('SMTP_EMAIL')
EMAIL_PASSWORD = os.getenv('SMTP_PASSWORD')
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = int(os.getenv('SMTP_PORT'))

DRY_RUN = os.getenv('DRY_RUN', 'True').lower() in ('true', '1', 't')  # Default to True for safety
TEST_EMAIL = os.getenv('ADMIN_EMAIL')

BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')  # S3 bucket name
LOCAL_FILE = os.getenv('EXCEL_TEMP_FILE')  # Local temp file for processing

DELAY_BETWEEN_EMAILS = 2
MAX_RETRIES = 2

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
        print(f"❌ Excel download failed: {e}")
        return False


def upload_excel():
    try:
        s3.upload_file(LOCAL_FILE, BUCKET_NAME, EXCEL_KEY)
        print("☁ Excel uploaded to S3")
    except Exception as e:
        print(f"❌ Upload failed: {e}")


def download_certificate_from_s3(s3_url):
    try:
        key = s3_url.split(".amazonaws.com/")[1]
        temp_file = key.split('/')[-1]

        s3.download_file(BUCKET_NAME, key, temp_file)
        return temp_file

    except Exception as e:
        print(f"❌ Certificate download failed: {e}")
        return None


# =========================
# EMAIL FUNCTION
# =========================
def send_email(to_email, name, s3_url):

    msg = EmailMessage()
    msg['Subject'] = "Your Certificate 🎓"
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email

    with open(os.getenv('EMAIL_TEMPLATE'), 'r') as f:
        html_template = f.read()

    html_content = html_template.replace("{name}", name)
    msg.add_alternative(html_content, subtype='html')

    local_file = download_certificate_from_s3(s3_url)
    if not local_file:
        return False

    with open(local_file, 'rb') as f:
        msg.add_attachment(
            f.read(),
            maintype='application',
            subtype='pdf',
            filename=os.path.basename(local_file)
        )

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)

        os.remove(local_file)
        return True

    except Exception as e:
        print(f"❌ Error sending to {to_email}: {e}")
        return False


# =========================
# MAIN SCRIPT
# =========================
def main():

    if not download_excel():
        return

    # Load ALL sheets
    all_sheets = pd.read_excel(LOCAL_FILE, sheet_name=None, engine="openpyxl")

    for sheet_name, df in all_sheets.items():
        print(f"\n🚀 Processing Course: {sheet_name}")

        # Ensure column exists
        if 'Certificate_Sent' not in df.columns:
            df['Certificate_Sent'] = ""

        for index, row in tqdm(df.iterrows(), total=len(df)):

            name = row.get('Name', '')
            original_email = row.get('Email', '')
            email = TEST_EMAIL if DRY_RUN else original_email
            s3_url = row.get('Certificate_Path', '')

            if not s3_url:
                continue

            # Skip already sent (only in production)
            if not DRY_RUN and df.loc[index, 'Certificate_Sent'] == "Sent":
                continue

            print(f"📧 Sending to: {email} (Original: {original_email})")

            success = False

            for attempt in range(MAX_RETRIES):
                success = send_email(email, name, s3_url)
                if success:
                    break

                print(f"🔁 Retry {attempt+1}")
                time.sleep(2)

            # Update ONLY in production
            if not DRY_RUN:
                df.loc[index, 'Certificate_Sent'] = "Sent" if success else "Failed"

            time.sleep(DELAY_BETWEEN_EMAILS)

            # Dry run: stop after first email
            if DRY_RUN:
                print("🧪 Dry run complete (1 email sent)")
                break

        # Update back into dictionary
        all_sheets[sheet_name] = df

        if DRY_RUN:
            break

    # =========================
    # SAFE SAVE (ONLY PROD)
    # =========================
    if not DRY_RUN:

        temp_file = LOCAL_FILE

        with pd.ExcelWriter(temp_file, engine='openpyxl') as writer:
            for sheet_name, df in all_sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        upload_excel()
        # # Atomic replace
        # os.replace(temp_file, LOCAL_FILE)

        

    print("\n✅ Done without corrupting Excel!")


# =========================
# RUN
# =========================
if __name__ == "__main__":
    main()