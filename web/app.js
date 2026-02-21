let rows = [];
let filteredRows = [];
let currentPage = 1;
const PAGE_SIZE = 20;
const COLUMNS = ["id_compteur", "id_client", "valeur_releve", "date_releve", "unite", "systeme_source"];

function setStatus(text) { document.getElementById("statusText").textContent = text; }
function setProgress(value) { document.getElementById("progressBar").style.width = `${Math.min(100, Math.max(0, value))}%`; }

function getVisibleRows() {
  const start = (currentPage - 1) * PAGE_SIZE;
  return filteredRows.slice(start, start + PAGE_SIZE);
}

function renderTable() {
  const tbody = document.querySelector("#resultsTable tbody");
  tbody.innerHTML = "";
  for (const row of getVisibleRows()) {
    const tr = document.createElement("tr");
    for (const column of COLUMNS) {
      const td = document.createElement("td");
      td.textContent = row[column] ?? "";
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / PAGE_SIZE));
  document.getElementById("pageInfo").textContent = `Page ${currentPage}/${totalPages}`;
}

function renderKpis() {
  document.getElementById("totalCount").textContent = String(filteredRows.length);
  document.getElementById("clientCount").textContent = String(new Set(filteredRows.map((r) => r.id_client)).size);
  if (!filteredRows.length) {
    document.getElementById("avgValue").textContent = "0.000";
    document.getElementById("lastDate").textContent = "-";
    drawLineChart([]); drawDonutChart([]); return;
  }
  const values = filteredRows.map((r) => Number(r.valeur_releve) || 0);
  document.getElementById("avgValue").textContent = (values.reduce((a,b)=>a+b,0)/values.length).toFixed(3);
  document.getElementById("lastDate").textContent = filteredRows.map((r)=>r.date_releve).sort((a,b)=>a<b?1:-1)[0];
  drawLineChart(filteredRows);
  drawDonutChart(filteredRows);
}

function drawLineChart(data) {
  const canvas = document.getElementById("lineChart");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if (!data.length) return;
  const sorted = [...data].sort((a,b)=>a.date_releve.localeCompare(b.date_releve));
  const values = sorted.map((r)=>Number(r.valeur_releve)||0);
  const max = Math.max(...values,1);
  const stepX = (canvas.width-40)/Math.max(1,values.length-1);
  ctx.strokeStyle = "#1f9dd9"; ctx.lineWidth = 2; ctx.beginPath();
  values.forEach((v,i)=>{
    const x = 20 + i*stepX;
    const y = canvas.height - 20 - (v/max)*(canvas.height-40);
    i===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
  });
  ctx.stroke();
}

function drawDonutChart(data) {
  const canvas = document.getElementById("donutChart");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if (!data.length) return;
  const byUnit = {};
  for (const r of data) byUnit[r.unite] = (byUnit[r.unite] || 0) + 1;
  const entries = Object.entries(byUnit);
  const total = entries.reduce((a,[,v])=>a+v,0);
  const colors = ["#1f9dd9", "#0f6d9d", "#58b5e6", "#7ec9ef", "#2f89bc"];
  let start = -Math.PI/2;
  entries.forEach(([label, val], i) => {
    const angle = (val/total)*Math.PI*2;
    ctx.beginPath();
    ctx.moveTo(canvas.width/2, canvas.height/2);
    ctx.arc(canvas.width/2, canvas.height/2, 85, start, start+angle);
    ctx.closePath();
    ctx.fillStyle = colors[i % colors.length];
    ctx.fill();
    start += angle;
  });
  ctx.beginPath();
  ctx.fillStyle = "#fff";
  ctx.arc(canvas.width/2, canvas.height/2, 45, 0, Math.PI*2);
  ctx.fill();
}

function applyFilter() {
  const q = (document.getElementById("searchInput").value || "").toLowerCase().trim();
  filteredRows = !q ? [...rows] : rows.filter((r) => COLUMNS.some((c)=>String(r[c]??"").toLowerCase().includes(q)));
  currentPage = 1;
  renderTable();
  renderKpis();
}

async function fileToBase64WithProgress(file) {
  const chunkSize = 1024 * 1024;
  let offset = 0;
  const chunks = [];
  while (offset < file.size) {
    const slice = file.slice(offset, offset + chunkSize);
    const buffer = await slice.arrayBuffer();
    chunks.push(...new Uint8Array(buffer));
    offset += chunkSize;
    setProgress((offset / file.size) * 80);
  }
  let binary = "";
  chunks.forEach((b)=>{ binary += String.fromCharCode(b); });
  setProgress(90);
  return btoa(binary);
}

async function importData(fileFromDrop = null) {
  const file = fileFromDrop || document.getElementById("fileInput").files[0];
  if (!file) return alert("Choisissez un fichier d'abord");
  setStatus(`Lecture de ${file.name} (${(file.size/1024/1024).toFixed(2)} MB)...`);

  let mapping = {};
  if (!document.getElementById("autoMapping").checked) {
    try { mapping = JSON.parse(document.getElementById("mappingInput").value || "{}"); }
    catch { return alert("JSON mapping invalide"); }
  }

  const payload = {
    filename: file.name,
    content_base64: await fileToBase64WithProgress(file),
    mapping,
    source_name: document.getElementById("sourceName").value || "unknown",
  };

  const response = await fetch("/api/import", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const data = await response.json();
  if (!response.ok) return alert(data.error || "Import échoué");

  rows = data.rows || [];
  if (data.detected_mapping && document.getElementById("autoMapping").checked) {
    document.getElementById("mappingInput").value = JSON.stringify(data.detected_mapping, null, 2);
  }
  setProgress(100);
  setStatus(`Import terminé: ${rows.length} lignes.`);
  applyFilter();
}

async function exportData(format) {
  const exportFiltered = document.getElementById("exportFiltered").checked;
  const payloadRows = exportFiltered ? filteredRows : rows;
  if (!payloadRows.length) return alert("Aucune donnée à exporter");
  const response = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows: payloadRows, format }),
  });
  const data = await response.json();
  if (!response.ok) return alert(data.error || "Export échoué");
  const link = document.createElement("a");
  link.href = `data:application/octet-stream;base64,${data.content_base64}`;
  link.download = data.filename;
  link.click();
}

function initDragDrop() {
  const zone = document.getElementById("dropZone");
  zone.addEventListener("dragover", (e)=>{ e.preventDefault(); zone.classList.add("active"); });
  zone.addEventListener("dragleave", ()=> zone.classList.remove("active"));
  zone.addEventListener("drop", (e)=>{
    e.preventDefault(); zone.classList.remove("active");
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) importData(file);
  });
}

document.getElementById("importBtn").addEventListener("click", () => importData());
document.getElementById("exportCsvBtn").addEventListener("click", () => exportData("csv"));
document.getElementById("exportXlsxBtn").addEventListener("click", () => exportData("xlsx"));
document.getElementById("searchInput").addEventListener("input", applyFilter);
document.getElementById("prevPageBtn").addEventListener("click", ()=>{ currentPage=Math.max(1,currentPage-1); renderTable(); });
document.getElementById("nextPageBtn").addEventListener("click", ()=>{ const t=Math.max(1,Math.ceil(filteredRows.length/PAGE_SIZE)); currentPage=Math.min(t,currentPage+1); renderTable(); });
initDragDrop();
