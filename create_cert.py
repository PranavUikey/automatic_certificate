import os
import pandas as pd
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from PyPDF2 import PdfReader, PdfWriter
import yaml
import boto3
from dotenv import load_dotenv


load_dotenv()


# =========================
# CONFIG
# =========================

BASE_CERT_DIR = os.getenv('CERTIFICATES_DIRECTORY')  

PAGE_WIDTH = 842.25
PAGE_HEIGHT = 604.08


# =========================
# AWS S3 CONFIG
# =========================
s3 = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION')
)

BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')  # S3 bucket name
EXCEL_KEY = os.getenv('EXCEL_FILE')   # e.g. certificates/Auto_Certificates_Sent.xlsx

LOCAL_FILE = os.getenv('EXCEL_TEMP_FILE')  # Local temp file for processing
# =========================
# S3 UPLOAD FUNCTION
# =========================

def download_excel():
    try:
        s3.download_file(BUCKET_NAME, EXCEL_KEY, LOCAL_FILE)
        print("📥 Excel downloaded from S3")
        return True
    except Exception as e:
        print(f"⚠ No existing Excel found on S3: {e}")
        return False

def upload_certificate(file_path, course, year, month):

    file_name = os.path.basename(file_path)
    s3_key = f"certificates/{course}/{year}/{month}/{file_name}"

    try:

        s3.upload_file(file_path, BUCKET_NAME, s3_key)

        url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{s3_key}"

        print(f"   ☁ Uploaded to S3: {url}")
        os.remove(s3_key)
        return url

    except Exception as e:
        print(f"   ❌ S3 upload failed: {e}")
        return None

def upload_excel():
    try:
        s3.upload_file(LOCAL_FILE, BUCKET_NAME, EXCEL_KEY)
        print("☁ Excel uploaded to S3")
    except Exception as e:
        print(f"❌ Upload failed: {e}")

# =========================
# CERTIFICATE ID GENERATOR
# =========================
def generate_certificate_id(course_name, student_id):

    course_prefix_map = {
        "Python": "PY",
        "Data Science": "DS",
        "Gen AI": "AI",
        "Machine Learning": "ML",
        "Deep Learning": "DL",
        "SQL": "SQ"
    }

    course_prefix = course_prefix_map.get(course_name.strip(), "XX")

    now = datetime.now()
    month_year = now.strftime("%m%y")

    return f"{course_prefix}-{month_year}-{int(student_id)}"


# =========================
# OVERLAY CREATOR
# =========================
def create_overlay(output_file, name, certificate_id, date):

    c = canvas.Canvas(output_file, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))

    name = name.title()

    c.setFont("Helvetica", 8)
    c.drawString(
        60,
        555,
        f"https://www.aiadventures.in/certificate/?certificate={certificate_id}"
    )

    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(PAGE_WIDTH / 2, 340, name)

    text_width = stringWidth(name, "Helvetica-Bold", 26)
    x_start = (PAGE_WIDTH / 2) - (text_width / 2)
    x_end = (PAGE_WIDTH / 2) + (text_width / 2)

    c.setLineWidth(1.2)
    c.line(x_start, 335, x_end, 335)

    c.setFont("Helvetica", 14)
    c.drawString(130, 233, certificate_id)
    c.drawString(660, 227, date)

    c.save()


# =========================
# MERGE TEMPLATE + OVERLAY
# =========================
def generate_final_certificate(template_file, overlay_file, output_file):

    template = PdfReader(template_file)
    overlay = PdfReader(overlay_file)

    writer = PdfWriter()

    page = template.pages[0]
    page.merge_page(overlay.pages[0])
    writer.add_page(page)

    with open(output_file, "wb") as f:
        writer.write(f)


# =========================
# MAIN PROCESSING FUNCTION
# =========================
def process_excel(file_path):

    if not os.path.exists(file_path):
        print("❌ Excel file not found.")
        return

    xls = pd.ExcelFile(file_path)

    current_year = datetime.now().strftime("%Y")
    current_month = datetime.now().strftime("%B")
    today_date = datetime.now().strftime("%d %b %Y")

    sheets_data = {}

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)

        if "Certificate_Issued" not in df.columns:
            df["Certificate_Issued"] = 0

        if "Issue_Date" not in df.columns:
            df["Issue_Date"] = ""

        if "Certificate_ID" not in df.columns:
            df["Certificate_ID"] = ""

        if "Certificate_Path" not in df.columns:
            df["Certificate_Path"] = ""

        sheets_data[sheet] = df

    # ---------------------------
    # PROCESS CERTIFICATES
    # ---------------------------
    for sheet_name, df in sheets_data.items():

        if df.empty:
            continue

        course_folder = os.path.join(BASE_CERT_DIR, sheet_name.strip())
        template_path = os.path.join(course_folder, "template.pdf")

        if not os.path.exists(template_path):
            print(f"⚠ Template not found for course: {sheet_name}")
            continue

        output_folder = os.path.join(course_folder, current_year, current_month)
        os.makedirs(output_folder, exist_ok=True)

        print(f"\n📘 Processing Course: {sheet_name}")

        for index, row in df.iterrows():
            

            if row["Certificate_Issued"] == 1:
                continue

            try:
                name = str(row["Name"]).strip()
                student_id = int(row["ID"])

                cert_id = generate_certificate_id(sheet_name, student_id)
                issue_date = datetime.now().strftime("%d %b %Y")

                overlay_path = os.path.join(output_folder, f"overlay_{student_id}.pdf")
                safe_name = name.replace(" ", "_")
                final_path = os.path.join(output_folder, f"{safe_name}_{student_id}.pdf")

                create_overlay(overlay_path, name, cert_id, issue_date)
                generate_final_certificate(template_path, overlay_path, final_path)

                os.remove(overlay_path)

                # 🚀 UPLOAD TO S3
                s3_url = upload_certificate(final_path, sheet_name, current_year, current_month)

                if not s3_url:
                    print("   ❌ Skipping due to upload failure")
                    continue

                # 🧹 Delete local file after upload
                os.remove(final_path)

                # 🔥 Update Excel
                sheets_data[sheet_name].loc[index, "Certificate_Issued"] = 1
                sheets_data[sheet_name].loc[index, "Issue_Date"] = today_date
                sheets_data[sheet_name].loc[index, "Certificate_ID"] = cert_id
                sheets_data[sheet_name].loc[index, "Certificate_Path"] = s3_url

                print(f"   ✓ Uploaded + Saved URL")
            except Exception as e:
                print(f"   ❌ Error processing row: {e}")

    # ---------------------------
    # SAFE SAVE
    # ---------------------------

    with pd.ExcelWriter(LOCAL_FILE, engine="openpyxl") as writer:
        for sheet, df in sheets_data.items():
            df.to_excel(writer, sheet_name=sheet[:31], index=False)
    upload_excel()
    # os.remove(BASE_CERT_DIR)
    print("\n🎉 Certificates uploaded to S3 and Excel updated!")


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    process_excel(LOCAL_FILE)


