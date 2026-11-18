import time
import os
import requests
import pymupdf
import openpyxl
from PIL import Image, ImageDraw, ImageFont

API_URL = "http://127.0.0.1:8000"


def load_font(size=24):
    """Load a crisp font on Windows/Linux so Tesseract OCR reads cleanly."""
    for font_name in ["arial.ttf", "DejaVuSans.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def create_test_files(run_id):
    """Generate 4 sample invoice files (CSV, Excel, PDF, PNG) with ground truth."""
    test_cases = [
        {
            "format": "CSV",
            "filename": "eval_sample.csv",
            "mime": "text/csv",
            "expected": {
                "invoice_number": f"INV-CSV-{run_id}",
                "supplier_name": "TechNova Supplies",
                "total": 1050.0,
            },
        },
        {
            "format": "Excel",
            "filename": "eval_sample.xlsx",
            "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "expected": {
                "invoice_number": f"INV-XLSX-{run_id}",
                "supplier_name": "Apex Office Gear",
                "total": 2200.0,
            },
        },
        {
            "format": "PDF",
            "filename": "eval_sample.pdf",
            "mime": "application/pdf",
            "expected": {
                "invoice_number": f"INV-PDF-{run_id}",
                "supplier_name": "Global Cloud Corp",
                "total": 1650.0,
            },
        },
        {
            "format": "Image (OCR)",
            "filename": "eval_sample.png",
            "mime": "image/png",
            "expected": {
                "invoice_number": f"INV-IMG-{run_id}",
                "supplier_name": "Metro Logistics",
                "total": 880.0,
            },
        },
    ]

    # 1. Create CSV
    with open("eval_sample.csv", "w", encoding="utf-8") as f:
        f.write(f"Invoice Number,INV-CSV-{run_id}\n")
        f.write("Invoice Date,2026-11-15\n")
        f.write("Supplier,TechNova Supplies\n")
        f.write("Customer,Dhaka Tech Ltd\n")
        f.write("Description,Quantity,Unit Price,Total\n")
        f.write("Business Laptop,1,1000,1000\n")
        f.write("Subtotal,,,1000\n")
        f.write("Tax,,,50\n")
        f.write("Total,,,1050\n")
        f.write("Currency,USD\n")

    # 2. Create Excel (.xlsx)
    wb = openpyxl.Workbook()
    ws = wb.active
    rows = [
        ["Invoice Number", f"INV-XLSX-{run_id}"],
        ["Invoice Date", "2026-11-16"],
        ["Supplier", "Apex Office Gear"],
        ["Customer", "Prime Solutions"],
        ["Description", "Quantity", "Unit Price", "Total"],
        ["Ergonomic Desk", 2, 1000, 2000],
        ["Subtotal", "", "", 2000],
        ["Tax", "", "", 200],
        ["Total", "", "", 2200],
        ["Currency", "USD"],
    ]
    for row in rows:
        ws.append(row)
    wb.save("eval_sample.xlsx")

    # 3. Create PDF (.pdf)
    pdf_doc = pymupdf.open()
    page = pdf_doc.new_page()
    pdf_text = (
        f"INVOICE\n"
        f"Invoice Number: INV-PDF-{run_id}\n"
        f"Invoice Date: 2026-11-17\n"
        f"Supplier: Global Cloud Corp\n"
        f"Customer: NextGen Systems\n\n"
        f"Item: Annual Cloud Server Hosting | Qty: 1 | Unit Price: 1500 | Total: 1500\n\n"
        f"Subtotal: 1500\n"
        f"Tax: 150\n"
        f"Total: 1650 USD\n"
    )
    page.insert_text((50, 60), pdf_text, fontsize=12)
    pdf_doc.save("eval_sample.pdf")
    pdf_doc.close()

    # 4. Create Image (.png) for OCR
    img = Image.new("RGB", (900, 520), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = load_font(26)
    img_lines = [
        "INVOICE",
        f"Invoice Number: INV-IMG-{run_id}",
        "Invoice Date: 2026-11-18",
        "Supplier: Metro Logistics",
        "Customer: Delta Retail",
        "Item: Freight Delivery Service - Qty 1 - Price 800 - Total 800",
        "Subtotal: 800",
        "Tax: 80",
        "Total: 880 USD",
    ]
    y_pos = 40
    for line in img_lines:
        draw.text((40, y_pos), line, fill=(0, 0, 0), font=font)
        y_pos += 48
    img.save("eval_sample.png")

    return test_cases


def check_field_matches(expected, extracted):
    """Compare expected vs extracted fields (invoice_number, supplier_name, total)."""
    if not isinstance(extracted, dict):
        return 0, 3, False

    matched = 0

    # 1. Invoice Number
    ext_inv = str(extracted.get("invoice_number") or "").strip().lower()
    if expected["invoice_number"].lower() in ext_inv:
        matched += 1

    # 2. Supplier Name
    ext_sup = str(extracted.get("supplier_name") or "").strip().lower()
    if expected["supplier_name"].lower() in ext_sup:
        matched += 1

    # 3. Total Amount
    total_matched = False
    try:
        ext_total = float(extracted.get("total"))
        if abs(ext_total - expected["total"]) < 0.01:
            matched += 1
            total_matched = True
    except (TypeError, ValueError):
        pass

    return matched, 3, total_matched


def evaluate_system():
    print("Starting Multi-Format System Evaluation...\n" + "-" * 60)
    run_id = int(time.time()) % 10000
    test_cases = create_test_files(run_id)
    results = []

    try:
        for case in test_cases:
            fmt = case["format"]
            filename = case["filename"]
            print(f"[*] Testing {fmt} pipeline ({filename})...")

            start_time = time.time()
            with open(filename, "rb") as f:
                upload_res = requests.post(
                    f"{API_URL}/upload",
                    files={"file": (filename, f, case["mime"])},
                )

            if upload_res.status_code != 200:
                print(f"    -> Upload failed (HTTP {upload_res.status_code})")
                results.append({
                    "format": fmt,
                    "status": "Failed",
                    "time": round(time.time() - start_time, 2),
                    "matched_fields": 0,
                    "total_fields": 3,
                    "total_match": False,
                    "extracted_total": None,
                    "expected_total": case["expected"]["total"],
                })
                continue

            job_id = upload_res.json().get("job_id")
            status = "Processing"
            res_json = {}
            attempts = 0

            while status == "Processing" and attempts < 60:
                time.sleep(0.5)
                res_json = requests.get(f"{API_URL}/status/{job_id}").json()
                status = res_json.get("status", "Processing")
                attempts += 1

            elapsed = round(time.time() - start_time, 2)
            ai_data = res_json.get("ai_extracted_data", {})
            matched, total_fields, total_match = check_field_matches(
                case["expected"], ai_data
            )

            results.append({
                "format": fmt,
                "status": status,
                "time": elapsed,
                "matched_fields": matched,
                "total_fields": total_fields,
                "total_match": total_match,
                "extracted_total": ai_data.get("total") if isinstance(ai_data, dict) else None,
                "expected_total": case["expected"]["total"],
            })

            print(
                f"    -> Status: {status} | Time: {elapsed}s | "
                f"Fields: {matched}/{total_fields} | "
                f"Total: {ai_data.get('total') if isinstance(ai_data, dict) else None} "
                f"(Expected: {case['expected']['total']})"
            )
            time.sleep(1)

        # Aggregate Metrics
        total_docs = len(results)
        completed_docs = sum(1 for r in results if r["status"] == "Completed")
        failed_docs = total_docs - completed_docs
        success_rate = round((completed_docs / total_docs) * 100, 1)
        failure_rate = round((failed_docs / total_docs) * 100, 1)
        avg_time = round(sum(r["time"] for r in results) / total_docs, 2)

        total_matched_fields = sum(r["matched_fields"] for r in results)
        total_possible_fields = sum(r["total_fields"] for r in results)
        field_accuracy = round((total_matched_fields / total_possible_fields) * 100, 1)

        total_amount_matches = sum(1 for r in results if r["total_match"])
        total_amount_accuracy = round((total_amount_matches / total_docs) * 100, 1)

        print("\n" + "=" * 68)
        print("MULTI-FORMAT AI SYSTEM EVALUATION REPORT")
        print("=" * 68)
        print(f"{'Format':<14} | {'Status':<10} | {'Time (s)':<8} | {'Fields':<8} | {'Total Match'}")
        print("-" * 68)
        for r in results:
            t_match = "PASS" if r["total_match"] else f"FAIL ({r['extracted_total']})"
            print(
                f"{r['format']:<14} | {r['status']:<10} | {r['time']:<8} | "
                f"{r['matched_fields']}/{r['total_fields']:<6} | {t_match}"
            )
        print("-" * 68)
        print(f"Total Documents Tested   : {total_docs} (CSV, Excel, PDF, Image)")
        print(f"Document Success Rate    : {success_rate}% ({completed_docs}/{total_docs})")
        print(f"Failure Rate             : {failure_rate}% ({failed_docs}/{total_docs})")
        print(f"Average Processing Time  : {avg_time} seconds / document")
        print(f"Field Extraction Accuracy: {field_accuracy}% ({total_matched_fields}/{total_possible_fields} key fields)")
        print(f"Total Amount Accuracy    : {total_amount_accuracy}% ({total_amount_matches}/{total_docs} invoices)")
        print("=" * 68)

    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to http://127.0.0.1:8000. Please start the FastAPI server first.")
    except Exception as e:
        print(f"Unexpected error during evaluation: {e}")
    finally:
        for case in test_cases:
            if os.path.exists(case["filename"]):
                os.remove(case["filename"])


if __name__ == "__main__":
    evaluate_system()
