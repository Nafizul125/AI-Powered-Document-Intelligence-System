import React, { useState, useEffect } from 'react';
import './App.css'; 

function App() {
  const [files, setFiles] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchType, setSearchType] = useState('keyword');
  
  // States for Manual Correction
  const [editingId, setEditingId] = useState(null);
  const [editData, setEditData] = useState({});

  useEffect(() => {
    fetchDocuments('', 'keyword');
  }, []);

  const fetchDocuments = async (query, type) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/search?query=${query}&search_type=${type}`);
      const data = await res.json();
      setDocuments(data.invoices || []);
    } catch (error) {
      console.error("Error fetching documents:", error);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    fetchDocuments(searchQuery, searchType);
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!files || files.length === 0) return;

    Array.from(files).forEach(async (file) => {
      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch("http://127.0.0.1:8000/upload", {
          method: "POST",
          body: formData,
        });
        const data = await res.json();
        
        if (data.job_id) {
          const newDoc = { _id: data.job_id, filename: file.name, status: "Processing", validation: null, ai_extracted_data: null, extracted_text: null };
          setDocuments((prev) => [newDoc, ...prev]);
          pollStatus(data.job_id);
        }
      } catch (err) {
        console.error("Upload failed for", file.name, err);
      }
    });
    setFiles(null);
  };

  const pollStatus = (jobId) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://127.0.0.1:8000/status/${jobId}`);
        const data = await res.json();

        setDocuments((prev) => prev.map((doc) => (doc._id === jobId ? data : doc)));

        if (data.status === "Completed" || data.status === "Failed") {
          clearInterval(interval);
        }
      } catch (error) {
        console.error("Polling error", error);
        clearInterval(interval);
      }
    }, 3000);
  };

  const handleReprocess = async (jobId) => {
    try {
      setDocuments((prev) => prev.map((doc) => doc._id === jobId ? { ...doc, status: "Processing" } : doc));
      await fetch(`http://127.0.0.1:8000/reprocess/${jobId}`, { method: "POST" });
      pollStatus(jobId);
    } catch (error) {
      console.error("Reprocess failed", error);
    }
  };

  const startEditing = (doc) => {
    setEditingId(doc._id);
    setEditData(doc.ai_extracted_data || {});
  };

  const saveCorrection = async (jobId) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/invoice/${jobId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corrected_data: editData }),
      });
      const data = await res.json();
      
      setDocuments((prev) => prev.map((doc) => (doc._id === jobId ? { ...doc, ai_extracted_data: editData, validation: data.validation, status: "Completed" } : doc)));
      setEditingId(null);
    } catch (error) {
      console.error("Correction save failed", error);
    }
  };

  return (
    <div style={{ padding: "20px", fontFamily: "Arial, sans-serif", maxWidth: "1000px", margin: "0 auto" }}>
      <h1 style={{ textAlign: "center" }}>AI Document Intelligence System</h1>
      
      {/* Upload Section */}
      <div style={{ border: "1px dashed #ccc", padding: "20px", marginBottom: "20px", textAlign: "center", borderRadius: "8px" }}>
        <h3>Upload Documents (PDF, JPG, PNG, CSV, Excel)</h3>
        <form onSubmit={handleUpload}>
          <input type="file" multiple onChange={(e) => setFiles(e.target.files)} />
          <button type="submit" disabled={!files} style={{ padding: "8px 16px", cursor: "pointer", backgroundColor: "#4CAF50", color: "white", border: "none", borderRadius: "4px" }}>
            Upload & Process All
          </button>
        </form>
      </div>

      {/* Search Section */}
      <div style={{ marginBottom: "20px", display: "flex", gap: "10px", justifyContent: "center" }}>
        <form onSubmit={handleSearch} style={{ display: "flex", gap: "10px", width: "100%" }}>
          <input 
            type="text" 
            placeholder="Search invoices (e.g. 'Laptop' or 'Computer parts')..." 
            value={searchQuery} 
            onChange={(e) => setSearchQuery(e.target.value)} 
            style={{ flex: 1, padding: "8px", border: "1px solid #ccc", borderRadius: "4px" }}
          />
          <select value={searchType} onChange={(e) => setSearchType(e.target.value)} style={{ padding: "8px", border: "1px solid #ccc", borderRadius: "4px" }}>
            <option value="keyword">Keyword Match</option>
            <option value="semantic">Semantic (AI) Match</option>
          </select>
          <button type="submit" style={{ padding: "8px 16px", backgroundColor: "#2196F3", color: "white", border: "none", borderRadius: "4px", cursor: "pointer" }}>
            Search
          </button>
        </form>
      </div>

      {/* History & Results Dashboard */}
      <h2>Processing History & Results ({documents.length})</h2>
      {documents.map((doc) => (
        <div key={doc._id} style={{ border: "1px solid #ddd", padding: "15px", marginBottom: "15px", borderRadius: "8px", backgroundColor: "#f9f9f9" }}>
          
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h4 style={{ margin: 0 }}>{doc.filename}</h4>
            <span style={{ 
              padding: "4px 8px", borderRadius: "4px", fontWeight: "bold",
              backgroundColor: doc.status === "Completed" ? "#d4edda" : doc.status === "Failed" ? "#f8d7da" : "#fff3cd",
              color: doc.status === "Completed" ? "#155724" : doc.status === "Failed" ? "#721c24" : "#856404"
            }}>
              {doc.status}
            </span>
          </div>

          {/* Validation Errors */}
          {doc.validation && doc.validation.manual_review_required && (
            <div style={{ marginTop: "10px", color: "#721c24", backgroundColor: "#f8d7da", padding: "8px", borderRadius: "4px", fontSize: "14px" }}>
              <strong>⚠️ Manual Review Required:</strong> {doc.validation.flags.join(" | ")}
            </div>
          )}
          
          {/* Failed Error Message */}
          {doc.status === "Failed" && (
            <div style={{ marginTop: "10px", color: "red" }}>
              <strong>Error:</strong> {doc.error}
              <button onClick={() => handleReprocess(doc._id)} style={{ marginLeft: "10px", padding: "4px 8px", cursor: "pointer", backgroundColor: "#6c757d", color: "white", border: "none", borderRadius: "4px" }}>
                Reprocess (Retry AI)
              </button>
            </div>
          )}

          {/* Raw Extracted Text (From OCR/PDF) */}
          {doc.extracted_text && (
            <details style={{ marginTop: "15px", padding: "10px", backgroundColor: "#e2e3e5", borderRadius: "4px" }}>
              <summary style={{ cursor: "pointer", fontWeight: "bold", color: "#383d41" }}>📄 View Raw Extracted Text (OCR/PDF)</summary>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "12px", marginTop: "10px", maxHeight: "200px", overflowY: "auto", borderTop: "1px solid #ccc", paddingTop: "10px" }}>
                {doc.extracted_text}
              </pre>
            </details>
          )}

          {/* Extracted Data Display / Edit Mode */}
          {doc.ai_extracted_data && (
            <div style={{ marginTop: "15px", backgroundColor: "white", padding: "15px", border: "1px solid #eee", borderRadius: "4px" }}>
              {editingId === doc._id ? (
                // EDIT MODE
                <div>
                  <strong>Edit Extracted Data:</strong>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginTop: "10px" }}>
                    <label>Invoice No: <input value={editData.invoice_number || ''} onChange={e => setEditData({...editData, invoice_number: e.target.value})} style={{width: '100%', padding: '4px'}} /></label>
                    <label>Subtotal: <input type="number" value={editData.subtotal || ''} onChange={e => setEditData({...editData, subtotal: parseFloat(e.target.value)})} style={{width: '100%', padding: '4px'}} /></label>
                    <label>Tax: <input type="number" value={editData.tax || ''} onChange={e => setEditData({...editData, tax: parseFloat(e.target.value)})} style={{width: '100%', padding: '4px'}} /></label>
                    <label>Total: <input type="number" value={editData.total || ''} onChange={e => setEditData({...editData, total: parseFloat(e.target.value)})} style={{width: '100%', padding: '4px'}} /></label>
                  </div>
                  <div style={{ marginTop: "15px" }}>
                    <button onClick={() => saveCorrection(doc._id)} style={{ padding: "6px 12px", backgroundColor: "#4CAF50", color: "white", border: "none", borderRadius: "4px", marginRight: "10px", cursor: "pointer" }}>Save Correction</button>
                    <button onClick={() => setEditingId(null)} style={{ padding: "6px 12px", cursor: "pointer", border: "1px solid #ccc", borderRadius: "4px" }}>Cancel</button>
                  </div>
                </div>
              ) : (
                // VIEW MODE - FULL INFORMATION
                <div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", fontSize: "14px", marginBottom: "15px" }}>
                    <div><strong>Invoice No:</strong> {doc.ai_extracted_data.invoice_number || 'N/A'}</div>
                    <div><strong>Date:</strong> {doc.ai_extracted_data.invoice_date || 'N/A'}</div>
                    <div><strong>Supplier:</strong> {doc.ai_extracted_data.supplier_name || 'N/A'}</div>
                    <div><strong>Customer:</strong> {doc.ai_extracted_data.customer_name || 'N/A'}</div>
                    <div><strong>Subtotal:</strong> {doc.ai_extracted_data.subtotal || 0}</div>
                    <div><strong>Tax:</strong> {doc.ai_extracted_data.tax || 0}</div>
                    <div><strong>Total:</strong> {doc.ai_extracted_data.total || 0} {doc.ai_extracted_data.currency || ''}</div>
                  </div>

                  {/* Line Items Table */}
                  {doc.ai_extracted_data.line_items && doc.ai_extracted_data.line_items.length > 0 && (
                    <div style={{ marginTop: "15px" }}>
                      <strong>Line Items:</strong>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px", marginTop: "8px" }}>
                        <thead>
                          <tr style={{ backgroundColor: "#f4f4f4" }}>
                            <th style={{ border: "1px solid #ddd", padding: "6px", textAlign: "left" }}>Description</th>
                            <th style={{ border: "1px solid #ddd", padding: "6px", textAlign: "center" }}>Qty</th>
                            <th style={{ border: "1px solid #ddd", padding: "6px", textAlign: "right" }}>Price</th>
                            <th style={{ border: "1px solid #ddd", padding: "6px", textAlign: "right" }}>Total</th>
                          </tr>
                        </thead>
                        <tbody>
                          {doc.ai_extracted_data.line_items.map((item, idx) => (
                            <tr key={idx}>
                              <td style={{ border: "1px solid #ddd", padding: "6px" }}>{item.description}</td>
                              <td style={{ border: "1px solid #ddd", padding: "6px", textAlign: "center" }}>{item.quantity}</td>
                              <td style={{ border: "1px solid #ddd", padding: "6px", textAlign: "right" }}>{item.unit_price}</td>
                              <td style={{ border: "1px solid #ddd", padding: "6px", textAlign: "right" }}>{item.total}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  <button onClick={() => startEditing(doc)} style={{ marginTop: "15px", padding: "6px 12px", cursor: "pointer", backgroundColor: "#ffc107", color: "#212529", border: "none", borderRadius: "4px", fontWeight: "bold" }}>
                    ✏️ Manual Edit
                  </button>

                  {/* Raw Structured JSON (From AI) */}
                  <details style={{ marginTop: "15px", padding: "10px", backgroundColor: "#eef2f5", borderRadius: "4px" }}>
                    <summary style={{ cursor: "pointer", fontWeight: "bold", color: "#0056b3" }}>🤖 View Structured AI JSON</summary>
                    <pre style={{ whiteSpace: "pre-wrap", fontSize: "12px", marginTop: "10px", borderTop: "1px solid #ccc", paddingTop: "10px" }}>
                      {JSON.stringify(doc.ai_extracted_data, null, 2)}
                    </pre>
                  </details>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default App;