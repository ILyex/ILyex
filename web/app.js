let rows = [];
const COLUMNS = ["meter_id", "customer_id", "reading_value", "reading_date", "unit", "source_system"];

function renderTable() {
  const tbody = document.querySelector("#resultsTable tbody");
  tbody.innerHTML = "";

  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const column of COLUMNS) {
      const td = document.createElement("td");
      td.textContent = row[column] ?? "";
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }

  document.getElementById("totalCount").textContent = String(rows.length);
  const clients = new Set(rows.map((r) => r.customer_id));
  document.getElementById("clientCount").textContent = String(clients.size);
}

async function fileToBase64(file) {
  const buffer = await file.arrayBuffer();
  let binary = "";
  for (const byte of new Uint8Array(buffer)) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

async function importData() {
  const file = document.getElementById("fileInput").files[0];
  if (!file) {
    alert("اختر ملف أولاً");
    return;
  }

  let mapping;
  try {
    mapping = JSON.parse(document.getElementById("mappingInput").value || "{}");
  } catch {
    alert("صيغة JSON في Mapping غير صحيحة");
    return;
  }

  const payload = {
    filename: file.name,
    content_base64: await fileToBase64(file),
    mapping,
    source_name: document.getElementById("sourceName").value || "unknown",
  };

  const response = await fetch("/api/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    alert(data.error || "فشل الاستيراد");
    return;
  }

  rows = data.rows || [];
  renderTable();
}

async function exportData(format) {
  if (!rows.length) {
    alert("لا توجد بيانات للتصدير");
    return;
  }

  const response = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows, format }),
  });

  const data = await response.json();
  if (!response.ok) {
    alert(data.error || "فشل التصدير");
    return;
  }

  const link = document.createElement("a");
  link.href = `data:application/octet-stream;base64,${data.content_base64}`;
  link.download = data.filename;
  link.click();
}

document.getElementById("importBtn").addEventListener("click", importData);
document.getElementById("exportCsvBtn").addEventListener("click", () => exportData("csv"));
document.getElementById("exportXlsxBtn").addEventListener("click", () => exportData("xlsx"));
