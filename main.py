import os
import json
import io
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
from dotenv import load_dotenv
from groq import AsyncGroq
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import pymupdf
import pytesseract
from PIL import Image
import openpyxl
import csv

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is missing. Please check your .env file.")

client = AsyncGroq(api_key=GROQ_API_KEY)
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["document_intelligence"]
invoices_collection = db["processed_invoices"]

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = FastAPI(title="AI Document Intelligence System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CorrectionRequest(BaseModel):
    corrected_data: Dict[str, Any]

async def validate_invoice_data(data: dict, current_document_id: str):
    flags = []
    invoice_number = data.get("invoice_number")
    if not invoice_number:
        flags.append("Missing Invoice Number")
    else:
        existing_invoice = await invoices_collection.find_one({
            "ai_extracted_data.invoice_number": invoice_number,
            "_id": {"$ne": ObjectId(current_document_id)}
        })
        if existing_invoice:
            flags.append(f"Duplicate Invoice: Invoice number '{invoice_number}' already exists in database.")

    if not data.get("total") and data.get("total") != 0:
        flags.append("Missing Total Amount")

    try:
        subtotal = float(data.get("subtotal") or 0)
        tax = float(data.get("tax") or 0)
        total = float(data.get("total") or 0)
        if abs((subtotal + tax) - total) > 0.1:
            flags.append(f"Math Inconsistency: Subtotal ({subtotal}) + Tax ({tax}) does not equal Total ({total})")
    except ValueError:
        flags.append("Invalid numeric values found in Subtotal, Tax, or Total")

    return {
        "is_valid": len(flags) == 0,
        "flags": flags,
        "manual_review_required": len(flags) > 0
    }

async def extract_structured_data_with_ai(text: str):
    prompt = f"""
    Extract the following fields from the invoice text below. 
    Return a valid JSON object ONLY. If a field is missing, use null.
    Fields to extract: 
    - invoice_number
    - invoice_date
    - supplier_name
    - customer_name
    - subtotal (numeric)
    - tax (numeric)
    - total (numeric)
    - currency
    - line_items (list of objects containing: description, quantity, unit_price, total)
    
    Invoice Text:
    {text}
    """
    try:
        response = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a strict data extraction assistant. You output only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            model="qwen/qwen3.8-27b",
            temperature=0,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content.strip()
        if result_text.startswith("```json"):
            result_text = result_text[7:-3].strip()
        elif result_text.startswith("```"):
            result_text = result_text[3:-3].strip()
            
        return json.loads(result_text)
    except Exception as e:
        return {"error": str(e)}

async def process_document_background(document_id: str, filename: str, contents: bytes):
    try:
        extracted_text = ""
        file_lower = filename.lower()
        
        if file_lower.endswith(".pdf"):
            try:
                pdf_document = pymupdf.open(stream=contents, filetype="pdf")
                for page_num in range(len(pdf_document)):
                    page = pdf_document[page_num]
                    extracted_text += page.get_text() + "\n"
            except Exception as pdf_err:
                raise Exception(f"Corrupted or invalid PDF file: {str(pdf_err)}")

        elif file_lower.endswith((".png", ".jpg", ".jpeg", ".tiff", ".bmp")):
            try:
                image = Image.open(io.BytesIO(contents))
                image = image.convert("L")
                extracted_text = pytesseract.image_to_string(image)
            except Exception as ocr_err:
                raise Exception(f"OCR processing failed: {str(ocr_err)}")

        elif file_lower.endswith(".csv"):
            try:
                text_data = contents.decode('utf-8', errors='ignore')
                csv_reader = csv.reader(io.StringIO(text_data))
                for row in csv_reader:
                    extracted_text += " ".join(row) + "\n"
            except Exception as csv_err:
                raise Exception(f"Corrupted or invalid CSV file: {str(csv_err)}")
        
        elif file_lower.endswith((".xlsx", ".xls")):
            try:
                wb = openpyxl.load_workbook(filename=io.BytesIO(contents), data_only=True)
                for sheet_name in wb.sheetnames:
                    sheet = wb[sheet_name]
                    extracted_text += f"\n--- Sheet: {sheet_name} ---\n"
                    for row in sheet.iter_rows(values_only=True):
                        row_data = [str(cell) for cell in row if cell is not None]
                        if row_data:
                            extracted_text += " ".join(row_data) + "\n"
            except Exception as xls_err:
                raise Exception(f"Corrupted or invalid Excel file: {str(xls_err)}")
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format")

        if not extracted_text.strip():
            await invoices_collection.update_one(
                {"_id": ObjectId(document_id)},
                {"$set": {"status": "Failed", "extracted_text": "", "error": "No text could be extracted from the document."}}
            )
            return

        structured_data = await extract_structured_data_with_ai(extracted_text)
        if "error" in structured_data:
            await invoices_collection.update_one(
                {"_id": ObjectId(document_id)},
                {"$set": {"status": "Failed", "extracted_text": extracted_text, "error": structured_data["error"]}}
            )
            return

        validation_results = await validate_invoice_data(structured_data, document_id)

        await invoices_collection.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {
                "status": "Completed",
                "extracted_text": extracted_text.strip(),
                "ai_extracted_data": structured_data,
                "validation": validation_results
            }}
        )

    except Exception as e:
        await invoices_collection.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": {"status": "Failed", "extracted_text": "", "error": str(e)}}
        )

@app.get("/")
def read_root():
    return {"message": "Welcome to AI Document Intelligence API!"}

@app.post("/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    try:
        contents = await file.read()
        initial_doc = {
            "filename": file.filename,
            "status": "Processing",
            "ai_extracted_data": None,
            "validation": None,
            "extracted_text": None
        }
        result = await invoices_collection.insert_one(initial_doc)
        document_id = str(result.inserted_id)
        background_tasks.add_task(process_document_background, document_id, file.filename, contents)
        return {"message": "File uploaded successfully. Processing started in background.", "job_id": document_id, "status_url": f"/status/{document_id}"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/status/{job_id}")
async def get_processing_status(job_id: str):
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=400, detail="Invalid Job ID format")
    try:
        doc = await invoices_collection.find_one({"_id": ObjectId(job_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Job not found")
        doc["_id"] = str(doc["_id"])
        return doc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/invoice/{job_id}")
async def manual_correction(job_id: str, request: CorrectionRequest):
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=400, detail="Invalid Job ID")
    try:
        correction = request.corrected_data
        validation_results = await validate_invoice_data(correction, job_id)
        validation_results["manual_review_required"] = False
        result = await invoices_collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"ai_extracted_data": correction, "validation": validation_results, "status": "Completed"}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return {"message": "Invoice manually corrected successfully", "validation": validation_results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reprocess/{job_id}")
async def reprocess_failed_job(job_id: str, background_tasks: BackgroundTasks):
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=400, detail="Invalid Job ID")
    try:
        doc = await invoices_collection.find_one({"_id": ObjectId(job_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if doc.get("status") != "Failed":
            return {"message": f"Job is currently {doc.get('status')}. Only failed jobs can be reprocessed."}
            
        extracted_text = doc.get("extracted_text")
        if not extracted_text:
            raise HTTPException(status_code=400, detail="No extracted text found. Please re-upload the original file.")

        await invoices_collection.update_one({"_id": ObjectId(job_id)}, {"$set": {"status": "Processing", "error": None}})

        async def retry_ai_extraction(doc_id: str, text: str):
            try:
                structured_data = await extract_structured_data_with_ai(text)
                if "error" in structured_data:
                    await invoices_collection.update_one({"_id": ObjectId(doc_id)}, {"$set": {"status": "Failed", "error": structured_data["error"]}})
                    return
                validation_results = await validate_invoice_data(structured_data, doc_id)
                await invoices_collection.update_one({"_id": ObjectId(doc_id)}, {"$set": {"status": "Completed", "ai_extracted_data": structured_data, "validation": validation_results}})
            except Exception as e:
                await invoices_collection.update_one({"_id": ObjectId(doc_id)}, {"$set": {"status": "Failed", "error": str(e)}})

        background_tasks.add_task(retry_ai_extraction, job_id, extracted_text)
        return {"message": "Reprocessing started in background.", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search")
async def search_invoices(query: str = None, search_type: str = "keyword"):
    try:
        invoices = []
        if search_type == "semantic" and query:
            cursor = invoices_collection.find({}, {"_id": 1, "extracted_text": 1, "filename": 1}).limit(20)
            docs_for_ai = []
            async for d in cursor:
                if d.get("extracted_text"):
                    docs_for_ai.append({"id": str(d["_id"]), "filename": d.get("filename", ""), "text": d["extracted_text"][:500]})
            
            if docs_for_ai:
                prompt = f"""You are a semantic search engine. Find documents that match the user's query conceptually. Query: "{query}". Documents: {json.dumps(docs_for_ai)}. Return ONLY a JSON object with key "matched_ids" containing list of matching string IDs."""
                response = await client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}], model="qwen/qwen3.8-27b", temperature=0, response_format={"type": "json_object"}
                )
                try:
                    matched_ids = json.loads(response.choices[0].message.content.strip()).get("matched_ids", [])
                except:
                    matched_ids = []
                    
                if matched_ids:
                    object_ids = [ObjectId(i) for i in matched_ids if ObjectId.is_valid(i)]
                    full_docs_cursor = invoices_collection.find({"_id": {"$in": object_ids}})
                    async for doc in full_docs_cursor:
                        doc["_id"] = str(doc["_id"])
                        invoices.append(doc)
        else:
            filter_query = {}
            if query:
                filter_query = {
                    "$or": [
                        {"filename": {"$regex": query, "$options": "i"}},
                        {"ai_extracted_data.invoice_number": {"$regex": query, "$options": "i"}},
                        {"ai_extracted_data.supplier_name": {"$regex": query, "$options": "i"}}
                    ]
                }
            cursor = invoices_collection.find(filter_query).sort([("_id", -1)]).limit(20)
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                invoices.append(doc)
                
        return {"total_found": len(invoices), "search_type": search_type, "invoices": invoices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    