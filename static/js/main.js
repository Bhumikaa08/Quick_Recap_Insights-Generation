// UI elements
const tabs = document.querySelectorAll('.tab');
const tabContents = document.querySelectorAll('.tab-content');

tabs.forEach(t => {
  t.addEventListener('click', (e) => {
    tabs.forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    const tab = t.dataset.tab;
    tabContents.forEach(c => c.style.display = c.id === tab ? 'block' : 'none');
  });
});

// Paste summarization
const summarizeBtn = document.getElementById('summarizeBtn');
const input = document.getElementById('inputText');
const summaryDiv = document.getElementById('summaryText');
const metaPre = document.getElementById('meta');
const ratio = document.getElementById('ratio');
const ratioVal = document.getElementById('ratioVal');
const methodSelect = document.getElementById('method');

ratio.addEventListener('input', () => { ratioVal.textContent = Math.round(ratio.value * 100) + '%'; });

summarizeBtn.addEventListener('click', async () => {
  const text = input.value.trim();
  if (!text) { alert('Please paste some text.'); return; }
  summaryDiv.textContent = 'Processing…';
  metaPre.textContent = '';
  try {
    const res = await fetch('/api/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, ratio: parseFloat(ratio.value), method: methodSelect.value })
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Server error');
      summaryDiv.textContent = 'Error generating summary.';
      return;
    }
    summaryDiv.textContent = data.summary;
    metaPre.textContent = JSON.stringify(data.meta, null, 2) + `\nElapsed: ${data.elapsed_seconds.toFixed(2)}s`;
    loadHistory();
  } catch (err) {
    summaryDiv.textContent = 'Error: ' + err.message;
  }
});

// File upload
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const fileMethod = document.getElementById('fileMethod');
const fileRatio = document.getElementById('fileRatio');
const fileRatioVal = document.getElementById('fileRatioVal');

fileRatio.addEventListener('input', () => { fileRatioVal.textContent = Math.round(fileRatio.value * 100) + '%'; });

uploadBtn.addEventListener('click', async () => {
  const file = fileInput.files[0];
  if (!file) { alert('Please select a file (.pdf, .docx, .txt).'); return; }

  const form = new FormData();
  form.append('file', file);
  form.append('method', fileMethod.value);
  form.append('ratio', parseFloat(fileRatio.value));

  summaryDiv.textContent = 'Processing file…';
  metaPre.textContent = '';

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Upload error');
      summaryDiv.textContent = 'Upload error.';
      return;
    }
    summaryDiv.textContent = data.summary;
    metaPre.textContent = JSON.stringify(data.meta, null, 2) + `\nElapsed: ${data.elapsed_seconds.toFixed(2)}s\nFile: ${data.filename}`;
    loadHistory();
  } catch (err) {
    summaryDiv.textContent = 'Error: ' + err.message;
  }
});

// History
async function loadHistory() {
  const list = document.getElementById('historyList');
  list.textContent = 'Loading…';
  try {
    const res = await fetch('/api/history');
    const entries = await res.json();
    if (!Array.isArray(entries)) { list.textContent = 'No history.'; return; }
    if (entries.length === 0) { list.textContent = 'No summaries yet.'; return; }

    list.innerHTML = '';
    entries.forEach(e => {
      const div = document.createElement('div');
      div.className = 'history-item';
      const snippet = (e.summary_text || '').slice(0, 220);
      div.innerHTML = `<strong>${snippet}${e.summary_text && e.summary_text.length > 220 ? '…' : ''}</strong>
                       <div>Method: ${e.method} ${e.filename ? `| File: ${e.filename}` : ''}</div>
                       <time>${new Date(e.created_at).toLocaleString()}</time>`;
      div.addEventListener('click', () => {
        summaryDiv.textContent = e.summary_text;
        metaPre.textContent = JSON.stringify({ method: e.method, filename: e.filename, created_at: e.created_at }, null, 2);
      });
      list.appendChild(div);
    });
  } catch (err) {
    list.textContent = 'Failed to load history.';
  }
}

// initial load
loadHistory();
