document.addEventListener('DOMContentLoaded', async () => {
  const user = await requireAdmin();
  if (!user) return;

  loadStats();
  loadKeysTable();

  // Tabs setup
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      
      tab.classList.add('active');
      document.getElementById(`tab-${tab.dataset.target}`).classList.add('active');
    });
  });

  // Search setup
  document.getElementById('searchKeys').addEventListener('input', (e) => {
    loadKeysTable(e.target.value);
  });

  // Drag and Drop (document level)
  const dropZone = document.getElementById('dropZone');
  document.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });
  document.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
  });
  document.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleDroppedFiles(e.dataTransfer.files);
    }
  });
});

async function loadStats() {
  try {
    const res = await fetch('/api/admin/stats');
    if (!res.ok) return;
    const stats = await res.json();
    
    document.getElementById('stat-total-keys').textContent = stats.total_keys;
    document.getElementById('stat-available-keys').textContent = stats.available_keys;
    document.getElementById('stat-redeemed-keys').textContent = stats.redeemed_keys;
    document.getElementById('stat-valid-cookies').textContent = stats.valid_cookies;
  } catch (e) {
    console.error('Failed to load stats', e);
  }
}

async function loadKeysTable(search = '') {
  try {
    const res = await fetch('/api/admin/keys');
    if (!res.ok) return;
    const data = await res.json();
    let keys = data.keys || [];
    
    if (search) {
      const s = search.toLowerCase();
      keys = keys.filter(k => k.key_code.toLowerCase().includes(s) || (k.user_email && k.user_email.toLowerCase().includes(s)));
    }
    
    const tbody = document.getElementById('keysTableBody');
    tbody.innerHTML = keys.map(k => {
      let statusBadge = `<span class="badge badge-success">Available</span>`;
      if (k.is_revoked) statusBadge = `<span class="badge badge-error">Revoked</span>`;
      else if (k.redeemed_at) statusBadge = `<span class="badge badge-blue">Redeemed</span>`;
      
      let cookieBadge = '-';
      if (k.redeemed_at) {
        cookieBadge = `<div class="badge ${k.cookie_valid ? 'badge-success' : 'badge-error'}">
          <div class="dot ${k.cookie_valid ? 'green' : 'red'}"></div>
          ${k.cookie_valid ? 'Valid' : 'Invalid'}
        </div>`;
      }

      return `
        <tr>
          <td style="font-family:monospace;">${k.key_code}</td>
          <td>${statusBadge}</td>
          <td>${k.user_email || '-'}</td>
          <td>${cookieBadge}</td>
          <td>
            ${!k.is_revoked ? `<button class="btn btn-danger" style="padding:0.3rem 0.6rem; font-size:0.8rem;" onclick="revokeKey(${k.id})">Revoke</button>` : ''}
          </td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    console.error('Failed to load keys', e);
  }
}

window.generateNewKeys = async function() {
  const count = document.getElementById('genCount').value;
  const res = await api('POST', '/api/admin/generate-keys', { count: parseInt(count) });
  
  if (res.keys) {
    showToast(`Generated ${res.keys.length} keys`, 'success');
    const resultDiv = document.getElementById('genResult');
    resultDiv.classList.remove('hidden');
    resultDiv.innerHTML = res.keys.join('<br>') + `<br><br><button class="btn btn-secondary" onclick="copyToClipboard('${res.keys.join('\\n')}')">Copy All</button>`;
    loadStats();
    loadKeysTable();
  } else {
    showToast('Failed to generate keys', 'error');
  }
}

window.revokeKey = async function(id) {
  if(!confirm('Are you sure you want to revoke this key?')) return;
  
  const res = await api('POST', '/api/admin/revoke-key', { key_id: id });
  if (res.success) {
    showToast('Key revoked', 'success');
    loadStats();
    loadKeysTable();
  } else {
    showToast('Failed to revoke key', 'error');
  }
}

async function handleDroppedFiles(files) {
  const fileArray = Array.from(files).filter(f => f.name.endsWith('.txt') || f.type.includes('text') || !f.type);
  if (fileArray.length === 0) {
    showToast('No text files found', 'error');
    return;
  }
  
  showToast(`Reading ${fileArray.length} files...`, 'success');
  
  let combinedContent = document.getElementById('cookieInput').value || '';
  if (combinedContent) combinedContent += '\n\n';
  
  const promises = fileArray.map(file => {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = e => resolve(e.target.result);
      reader.onerror = () => resolve('');
      reader.readAsText(file);
    });
  });
  
  const contents = await Promise.all(promises);
  combinedContent += contents.filter(c => c.trim()).join('\n\n');
  
  document.getElementById('cookieInput').value = combinedContent;
  showToast(`Loaded ${fileArray.length} files, ready to upload`, 'success');
}

window.uploadCookies = async function() {
  const content = document.getElementById('cookieInput').value.trim();
  if (!content) {
    showToast('Please provide cookie data', 'error');
    return;
  }
  
  showToast('Uploading and validating...', 'success');
  const res = await api('POST', '/api/admin/upload-cookies', { cookie: content });
  
  if (res.error) {
    showToast(res.error, 'error');
    return;
  }
  
  const resultDiv = document.getElementById('cookieResult');
  resultDiv.classList.remove('hidden');
  resultDiv.innerHTML = `
    <div style="display:flex; gap:15px; font-weight:500;">
      <span style="color:var(--success)">✅ ${res.added || 0} Added</span>
      <span style="color:var(--blue)">⏭️ ${res.skipped || 0} Skipped</span>
      <span style="color:var(--error)">❌ ${res.invalid || 0} Invalid</span>
    </div>
  `;
  document.getElementById('cookieInput').value = '';
  loadStats();
}
