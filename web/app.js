let rows = [];
const cols = ['meter_id','customer_id','reading_value','reading_date','unit','source_system'];
function render(){
  const tbody=document.querySelector('#resultsTable tbody');tbody.innerHTML='';
  rows.forEach(r=>{const tr=document.createElement('tr');cols.forEach(c=>{const td=document.createElement('td');td.textContent=r[c]||'';tr.appendChild(td)});tbody.appendChild(tr)});
  totalCount.textContent=rows.length;clientCount.textContent=new Set(rows.map(r=>r.customer_id)).size;
}
async function toBase64(file){const buf=await file.arrayBuffer();let bin='';new Uint8Array(buf).forEach(b=>bin+=String.fromCharCode(b));return btoa(bin)}
importBtn.onclick=async()=>{const f=fileInput.files[0];if(!f)return alert('اختر ملف');
  let mapping={};try{mapping=JSON.parse(mappingInput.value||'{}')}catch(e){return alert('Mapping JSON غير صحيح')}
  const res=await fetch('/api/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:f.name,content_base64:await toBase64(f),mapping,source_name:sourceName.value})});
  const data=await res.json(); if(!res.ok) return alert(data.error||'error'); rows=data.rows; render();
};
async function exportData(format){if(!rows.length)return alert('لا بيانات'); const res=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows,format})});const data=await res.json();const a=document.createElement('a');a.href='data:application/octet-stream;base64,'+data.content_base64;a.download=data.filename;a.click();}
exportCsvBtn.onclick=()=>exportData('csv');exportXlsxBtn.onclick=()=>exportData('xlsx');
