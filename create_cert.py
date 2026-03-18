import os
import pandas as pd
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from PyPDF2 import PdfReader, PdfWriter


# =========================
# CONFIG
# =========================
BASE_CERT_DIR = "certificates"
EXCEL_FILE = "Auto_Certificates_Sent.xlsx"

PAGE_WIDTH = 842.25
PAGE_HEIGHT = 604.08


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

    # Verification URL
    c.setFont("Helvetica", 8)
    c.drawString(
        60,
        555,
        f"https://www.aiadventures.in/certificate/?certificate={certificate_id}"
    )

    # Student Name
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(PAGE_WIDTH / 2, 340, name)

    text_width = stringWidth(name, "Helvetica-Bold", 26)
    x_start = (PAGE_WIDTH / 2) - (text_width / 2)
    x_end = (PAGE_WIDTH / 2) + (text_width / 2)

    underline_y = 340 - 5
    c.setLineWidth(1.2)
    c.line(x_start, underline_y, x_end, underline_y)

    # Certificate ID
    c.setFont("Helvetica", 14)
    c.drawString(130, 233, certificate_id)

    # Date
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

    # 🔥 Load all sheets into memory ONCE
    sheets_data = {}

    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)

        if "Certificate_Issued" not in df.columns:
            df["Certificate_Issued"] = 0

        if "Issue_Date" not in df.columns:
            df["Issue_Date"] = ""
        if "Certificate_ID" not in df.columns:
            df["Certificate_ID"] = ""

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

            # 🔥 Skip already issued
            if row["Certificate_Issued"] == 1:
                continue

            try:
                name = str(row["Name"]).strip()
                student_id = int(row["ID"])

                cert_id = generate_certificate_id(sheet_name, student_id)
                issue_date = datetime.now().strftime("%d %b %Y")

                overlay_path = os.path.join(
                    output_folder,
                    f"overlay_{student_id}.pdf"
                )

                safe_name = name.replace(" ", "_")
                final_path = os.path.join(
                    output_folder,
                    f"{safe_name}_{student_id}.pdf"
                )

                create_overlay(
                    output_file=overlay_path,
                    name=name,
                    certificate_id=cert_id,
                    date=issue_date
                )

                generate_final_certificate(
                    template_path,
                    overlay_path,
                    final_path
                )

                os.remove(overlay_path)

                # 🔥 Update in memory only
                sheets_data[sheet_name].loc[index, "Certificate_Issued"] = 1
                sheets_data[sheet_name].loc[index, "Issue_Date"] = today_date
                sheets_data[sheet_name].loc[index, "Certificate_ID"] = cert_id

                print(f"   ✓ Generated: {final_path}")

            except Exception as e:
                print(f"   ❌ Error processing row: {e}")

    # ---------------------------
    # SAFE SAVE (ATOMIC WRITE)
    # ---------------------------
    base_name, ext = os.path.splitext(file_path)
    temp_file = base_name + "_temp" + ext

    with pd.ExcelWriter(temp_file, engine="openpyxl") as writer:
        for sheet, df in sheets_data.items():
            df.to_excel(writer, sheet_name=sheet[:31], index=False)

    os.replace(temp_file, file_path)

    print("\n🎉 All certificates generated and Excel safely updated!")


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    process_excel(EXCEL_FILE)