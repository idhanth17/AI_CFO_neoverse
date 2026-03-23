/* ═══════════════════════════════════════════════════
   AI CFO — Frontend App Logic
   Full mic recording + all features
   ═══════════════════════════════════════════════════ */

// =======================================================================
// GLOBAL STATE & SECRETS
// =======================================================================
const API = 'http://localhost:8000';
const API_KEY = 'neoverse-secure-key-2026';

const LANG_FLAGS = { en: '🇬🇧', ta: '🇮🇳', ml: '🇮🇳', hi: '🇮🇳', kn: '🇮🇳' };

// ─── Recording state ──────────────────────────────────────────────────────────
const rec = {
  voice: { mediaRecorder: null, chunks: [], blob: null, timer: null, seconds: 0 },
};

// ─── File upload state ────────────────────────────────────────────────────────
let voiceFile = null;
let invFile = null;

// ─── Current tab state ────────────────────────────────────────────────────────
let currentTab = 'dashboard';
let currentAnalyticsTab = 'profit';

// ═══════════════════════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════════

function showTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');
  document.getElementById(`nav-${tab}`)?.classList.add('active');

  const titles = {
    dashboard: '📊 Dashboard', speech: '🎙️ Speech & Sales',
    invoices: '📄 Invoices', inventory: '📦 Inventory',
    analytics: '📈 Analytics', 'sales-list': '🧾 Sales History',
  };
  document.getElementById('page-title').textContent = titles[tab] || tab;

  if (tab === 'dashboard') loadDashboard();
  if (tab === 'invoices') loadInvoices();
  if (tab === 'inventory') { loadInventory(); loadLowStock(); }
  if (tab === 'analytics') loadCurrentAnalytics();
  if (tab === 'sales-list') loadSalesHistory();
}

function refreshCurrentTab() { showTab(currentTab); }

function showSubTab(name) {
  currentAnalyticsTab = name;
  document.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
  document.getElementById(`stab-${name}`)?.classList.add('active');
  const labels = { profit: 'Profit Analysis', demand: 'Demand Forecast', restock: 'Restock Recommendations', gst: 'GST Summary' };
  document.getElementById('analytics-title').textContent = labels[name];
  loadCurrentAnalytics();
}

function toggleAddProduct() {
  const f = document.getElementById('add-product-form');
  f.style.display = f.style.display === 'none' ? 'flex' : 'none';
}

// ═══════════════════════════════════════════════════════════════════════════════
// HEALTH CHECK
// ═══════════════════════════════════════════════════════════════════════════════

async function checkHealth() {
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  try {
    const r = await fetch(`${API}/health`, {
      signal: AbortSignal.timeout(4000),
      headers: { 'X-API-Key': API_KEY }
    });
    if (r.ok) { dot.className = 'status-dot online'; txt.textContent = 'Backend online'; }
    else throw new Error();
  } catch {
    dot.className = 'status-dot offline';
    txt.textContent = 'Backend offline';
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// MIC RECORDING — Record / Stop / Discard
// ═══════════════════════════════════════════════════════════════════════════════

async function startRecording(prefix) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const r = rec[prefix];
    r.chunks = []; r.seconds = 0;

    // Use browser's default supported audio type
    const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';

    r.mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
    r.mediaRecorder.ondataavailable = e => { if (e.data.size > 0) r.chunks.push(e.data); };
    r.mediaRecorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      r.blob = new Blob(r.chunks, { type: r.mediaRecorder.mimeType || 'audio/webm' });
      onRecordingDone(prefix);
    };
    r.mediaRecorder.start(100);

    // UI
    setEl(`${prefix}-rec-start`, 'display', 'none');
    setEl(`${prefix}-rec-stop`, 'display', '');
    setEl(`${prefix}-rec-discard`, 'display', 'none');
    setEl(`${prefix}-mic-timer`, 'display', '');
    addClass(`${prefix}-mic-area`, 'recording');
    addClass(`${prefix}-mic-visual`, 'recording');
    document.getElementById(`${prefix}-mic-status`).textContent = '🔴 Recording…';

    r.timer = setInterval(() => {
      r.seconds++;
      const m = String(Math.floor(r.seconds / 60)).padStart(2, '0');
      const s = String(r.seconds % 60).padStart(2, '0');
      document.getElementById(`${prefix}-mic-timer`).textContent = `${m}:${s}`;
    }, 1000);

  } catch (e) {
    toast('Microphone access denied. Please allow mic in browser settings.', 'error');
  }
}

function stopRecording(prefix) {
  const r = rec[prefix];
  if (r.mediaRecorder && r.mediaRecorder.state !== 'inactive') {
    clearInterval(r.timer);
    r.mediaRecorder.stop();
  }
}

function discardRecording(prefix) {
  const r = rec[prefix];
  r.blob = null; r.chunks = []; r.seconds = 0;
  clearInterval(r.timer);

  // Reset UI
  setEl(`${prefix}-rec-start`, 'display', '');
  setEl(`${prefix}-rec-stop`, 'display', 'none');
  setEl(`${prefix}-rec-discard`, 'display', 'none');
  setEl(`${prefix}-mic-timer`, 'display', 'none');
  setEl(`${prefix}-recorded-tag`, 'display', 'none');
  removeClass(`${prefix}-mic-area`, 'recording', 'ready');
  removeClass(`${prefix}-mic-visual`, 'recording', 'ready');
  document.getElementById(`${prefix}-mic-status`).textContent = 'Click to start recording';
  document.getElementById(`${prefix}-btn`).disabled = true;
}

function onRecordingDone(prefix) {
  const r = rec[prefix];
  clearInterval(r.timer);

  // UI
  setEl(`${prefix}-rec-start`, 'display', '');
  setEl(`${prefix}-rec-stop`, 'display', 'none');
  setEl(`${prefix}-rec-discard`, 'display', '');
  setEl(`${prefix}-mic-timer`, 'display', 'none');
  removeClass(`${prefix}-mic-area`, 'recording');
  removeClass(`${prefix}-mic-visual`, 'recording');
  addClass(`${prefix}-mic-area`, 'ready');
  addClass(`${prefix}-mic-visual`, 'ready');

  const secs = rec[prefix].seconds;
  document.getElementById(`${prefix}-mic-status`).textContent = `✅ Recording ready (${secs}s)`;

  const url = URL.createObjectURL(r.blob);
  const tag = document.getElementById(`${prefix}-recorded-tag`);
  tag.style.display = 'block';
  tag.innerHTML = `🎙️ Recorded (${secs}s) &nbsp; <audio controls src="${url}" style="height:28px;vertical-align:middle"></audio>`;

  document.getElementById(`${prefix}-btn`).disabled = false;
  toast('Recording complete. Ready to submit!', 'success');
}

// ─── Mode toggle (Record / Upload) ───────────────────────────────────────────
function setVoiceMode(mode) {
  document.getElementById('voice-mode-record').classList.toggle('active', mode === 'record');
  document.getElementById('voice-mode-upload').classList.toggle('active', mode === 'upload');
  document.getElementById('voice-record-ui').style.display = mode === 'record' ? '' : 'none';
  document.getElementById('voice-upload-ui').style.display = mode === 'upload' ? '' : 'none';
  voiceFile = null;
  document.getElementById('voice-btn').disabled = true;
  if (mode === 'record') discardRecording('voice');
}

// ─── File upload helpers ──────────────────────────────────────────────────────
function handleVoiceFile(input) {
  voiceFile = input.files[0] || null;
  if (voiceFile) {
    document.getElementById('voice-file-name').style.display = 'block';
    document.getElementById('voice-file-name').textContent = `📁 ${voiceFile.name} (${(voiceFile.size / 1024).toFixed(1)} KB)`;
    document.getElementById('voice-zone').classList.add('has-file');
    document.getElementById('voice-btn').disabled = false;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// VOICE SALE
// ═══════════════════════════════════════════════════════════════════════════════

let currentAmendSaleId = null;

async function runVoiceSale() {
  const isRecordMode = document.getElementById('voice-mode-record').classList.contains('active');
  const audioBlob = isRecordMode ? rec.voice.blob : null;
  const audioFile = isRecordMode ? null : voiceFile;

  if (!audioBlob && !audioFile) { toast('No audio to submit', 'error'); return; }

  const btn = document.getElementById('voice-btn');
  const res = document.getElementById('voice-result');
  setBtnLoading(btn, true, 'Processing…');
  setResult(res, '');

  try {
    const fd = new FormData();
    if (audioBlob) {
      const ext = audioBlob.type.includes('ogg') ? 'ogg' : 'webm';
      fd.append('file', audioBlob, `recording.${ext}`);
    } else {
      fd.append('file', audioFile);
    }

    if (currentAmendSaleId) {
      fd.append('amend_sale_id', currentAmendSaleId);
      currentAmendSaleId = null;
    }

    const selectedLang = document.getElementById('voice-sale-lang')?.value;
    if (selectedLang) {
      fd.append('language', selectedLang);
    }

    const data = await apiPost('/api/sales/voice', fd, true);
    const conf = Math.round((data.language_probability || 0) * 100);
    const cls = data.status === 'processed' ? 'success' : (data.status === 'needs_action' ? 'orange' : (data.status === 'pending_confirmation' ? 'info' : 'error'));

    let extraHtml = '';
    if (data.status === 'needs_action' && data.missing_products && data.missing_products.length > 0) {
      extraHtml = `
        <div style="margin-top: 15px; padding: 12px; background: rgba(255, 165, 0, 0.1); border-left: 3px solid var(--orange); border-radius: 4px;">
          <h4 style="margin: 0 0 8px 0; color: var(--orange)">Products Not in Inventory</h4>
          <p style="margin: 0 0 10px 0; font-size: 13px">The following items are missing: <strong>${data.missing_products.join(', ')}</strong></p>
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-primary btn-sm" onclick="showTab('inventory'); toggleAddProduct();">Add to Inventory</button>
            <button class="btn btn-ghost btn-sm" style="color: var(--red)" onclick="cancelSale()">Cancel Sale (Stock Unavailable)</button>
          </div>
        </div>
      `;
    } else if (data.status === 'pending_confirmation') {
      extraHtml = `
        <div style="margin-top: 15px; padding: 12px; background: rgba(33, 150, 243, 0.1); border-left: 3px solid var(--primary); border-radius: 4px;">
          <h4 style="margin: 0 0 8px 0; color: var(--primary)">Please Confirm Sale</h4>
          <p style="margin: 0 0 10px 0; font-size: 13px">Review the parsed items above. Click Confirm to log this sale, or Amend to correct it via voice.</p>
          <div class="actions-row" data-sale-id="${data.sale_id}" style="display: flex; gap: 8px;">
            <button class="btn btn-primary btn-sm" onclick="confirmSale(${data.sale_id})">Confirm Sale</button>
            <button class="btn btn-ghost btn-sm" style="color: var(--primary)" onclick="startAmendVoice(${data.sale_id}, '${escapeSingleQuotes(data.english_transcript)}')">Amend via Mic</button>
            <button class="btn btn-ghost btn-sm" style="color: var(--red)" onclick="cancelSale()">Cancel</button>
          </div>
        </div>
      `;
    }

    setResult(res, `
      <div class="result-row"><span class="result-label">Status</span><span class="result-val"><span class="badge badge-${data.status}">${data.status}</span></span></div>
      <div class="result-row"><span class="result-label">Sale ID</span><span class="result-val">#${data.sale_id}</span></div>
      <div class="result-row"><span class="result-label">Language</span><span class="result-val"><span class="lang-chip">${LANG_FLAGS[data.detected_language] || '🌐'} ${data.language_name} (${conf}%)</span></span></div>
      <div class="result-row"><span class="result-label">Customer Name</span><span class="result-val">${escHtml(data.customer_name || 'N/A')}</span></div>
      <div class="result-row"><span class="result-label">Payment</span><span class="result-val"><span class="badge badge-${data.payment_status === 'paid' ? 'success' : (data.payment_status === 'partial' ? 'info' : 'orange')}">${data.payment_status === 'paid' ? 'Paid' : (data.payment_status === 'partial' ? 'Partial' : 'Credit / Due')}</span></span></div>
      <div class="result-row"><span class="result-label">Transcript</span><span class="result-val">${escHtml(data.transcript || '(empty)')}</span></div>
      <div class="result-row"><span class="result-label">English Translation</span><span class="result-val highlight">${escHtml(data.english_transcript || '(empty)')}</span></div>
      <div class="result-row"><span class="result-label">Inferred DB Items</span><span class="result-val" style="color: var(--primary); font-weight: 600;">${(data.parsed_item_details || []).map(i => i.inferred_name ? escHtml(i.inferred_name) : `<span style="color:var(--red)">Unmatched (${escHtml(i.raw_name)})</span>`).join(', ') || 'None'
      }</span></div>
      
      <div class="result-row" style="margin-top: 15px; margin-bottom: 5px; border-bottom: 1px solid var(--border); padding-bottom: 5px; display: flex; justify-content: space-between; align-items: center;">
        <span class="result-label" style="font-weight: 600;">Items Parsed (${data.items_parsed})</span>
        ${data.status === 'pending_confirmation' ? '<span style="font-size: 11px; color: var(--text-muted); padding-right: 5px">✏️ You can edit quantities and prices before confirming</span>' : ''}
      </div>
      <div id="parsed-items-container-${data.sale_id}">
      ${(data.parsed_item_details || []).map(itm => `
         <div class="result-row parsed-item-row" data-item-id="${itm.id || ''}" style="background: rgba(0,0,0,0.02); padding: 8px; border-radius: 4px; margin-bottom: 5px; display: flex; align-items: center; justify-content: space-between;">
           <div style="flex: 1; min-width: 0;">
             <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
               ${(data.status === 'pending_confirmation' || data.status === 'needs_action')
          ? `<input type="number" class="edit-qty text-input" value="${itm.quantity}" step="any">`
          : `<strong>${itm.quantity}x</strong>`}
               <strong style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escHtml(itm.raw_name)}">${escHtml(itm.raw_name)}</strong>
               ${(data.status === 'pending_confirmation' || data.status === 'needs_action')
          ? `<button class="btn btn-ghost btn-sm" style="color: var(--red); padding: 2px 6px; margin-left: auto;" onclick="markItemDeleted(this)" title="Delete Item">🗑️</button>`
          : ''}
             </div>
             ${itm.inferred_name
          ? `<small style="color: var(--primary); font-weight: 600; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="Matched as: ${escHtml(itm.inferred_name)}">Matched: ${escHtml(itm.inferred_name)} 
                  ${(data.status === 'pending_confirmation' || data.status === 'needs_action')
            ? `(₹<input type="number" class="edit-price text-input" value="${itm.unit_price}" step="any">)`
            : `(₹${itm.unit_price})`}
                  </small>`
          : `<small style="color: var(--red); display: block;">Unmatched item</small>`}
           </div>
           ${(data.status !== 'pending_confirmation' && data.status !== 'needs_action') ? `<span class="result-val" style="font-weight: 600; padding-left: 10px;">₹${fNum(itm.total_amount)}</span>` : ''}
         </div>
      `).join('')}
      </div>

      <div class="result-row" style="margin-top: 10px; font-size: 16px;"><span class="result-label">Total Amount</span><span class="result-val" style="color: var(--primary); font-weight: bold;">₹${fNum(data.total_amount)}</span></div>
      <div class="result-row"><span class="result-label">Message</span><span class="result-val td-muted">${escHtml(data.message || '')}</span></div>
      ${extraHtml}
    `, cls);

    if (data.status === 'processed') toast(`Sale #${data.sale_id} recorded! ₹${fNum(data.total_amount)}`, 'success');
    else if (data.status === 'pending_confirmation') toast('Sale pending confirmation.', 'info');
    else if (data.status === 'needs_action') toast('Action required: Products missing from inventory', 'orange');
    else toast('Voice sale: ' + (data.message || 'no items detected'), 'error');

    if (data.status === 'processed' && data.payment_status !== 'paid') {
      setTimeout(() => toast(`📱 SMS Sent to ${data.customer_name || 'Customer'}: pending payment reminder`, 'info'), 1000);
    }
  } catch (e) {
    setResult(res, errMsg(e), 'error');
  } finally {
    setBtnLoading(btn, false, '▶ Submit Voice Sale');
  }
}

function escapeSingleQuotes(str) {
  return (str || '').replace(/'/g, "\\'");
}

function startAmendVoice(saleId, oldTranscript) {
  currentAmendSaleId = saleId;
  const prevText = escHtml(oldTranscript || "N/A");
  document.getElementById('voice-result').innerHTML = `
    <div style="padding:15px; border:2px dashed var(--primary); border-radius:8px; text-align:center;">
       <div style="font-weight: 600; font-size: 14px; margin-bottom: 5px; color: var(--primary);">Amending Sale #${saleId}</div>
       <div style="font-size:13px; color:var(--text); margin-bottom: 8px; background: rgba(0,0,0,0.02); padding: 5px; border-radius: 4px;">
         <em>Previous Input: "${prevText}"</em>
       </div>
       <div style="font-size:12px; color:var(--text-muted)">Please record your corrections now. The AI will merge this with the previous transcript.</div>
    </div>
  `;
  showTab('speech');
  // Auto-activate voice record tab
  document.getElementById('voice-mode-record').click();
}

function markItemDeleted(btn) {
  const row = btn.closest('.parsed-item-row');
  const isDeleted = row.classList.toggle('item-deleted');
  if (isDeleted) {
    row.style.opacity = '0.5';
    row.style.textDecoration = 'line-through';
    btn.textContent = 'Undo';
    btn.style.color = 'var(--text-muted)';
  } else {
    row.style.opacity = '1';
    row.style.textDecoration = 'none';
    btn.textContent = '🗑️';
    btn.style.color = 'var(--red)';
  }
}

async function confirmSale(saleId) {
  try {
    const overrides = [];
    const container = document.getElementById(`parsed-items-container-${saleId}`);

    if (container) {
      const rows = container.querySelectorAll('.parsed-item-row');
      rows.forEach(row => {
        const id = parseInt(row.dataset.itemId);
        if (!id) return;

        const isDeleted = row.classList.contains('item-deleted');
        const qtyInput = row.querySelector('.edit-qty');
        const priceInput = row.querySelector('.edit-price');

        let qty = 0;
        let price = 0;

        if (qtyInput && priceInput) {
          qty = parseFloat(qtyInput.value) || 0;
          price = parseFloat(priceInput.value) || 0;
        }

        overrides.push({
          id: id,
          quantity: qty,
          unit_price: price,
          deleted: isDeleted
        });
      });
    }

    const overridesObj = overrides.length > 0 ? { overrides } : {};
    const data = await apiPost('/api/sales/' + saleId + '/confirm', JSON.stringify(overridesObj), false);

    if (data.status === 'processed') {
      toast(`Sale #${data.sale_id} confirmed! Final Total: ₹${fNum(data.total_amount)}`, 'success');

      // Update UI to prevent resubmission
      const actionsDiv = document.querySelector(`.actions-row[data-sale-id="${saleId}"]`);
      if (actionsDiv) {
        actionsDiv.innerHTML = `
          <div style="color: var(--green); font-weight: 500; display: flex; align-items: center; gap: 6px;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
            Sale Successfully Recorded
          </div>
        `;
      }

      if (data.payment_status !== 'paid') {
        setTimeout(() => toast(`📱 SMS Sent to ${data.customer_name || 'Customer'}: pending payment reminder`, 'info'), 1000);
      }

      // Delay fetching table so DB can flush properly
      setTimeout(() => {
        loadAnalytics();
        loadInventory();
      }, 500);

    } else {
      toast(data.message || 'Error confirming sale', 'error');
    }
  } catch (e) {
    toast(errMsg(e), 'error');
  }
}

function cancelSale() {
  document.getElementById('voice-result').innerHTML = '';
  document.getElementById('text-sale-result').innerHTML = '';
  document.getElementById('text-sale-input').value = '';
  toast('Sale cancelled.', 'info');
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEXT SALE + SAMPLE CHIPS
// ═══════════════════════════════════════════════════════════════════════════════

function setSample(text) {
  document.getElementById('text-sale-input').value = text;
  document.getElementById('text-sale-input').focus();
}

async function runTextSale() {
  const text = document.getElementById('text-sale-input').value.trim();
  const lang = document.getElementById('text-sale-lang').value;
  const res = document.getElementById('text-sale-result');
  if (!text) { toast('Please enter sale text', 'error'); return; }

  setResult(res, '<span class="spinner"></span> Processing…', 'info');

  try {
    const body = { text };
    if (lang) body.language = lang;
    if (currentAmendSaleId) {
      body.amend_sale_id = currentAmendSaleId;
      currentAmendSaleId = null;
    }
    const data = await apiPost('/api/sales/text', JSON.stringify(body));
    const conf = Math.round((data.language_probability || 0) * 100);
    const cls = data.status === 'processed' ? 'success' : (data.status === 'needs_action' ? 'orange' : (data.status === 'pending_confirmation' ? 'info' : 'error'));

    let extraHtml = '';
    if (data.status === 'needs_action' && data.missing_products && data.missing_products.length > 0) {
      extraHtml = `
        <div style="margin-top: 15px; padding: 12px; background: rgba(255, 165, 0, 0.1); border-left: 3px solid var(--orange); border-radius: 4px;">
          <h4 style="margin: 0 0 8px 0; color: var(--orange)">Products Not in Inventory</h4>
          <p style="margin: 0 0 10px 0; font-size: 13px">The following items are missing: <strong>${data.missing_products.join(', ')}</strong></p>
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-primary btn-sm" onclick="showTab('inventory'); toggleAddProduct();">Add to Inventory</button>
            <button class="btn btn-ghost btn-sm" style="color: var(--red)" onclick="cancelSale()">Cancel Sale</button>
          </div>
        </div>
      `;
    } else if (data.status === 'pending_confirmation') {
      extraHtml = `
        <div style="margin-top: 15px; padding: 12px; background: rgba(33, 150, 243, 0.1); border-left: 3px solid var(--primary); border-radius: 4px;">
          <h4 style="margin: 0 0 8px 0; color: var(--primary)">Please Confirm Sale</h4>
          <p style="margin: 0 0 10px 0; font-size: 13px">Review the parsed items above. Click Confirm to log this sale, or Amend to correct it.</p>
          <div class="actions-row" data-sale-id="${data.sale_id}" style="display: flex; gap: 8px;">
            <button class="btn btn-primary btn-sm" onclick="confirmSale(${data.sale_id})">Confirm Sale</button>
            <button class="btn btn-ghost btn-sm" style="color: var(--primary)" onclick="startAmendVoice(${data.sale_id}, '${escapeSingleQuotes(data.english_transcript)}')">Amend via Mic</button>
            <button class="btn btn-ghost btn-sm" style="color: var(--red)" onclick="cancelSale()">Cancel</button>
          </div>
        </div>
      `;
    }

    setResult(res, `
      <div class="result-row"><span class="result-label">Status</span><span class="result-val"><span class="badge badge-${data.status}">${data.status}</span></span></div>
      <div class="result-row"><span class="result-label">Sale ID</span><span class="result-val">#${data.sale_id}</span></div>
      <div class="result-row"><span class="result-label">Language</span><span class="result-val"><span class="lang-chip">${LANG_FLAGS[data.detected_language] || '🌐'} ${data.language_name}</span></span></div>
      <div class="result-row"><span class="result-label">Customer Name</span><span class="result-val">${escHtml(data.customer_name || 'N/A')}</span></div>
      <div class="result-row"><span class="result-label">Payment</span><span class="result-val"><span class="badge badge-${data.payment_status === 'paid' ? 'success' : (data.payment_status === 'partial' ? 'info' : 'orange')}">${data.payment_status === 'paid' ? 'Paid' : (data.payment_status === 'partial' ? 'Partial' : 'Credit / Due')}</span></span></div>
      <div class="result-row"><span class="result-label">English Text</span><span class="result-val highlight">${escHtml(data.english_transcript || data.transcript || '')}</span></div>
      <div class="result-row"><span class="result-label">Inferred DB Items</span><span class="result-val" style="color: var(--primary); font-weight: 600;">${(data.parsed_item_details || []).map(i => i.inferred_name ? escHtml(i.inferred_name) : `<span style="color:var(--red)">Unmatched (${escHtml(i.raw_name)})</span>`).join(', ') || 'None'
      }</span></div>
      
      <div class="result-row" style="margin-top: 15px; margin-bottom: 5px; border-bottom: 1px solid var(--border); padding-bottom: 5px;">
        <span class="result-label" style="font-weight: 600;">Items Parsed (${data.items_parsed})</span>
      </div>
      ${(data.parsed_item_details || []).map(itm => `
         <div class="result-row" style="background: rgba(0,0,0,0.02); padding: 8px; border-radius: 4px; margin-bottom: 5px;">
           <span class="result-label" style="width: auto; margin-right: 15px;">
             ${itm.quantity}x <strong>${escHtml(itm.raw_name)}</strong>
             ${itm.inferred_name ? `<br><small style="color: var(--primary); font-weight: 600;">Matched as: ${escHtml(itm.inferred_name)} (₹${itm.unit_price})</small>` : `<br><small style="color: var(--red);">Unmatched item</small>`}
           </span>
           <span class="result-val" style="text-align: right; font-weight: 600;">₹${fNum(itm.total_amount)}</span>
         </div>
      `).join('')}

      <div class="result-row" style="margin-top: 10px; font-size: 16px;"><span class="result-label">Total Amount</span><span class="result-val" style="color: var(--primary); font-weight: bold;">₹${fNum(data.total_amount)}</span></div>
      <div class="result-row"><span class="result-label">Message</span><span class="result-val td-muted">${escHtml(data.message || '')}</span></div>
      ${extraHtml}
    `, cls);

    if (data.status === 'processed') {
      toast(`Sale #${data.sale_id} recorded! ₹${fNum(data.total_amount)}`, 'success');
      document.getElementById('text-sale-input').value = '';
      if (data.payment_status !== 'paid') {
        setTimeout(() => toast(`📱 SMS Sent to ${data.customer_name || 'Customer'}: pending payment reminder`, 'info'), 1000);
      }
    } else if (data.status === 'pending_confirmation') {
      toast('Sale pending confirmation.', 'info');
    } else if (data.status === 'needs_action') {
      toast('Action required: Products missing from inventory', 'orange');
    }
  } catch (e) {
    setResult(res, errMsg(e), 'error');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('text-sale-input')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') runTextSale();
  });
});

// ═══════════════════════════════════════════════════════════════════════════════
// INVOICES
// ═══════════════════════════════════════════════════════════════════════════════

function handleInvFile(input) {
  invFile = input.files[0] || null;
  if (invFile) {
    document.getElementById('inv-file-name').style.display = 'block';
    document.getElementById('inv-file-name').textContent = `📁 ${invFile.name} (${(invFile.size / 1024).toFixed(1)} KB)`;
    document.getElementById('inv-zone').classList.add('has-file');
    document.getElementById('inv-btn').disabled = false;
  }
}

let currentPendingInvoiceId = null;

async function runInvoiceUpload() {
  if (!invFile) return;
  const btn = document.getElementById('inv-btn');
  const res = document.getElementById('inv-result');
  const confirmSection = document.getElementById('inv-confirm-section');
  const tbody = document.querySelector('#inv-confirm-table tbody');

  setBtnLoading(btn, true, 'Processing OCR…');
  setResult(res, '');
  confirmSection.style.display = 'none';

  try {
    const fd = new FormData();
    fd.append('file', invFile);
    const data = await apiPost('/api/invoices/upload', fd, true);

    // Always show summary
    const cls = data.status === 'processed' ? 'success' : (data.status === 'pending_confirmation' ? 'info' : 'error');
    setResult(res, `
      <div class="result-row"><span class="result-label">Status</span><span class="result-val"><span class="badge badge-${data.status}">${data.status}</span></span></div>
      <div class="result-row"><span class="result-label">Invoice ID</span><span class="result-val">#${data.invoice_id}</span></div>
      <div class="result-row"><span class="result-label">Items Parsed</span><span class="result-val">${data.items_parsed}</span></div>
      <div class="result-row"><span class="result-label">Total Amount</span><span class="result-val">₹${fNum(data.total_amount)}</span></div>
      <div class="result-row"><span class="result-label">Total GST</span><span class="result-val">₹${fNum(data.total_gst)}</span></div>
      <div class="result-row"><span class="result-label">Message</span><span class="result-val td-muted">${escHtml(data.message || '')}</span></div>
    `, cls);

    if (data.status === 'processed') {
      toast(`Invoice #${data.invoice_id} processed!`, 'success');
      loadInvoices();
    } else if (data.status === 'pending_confirmation') {
      toast(`Invoice parsed! Please review the ${data.items_parsed} items.`, 'info');
      currentPendingInvoiceId = data.invoice_id;

      // Render interactive table
      tbody.innerHTML = '';
      (data.parsed_item_details || []).forEach((itm, idx) => {
        const tr = document.createElement('tr');
        tr.dataset.itemId = itm.id || idx;
        tr.innerHTML = `
          <td><strong>${escHtml(itm.raw_name)}</strong></td>
          <td>${itm.inferred_name ? `<span style="color:var(--primary); font-weight:600;">${escHtml(itm.inferred_name)}</span>` : '<span style="color:var(--red);">New Item</span>'}</td>
          <td><input type="number" class="input p-qty" value="${itm.quantity}" min="0" step="0.01" style="width:70px; padding:4px;" ${!itm.quantity ? 'style="border-color:var(--red)"' : ''} /></td>
          <td><input type="number" class="input p-cost" value="${itm.unit_price.toFixed(2)}" min="0" step="0.01" style="width:90px; padding:4px;" ${!itm.unit_price ? 'style="border-color:var(--red)"' : ''} /></td>
          <td><input type="number" class="input p-profit" value="20" min="0" max="999" step="1" style="width:70px; padding:4px;" /></td>
          <td><input type="number" class="input p-sale" value="${(itm.unit_price * 1.2).toFixed(2)}" readonly style="width:90px; padding:4px; background:var(--bg-card);" /></td>
          <td><button class="btn btn-ghost btn-danger" style="padding:4px;" onclick="dropInvoiceItem(this)">❌</button></td>
        `;

        // Attach recalculate logic
        const costI = tr.querySelector('.p-cost');
        const profI = tr.querySelector('.p-profit');
        const saleI = tr.querySelector('.p-sale');
        const recalc = () => {
          const c = parseFloat(costI.value) || 0;
          const p = parseFloat(profI.value) || 0;
          saleI.value = (c * (1 + p / 100)).toFixed(2);
        };
        costI.addEventListener('input', recalc);
        profI.addEventListener('input', recalc);

        tbody.appendChild(tr);
      });

      confirmSection.style.display = 'block';
    }

  } catch (e) {
    setResult(res, errMsg(e), 'error');
  } finally {
    setBtnLoading(btn, false, '▲ Upload Invoice (Wait ~30s)');
  }
}

async function submitInvoiceConfirmation() {
  if (!currentPendingInvoiceId) return;
  const btn = document.getElementById('inv-confirm-btn');
  const tbody = document.querySelector('#inv-confirm-table tbody');
  const res = document.getElementById('inv-result');
  const confirmSection = document.getElementById('inv-confirm-section');

  const overrides = [];
  let hasMissing = false;

  tbody.querySelectorAll('tr').forEach(tr => {
    const isDeleted = tr.classList.contains('deleted');
    const id = parseInt(tr.dataset.itemId, 10);
    const q = parseFloat(tr.querySelector('.p-qty').value) || 0;
    const c = parseFloat(tr.querySelector('.p-cost').value) || 0;
    const p = parseFloat(tr.querySelector('.p-profit').value) || 0;

    if (!isDeleted && (q <= 0 || c <= 0)) hasMissing = true;

    overrides.push({
      id: id,
      quantity: q,
      unit_price: c,
      profit_percentage: p,
      deleted: isDeleted
    });
  });

  if (hasMissing) {
    toast("Please fill in missing quantities or cost prices (or drop the item)", "error");
    return;
  }

  setBtnLoading(btn, true, 'Updating Inventory…');
  try {
    const data = await apiPost(`/api/invoices/${currentPendingInvoiceId}/confirm`, { overrides: overrides });

    confirmSection.style.display = 'none';
    setResult(res, `
      <div class="result-row"><span class="result-label">Status</span><span class="result-val"><span class="badge badge-success">Processed</span></span></div>
      <div class="result-row"><span class="result-label">Items Committed</span><span class="result-val">${data.items_parsed}</span></div>
      <div class="result-row"><span class="result-label">Message</span><span class="result-val">${escHtml(data.message)}</span></div>
    `, 'success');

    toast("Inventory successfully updated!", "success");
    currentPendingInvoiceId = null;
    document.getElementById('inv-zone').classList.remove('has-file');
    invFile = null;
    document.getElementById('inv-file-name').style.display = 'none';
    loadInvoices();
    loadInventory();
  } catch (e) {
    toast(errMsg(e), 'error');
  } finally {
    setBtnLoading(btn, false, '✅ Verify & Update Inventory');
  }
}

async function loadInvoices() {
  const el = document.getElementById('invoices-table');
  el.innerHTML = '<div class="empty-state"><span class="spinner"></span></div>';
  try {
    const rows = await apiFetch('/api/invoices/');
    if (!rows.length) { el.innerHTML = '<div class="empty-state">No invoices yet.</div>'; return; }
    el.innerHTML = `<table>
      <thead><tr><th>#</th><th>Supplier</th><th>Invoice No.</th><th>Total</th><th>GST</th><th>Status</th><th>Date</th></tr></thead>
      <tbody>${rows.map(r => `<tr>
        <td class="td-muted">${r.id}</td>
        <td>${escHtml(r.supplier_name || '—')}</td>
        <td class="td-mono">${escHtml(r.invoice_number || '—')}</td>
        <td class="td-mono">₹${fNum(r.total_amount)}</td>
        <td class="td-mono">₹${fNum(r.total_gst)}</td>
        <td><span class="badge badge-${r.status}">${r.status}</span></td>
        <td class="td-muted">${fDate(r.created_at)}</td>
      </tr>`).join('')}</tbody></table>`;
  } catch (e) { el.innerHTML = `<div class="empty-state">${errMsg(e)}</div>`; }
}

// ═══════════════════════════════════════════════════════════════════════════════
// INVENTORY
// ═══════════════════════════════════════════════════════════════════════════════

function prefillProduct(name, sku, cost, sell, gst, stock, unit, reorder) {
  document.getElementById('p-name').value = name;
  document.getElementById('p-sku').value = sku;
  document.getElementById('p-cost').value = cost;
  document.getElementById('p-sell').value = sell;
  document.getElementById('p-gst').value = gst;
  document.getElementById('p-stock').value = stock;
  document.getElementById('p-unit').value = unit;
  document.getElementById('p-reorder').value = reorder;
}

async function loadInventory() {
  const el = document.getElementById('inventory-table');
  el.innerHTML = '<div class="empty-state"><span class="spinner"></span></div>';
  try {
    const rows = await apiFetch('/api/inventory/');
    if (!rows.length) {
      el.innerHTML = '<div class="empty-state">No products yet. Click "+ Add Product" to get started.</div>';
      return;
    }
    el.innerHTML = `<table>
      <thead><tr><th>#</th><th>Name</th><th>SKU</th><th>Stock</th><th>Unit</th><th>Cost ₹</th><th>Sell ₹</th><th>GST%</th><th>Reorder</th><th></th></tr></thead>
      <tbody>${rows.map(r => `<tr>
        <td class="td-muted">${r.id}</td>
        <td><strong>${escHtml(r.name)}</strong></td>
        <td class="td-mono td-muted">${escHtml(r.sku || '—')}</td>
        <td class="td-mono" style="color:${r.current_stock <= r.reorder_point ? 'var(--red)' : 'var(--green)'};font-weight:600">${r.current_stock}</td>
        <td class="td-muted">${r.unit}</td>
        <td class="td-mono">${fNum(r.cost_price)}</td>
        <td class="td-mono">${fNum(r.selling_price)}</td>
        <td class="td-mono">${r.gst_rate}%</td>
        <td class="td-mono">${r.reorder_point}</td>
        <td><button class="btn btn-danger" onclick="deleteProduct(${r.id},'${escHtml(r.name)}')">Delete</button></td>
      </tr>`).join('')}</tbody></table>`;
  } catch (e) { el.innerHTML = `<div class="empty-state">${errMsg(e)}</div>`; }
}

async function loadLowStock() {
  const el = document.getElementById('lowstock-table');
  el.innerHTML = '<div class="empty-state"><span class="spinner"></span></div>';
  try {
    const rows = await apiFetch('/api/inventory/low-stock');
    if (!rows.length) { el.innerHTML = '<div class="empty-state" style="color:var(--green)">✅ All stock levels healthy!</div>'; return; }
    el.innerHTML = `<table>
      <thead><tr><th>Product</th><th>Current Stock</th><th>Reorder Point</th><th>Unit</th></tr></thead>
      <tbody>${rows.map(r => `<tr>
        <td style="color:var(--orange);font-weight:600">⚠️ ${escHtml(r.name)}</td>
        <td class="td-mono" style="color:var(--red)">${r.current_stock}</td>
        <td class="td-mono">${r.reorder_point}</td>
        <td>${r.unit}</td>
      </tr>`).join('')}</tbody></table>`;
  } catch (e) { el.innerHTML = `<div class="empty-state">${errMsg(e)}</div>`; }
}

async function addProduct() {
  const name = document.getElementById('p-name').value.trim();
  const sku = document.getElementById('p-sku').value.trim();
  const body = {
    name, cost_price: +document.getElementById('p-cost').value || 0,
    selling_price: +document.getElementById('p-sell').value || 0,
    gst_rate: +document.getElementById('p-gst').value || 0,
    current_stock: +document.getElementById('p-stock').value || 0,
    unit: document.getElementById('p-unit').value.trim() || 'pcs',
    reorder_point: +document.getElementById('p-reorder').value || 5,
  };
  if (sku) body.sku = sku;
  if (!name) { toast('Product name required', 'error'); return; }
  const res = document.getElementById('add-product-result');
  setResult(res, '<span class="spinner"></span> Saving…', 'info');
  try {
    await apiPost('/api/inventory/', JSON.stringify(body));
    setResult(res, `✅ "${escHtml(name)}" added!`, 'success');
    toast(`Added: ${name}`, 'success');
    loadInventory(); loadLowStock();
  } catch (e) { setResult(res, errMsg(e), 'error'); }
}

async function deleteProduct(id, name) {
  if (!confirm(`Deactivate "${name}"?`)) return;
  try {
    const r = await fetch(`${API}/api/inventory/${id}`, {
      method: 'DELETE',
      headers: { 'X-API-Key': API_KEY }
    });
    if (r.ok || r.status === 204) { toast(`"${name}" deactivated`, 'info'); loadInventory(); loadLowStock(); }
    else throw new Error(`HTTP ${r.status}`);
  } catch (e) { toast('Delete failed: ' + e.message, 'error'); }
}

// ═══════════════════════════════════════════════════════════════════════════════
// ANALYTICS
// ═══════════════════════════════════════════════════════════════════════════════

async function loadCurrentAnalytics() {
  const el = document.getElementById('analytics-table');
  const tab = currentAnalyticsTab;
  el.innerHTML = '<div class="empty-state"><span class="spinner"></span> Loading…</div>';
  try {
    if (tab === 'profit') {
      const rows = await apiFetch('/api/analytics/profit');
      if (!rows.length) { el.innerHTML = '<div class="empty-state">No data. Add products &amp; record sales first.</div>'; return; }
      el.innerHTML = `<table>
        <thead><tr><th>Product</th><th>Units Sold</th><th>Revenue</th><th>COGS</th><th>Gross Profit</th><th>Margin</th></tr></thead>
        <tbody>${rows.map(r => `<tr>
          <td><strong>${escHtml(r.product_name)}</strong></td>
          <td class="td-mono">${r.units_sold} ${r.unit}</td>
          <td class="td-mono">₹${fNum(r.total_revenue)}</td>
          <td class="td-mono">₹${fNum(r.total_cogs)}</td>
          <td class="td-mono" style="color:${r.gross_profit >= 0 ? 'var(--green)' : 'var(--red)'};font-weight:600">₹${fNum(r.gross_profit)}</td>
          <td class="td-mono">${(r.margin_pct || 0).toFixed(1)}%</td>
        </tr>`).join('')}</tbody></table>`;
    } else if (tab === 'demand') {
      const rows = await apiFetch('/api/analytics/demand');
      if (!rows.length) { el.innerHTML = '<div class="empty-state">Not enough sales data for forecasting.</div>'; return; }
      el.innerHTML = `<table>
        <thead><tr><th>Product</th><th>Stock</th><th>Avg Daily Sales</th><th>7-Day Forecast</th><th>30-Day Forecast</th><th>Days Until Stockout</th></tr></thead>
        <tbody>${rows.map(r => `<tr>
          <td><strong>${escHtml(r.product_name)}</strong></td>
          <td class="td-mono">${r.current_stock} ${r.unit}</td>
          <td class="td-mono">${(r.avg_daily_sales || 0).toFixed(2)}</td>
          <td class="td-mono">${(r.forecast_7d || 0).toFixed(1)}</td>
          <td class="td-mono">${(r.forecast_30d || 0).toFixed(1)}</td>
          <td class="td-mono" style="color:${(r.days_until_stockout ?? 999) < 7 ? 'var(--red)' : (r.days_until_stockout ?? 999) < 14 ? 'var(--orange)' : 'var(--green)'}">
            ${r.days_until_stockout ?? '∞'} days</td>
        </tr>`).join('')}</tbody></table>`;
    } else if (tab === 'restock') {
      const rows = await apiFetch('/api/analytics/restock');
      if (!rows.length) { el.innerHTML = '<div class="empty-state">No restock recommendations.</div>'; return; }
      el.innerHTML = `<table>
        <thead><tr><th>Product</th><th>Stock</th><th>Reorder Qty</th><th>Urgency</th><th>Reason</th></tr></thead>
        <tbody>${rows.map(r => `<tr>
          <td><strong>${escHtml(r.product_name)}</strong></td>
          <td class="td-mono">${r.current_stock} ${r.unit}</td>
          <td class="td-mono" style="color:var(--accent);font-weight:700">${r.reorder_quantity} ${r.unit}</td>
          <td><span class="badge badge-${r.urgency}">${r.urgency}</span></td>
          <td class="td-muted">${escHtml(r.reason || '')}</td>
        </tr>`).join('')}</tbody></table>`;
    } else if (tab === 'gst') {
      const rows = await apiFetch('/api/analytics/gst');
      if (!rows.length) { el.innerHTML = '<div class="empty-state">No GST data. Process invoices first.</div>'; return; }
      el.innerHTML = `<table>
        <thead><tr><th>Month</th><th>Taxable</th><th>CGST</th><th>SGST</th><th>IGST</th><th>Total GST</th><th>Items</th></tr></thead>
        <tbody>${rows.map(r => `<tr>
          <td>${r.year}-${String(r.month).padStart(2, '0')}</td>
          <td class="td-mono">₹${fNum(r.taxable_amount)}</td>
          <td class="td-mono">₹${fNum(r.cgst)}</td>
          <td class="td-mono">₹${fNum(r.sgst)}</td>
          <td class="td-mono">₹${fNum(r.igst)}</td>
          <td class="td-mono" style="color:var(--orange);font-weight:700">₹${fNum(r.total_gst)}</td>
          <td class="td-mono">${r.item_count}</td>
        </tr>`).join('')}</tbody></table>`;
    }
  } catch (e) { el.innerHTML = `<div class="empty-state">${errMsg(e)}</div>`; }
}

// ═══════════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════════════════════════════

async function loadDashboard() {
  const grid = document.getElementById('stat-grid');
  grid.innerHTML = Array(6).fill('<div class="stat-card skeleton"></div>').join('');
  try {
    const d = await apiFetch('/api/analytics/dashboard');
    const stats = [
      { label: 'Total Products', value: d.total_products, icon: '📦', cls: 'accent' },
      { label: 'Low Stock Items', value: d.low_stock_count, icon: '⚠️', cls: d.low_stock_count > 0 ? 'orange' : 'green' },
      { label: 'Total Sales', value: d.total_sales, icon: '🛒', cls: 'accent' },
      { label: 'Total Invoices', value: d.total_invoices, icon: '📄', cls: 'accent' },
      { label: 'Total Revenue', value: `₹${fNum(d.total_revenue)}`, icon: '💰', cls: 'green' },
      { label: 'Total Purchases', value: `₹${fNum(d.total_purchases)}`, icon: '🏪', cls: 'accent' },
    ];
    grid.innerHTML = stats.map(s => `
      <div class="stat-card">
        <div class="stat-label">${s.label}</div>
        <div class="stat-value ${s.cls}">${s.value}</div>
        <div class="stat-icon">${s.icon}</div>
      </div>`).join('');
    renderProfitTable(d.profit_summary || []);
    renderRestockTable(d.restock_recs || []);
  } catch (e) {
    grid.innerHTML = `<div class="stat-card" style="grid-column:1/-1"><div class="empty-state">${errMsg(e)}</div></div>`;
  }
}

function renderProfitTable(rows) {
  const el = document.getElementById('profit-table');
  if (!rows.length) { el.innerHTML = '<div class="empty-state">No profit data yet. Add products &amp; record sales.</div>'; return; }
  el.innerHTML = `<table>
    <thead><tr><th>Product</th><th>Revenue</th><th>Gross Profit</th><th>Margin</th></tr></thead>
    <tbody>${rows.map(r => `<tr>
      <td>${escHtml(r.product_name)}</td>
      <td class="td-mono">₹${fNum(r.total_revenue)}</td>
      <td class="td-mono" style="color:${r.gross_profit >= 0 ? 'var(--green)' : 'var(--red)'}">₹${fNum(r.gross_profit)}</td>
      <td class="td-mono">${(r.margin_pct || 0).toFixed(1)}%</td>
    </tr>`).join('')}</tbody></table>`;
}

function renderRestockTable(rows) {
  const el = document.getElementById('restock-table');
  if (!rows.length) { el.innerHTML = '<div class="empty-state">No restock recommendations.</div>'; return; }
  el.innerHTML = `<table>
    <thead><tr><th>Product</th><th>Stock</th><th>Reorder Qty</th><th>Urgency</th></tr></thead>
    <tbody>${rows.map(r => `<tr>
      <td>${escHtml(r.product_name)}</td>
      <td class="td-mono">${r.current_stock} ${r.unit}</td>
      <td class="td-mono">${r.reorder_quantity} ${r.unit}</td>
      <td><span class="badge badge-${r.urgency}">${r.urgency}</span></td>
    </tr>`).join('')}</tbody></table>`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SALES HISTORY
// ═══════════════════════════════════════════════════════════════════════════════

async function loadSalesHistory() {
  const el = document.getElementById('sales-history-table');
  el.innerHTML = '<div class="empty-state"><span class="spinner"></span></div>';
  try {
    const rows = await apiFetch('/api/sales/');
    if (!rows.length) { el.innerHTML = '<div class="empty-state">No sales yet.</div>'; return; }
    el.innerHTML = `<table>
      <thead><tr><th>#</th><th>Status</th><th>Language</th><th>Transcript</th><th>English</th><th>Items</th><th>Total</th><th>Date</th></tr></thead>
      <tbody>${rows.map(r => `<tr>
        <td class="td-muted">${r.id}</td>
        <td><span class="badge badge-${r.status}">${r.status}</span></td>
        <td>${r.language_name ? `<span class="lang-chip">${LANG_FLAGS[r.detected_language] || '🌐'} ${r.language_name}</span>` : '<span class="td-muted">—</span>'}</td>
        <td style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(r.raw_text || '')}">${escHtml(r.raw_text || '—')}</td>
        <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--green)" title="${escHtml(r.english_transcript || '')}">${escHtml(r.english_transcript || '—')}</td>
        <td class="td-mono">${(r.items || []).length}</td>
        <td class="td-mono">₹${fNum(r.total_amount)}</td>
        <td class="td-muted">${fDate(r.created_at)}</td>
      </tr>`).join('')}</tbody></table>`;
  } catch (e) { el.innerHTML = `<div class="empty-state">${errMsg(e)}</div>`; }
}

// ═══════════════════════════════════════════════════════════════════════════════
// API HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

async function apiFetch(path, method = 'GET') {
  const r = await fetch(API + path, {
    method,
    headers: { 'X-API-Key': API_KEY }
  });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try { const j = await r.json(); detail = j.detail || JSON.stringify(j); } catch { }
    throw new Error(detail);
  }
  return r.json();
}

async function apiPost(path, body, isFormData = false) {
  const headers = isFormData ? {} : { 'Content-Type': 'application/json' };
  headers['X-API-Key'] = API_KEY;
  const fetchBody = isFormData ? body : (typeof body === 'string' ? body : JSON.stringify(body));
  const r = await fetch(API + path, { method: 'POST', headers, body: fetchBody });
  if (!r.ok) {
    let detail = `HTTP ${r.status}`;
    try { const j = await r.json(); detail = j.detail || JSON.stringify(j); } catch { }
    throw new Error(detail);
  }
  return r.json();
}

// ═══════════════════════════════════════════════════════════════════════════════
// UI HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

function setResult(el, html, cls = '') {
  el.style.display = html ? 'block' : 'none';
  el.className = 'result-box' + (cls ? ' ' + cls : '');
  el.innerHTML = html;
}

function setBtnLoading(btn, loading, label) {
  if (!btn) return;
  if (loading) { btn._orig = btn.innerHTML; btn.innerHTML = `<span class="spinner"></span> ${label}`; btn.disabled = true; }
  else { btn.innerHTML = btn._orig || label; btn.disabled = false; }
}

function toast(msg, type = 'info') {
  const ctr = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  el.innerHTML = `<span>${icons[type] || ''}</span><span>${escHtml(String(msg))}</span>`;
  ctr.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .4s'; setTimeout(() => el.remove(), 400); }, 4000);
}

function setEl(id, prop, val) { const e = document.getElementById(id); if (e) e.style[prop] = val; }
function addClass(id, ...cls) { const e = document.getElementById(id); if (e) e.classList.add(...cls); }
function removeClass(id, ...cls) { const e = document.getElementById(id); if (e) e.classList.remove(...cls); }
function escHtml(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function fNum(n) { return (parseFloat(n) || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function fDate(s) { if (!s) return '—'; try { return new Date(s).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }); } catch { return String(s).slice(0, 16); } }
function errMsg(e) {
  const msg = e?.message || String(e);
  if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('ERR_CONNECTION_REFUSED'))
    return '❌ Cannot connect to backend. Is <code>http://localhost:8000</code> running?';
  return escHtml(msg);
}

// ═══════════════════════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════════════════════

checkHealth();
setInterval(checkHealth, 15000);
loadDashboard();

async function cancelInvoice() {
  if (currentPendingInvoiceId) {
    try {
      await fetch(`${API}/api/invoices/${currentPendingInvoiceId}`, {
        method: 'DELETE',
        headers: { 'X-API-Key': API_KEY }
      });
    } catch (e) {
      console.error("Failed to delete invoice:", e);
    }
  }

  currentPendingInvoiceId = null;
  invFile = null;

  const fileInput = document.getElementById('inv-file');
  if (fileInput) fileInput.value = '';

  const fileNameTag = document.getElementById('inv-file-name');
  if (fileNameTag) fileNameTag.style.display = 'none';

  const zone = document.getElementById('inv-zone');
  if (zone) zone.classList.remove('has-file');

  const result = document.getElementById('inv-result');
  if (result) result.style.display = 'none';

  const confirmSection = document.getElementById('inv-confirm-section');
  if (confirmSection) confirmSection.style.display = 'none';

  const uploadBtn = document.getElementById('inv-btn');
  if (uploadBtn) uploadBtn.disabled = true;

  toast('Invoice cancelled and removed.', 'info');
  loadInvoices();
}

function dropInvoiceItem(btn) {
  const tr = btn.closest('tr');
  if (!tr) return;
  tr.classList.toggle('deleted');
  const isDeleted = tr.classList.contains('deleted');
  btn.textContent = isDeleted ? '♻️' : '❌';
  toast(isDeleted ? 'Item dropped — will be skipped on confirm' : 'Item restored', 'info');
}

// ═══════════════════════════════════════════════════════════════════════════════
// CHATBOT WIDGET
// ═══════════════════════════════════════════════════════════════════════════════

let chatbotOpen = false;

function toggleChatbot() {
  chatbotOpen = !chatbotOpen;
  const panel = document.getElementById('chatbot-panel');
  const fab = document.getElementById('chatbot-fab');
  if (chatbotOpen) {
    panel.classList.add('open');
    fab.classList.add('active');
    document.getElementById('chatbot-input').focus();
  } else {
    panel.classList.remove('open');
    fab.classList.remove('active');
  }
}

function chatSuggestion(text) {
  document.getElementById('chatbot-input').value = text;
  sendChatMessage();
  // Hide suggestions after first use
  const sugg = document.getElementById('chatbot-suggestions');
  if (sugg) sugg.style.display = 'none';
}

function addChatMessage(text, sender) {
  const container = document.getElementById('chatbot-messages');
  const div = document.createElement('div');
  div.className = `chat-msg ${sender}`;
  div.innerHTML = `<div class="chat-bubble">${escHtml(text)}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function addChatBubbleHTML(html, sender) {
  const container = document.getElementById('chatbot-messages');
  const div = document.createElement('div');
  div.className = `chat-msg ${sender}`;
  div.innerHTML = `<div class="chat-bubble">${html}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

async function sendChatMessage() {
  const input = document.getElementById('chatbot-input');
  const query = input.value.trim();
  if (!query) return;

  // Show user message
  addChatMessage(query, 'user');
  input.value = '';

  // Show typing indicator
  const typingDiv = addChatBubbleHTML('<span class="typing-dots"><span>.</span><span>.</span><span>.</span></span>', 'bot');

  try {
    const fd = new FormData();
    fd.append('query', query);
    fd.append('enable_tts', 'false');

    const res = await fetch(`${API}/api/chatbot/text-query`, {
      method: 'POST',
      body: fd,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Server error (${res.status})`);
    }

    const data = await res.json();

    // Remove typing indicator
    typingDiv.remove();

    // Build response
    let responseHTML = escHtml(data.answer_text || 'No response.');

    // Add metadata badge
    const langBadge = data.detected_language ? `<span class="chat-meta">${data.detected_language}</span>` : '';
    const intentBadge = data.intent ? `<span class="chat-meta">${data.intent.replace('_', ' ')}</span>` : '';
    responseHTML += `<div class="chat-meta-row">${langBadge}${intentBadge}</div>`;

    addChatBubbleHTML(responseHTML, 'bot');

  } catch (err) {
    typingDiv.remove();
    addChatBubbleHTML(`<span style="color: var(--red);">Error: ${escHtml(err.message)}</span>`, 'bot');
  }
}

// Enter key handler for chatbot input
document.addEventListener('DOMContentLoaded', () => {
  const chatInput = document.getElementById('chatbot-input');
  if (chatInput) {
    chatInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') sendChatMessage();
    });
  }
});
