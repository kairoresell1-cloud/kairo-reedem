document.addEventListener('DOMContentLoaded', async () => {
  const user = await checkAuth(true);
  if (!user) return;

  document.getElementById('navAuth').innerHTML = `
    ${user.is_admin ? '<a href="/static/admin.html" class="gold" style="margin-right: 15px;">Admin</a>' : ''}
    <div style="display: flex; align-items: center; gap: 10px;">
      <span style="color:var(--text-muted)">${user.name}</span>
      <img src="${user.avatar_url || 'https://ui-avatars.com/api/?name=' + user.name + '&background=191919&color=fff'}" style="width:35px; height:35px; border-radius:50%;">
      <a href="/auth/logout" class="btn btn-secondary" style="padding: 0.4rem 1rem;">Logout</a>
    </div>
  `;

  document.getElementById('welcomeMsg').textContent = `Your Keys, ${user.name}`;

  loadKeys();
});

async function loadKeys() {
  const keysGrid = document.getElementById('keysGrid');
  const emptyState = document.getElementById('emptyState');
  
  const response = await fetch('/api/my-keys');
  if (!response.ok) return;
  const keys = await response.json();
  
  if (keys.length === 0) {
    emptyState.classList.remove('hidden');
    keysGrid.classList.add('hidden');
    return;
  }
  
  emptyState.classList.add('hidden');
  keysGrid.classList.remove('hidden');
  
  keysGrid.innerHTML = keys.map(k => `
    <div class="card" id="key-card-${k.id}">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
        <h3 style="letter-spacing:1px; cursor:pointer;" onclick="toggleKey(${k.id}, '${k.key_code}')" id="key-display-${k.id}">
          ${maskKey(k.key_code)}
        </h3>
        <div class="badge ${k.cookie_valid ? 'badge-success' : 'badge-error'}">
          <div class="dot ${k.cookie_valid ? 'green' : 'red'}"></div>
          ${k.cookie_valid ? 'Valid' : 'Checking'}
        </div>
      </div>
      <p style="font-size:0.8rem; color:var(--text-muted); margin-bottom:1.5rem;">
        Redeemed: ${new Date(k.redeemed_at).toLocaleDateString()}
      </p>
      
      <div style="display:flex; gap:10px; margin-bottom:1rem;">
        <button class="btn btn-primary" style="flex:1; padding:0.5rem;" onclick="generateLink(${k.id}, 'pc')">
          🖥️ PC Link
        </button>
        <button class="btn btn-secondary" style="flex:1; padding:0.5rem;" onclick="generateLink(${k.id}, 'mobile')">
          📱 Mobile
        </button>
      </div>
      <div id="link-container-${k.id}" class="hidden" style="background:rgba(0,0,0,0.4); padding:0.8rem; border-radius:6px; border:1px solid var(--card-border); word-break:break-all; font-size:0.85rem; margin-top:10px; position:relative;">
        <span id="link-text-${k.id}"></span>
        <button onclick="copyLink(${k.id})" style="position:absolute; right:5px; top:5px; background:var(--accent-red); border:none; color:white; border-radius:4px; cursor:pointer; padding:2px 8px; font-size:0.8rem;">Copy</button>
      </div>
    </div>
  `).join('');
}

function maskKey(key) {
  if(!key || key.length < 15) return 'KAIRO-****-****-****';
  const parts = key.split('-');
  return `${parts[0]}-****-****-${parts[3]}`;
}

window.toggleKey = function(id, fullKey) {
  const display = document.getElementById(`key-display-${id}`);
  if (display.innerText.includes('****')) {
    display.innerText = fullKey;
  } else {
    display.innerText = maskKey(fullKey);
  }
}

window.generateLink = async function(id, type) {
  const res = await api('POST', '/api/generate-link', { key_id: id });
  if (res.error) {
    showToast(res.error, 'error');
    return;
  }
  
  const linkContainer = document.getElementById(`link-container-${id}`);
  const linkText = document.getElementById(`link-text-${id}`);
  const url = type === 'mobile' ? res.mobile_url : res.url;
  
  if(!url) {
    showToast('Failed to generate link', 'error');
    return;
  }
  
  linkText.textContent = url;
  linkText.dataset.url = url;
  linkContainer.classList.remove('hidden');
}

window.copyLink = function(id) {
  const url = document.getElementById(`link-text-${id}`).dataset.url;
  copyToClipboard(url);
}
