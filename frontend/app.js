const form = document.querySelector("#analysisForm");
const textInput = document.querySelector("#documentText");
const fileInput = document.querySelector("#documentFile");
const analyzeBtn = document.querySelector("#analyzeBtn");
const clearBtn = document.querySelector("#clearBtn");
const sampleButtons = document.querySelectorAll("[data-sample], [data-sample-url]");
const exportBtn = document.querySelector("#exportBtn");
const serviceStatus = document.querySelector("#serviceStatus");
const emptyState = document.querySelector("#emptyState");
const report = document.querySelector("#report");
const fileStatus = document.querySelector("#fileStatus");

const API_BASE = (() => {
  const savedBase = window.localStorage.getItem("apiBaseUrl");
  if (savedBase) return savedBase.replace(/\/$/, "");
  return window.location.port && window.location.port !== "8000" ? "http://127.0.0.1:8000" : "";
})();

const sampleDocument = `Invoice No: INV-2048
Invoice Date: 30/06/2026
Vendor: Northwind Components Pvt Ltd
Bill To: Enterprise Finance Team
PO Number: PO-77891
GST: 29ABCDE1234F1Z5
Contact: finance@example.com
Phone: +91 98765 43210
Account Number: 123456789012
Grand Total: INR 248,750.00
Material: MAT-7788
This invoice is generated from the ERP procurement workflow for validation and payment processing.`;

// Labels the regex rules don't recognise, so the LLM extraction fallback kicks in.
const unusualInvoiceSample = `TAX INVOICE
Bill No: B-5521
Dated: 12/03/2026
Seller: Acme Traders LLP
Billed To: Riverside Retail
Item: Office chairs x 8
Net Payable: 12,400.00
Queries: accounts@acmetraders.example`;

const goodCsvSample = `invoice_number,invoice_date,vendor,purchase_order,material,total_amount,currency,contact_email,status
INV-2048,2026-06-30,Northwind Components Pvt Ltd,PO-77891,MAT-7788,248750.00,INR,finance@northwind.example,Ready for validation
INV-2049,2026-06-29,Apex Industrial Supplies,PO-77892,MAT-4491,87500.00,INR,accounts@apex.example,Ready for validation
INV-2050,2026-06-28,MetroTech Services,PO-77893,MAT-9920,151250.00,INR,billing@metrotech.example,Ready for validation
INV-2051,2026-06-27,BlueRiver Logistics,PO-77894,MAT-1180,64200.00,INR,finance@blueriver.example,Ready for validation`;

const errorCsvSample = `invoice_number,invoice_date,vendor,purchase_order,material,total_amount,currency,contact_email,status
INV-3001,2026-06-31,,PO-90001,MAT-1001,12000.00,INR,finance@example.com,Missing vendor and invalid date
,2026-06-25,Faulty Components Ltd,PO-90002,MAT-1002,not_available,INR,accounts@faulty.example,Missing invoice number and invalid amount
INV-3003,2026/13/01,DataWorks Services,,MAT-1003,-4500.00,INR,billing@dataworks.example,Invalid date and negative amount
INV-3003,2026/13/01,DataWorks Services,,MAT-1003,-4500.00,INR,billing@dataworks.example,Duplicate row
INV-3005,2026-06-24,Secure Parts Pvt Ltd,PO-90005,MAT-1005,75000.00,INR,user@example.com PAN ABCDE1234F,PII mixed into email column`;

async function checkHealth() {
  try {
    const response = await fetch(`${API_BASE}/api/health`);
    if (!response.ok) throw new Error("Service unavailable");
    const data = await response.json();
    serviceStatus.textContent = `Online - ${data.cache_backend}`;
    serviceStatus.className = "status ok";
  } catch {
    serviceStatus.textContent = "Offline";
    serviceStatus.className = "status error";
  }
}

function setLoading(isLoading) {
  analyzeBtn.disabled = isLoading;
  if (isLoading) {
    analyzeBtn.textContent = "Analyzing";
    return;
  }
  analyzeBtn.textContent = fileInput.files[0] ? "Analyze file" : "Analyze";
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setFileStatus(title, detail, state = "") {
  fileStatus.className = `file-status ${state}`.trim();
  fileStatus.innerHTML = "";
  const strong = document.createElement("strong");
  strong.textContent = title;
  const span = document.createElement("span");
  span.textContent = detail;
  fileStatus.append(strong, span);
}

function isPreviewableFile(file) {
  const lowerName = file.name.toLowerCase();
  const previewExtensions = [".csv", ".txt", ".json", ".xml", ".html", ".htm", ".md", ".log", ".data"];
  return file.type.startsWith("text/") || previewExtensions.some((extension) => lowerName.endsWith(extension));
}

function previewSelectedFile(file) {
  if (!file) {
    setFileStatus("No file selected", "Choose a file or paste text below.");
    analyzeBtn.textContent = "Analyze";
    return;
  }

  analyzeBtn.textContent = "Analyze file";
  const detail = `${file.name} - ${formatFileSize(file.size)}. Click Analyze file to process this upload.`;

  if (!isPreviewableFile(file)) {
    setFileStatus("File ready", `${detail} Preview is unavailable for this file type.`, "ready");
    textInput.value = "";
    textInput.placeholder = "File selected. Click Analyze file to process the upload.";
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    const content = String(reader.result || "");
    textInput.value = content.length > 120000 ? `${content.slice(0, 120000)}\n\n[Preview truncated]` : content;
    textInput.placeholder = "Selected file preview";
    setFileStatus("File preview loaded", detail, "ready");
  };
  reader.onerror = () => {
    textInput.value = "";
    setFileStatus("File ready", `${detail} Preview could not be loaded, but the file can still be analyzed.`, "warning");
  };
  reader.readAsText(file);
}

function fillList(element, values, emptyText) {
  element.innerHTML = "";
  const items = values.length ? values : [emptyText];
  for (const value of items) {
    const li = document.createElement("li");
    li.textContent = value;
    element.appendChild(li);
  }
}

function renderFields(fields, sources = {}) {
  const list = document.querySelector("#fieldsList");
  list.innerHTML = "";
  const entries = Object.entries(fields || {});
  if (!entries.length) {
    const dt = document.createElement("dt");
    dt.textContent = "Status";
    const dd = document.createElement("dd");
    dd.textContent = "No high-confidence fields found";
    list.append(dt, dd);
    return;
  }
  for (const [key, value] of entries) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key.replaceAll("_", " ");
    dd.textContent = value;
    if (sources[key] === "llm") {
      const badge = document.createElement("span");
      badge.className = "source-badge";
      badge.textContent = "LLM";
      badge.title = "Missed by the rules, extracted by the LLM and validated against the document";
      dd.append(" ", badge);
    }
    list.append(dt, dd);
  }
}

function renderTrace(trace) {
  const list = document.querySelector("#traceList");
  list.innerHTML = "";
  for (const step of trace || []) {
    const li = document.createElement("li");
    const title = document.createElement("strong");
    title.textContent = `${step.agent} - ${step.status}`;
    const detail = document.createElement("span");
    detail.textContent = ` - ${step.message} (${step.duration_ms} ms)`;
    li.append(title, detail);
    list.appendChild(li);
  }
}

function appendFormattedText(parent, text) {
  const parts = String(text || "").split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  for (const part of parts) {
    if (part.startsWith("**") && part.endsWith("**")) {
      const strong = document.createElement("strong");
      strong.className = "summary-inline-heading";
      strong.textContent = part.slice(2, -2).trim();
      parent.appendChild(strong);
      continue;
    }
    parent.appendChild(document.createTextNode(part.replace(/\*\*/g, "")));
  }
}

function splitMarkdownSections(text) {
  const normalized = String(text || "").replace(/\r/g, "");
  const prepared = normalized
    .replace(/\s+(\*\*[^*]{2,80}:\*\*)/g, (fullMatch, heading, offset, source) => {
      const before = source.slice(Math.max(0, offset - 8), offset);
      return /\d+\.\s*$/.test(before) ? fullMatch : `\n${heading}`;
    })
    .trim();
  const headingPattern = /^\*\*([^*]{2,80}:)\*\*/gm;
  const sections = [];
  let match;
  let lastIndex = 0;
  let currentTitle = "Overview";

  while ((match = headingPattern.exec(prepared)) !== null) {
    const content = prepared.slice(lastIndex, match.index).trim();
    if (content) {
      sections.push({ title: currentTitle, content });
    }
    currentTitle = match[1].replace(/:$/, "").trim();
    lastIndex = headingPattern.lastIndex;
  }

  const finalContent = prepared.slice(lastIndex).trim();
  if (finalContent) {
    sections.push({ title: currentTitle, content: finalContent });
  }

  return sections.length ? sections : [{ title: "Overview", content: prepared || "No summary available." }];
}

function renderSummary(text) {
  const container = document.querySelector("#summaryText");
  container.innerHTML = "";
  for (const section of splitMarkdownSections(text)) {
    const block = document.createElement("div");
    block.className = "summary-block";

    const heading = document.createElement("h4");
    heading.textContent = section.title;
    block.appendChild(heading);

    const listMatches = section.content.match(/\b\d+\.\s+/g) || [];
    if (listMatches.length > 1 || /^\d+\.\s+/.test(section.content)) {
      const list = document.createElement("ol");
      const items = section.content
        .split(/\s+(?=\d+\.\s+)/)
        .map((item) => item.replace(/^\d+\.\s+/, "").trim())
        .filter(Boolean);
      for (const item of items) {
        const li = document.createElement("li");
        appendFormattedText(li, item);
        list.appendChild(li);
      }
      block.appendChild(list);
    } else {
      const paragraph = document.createElement("p");
      appendFormattedText(paragraph, section.content);
      block.appendChild(paragraph);
    }

    container.appendChild(block);
  }
}

function renderReport(data) {
  emptyState.hidden = true;
  report.hidden = false;
  exportBtn.disabled = false;

  document.querySelector("#documentType").textContent = data.document_type;
  document.querySelector("#cacheState").textContent = data.cache_hit ? "Hit" : "Miss";
  document.querySelector("#tokenMetric").textContent =
    `${data.metrics.estimated_reduced_tokens} / ${data.metrics.estimated_original_tokens}`;
  document.querySelector("#sourceType").textContent = data.metrics.filename
    ? `${data.metrics.source_type} - ${data.metrics.filename}`
    : data.metrics.source_type;
  renderSummary(data.summary);
  document.querySelector("#tokenTree").textContent = data.token_tree;

  renderFields(data.extracted_fields, data.field_sources);
  fillList(
    document.querySelector("#piiList"),
    (data.pii_findings || []).map((item) => `${item.type}: ${item.count} masked as ${item.masked_value}`),
    "No PII detected"
  );
  fillList(document.querySelector("#recommendationsList"), data.recommendations || [], "No recommendations");
  renderTrace(data.trace);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setLoading(true);
  try {
    const payload = new FormData();
    const selectedFile = fileInput.files[0];
    if (selectedFile) {
      payload.append("file", selectedFile);
    } else {
      payload.append("text", textInput.value);
    }
    const response = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      body: payload,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Analysis failed");
    }
    renderReport(data);
    await checkHealth();
  } catch (error) {
    emptyState.hidden = false;
    report.hidden = true;
    exportBtn.disabled = true;
    emptyState.textContent = error.message;
  } finally {
    setLoading(false);
  }
});

clearBtn.addEventListener("click", () => {
  form.reset();
  setFileStatus("No file selected", "Choose a file or paste text below.");
  textInput.placeholder = "Paste text here, or choose a CSV/TXT-style file to preview it";
  analyzeBtn.textContent = "Analyze";
  emptyState.hidden = false;
  emptyState.textContent = "Run an analysis to see classification, agent trace, token reduction, and cache status.";
  report.hidden = true;
  exportBtn.disabled = true;
});

async function loadSample(button) {
  try {
    setLoading(true);
    const sampleType = button.dataset.sample;
    if (sampleType === "good-csv") {
      textInput.value = goodCsvSample;
    } else if (sampleType === "error-csv") {
      textInput.value = errorCsvSample;
    } else if (sampleType === "unusual-invoice") {
      textInput.value = unusualInvoiceSample;
    } else {
      textInput.value = sampleDocument;
    }
    fileInput.value = "";
    setFileStatus("Sample loaded", "Sample text is ready. Click Analyze to process it.", "ready");
    analyzeBtn.textContent = "Analyze";
    emptyState.hidden = false;
    emptyState.textContent = "Sample loaded into the text area. Click Analyze to process it.";
    report.hidden = true;
    exportBtn.disabled = true;
    textInput.focus();
  } catch (error) {
    emptyState.hidden = false;
    emptyState.textContent = error.message;
  } finally {
    setLoading(false);
  }
}

for (const button of sampleButtons) {
  button.addEventListener("click", () => loadSample(button));
}

fileInput.addEventListener("change", () => {
  previewSelectedFile(fileInput.files[0]);
  emptyState.hidden = false;
  emptyState.textContent = fileInput.files[0]
    ? "File selected. Review the preview if available, then click Analyze file."
    : "Run an analysis to see classification, agent trace, token reduction, and cache status.";
  report.hidden = true;
  exportBtn.disabled = true;
});

exportBtn.addEventListener("click", () => {
  if (window.html2pdf) {
    window.html2pdf().set({
      margin: 0.45,
      filename: "multi-agent-analysis-report.pdf",
      html2canvas: { scale: 2 },
      jsPDF: { unit: "in", format: "a4", orientation: "portrait" },
    }).from(report).save();
    return;
  }
  window.print();
});

checkHealth();
