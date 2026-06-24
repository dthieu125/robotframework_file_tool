/**
 * Robot Framework Web Tool – main.js
 * Single-page application logic for all 4 features.
 */

'use strict';

/* ===================================================================
   UTILITIES
=================================================================== */

function showToast(message, type = 'info') {
  const icons = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info', warning: 'fa-triangle-exclamation' };
  const id = 'toast-' + Date.now();
  const html = `
    <div id="${id}" class="toast toast-${type} align-items-center" role="alert" aria-atomic="true">
      <div class="toast-header">
        <i class="fa-solid ${icons[type] || icons.info} me-2"></i>
        <strong class="me-auto">${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
        <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
      </div>
      <div class="toast-body">${message}</div>
    </div>`;
  document.getElementById('toast-container').insertAdjacentHTML('beforeend', html);
  const el = document.getElementById(id);
  const t = new bootstrap.Toast(el, { delay: 4500 });
  t.show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

function copyToClipboard(text, label = 'Content') {
  navigator.clipboard.writeText(text).then(() => {
    showToast(`${label} copied to clipboard`, 'success');
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(`${label} copied to clipboard`, 'success');
  });
}

function setLoading(btn, loading, text = '') {
  if (loading) {
    btn.dataset.origText = btn.innerHTML;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>${text || 'Processing...'}`;
    btn.disabled = true;
  } else {
    btn.innerHTML = btn.dataset.origText || btn.innerHTML;
    btn.disabled = false;
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function setupDropzone(dropzone, fileInput, onFile, multiple = false) {
  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('drag-over'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
  dropzone.addEventListener('drop', e => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    const files = Array.from(e.dataTransfer.files);
    if (files.length) onFile(multiple ? files : [files[0]]);
  });
  fileInput.addEventListener('change', () => {
    const files = Array.from(fileInput.files);
    if (files.length) onFile(multiple ? files : [files[0]]);
    fileInput.value = '';
  });
}

/* ===================================================================
   THEME TOGGLE
=================================================================== */

(function () {
  const html = document.documentElement;
  const toggle = document.getElementById('theme-toggle');
  const iconLight = document.getElementById('theme-icon-light');
  const iconDark = document.getElementById('theme-icon-dark');

  function applyTheme(theme) {
    html.setAttribute('data-theme', theme);
    localStorage.setItem('rf-theme', theme);
    if (theme === 'light') {
      iconLight.style.display = '';
      iconDark.style.display = 'none';
    } else {
      iconLight.style.display = 'none';
      iconDark.style.display = '';
    }
  }

  const saved = localStorage.getItem('rf-theme') || 'dark';
  applyTheme(saved);

  toggle.addEventListener('click', () => {
    const current = html.getAttribute('data-theme') || 'dark';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  });
})();

/* ===================================================================
   NAVIGATION
=================================================================== */

document.querySelectorAll('.sidebar-nav .nav-item').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    const panel = item.dataset.panel;
    document.querySelectorAll('.sidebar-nav .nav-item').forEach(n => n.classList.remove('active'));
    item.classList.add('active');
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`panel-${panel}`).classList.add('active');
  });
});

/* ===================================================================
   TOOLTIPS
=================================================================== */

document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
  new bootstrap.Tooltip(el);
});

/* ===================================================================
   1. REPORT MERGER
=================================================================== */

(function () {
  const dropzone = document.getElementById('merger-dropzone');
  const fileInput = document.getElementById('merger-file-input');
  fileInput.setAttribute('multiple', '');

  let mergerFiles = [];
  const MERGER_SETTINGS_KEY = 'rf-merger-settings';
  const mergerSettings = {
    updateHistory: 'keep',
    clearInputsAfterMerge: false,
    cleanupAgeHours: 24,
  };

  /**
   * Per-file metadata cache.  Each File is mapped to
   *   { suiteName: string, sourcePath: string }
   * so we only have to read each file once.
   */
  const fileMeta = new WeakMap();

  function readMergerSettings() {
    try {
      const saved = JSON.parse(localStorage.getItem(MERGER_SETTINGS_KEY) || '{}');
      Object.assign(mergerSettings, saved);
    } catch { /* keep defaults */ }
  }

  function applyMergerSettingsToUi() {
    const historyEl = document.querySelector(`input[name="merger-history-setting"][value="${mergerSettings.updateHistory}"]`);
    if (historyEl) historyEl.checked = true;
    document.getElementById('merger-clear-inputs-after-merge').checked = !!mergerSettings.clearInputsAfterMerge;
    document.getElementById('cleanup-age-hours').value = mergerSettings.cleanupAgeHours || 24;
  }

  function collectMergerSettingsFromUi() {
    mergerSettings.updateHistory =
      document.querySelector('input[name="merger-history-setting"]:checked')?.value || 'keep';
    mergerSettings.clearInputsAfterMerge =
      document.getElementById('merger-clear-inputs-after-merge').checked;
    mergerSettings.cleanupAgeHours =
      Math.max(1, parseInt(document.getElementById('cleanup-age-hours').value, 10) || 24);
    localStorage.setItem(MERGER_SETTINGS_KEY, JSON.stringify(mergerSettings));
  }

  async function loadServerSettings() {
    readMergerSettings();
    try {
      const res = await fetch('/api/settings');
      if (res.ok) {
        const data = await res.json();
        if (data.cleanup_age_hours) mergerSettings.cleanupAgeHours = data.cleanup_age_hours;
      }
    } catch { /* settings are optional */ }
    applyMergerSettingsToUi();
  }

  async function saveServerSettings() {
    await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cleanup_age_hours: mergerSettings.cleanupAgeHours }),
    });
  }

  function clearMergerInputs() {
    mergerFiles = [];
    document.getElementById('merger-file-input').value = '';
    document.getElementById('merger-file-list').innerHTML = '';
    document.getElementById('merger-suite-name-select').innerHTML = '<option value="__auto__">Auto-detect from files</option>';
    document.getElementById('merger-suite-name-custom').value = '';
    document.getElementById('merger-suite-name-custom').style.display = 'none';
  }

  loadServerSettings();

  document.getElementById('merger-settings-save-btn').addEventListener('click', async () => {
    const btn = document.getElementById('merger-settings-save-btn');
    collectMergerSettingsFromUi();
    setLoading(btn, true, 'Saving...');
    try {
      await saveServerSettings();
      showToast('Report merger settings saved', 'success');
      bootstrap.Modal.getInstance(document.getElementById('merger-settings-modal'))?.hide();
    } catch (err) {
      showToast(err.message || 'Failed to save settings', 'error');
    } finally {
      setLoading(btn, false);
    }
  });

  document.getElementById('cleanup-now-btn').addEventListener('click', async () => {
    const btn = document.getElementById('cleanup-now-btn');
    collectMergerSettingsFromUi();
    setLoading(btn, true, 'Cleaning...');
    try {
      await saveServerSettings();
      const res = await fetch('/api/cleanup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cleanup_age_hours: mergerSettings.cleanupAgeHours }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || 'Cleanup failed');
      const removed = data.removed || {};
      showToast(`Cleaned ${removed.uploads || 0} upload item(s) and ${removed.results || 0} result item(s)`, 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setLoading(btn, false);
    }
  });

  // Show/hide the Update mode hint when mode radio changes
  document.querySelectorAll('input[name="merger-mode"]').forEach(radio => {
    radio.addEventListener('change', () => {
      const hint = document.getElementById('merger-update-hint');
      hint.style.display = radio.value === 'update' && radio.checked ? '' : 'none';
    });
  });

  // --- Suite metadata helpers --------------------------------------------

  /**
   * Read the first ~32 KB of *file* and extract the top-level <suite> tag's
   * ``name`` and ``source`` attributes.  Reading only the head of the file
   * keeps things fast even for large output.xml files (the root <suite> tag
   * is always near the top).
   */
  function extractSuiteMetaFromFile(file) {
    return new Promise(resolve => {
      const HEAD_BYTES = 32 * 1024;
      const blob = file.size > HEAD_BYTES ? file.slice(0, HEAD_BYTES) : file;
      const reader = new FileReader();
      reader.onload = e => {
        const text = e.target.result || '';
        // Try the proper parser first (works when the head is well-formed XML)
        try {
          const doc = new DOMParser().parseFromString(text, 'text/xml');
          const suite = doc.querySelector('suite');
          if (suite) {
            resolve({
              suiteName: suite.getAttribute('name') || '',
              sourcePath: suite.getAttribute('source') || '',
            });
            return;
          }
        } catch { /* fall through to regex */ }
        // Regex fallback – the chunk is almost certainly truncated mid-content
        const tag = text.match(/<suite\b[^>]*>/);
        if (tag) {
          const nameMatch = tag[0].match(/\bname="([^"]*)"/);
          const srcMatch = tag[0].match(/\bsource="([^"]*)"/);
          resolve({
            suiteName: nameMatch ? nameMatch[1] : '',
            sourcePath: srcMatch ? srcMatch[1] : '',
          });
          return;
        }
        resolve({ suiteName: '', sourcePath: '' });
      };
      reader.onerror = () => resolve({ suiteName: '', sourcePath: '' });
      reader.readAsText(blob);
    });
  }

  /** Get cached metadata for *file*, reading from disk on cache miss. */
  async function getFileMeta(file) {
    let meta = fileMeta.get(file);
    if (!meta) {
      meta = await extractSuiteMetaFromFile(file);
      fileMeta.set(file, meta);
    }
    return meta;
  }

  /** Re-populate the Suite Name <select> based on currently queued files. */
  async function updateSuiteNameDropdown() {
    const select = document.getElementById('merger-suite-name-select');
    const customInput = document.getElementById('merger-suite-name-custom');
    if (!mergerFiles.length) {
      select.innerHTML = '<option value="__auto__">Auto-detect from files</option>';
      customInput.style.display = 'none';
      return;
    }
    const metas = await Promise.all(mergerFiles.map(getFileMeta));
    const uniqueNames = [...new Set(metas.map(m => m.suiteName).filter(n => n))];

    const prevValue = select.value;
    select.innerHTML = '';
    if (uniqueNames.length === 0) {
      select.add(new Option('Auto-detect from files', '__auto__'));
    } else {
      uniqueNames.forEach(n => select.add(new Option(n, n)));
    }
    select.add(new Option('Custom…', '__custom__'));

    // Restore previous selection if still available
    const stillAvailable = [...select.options].some(o => o.value === prevValue);
    if (stillAvailable) select.value = prevValue;

    // Show/hide custom input
    customInput.style.display = select.value === '__custom__' ? '' : 'none';
  }

  document.getElementById('merger-suite-name-select').addEventListener('change', function () {
    const customInput = document.getElementById('merger-suite-name-custom');
    customInput.style.display = this.value === '__custom__' ? '' : 'none';
  });

  // --- File list ---------------------------------------------------------

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  }

  function formatFileDate(ms) {
    if (!ms) return '—';
    const d = new Date(ms);
    const date = d.getFullYear() + '-' +
      String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0');
    const time = String(d.getHours()).padStart(2, '0') + ':' +
      String(d.getMinutes()).padStart(2, '0');
    return date + ' ' + time;
  }

  function renderFileList() {
    const container = document.getElementById('merger-file-list');
    if (!mergerFiles.length) { container.innerHTML = ''; return; }

    const rows = mergerFiles.map((f, i) => {
      const meta = fileMeta.get(f);
      let pathCell;
      if (!meta) {
        pathCell = '<span class="file-path file-path-loading">Reading…</span>';
      } else if (meta.sourcePath) {
        pathCell = `<span class="file-path" title="${escapeHtml(meta.sourcePath)}">${escapeHtml(meta.sourcePath)}</span>`;
      } else {
        pathCell = '<span class="file-path file-path-empty" title="No &lt;suite source=&quot;...&quot;&gt; attribute found in this file">—</span>';
      }
      return `
      <tr>
        <td class="col-num">${i + 1}</td>
        <td class="col-name" title="${escapeHtml(f.name)}">
          <span class="file-name">
            <i class="fa-solid fa-file-code me-1" style="color:var(--accent-blue);opacity:.7"></i>${escapeHtml(f.name)}
          </span>
        </td>
        <td class="col-path">${pathCell}</td>
        <td class="col-size">${formatBytes(f.size)}</td>
        <td class="col-date">${formatFileDate(f.lastModified)}</td>
        <td class="col-del">
          <button class="merger-file-del-btn" data-idx="${i}" title="Remove">
            <i class="fa-solid fa-xmark"></i>
          </button>
        </td>
      </tr>`;
    }).join('');

    container.innerHTML = `
      <div class="merger-file-table-wrap">
        <table class="merger-file-table">
          <thead>
            <tr>
              <th class="col-num">#</th>
              <th class="col-name">File Name</th>
              <th class="col-path">Source Path</th>
              <th class="col-size">Size</th>
              <th class="col-date">Modified</th>
              <th class="col-del"></th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;

    container.querySelectorAll('.merger-file-del-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        mergerFiles.splice(parseInt(btn.dataset.idx), 1);
        renderFileList();
        updateSuiteNameDropdown();
      });
    });
  }

  setupDropzone(dropzone, fileInput, async files => {
    const xmlFiles = files.filter(f => f.name.endsWith('.xml'));
    if (!xmlFiles.length) { showToast('Only .xml files are accepted', 'warning'); return; }
    mergerFiles = [...mergerFiles, ...xmlFiles];
    renderFileList();                                  // immediate feedback
    updateSuiteNameDropdown();
    // Read every newly added file in parallel, then re-render so the
    // Source Path column can replace its "Reading…" placeholder.
    await Promise.all(xmlFiles.map(getFileMeta));
    renderFileList();
  }, true);

  document.getElementById('merger-btn').addEventListener('click', async () => {
    if (mergerFiles.length < 2) {
      showToast('Please select at least 2 output.xml files', 'warning');
      return;
    }
    const isUpdateMode = document.querySelector('input[name="merger-mode"]:checked')?.value === 'update';
    collectMergerSettingsFromUi();
    const btn = document.getElementById('merger-btn');
    setLoading(btn, true, isUpdateMode ? 'Updating...' : 'Merging...');

    const fd = new FormData();
    mergerFiles.forEach(f => fd.append('files', f));
    fd.append('flatten', document.getElementById('merger-flatten').checked);
    fd.append('output_name', document.getElementById('merger-output-name').value.trim());
    fd.append('update_mode', isUpdateMode);
    fd.append('keep_update_history', mergerSettings.updateHistory === 'keep');

    const suiteNameSelect = document.getElementById('merger-suite-name-select');
    let suiteName = '';
    if (suiteNameSelect.value === '__custom__') {
      suiteName = document.getElementById('merger-suite-name-custom').value.trim();
    } else if (suiteNameSelect.value !== '__auto__') {
      suiteName = suiteNameSelect.value;
    }
    if (suiteName) fd.append('suite_name', suiteName);

    try {
      const res = await fetch('/api/merge', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || 'Merge failed');

      if (data.skipped_duplicates && data.skipped_duplicates.length > 0) {
        const dupNames = data.skipped_duplicates.map(n => `"${n}"`).join(', ');
        showToast(
          `Skipped ${data.skipped_duplicates.length} duplicate file(s): ${dupNames}. ` +
          `Merged ${data.unique_file_count} unique file(s).`,
          'warning'
        );
      }

      const results = document.getElementById('merger-results');
      results.style.display = 'block';

      // Update the result card header to reflect mode
      const resultHeader = results.querySelector('.card-header');
      if (resultHeader) {
        if (data.update_mode) {
          resultHeader.innerHTML = '<i class="fa-solid fa-rotate me-2"></i>Update complete — test results replaced!';
        } else {
          resultHeader.innerHTML = '<i class="fa-solid fa-circle-check me-2"></i>Merge successful!';
        }
      }

      document.getElementById('merger-download-all').href = data.download_url;

      let filesHtml = data.files.map(f => `
        <div class="file-chip mb-1">
          <i class="fa-solid fa-file-code"></i> ${escapeHtml(f)}
        </div>`).join('');

      if (data.update_mode) {
        const historyText = data.keep_update_history
          ? 'Old result history has been kept beside the newest status.'
          : `Old result history has been removed from ${data.stripped_history_count || 0} updated test(s).`;
        filesHtml += `
          <div class="alert alert-info mt-2 mb-0 py-2 px-3" style="font-size:13px">
            <i class="fa-solid fa-rotate me-1"></i>
            <strong>Update mode:</strong> Tests from later files have replaced same-named tests in earlier files. ${historyText}
          </div>`;
      }

      if (data.skipped_duplicates && data.skipped_duplicates.length > 0) {
        filesHtml += `
          <div class="alert alert-warning mt-2 mb-0 py-2 px-3" style="font-size:13px">
            <i class="fa-solid fa-triangle-exclamation me-1"></i>
            <strong>${data.skipped_duplicates.length} duplicate file(s) skipped:</strong>
            ${data.skipped_duplicates.map(n => `<span class="file-chip ms-1"><i class="fa-solid fa-copy"></i> ${escapeHtml(n)}</span>`).join('')}
          </div>`;
      }

      document.getElementById('merger-result-files').innerHTML = filesHtml;

      const reportBtn = document.getElementById('merger-view-report-btn');
      const logBtn = document.getElementById('merger-view-log-btn');
      const frameWrap = document.getElementById('merger-report-frame-wrap');
      frameWrap.style.display = 'none';

      if (data.report_url) {
        reportBtn.style.display = '';
        reportBtn.dataset.url = data.report_url;
      }
      if (data.log_url) {
        logBtn.style.display = '';
        logBtn.dataset.url = data.log_url;
      }

      const fileCount = data.unique_file_count || mergerFiles.length;
      if (data.update_mode) {
        showToast(`Update complete! ${fileCount} file(s) processed — matching tests replaced.`, 'success');
      } else {
        showToast(`Successfully merged ${fileCount} file(s)!`, 'success');
      }
      if (mergerSettings.clearInputsAfterMerge) {
        clearMergerInputs();
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setLoading(btn, false);
    }
  });

  document.getElementById('merger-view-report-btn').addEventListener('click', function () {
    const url = this.dataset.url;
    if (!url) return;
    const wrap = document.getElementById('merger-report-frame-wrap');
    document.getElementById('merger-report-frame').src = url;
    wrap.style.display = '';
    wrap.scrollIntoView({ behavior: 'smooth' });
  });

  document.getElementById('merger-view-log-btn').addEventListener('click', function () {
    const url = this.dataset.url;
    if (!url) return;
    window.open(url, '_blank');
  });

  document.getElementById('merger-report-close').addEventListener('click', () => {
    const wrap = document.getElementById('merger-report-frame-wrap');
    wrap.style.display = 'none';
    document.getElementById('merger-report-frame').src = '';
  });
})();

/* ===================================================================
   2. FILE STATISTICS
=================================================================== */

(function () {
  let statsData = null;
  let sourceEditor = null;

  document.getElementById('stats-tab-file').addEventListener('click', () => {
    document.getElementById('stats-input-file').style.display = '';
    document.getElementById('stats-input-paste').style.display = 'none';
    document.getElementById('stats-tab-file').classList.add('active');
    document.getElementById('stats-tab-paste').classList.remove('active');
  });
  document.getElementById('stats-tab-paste').addEventListener('click', () => {
    document.getElementById('stats-input-file').style.display = 'none';
    document.getElementById('stats-input-paste').style.display = '';
    document.getElementById('stats-tab-file').classList.remove('active');
    document.getElementById('stats-tab-paste').classList.add('active');
  });

  let statsFile = null;
  const dropzone = document.getElementById('stats-dropzone');
  const fileInput = document.getElementById('stats-file-input');
  setupDropzone(dropzone, fileInput, files => {
    statsFile = files[0];
    document.getElementById('stats-selected-file').textContent = `Selected: ${statsFile.name} (${(statsFile.size / 1024).toFixed(1)} KB)`;
  });

  document.getElementById('stats-clear-btn').addEventListener('click', () => {
    statsFile = null;
    document.getElementById('stats-selected-file').textContent = '';
    document.getElementById('stats-paste-content').value = '';
    document.getElementById('stats-results').style.display = 'none';
    statsData = null;
  });

  document.getElementById('stats-analyze-btn').addEventListener('click', async () => {
    const btn = document.getElementById('stats-analyze-btn');
    const pasteMode = document.getElementById('stats-input-paste').style.display !== 'none';

    let fd;
    if (pasteMode) {
      const content = document.getElementById('stats-paste-content').value.trim();
      if (!content) { showToast('Please paste the robot file content', 'warning'); return; }
      fd = JSON.stringify({ content });
    } else {
      if (!statsFile) { showToast('Please select a .robot file', 'warning'); return; }
      fd = new FormData();
      fd.append('file', statsFile);
    }

    setLoading(btn, true, 'Analyzing...');
    try {
      const res = await fetch('/api/statistics', {
        method: 'POST',
        ...(pasteMode
          ? { headers: { 'Content-Type': 'application/json' }, body: fd }
          : { body: fd }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || 'Analysis failed');
      statsData = data;
      renderStats(data);
      showToast('Analysis complete!', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setLoading(btn, false);
    }
  });

  function renderStats(data) {
    const results = document.getElementById('stats-results');
    results.style.display = 'block';

    const s = data.summary;
    document.getElementById('stats-summary-cards').innerHTML = `
      <div class="col-6 col-md-3"><div class="summary-card"><div class="sc-value sc-blue">${s.total_test_cases}</div><div class="sc-label">Test Cases</div></div></div>
      <div class="col-6 col-md-3"><div class="summary-card"><div class="sc-value sc-green">${s.total_keywords}</div><div class="sc-label">Keywords</div></div></div>
      <div class="col-6 col-md-3"><div class="summary-card"><div class="sc-value sc-purple">${s.total_variables}</div><div class="sc-label">Variables</div></div></div>
      <div class="col-6 col-md-3"><div class="summary-card"><div class="sc-value sc-yellow">${s.total_lines}</div><div class="sc-label">Lines of Code</div></div></div>`;

    document.getElementById('badge-tc').textContent = s.total_test_cases;
    document.getElementById('badge-kw').textContent = s.total_keywords;
    document.getElementById('badge-vars').textContent = s.total_variables;

    renderTcTable(data.test_cases);
    renderKwTable(data.keywords);
    renderSettings(data.settings);
    renderVarTable(data.variables);

    const srcContainer = document.getElementById('stats-source-editor');
    srcContainer.innerHTML = '';
    if (sourceEditor) { sourceEditor.toTextArea(); sourceEditor = null; }
    const ta = document.createElement('textarea');
    srcContainer.appendChild(ta);
    ta.value = data.raw_content || '';
    sourceEditor = CodeMirror.fromTextArea(ta, {
      mode: 'robot',
      theme: document.documentElement.getAttribute('data-theme') === 'light' ? 'default' : 'dracula',
      lineNumbers: true,
      readOnly: true,
      autoRefresh: true,
      lineWrapping: false,
    });
  }

  function renderTcTable(tcs) {
    renderTable('tc-tbody', tcs, (tc, i) => `
      <tr>
        <td class="text-muted">${i + 1}</td>
        <td>
          <span class="fw-semibold" style="color:var(--accent-blue)">${escapeHtml(tc.name)}</span>
          ${tc.template ? `<span class="tag-badge ms-1"><i class="fa-solid fa-table me-1"></i>template</span>` : ''}
        </td>
        <td>${tc.tags.map(t => `<span class="tag-badge">${escapeHtml(t)}</span>`).join('')}</td>
        <td><span class="badge bg-secondary">${tc.step_count}</span></td>
        <td class="text-muted">${tc.lineno}</td>
        <td><button class="row-expand-btn" data-type="tc" data-idx="${i}" title="View details"><i class="fa-solid fa-eye"></i></button></td>
      </tr>`);
    bindExpandBtns('tc-tbody', 'tc');
  }

  function renderKwTable(kws) {
    renderTable('kw-tbody', kws, (kw, i) => `
      <tr>
        <td class="text-muted">${i + 1}</td>
        <td><span class="fw-semibold" style="color:var(--accent-teal)">${escapeHtml(kw.name)}</span></td>
        <td>${kw.arguments.map(a => `<code>${escapeHtml(a)}</code>`).join(' ')}</td>
        <td><span class="badge bg-secondary">${kw.step_count}</span></td>
        <td class="text-muted">${kw.lineno}</td>
        <td><button class="row-expand-btn" data-type="kw" data-idx="${i}" title="View details"><i class="fa-solid fa-eye"></i></button></td>
      </tr>`);
    bindExpandBtns('kw-tbody', 'kw');
  }

  function renderTable(tbodyId, items, rowFn) {
    const tbody = document.getElementById(tbodyId);
    tbody.innerHTML = items.length
      ? items.map(rowFn).join('')
      : '<tr><td colspan="6" class="text-center text-muted py-4">No data</td></tr>';
  }

  function bindExpandBtns(tbodyId, type) {
    document.getElementById(tbodyId).querySelectorAll('.row-expand-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (!statsData) return;
        const idx = parseInt(btn.dataset.idx);
        const item = type === 'tc' ? statsData.test_cases[idx] : statsData.keywords[idx];
        showDetailModal(item, type);
      });
    });
  }

  function renderVarTable(vars) {
    const tbody = document.getElementById('var-tbody');
    tbody.innerHTML = vars.length
      ? vars.map((v, i) => `
        <tr>
          <td class="text-muted">${i + 1}</td>
          <td><code class="rf-variable">${escapeHtml(v.name)}</code></td>
          <td class="font-mono text-secondary">${escapeHtml(v.value)}</td>
          <td class="text-muted">${v.lineno}</td>
        </tr>`).join('')
      : '<tr><td colspan="4" class="text-center text-muted py-4">No variables</td></tr>';
  }

  function renderSettings(s) {
    const container = document.getElementById('settings-content');
    let html = '';

    if (s.libraries.length) {
      html += settingsGroup('Libraries', s.libraries.map(lib => `
        <div class="settings-item">
          <div class="settings-item-icon si-lib"><i class="fa-solid fa-puzzle-piece"></i></div>
          <div class="settings-item-body">
            <div class="settings-item-name">${escapeHtml(lib.name)}</div>
            <div class="settings-item-meta">
              ${lib.args.length ? 'Args: ' + lib.args.map(a => `<code>${escapeHtml(a)}</code>`).join(', ') : ''}
              ${lib.alias ? ' · Alias: <code>' + escapeHtml(lib.alias) + '</code>' : ''}
              · Line ${lib.lineno}
            </div>
          </div>
        </div>`).join(''));
    }

    if (s.resources.length) {
      html += settingsGroup('Resources', s.resources.map(r => `
        <div class="settings-item">
          <div class="settings-item-icon si-res"><i class="fa-solid fa-link"></i></div>
          <div class="settings-item-body">
            <div class="settings-item-name">${escapeHtml(r.name)}</div>
            <div class="settings-item-meta">Line ${r.lineno}</div>
          </div>
        </div>`).join(''));
    }

    if (s.variables_files.length) {
      html += settingsGroup('Variables Files', s.variables_files.map(v => `
        <div class="settings-item">
          <div class="settings-item-icon si-var"><i class="fa-solid fa-file-code"></i></div>
          <div class="settings-item-body">
            <div class="settings-item-name">${escapeHtml(v.name)}</div>
            <div class="settings-item-meta">Line ${v.lineno}</div>
          </div>
        </div>`).join(''));
    }

    const suiteItems = [];
    if (s.suite_setup) suiteItems.push({ label: 'Suite Setup', val: s.suite_setup });
    if (s.suite_teardown) suiteItems.push({ label: 'Suite Teardown', val: s.suite_teardown });
    if (s.test_setup) suiteItems.push({ label: 'Test Setup', val: s.test_setup });
    if (s.test_teardown) suiteItems.push({ label: 'Test Teardown', val: s.test_teardown });
    if (suiteItems.length) {
      html += settingsGroup('Hooks', suiteItems.map(i => `
        <div class="settings-item">
          <div class="settings-item-icon si-setup"><i class="fa-solid fa-arrows-spin"></i></div>
          <div class="settings-item-body">
            <div class="settings-item-name">${i.label}</div>
            <div class="settings-item-meta"><code>${escapeHtml(i.val)}</code></div>
          </div>
        </div>`).join(''));
    }

    if (s.test_tags.length) {
      html += settingsGroup('Default Tags', `<div class="p-2">${s.test_tags.map(t => `<span class="tag-badge">${escapeHtml(t)}</span>`).join('')}</div>`);
    }

    if (!html) html = '<p class="text-muted text-center py-4">No settings found</p>';
    container.innerHTML = html;
  }

  function settingsGroup(title, inner) {
    return `<div class="settings-group"><div class="settings-group-title">${title}</div>${inner}</div>`;
  }

  function showDetailModal(item, type) {
    const modal = document.getElementById('detail-modal');
    document.getElementById('detail-modal-title').textContent = item.name;

    let html = '';

    if (item.doc) {
      html += `<div class="detail-section">
        <div class="detail-section-title">Documentation</div>
        <div class="detail-doc">${escapeHtml(item.doc)}</div>
      </div>`;
    }

    const metaItems = [];
    if (type === 'tc') {
      if (item.tags.length)
        metaItems.push({ label: 'Tags', val: item.tags.map(t => `<span class="tag-badge">${escapeHtml(t)}</span>`).join('') });
      if (item.setup)
        metaItems.push({ label: 'Setup', val: `<code>${escapeHtml(item.setup)}</code>` });
      if (item.teardown)
        metaItems.push({ label: 'Teardown', val: `<code>${escapeHtml(item.teardown)}</code>` });
      if (item.template)
        metaItems.push({ label: 'Template', val: `<code>${escapeHtml(item.template)}</code>` });
    } else {
      if (item.arguments.length)
        metaItems.push({ label: 'Arguments', val: item.arguments.map(a => `<code>${escapeHtml(a)}</code>`).join(' ') });
      if (item.return_type)
        metaItems.push({ label: 'Return', val: `<code>${escapeHtml(item.return_type)}</code>` });
      if (item.tags.length)
        metaItems.push({ label: 'Tags', val: item.tags.map(t => `<span class="tag-badge">${escapeHtml(t)}</span>`).join('') });
    }
    metaItems.push({ label: 'Line', val: item.lineno });

    if (metaItems.length) {
      html += `<div class="detail-section"><div class="detail-section-title">Metadata</div>
        ${metaItems.map(m => `<div class="d-flex gap-3 mb-1"><span class="text-muted" style="width:90px;font-size:12px">${m.label}</span><span>${m.val}</span></div>`).join('')}
      </div>`;
    }

    if (item.steps.length) {
      html += `<div class="detail-section">
        <div class="detail-section-title">Steps (${item.steps.length})</div>
        ${item.steps.map((step, i) => `
          <div class="detail-step">
            <span class="step-num">${i + 1}.</span>
            <div>
              <span class="step-name">${escapeHtml(step.name)}</span>
              ${step.args.length ? `<span class="step-args ms-2">${step.args.map(a => escapeHtml(a)).join('    ')}</span>` : ''}
              <span class="text-muted ms-2" style="font-size:11px">(line ${step.lineno})</span>
            </div>
          </div>`).join('')}
      </div>`;
    }

    document.getElementById('detail-modal-body').innerHTML = html;

    const copyText = `Name: ${item.name}\n` +
      (item.doc ? `Doc: ${item.doc}\n` : '') +
      (item.steps.length ? `Steps:\n${item.steps.map((s, i) => `  ${i + 1}. ${s.name}${s.args.length ? '    ' + s.args.join('    ') : ''}`).join('\n')}` : '');
    document.getElementById('detail-copy-btn').onclick = () => copyToClipboard(copyText, item.name);

    new bootstrap.Modal(modal).show();
  }

  function filterAndSort(items, searchVal, sortVal) {
    let filtered = items.filter(item => {
      const q = searchVal.toLowerCase();
      return !q ||
        item.name.toLowerCase().includes(q) ||
        (item.tags || []).some(t => t.toLowerCase().includes(q)) ||
        (item.arguments || []).some(a => a.toLowerCase().includes(q)) ||
        (item.doc || '').toLowerCase().includes(q);
    });
    const dir = sortVal.startsWith('-') ? -1 : 1;
    const field = sortVal.replace(/^-/, '');
    filtered.sort((a, b) => {
      let va = a[field], vb = b[field];
      if (field === 'name') { va = (va || '').toLowerCase(); vb = (vb || '').toLowerCase(); }
      if (field === 'tags') { va = (va || []).join(','); vb = (vb || []).join(','); }
      if (field === 'args') { va = (a.arguments || []).length; vb = (b.arguments || []).length; }
      if (field === 'steps') { va = a.step_count || 0; vb = b.step_count || 0; }
      if (va < vb) return -dir;
      if (va > vb) return dir;
      return 0;
    });
    return filtered;
  }

  ['tc', 'kw'].forEach(type => {
    const searchEl = document.getElementById(`${type}-search`);
    const sortEl = document.getElementById(`${type}-sort`);
    [searchEl, sortEl].forEach(el => {
      el && el.addEventListener('input', () => {
        if (!statsData) return;
        const items = type === 'tc' ? statsData.test_cases : statsData.keywords;
        const filtered = filterAndSort(items, searchEl.value, sortEl.value);
        if (type === 'tc') renderTcTable(filtered);
        else renderKwTable(filtered);
      });
    });
  });

  document.getElementById('var-search').addEventListener('input', function () {
    if (!statsData) return;
    const q = this.value.toLowerCase();
    const filtered = statsData.variables.filter(v =>
      v.name.toLowerCase().includes(q) || v.value.toLowerCase().includes(q)
    );
    renderVarTable(filtered);
  });

  document.querySelectorAll('[data-stats-tab]').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const tab = link.dataset.statsTab;
      document.querySelectorAll('[data-stats-tab]').forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      document.querySelectorAll('.stats-tab-content').forEach(c => c.style.display = 'none');
      document.getElementById(`stats-tab-${tab}`).style.display = '';
      if (tab === 'source' && sourceEditor) setTimeout(() => sourceEditor.refresh(), 50);
    });
  });

  document.getElementById('tc-copy-all').addEventListener('click', () => {
    if (!statsData) return;
    copyToClipboard(statsData.test_cases.map(tc => tc.name).join('\n'), 'Test case names');
  });
  document.getElementById('kw-copy-all').addEventListener('click', () => {
    if (!statsData) return;
    copyToClipboard(statsData.keywords.map(kw => kw.name).join('\n'), 'Keyword names');
  });
  document.getElementById('vars-copy-all').addEventListener('click', () => {
    if (!statsData) return;
    copyToClipboard(statsData.variables.map(v => `${v.name}    ${v.value}`).join('\n'), 'Variables');
  });
  document.getElementById('source-copy').addEventListener('click', () => {
    if (!statsData) return;
    copyToClipboard(statsData.raw_content, 'Source code');
  });
})();

/* ===================================================================
   3. TEST RUNNER
=================================================================== */

(function () {
  let robotFile = null;
  let configFile = null;
  let currentRunId = null;
  let evtSource = null;

  const runnerDropzone = document.getElementById('runner-dropzone');
  const runnerInput = document.getElementById('runner-file-input');
  setupDropzone(runnerDropzone, runnerInput, files => {
    robotFile = files[0];
    document.getElementById('runner-selected-file').textContent =
      `Selected: ${robotFile.name} (${(robotFile.size / 1024).toFixed(1)} KB)`;
  });

  const configDropzone = document.getElementById('runner-config-dropzone');
  const configInput = document.getElementById('runner-config-input');
  setupDropzone(configDropzone, configInput, files => {
    configFile = files[0];
    document.getElementById('runner-config-file').textContent =
      `Selected: ${configFile.name}`;
  });

  document.getElementById('runner-start-btn').addEventListener('click', async () => {
    if (!robotFile) { showToast('Please select a .robot file', 'warning'); return; }

    const terminal = document.getElementById('runner-terminal');
    terminal.innerHTML = '';
    document.getElementById('runner-terminal-card').style.display = '';
    document.getElementById('runner-results').style.display = 'none';
    document.getElementById('runner-status-badge').className = 'badge bg-warning';
    document.getElementById('runner-status-badge').textContent = 'Running...';
    document.getElementById('runner-report-frame-wrap').style.display = 'none';

    if (evtSource) { evtSource.close(); evtSource = null; }

    const btn = document.getElementById('runner-start-btn');
    setLoading(btn, true, 'Running...');

    const fd = new FormData();
    fd.append('robot_file', robotFile);
    if (configFile) fd.append('config_file', configFile);
    fd.append('include_tags', document.getElementById('runner-include-tags').value);
    fd.append('exclude_tags', document.getElementById('runner-exclude-tags').value);
    fd.append('variables', document.getElementById('runner-variables').value);

    try {
      const res = await fetch('/api/run', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || 'Failed to start run');

      currentRunId = data.run_id;
      connectStream(currentRunId);
    } catch (err) {
      showToast(err.message, 'error');
      setLoading(btn, false);
    }
  });

  function connectStream(runId) {
    const terminal = document.getElementById('runner-terminal');
    evtSource = new EventSource(`/api/run/${runId}/stream`);

    evtSource.onmessage = function (e) {
      const msg = JSON.parse(e.data);
      if (msg.type === 'output') {
        appendTerminalLine(terminal, msg.data);
      } else if (msg.type === 'done') {
        evtSource.close();
        const passed = msg.exit_code === 0;
        const badge = document.getElementById('runner-status-badge');
        badge.className = `badge ${passed ? 'bg-success' : 'bg-danger'}`;
        badge.textContent = passed ? 'PASSED' : 'FAILED';

        const header = document.getElementById('runner-result-header');
        header.className = `card-header ${passed ? 'text-success' : 'text-danger'}`;
        header.innerHTML = `<i class="fa-solid fa-${passed ? 'circle-check' : 'circle-xmark'} me-2"></i>
          ${passed ? 'All tests PASSED' : 'Some tests FAILED'} (exit code: ${msg.exit_code})`;

        document.getElementById('runner-download-btn').href = msg.download_url;
        document.getElementById('runner-results').style.display = '';
        document.getElementById('runner-view-report-btn').dataset.runId = runId;
        document.getElementById('runner-view-log-btn').dataset.runId = runId;
        setLoading(document.getElementById('runner-start-btn'), false);
        showToast(passed ? 'Tests completed — PASSED' : 'Tests completed — some FAILED', passed ? 'success' : 'warning');
      } else if (msg.type === 'error') {
        evtSource.close();
        appendTerminalLine(terminal, `\nERROR: ${msg.data}`, 't-fail');
        setLoading(document.getElementById('runner-start-btn'), false);
        showToast(`Error: ${msg.data}`, 'error');
      }
    };

    evtSource.onerror = function () {
      evtSource.close();
      appendTerminalLine(terminal, '\n[Stream connection lost]', 't-warn');
      setLoading(document.getElementById('runner-start-btn'), false);
    };
  }

  function appendTerminalLine(terminal, text, extraClass = '') {
    const span = document.createElement('span');
    const colored = colorizeOutput(text);
    span.innerHTML = colored + '\n';
    if (extraClass) span.className = extraClass;
    terminal.appendChild(span);
    terminal.scrollTop = terminal.scrollHeight;
  }

  function colorizeOutput(text) {
    const t = escapeHtml(text);
    if (/^\s*={3,}/.test(text)) return `<span class="t-sep">${t}</span>`;
    if (/\bPASS\b/.test(text)) return `<span class="t-pass">${t}</span>`;
    if (/\bFAIL\b/.test(text)) return `<span class="t-fail">${t}</span>`;
    if (/\bWARN\b/i.test(text)) return `<span class="t-warn">${t}</span>`;
    if (/^(Running|Checking)/.test(text.trim())) return `<span class="t-info">${t}</span>`;
    if (/\s+::\s+/.test(text)) return `<span class="t-suite">${t}</span>`;
    return t;
  }

  document.getElementById('terminal-copy').addEventListener('click', () => {
    copyToClipboard(document.getElementById('runner-terminal').innerText, 'Terminal output');
  });
  document.getElementById('terminal-clear').addEventListener('click', () => {
    document.getElementById('runner-terminal').innerHTML = '';
  });

  document.getElementById('runner-view-report-btn').addEventListener('click', function () {
    const runId = this.dataset.runId;
    if (!runId) return;
    const wrap = document.getElementById('runner-report-frame-wrap');
    const frame = document.getElementById('runner-report-frame');
    frame.src = `/api/run/${runId}/report`;
    wrap.style.display = '';
    wrap.scrollIntoView({ behavior: 'smooth' });
  });

  document.getElementById('runner-view-log-btn').addEventListener('click', function () {
    const runId = this.dataset.runId;
    if (!runId) return;
    window.open(`/api/run/${runId}/log`, '_blank');
  });
})();

/* ===================================================================
   4. NAME FORMATTER
=================================================================== */

(function () {
  let fmtFile = null;
  let fmtContent = '';
  let previewData = null;
  let templateVarCount = 0;

  document.getElementById('fmt-tab-file').addEventListener('click', () => {
    document.getElementById('fmt-input-file').style.display = '';
    document.getElementById('fmt-input-paste').style.display = 'none';
    document.getElementById('fmt-tab-file').classList.add('active');
    document.getElementById('fmt-tab-paste').classList.remove('active');
  });
  document.getElementById('fmt-tab-paste').addEventListener('click', () => {
    document.getElementById('fmt-input-file').style.display = 'none';
    document.getElementById('fmt-input-paste').style.display = '';
    document.getElementById('fmt-tab-file').classList.remove('active');
    document.getElementById('fmt-tab-paste').classList.add('active');
  });

  const fmtDropzone = document.getElementById('fmt-dropzone');
  const fmtInput = document.getElementById('fmt-file-input');
  setupDropzone(fmtDropzone, fmtInput, files => {
    fmtFile = files[0];
    document.getElementById('fmt-selected-file').textContent = `Selected: ${fmtFile.name}`;
  });

  document.getElementById('fmt-numbering').addEventListener('change', function () {
    document.getElementById('fmt-numbering-options').style.display = this.checked ? '' : 'none';
  });

  document.getElementById('fmt-add-var').addEventListener('click', () => {
    const container = document.getElementById('fmt-template-vars');
    const id = templateVarCount++;
    const row = document.createElement('div');
    row.className = 'd-flex gap-2 mb-1 align-items-center';
    row.id = `tvar-row-${id}`;
    row.innerHTML = `
      <input type="text" class="form-control form-control-sm font-mono" placeholder="{variable_name}" id="tvar-key-${id}" style="width:140px" />
      <span class="text-muted">=</span>
      <input type="text" class="form-control form-control-sm" placeholder="Value" id="tvar-val-${id}" style="flex:1" />
      <button class="btn btn-xs btn-outline-secondary" onclick="document.getElementById('tvar-row-${id}').remove()">
        <i class="fa-solid fa-xmark"></i>
      </button>`;
    container.appendChild(row);
  });

  function buildRules() {
    const rules = {};

    const find = document.getElementById('fmt-find').value.trim();
    const replace = document.getElementById('fmt-replace').value;
    if (find) { rules.find_pattern = find; rules.replace_pattern = replace; }
    rules.case_insensitive = document.getElementById('fmt-case-insensitive').checked;

    const prefix = document.getElementById('fmt-prefix').value;
    const suffix = document.getElementById('fmt-suffix').value;
    if (prefix) rules.prefix = prefix;
    if (suffix) rules.suffix = suffix;

    const caseConv = document.getElementById('fmt-case').value;
    if (caseConv) rules.case_conversion = caseConv;

    if (document.getElementById('fmt-spaces-to-underscore').checked) rules.spaces_to_underscores = true;

    const tmpl = document.getElementById('fmt-template').value.trim();
    if (tmpl) {
      rules.template = tmpl;
      const tvars = {};
      document.querySelectorAll('[id^="tvar-key-"]').forEach(keyEl => {
        const id = keyEl.id.replace('tvar-key-', '');
        const k = keyEl.value.replace(/[{}]/g, '').trim();
        const v = document.getElementById(`tvar-val-${id}`)?.value || '';
        if (k) tvars[k] = v;
      });
      if (Object.keys(tvars).length) rules.template_vars = tvars;
    }

    if (document.getElementById('fmt-numbering').checked) {
      rules.numbering = true;
      rules.numbering_start = parseInt(document.getElementById('fmt-num-start').value) || 1;
      rules.numbering_step = parseInt(document.getElementById('fmt-num-step').value) || 1;
    }

    return rules;
  }

  async function getContent() {
    const pasteMode = document.getElementById('fmt-input-paste').style.display !== 'none';
    if (pasteMode) {
      const c = document.getElementById('fmt-paste-content').value.trim();
      if (!c) throw new Error('Please paste the robot file content');
      return { content: c, filename: 'pasted.robot' };
    } else {
      if (!fmtFile) throw new Error('Please select a .robot file');
      return { file: fmtFile, filename: fmtFile.name };
    }
  }

  document.getElementById('fmt-preview-btn').addEventListener('click', async () => {
    const btn = document.getElementById('fmt-preview-btn');
    setLoading(btn, true, 'Previewing...');
    try {
      const { content, file, filename } = await getContent();
      const rules = buildRules();

      let res;
      if (file) {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('rules', JSON.stringify(rules));
        res = await fetch('/api/format/preview', { method: 'POST', body: fd });
      } else {
        res = await fetch('/api/format/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content, filename, rules }),
        });
      }

      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error);

      previewData = data;
      renderPreview(data);
      showToast(`Preview: ${data.total_changes} change(s) across ${data.total_tests} test case(s)`, 'info');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setLoading(btn, false);
    }
  });

  function renderPreview(data) {
    const section = document.getElementById('fmt-preview-section');
    section.style.display = '';
    document.getElementById('fmt-change-count').textContent = `${data.total_changes} change(s)`;
    document.getElementById('fmt-change-count').className = `badge ms-2 ${data.total_changes ? 'bg-warning' : 'bg-secondary'}`;

    const tbody = document.getElementById('fmt-preview-tbody');
    tbody.innerHTML = data.changes.map((c, i) => `
      <tr class="${c.unchanged ? '' : 'table-active'}">
        <td class="text-muted">${c.lineno}</td>
        <td class="font-mono fmt-${c.unchanged ? 'unchanged' : 'changed'}">${escapeHtml(c.original)}</td>
        <td class="font-mono">
          <span class="${c.unchanged ? 'text-muted' : 'text-warning fw-semibold'}">${escapeHtml(c.new)}</span>
          <button class="btn btn-xs btn-outline-secondary ms-2" onclick="copyToClipboard('${escapeHtml(c.new).replace(/'/g, "\\'")}', 'Name')">
            <i class="fa-solid fa-copy"></i>
          </button>
        </td>
        <td>
          ${c.unchanged
            ? '<span class="status-unchanged"><i class="fa-solid fa-minus"></i> Unchanged</span>'
            : '<span class="status-changed"><i class="fa-solid fa-pen"></i> Changed</span>'}
        </td>
      </tr>`).join('');
  }

  document.getElementById('fmt-copy-new-names').addEventListener('click', () => {
    if (!previewData) return;
    copyToClipboard(previewData.changes.map(c => c.new).join('\n'), 'New test case names');
  });

  document.getElementById('fmt-apply-btn').addEventListener('click', async () => {
    const btn = document.getElementById('fmt-apply-btn');
    setLoading(btn, true, 'Applying...');
    try {
      const { content, file, filename } = await getContent();
      const rules = buildRules();

      let res;
      if (file) {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('rules', JSON.stringify(rules));
        res = await fetch('/api/format/apply', { method: 'POST', body: fd });
      } else {
        res = await fetch('/api/format/apply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content, filename, rules }),
        });
      }

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || 'Apply failed');
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `formatted_${filename || 'test.robot'}`;
      a.click();
      URL.revokeObjectURL(url);
      showToast('File downloaded!', 'success');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setLoading(btn, false);
    }
  });

  document.getElementById('fmt-reset-btn').addEventListener('click', () => {
    ['fmt-find', 'fmt-replace', 'fmt-prefix', 'fmt-suffix', 'fmt-template'].forEach(id => {
      document.getElementById(id).value = '';
    });
    document.getElementById('fmt-case').value = '';
    document.getElementById('fmt-spaces-to-underscore').checked = false;
    document.getElementById('fmt-case-insensitive').checked = false;
    document.getElementById('fmt-numbering').checked = false;
    document.getElementById('fmt-numbering-options').style.display = 'none';
    document.getElementById('fmt-template-vars').innerHTML = '';
    document.getElementById('fmt-preview-section').style.display = 'none';
    showToast('Rules have been reset', 'info');
  });
})();
