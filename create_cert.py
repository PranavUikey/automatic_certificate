

import os
import pandas as pd
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from PyPDF2 import PdfReader, PdfWriter
import boto3
from dotenv import load_dotenv

load_dotenv()

# =========================
# CONFIG
# =========================

PAGE_WIDTH = 842.25
PAGE_HEIGHT = 604.08

BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')
EXCEL_KEY = os.getenv('EXCEL_FILE')
LOCAL_FILE = os.getenv('EXCEL_TEMP_FILE')

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
# DOWNLOAD TEMPLATE FROM S3
# =========================
def download_template(course_name):
    s3_key = f"certificates/{course_name}/template.pdf"
    local_path = f"template_{course_name}.pdf"

    try:
        s3.download_file(BUCKET_NAME, s3_key, local_path)
        print(f"📥 Template downloaded: {course_name}")
        return local_path
    except Exception as e:
        print(f"❌ Template missing for {course_name}: {e}")
        return None

# =========================
# DOWNLOAD EXCEL
# =========================
def download_excel():
    try:
        s3.download_file(BUCKET_NAME, EXCEL_KEY, LOCAL_FILE)
        print("📥 Excel downloaded from S3")
        return True
    except Exception as e:
        print(f"⚠ No Excel found: {e}")
        return False

# =========================
# UPLOAD CERTIFICATE
# =========================
def upload_certificate(file_path, course, year, month):
    file_name = os.path.basename(file_path)
    s3_key = f"certificates/{course}/{year}/{month}/{file_name}"

    try:
        s3.upload_file(file_path, BUCKET_NAME, s3_key)

        url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{s3_key}"
        print(f"   ☁ Uploaded: {url}")

        return url
    except Exception as e:
        print(f"   ❌ Upload failed: {e}")
        return None

# =========================
# UPLOAD EXCEL
# =========================
def upload_excel():
    try:
        s3.upload_file(LOCAL_FILE, BUCKET_NAME, EXCEL_KEY)
        print("☁ Excel uploaded")
    except Exception as e:
        print(f"❌ Excel upload failed: {e}")

# =========================
# CERTIFICATE ID
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

    prefix = course_prefix_map.get(course_name.strip(), "XX")
    month_year = datetime.now().strftime("%m%y")

    return f"{prefix}-{month_year}-{int(student_id)}"

# =========================
# CREATE OVERLAY
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
# MAIN PROCESS
# =========================
def process_excel(file_path):

    if not os.path.exists(file_path):
        print("❌ Excel not found")
        return

    xls = pd.ExcelFile(file_path)

    current_year = datetime.now().strftime("%Y")
    current_month = datetime.now().strftime("%B")
    today_date = datetime.now().strftime("%d %b %Y")

    sheets_data = {}

    # Prepare sheets
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)

        for col in ["Certificate_Issued", "Issue_Date", "Certificate_ID", "Certificate_Path"]:
            if col not in df.columns:
                df[col] = "" if col != "Certificate_Issued" else 0

        sheets_data[sheet] = df

    # ---------------------------
    # PROCESS EACH COURSE
    # ---------------------------
    for sheet_name, df in sheets_data.items():

        if df.empty:
            continue

        course_name = sheet_name.strip()

        template_path = download_template(course_name)

        if not template_path:
            continue

        output_folder = os.path.join("temp_output", course_name, current_year, current_month)
        os.makedirs(output_folder, exist_ok=True)

        print(f"\n📘 Processing: {course_name}")

        for index, row in df.iterrows():

            if row["Certificate_Issued"] == 1:
                continue

            try:
                name = str(row["Name"]).strip()
                student_id = int(row["ID"])

                cert_id = generate_certificate_id(course_name, student_id)

                overlay_path = os.path.join(output_folder, f"overlay_{student_id}.pdf")
                final_path = os.path.join(output_folder, f"{name.replace(' ', '_')}_{student_id}.pdf")

                create_overlay(overlay_path, name, cert_id, today_date)
                generate_final_certificate(template_path, overlay_path, final_path)

                os.remove(overlay_path)

                # Upload
                s3_url = upload_certificate(final_path, course_name, current_year, current_month)

                if not s3_url:
                    continue

                os.remove(final_path)

                # Update Excel
                sheets_data[sheet_name].loc[index, "Certificate_Issued"] = 1
                sheets_data[sheet_name].loc[index, "Issue_Date"] = today_date
                sheets_data[sheet_name].loc[index, "Certificate_ID"] = cert_id
                sheets_data[sheet_name].loc[index, "Certificate_Path"] = s3_url

                print("   ✓ Done")

            except Exception as e:
                print(f"   ❌ Error: {e}")

        # Delete template after course
        if os.path.exists(template_path):
            os.remove(template_path)

    # Save Excel
    with pd.ExcelWriter(LOCAL_FILE, engine="openpyxl") as writer:
        for sheet, df in sheets_data.items():
            df.to_excel(writer, sheet_name=sheet[:31], index=False)

    upload_excel()

    print("\n🎉 All certificates generated & uploaded!")

# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    download_excel()
    process_excel(LOCAL_FILE)