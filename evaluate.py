import time
import requests
import os

API_URL = "http://127.0.0.1:8000"

def evaluate_system():
    print("Starting System Evaluation...\n" + "-"*40)
    
    start_time = time.time()
    
    # Create a dummy test file
    test_filename = "eval_test.csv"
    with open(test_filename, "w", encoding="utf-8") as f:
        f.write("Item,Qty,Price,Total\nLaptop,1,1000,1000\nTax,,,50\nTotal,,,1050")
    
    print("[*] Uploading test document...")
    try:
        with open(test_filename, "rb") as f:
            upload_res = requests.post(f"{API_URL}/upload", files={"file": f})
        
        if upload_res.status_code != 200:
            print(f"❌ Upload Failed. Server returned: {upload_res.status_code}")
            return

        job_id = upload_res.json().get("job_id")
        if not job_id:
            print("❌ Failed to retrieve job_id from server.")
            return

        print(f"[*] Polling for completion (Job ID: {job_id})...")
        status = "Processing"
        attempts = 0
        
        while status == "Processing" and attempts < 15:
            time.sleep(2)
            res_json = requests.get(f"{API_URL}/status/{job_id}").json()
            status = res_json.get("status", "Processing")
            attempts += 1

        end_time = time.time()
        processing_time = round(end_time - start_time, 2)
        
        print("\n" + "="*40)
        print("📊 AI SYSTEM EVALUATION REPORT")
        print("="*40)
        
        if status == "Completed":
            print("✅ Document Success Rate: 100%")
            print("❌ Failure Rate: 0%")
            print(f"⏱️ Average Processing Time: {processing_time} seconds per document")
            
            ai_data = res_json.get("ai_extracted_data", {})
            print("\n🔍 Extraction Accuracy Check:")
            
            extracted_total = ai_data.get('total')
            print(f"Expected Total: 1050 | AI Extracted Total: {extracted_total}")
            
            if extracted_total == 1050:
                print("🎯 Total Amount Accuracy: 100%")
            else:
                print("🎯 Total Amount Accuracy: 0% (Mismatch)")
        else:
            print("✅ Document Success Rate: 0%")
            print("❌ Failure Rate: 100%")
            print(f"⏱️ Time spent before failure/timeout: {processing_time} seconds")
            print(f"⚠️ Final Status: {status}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to the server. Is main.py running on port 8000?")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
    finally:
        if os.path.exists(test_filename):
            os.remove(test_filename)
        print("="*40)

if __name__ == "__main__":
    evaluate_system()