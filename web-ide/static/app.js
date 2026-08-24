const state = {
  target: 'arduino',
  files: [],
  devices: [],
  activeFile: null,
  savedContent: '',
  activeJob: null,
  jobs: [],
  pollTimer: null,
  searchMatches: [],
  searchMarkers: [],
  activeMatch: -1,
  matchCase: false,
  wholeWord: false,
  selectedLines: [],
};

const targets = {
  arduino: { name: 'SparkFun RedBoard', mcu: 'ATmega328P · 5 V · 16 MHz · Uno-compatible', extension: '.ino', portHint: 'VID_0403', program: 'Upload' },
  olimex: { name: 'Olimex AVR-MT128', mcu: 'ATmega128-16AI · 5 V · 16 MHz', extension: '.c', portHint: 'VID_15BA', program: 'Flash' },
};

const editor = CodeMirror(document.getElementById('editor'), {
  value: '// Select a source file from the project pane.\n',
  mode: 'text/x-c++src',
  theme: 'default',
  lineNumbers: true,
  indentUnit: 2,
  tabSize: 2,
  lineWrapping: false,
  matchBrackets: true,
  styleActiveLine: true,
});

lucide.createIcons();

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.description || payload.message || `Request failed (${response.status})`);
  return payload;
}

function toast(message) {
  const element = document.getElementById('toast');
  element.textContent = message;
  element.classList.add('visible');
  clearTimeout(element.timer);
  element.timer = setTimeout(() => element.classList.remove('visible'), 2600);
}

function currentPort() {
  return document.getElementById('portSelect').value;
}

function fileMatchesTarget(path) {
  const extension = targets[state.target].extension;
  return path.toLowerCase().endsWith(extension);
}

async function loadFiles(selectPreferred = false) {
  const result = await api('/api/files');
  state.files = result.files;
  const list = document.getElementById('fileList');
  list.innerHTML = '';
  const groups = new Map();
  state.files.forEach((path) => {
    const parts = path.split('/');
    const group = parts.length > 1 ? parts.slice(0, -1).join('/') : 'Project';
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(path);
  });
  groups.forEach((paths, group) => {
    const section = document.createElement('section');
    section.className = 'file-group';
    const heading = document.createElement('div');
    heading.className = 'file-group-heading';
    heading.innerHTML = `<i data-lucide="folder"></i><span>${group}</span>`;
    section.appendChild(heading);
    paths.forEach((path) => {
      const filename = path.split('/').pop();
      const button = document.createElement('button');
      button.className = `file-button${path === state.activeFile ? ' active' : ''}`;
      button.title = path;
      button.dataset.path = path;
      button.innerHTML = `<i data-lucide="file-code-2"></i><span>${filename}</span>`;
      button.addEventListener('click', () => openFile(path));
      section.appendChild(button);
    });
    list.appendChild(section);
  });
  document.getElementById('fileCount').textContent = `${state.files.length} sources`;
  lucide.createIcons();
  if (selectPreferred || !state.activeFile) {
    const preferred = state.files.find(fileMatchesTarget) || state.files[0];
    if (preferred) await openFile(preferred);
  }
}

async function openFile(path) {
  if (state.activeFile && editor.getValue() !== state.savedContent && !confirm('Discard unsaved changes?')) return;
  const result = await api(`/api/file?path=${encodeURIComponent(path)}`);
  state.activeFile = result.path;
  state.savedContent = result.content;
  editor.setValue(result.content);
  editor.clearHistory();
  editor.setOption('mode', path.endsWith('.ino') || path.endsWith('.cpp') ? 'text/x-c++src' : 'text/x-csrc');
  document.getElementById('activeFile').textContent = result.path;
  document.getElementById('languageMode').textContent = path.endsWith('.c') ? 'C' : 'C++';
  document.querySelectorAll('.file-button').forEach((button) => button.classList.toggle('active', button.dataset.path === path));
  updateDirty();
  editor.focus();
  refreshSearch();
}

async function reloadSource() {
  if (!state.activeFile) return;
  if (editor.getValue() !== state.savedContent && !confirm('Discard unsaved changes and reload from disk?')) return;
  await openFile(state.activeFile);
  toast(`Reloaded ${state.activeFile}`);
}

async function saveFile() {
  if (!state.activeFile) return;
  const content = editor.getValue();
  await api(`/api/file?path=${encodeURIComponent(state.activeFile)}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
  state.savedContent = content;
  updateDirty();
  toast(`Saved ${state.activeFile}`);
}

function updateDirty() {
  document.getElementById('dirtyDot').classList.toggle('visible', editor.getValue() !== state.savedContent);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function searchExpression() {
  const query = document.getElementById('findInput').value;
  if (!query) return null;
  const source = state.wholeWord ? `\\b${escapeRegExp(query)}\\b` : escapeRegExp(query);
  return new RegExp(source, state.matchCase ? 'g' : 'gi');
}

function clearSearchMarkers() {
  state.searchMarkers.forEach((marker) => marker.clear());
  state.searchMarkers = [];
}

function markSearchMatches() {
  clearSearchMarkers();
  state.searchMatches.forEach((match, index) => {
    const marker = editor.markText(match.from, match.to, {
      className: index === state.activeMatch ? 'cm-search-current' : 'cm-searching',
    });
    state.searchMarkers.push(marker);
  });
}

function refreshSearch() {
  const expression = searchExpression();
  state.searchMatches = [];
  state.activeMatch = -1;
  clearSearchMarkers();
  if (!expression) {
    document.getElementById('matchCount').textContent = 'No matches';
    return;
  }

  const text = editor.getValue();
  let match;
  while ((match = expression.exec(text)) !== null) {
    state.searchMatches.push({
      from: editor.posFromIndex(match.index),
      to: editor.posFromIndex(match.index + match[0].length),
    });
    if (match[0].length === 0) expression.lastIndex += 1;
  }
  document.getElementById('matchCount').textContent = state.searchMatches.length
    ? `0 of ${state.searchMatches.length}`
    : 'No matches';
  markSearchMatches();
}

function showSearch(replace = false) {
  document.getElementById('editorSearch').classList.add('visible');
  document.getElementById('replaceControls').classList.toggle('visible', replace);
  document.getElementById('toggleReplace').classList.toggle('active', replace);
  const input = document.getElementById('findInput');
  if (!input.value && editor.somethingSelected()) input.value = editor.getSelection();
  input.focus();
  input.select();
  refreshSearch();
}

function closeSearch() {
  document.getElementById('editorSearch').classList.remove('visible');
  clearSearchMarkers();
  editor.focus();
}

function navigateMatch(direction) {
  if (!state.searchMatches.length) return;
  state.activeMatch = (state.activeMatch + direction + state.searchMatches.length) % state.searchMatches.length;
  const match = state.searchMatches[state.activeMatch];
  markSearchMatches();
  editor.setSelection(match.from, match.to);
  editor.scrollIntoView({ from: match.from, to: match.to }, 90);
  document.getElementById('matchCount').textContent = `${state.activeMatch + 1} of ${state.searchMatches.length}`;
}

function replaceCurrent() {
  if (state.activeMatch < 0) navigateMatch(1);
  if (state.activeMatch < 0) return;
  const match = state.searchMatches[state.activeMatch];
  editor.replaceRange(document.getElementById('replaceInput').value, match.from, match.to);
  refreshSearch();
  navigateMatch(1);
}

function replaceAllMatches() {
  if (!state.searchMatches.length) return;
  const replacement = document.getElementById('replaceInput').value;
  editor.operation(() => {
    [...state.searchMatches].reverse().forEach((match) => editor.replaceRange(replacement, match.from, match.to));
  });
  const count = state.searchMatches.length;
  refreshSearch();
  toast(`Replaced ${count} matches`);
}

function updateSelectedLineIndicators() {
  state.selectedLines.forEach((line) => {
    editor.removeLineClass(line, 'gutter', 'selected-line-gutter');
    editor.removeLineClass(line, 'background', 'selected-line-background');
  });
  state.selectedLines = [];
  const selections = editor.listSelections();
  selections.forEach((selection) => {
    const start = Math.min(selection.anchor.line, selection.head.line);
    const end = Math.max(selection.anchor.line, selection.head.line);
    for (let line = start; line <= end; line += 1) {
      state.selectedLines.push(line);
      editor.addLineClass(line, 'gutter', 'selected-line-gutter');
      if (start !== end || editor.somethingSelected()) editor.addLineClass(line, 'background', 'selected-line-background');
    }
  });
}

async function loadDevices() {
  try {
    const result = await api('/api/devices');
    state.devices = result.devices;
    renderDevices();
    const connection = document.getElementById('connectionState');
    connection.classList.add('online');
    connection.lastElementChild.textContent = `${state.devices.length} devices online`;
  } catch (error) {
    document.getElementById('connectionState').lastElementChild.textContent = 'Server unavailable';
  }
}

function portFromName(name) {
  return (name.match(/\((COM\d+)\)/i) || [])[1] || '';
}

function renderDevices() {
  const list = document.getElementById('deviceList');
  list.innerHTML = '';
  state.devices.forEach((device) => {
    const port = portFromName(device.Name);
    const identity = device.DeviceID.includes('VID_15BA') ? 'Olimex ISP500-TINY' : device.DeviceID.includes('VID_0403') ? 'SparkFun RedBoard FTDI' : device.Manufacturer;
    const row = document.createElement('div');
    row.className = 'device-row';
    row.innerHTML = `<span class="device-dot"></span><div class="device-copy"><strong>${identity}</strong><span>${device.Status}</span></div><span class="device-port">${port}</span>`;
    list.appendChild(row);
  });

  const select = document.getElementById('portSelect');
  const previous = select.value;
  select.innerHTML = state.devices.map((device) => {
    const port = portFromName(device.Name);
    return `<option value="${port}">${port} · ${device.DeviceID.includes('VID_15BA') ? 'Olimex ISP' : 'USB serial'}</option>`;
  }).join('');
  const targetPort = state.devices.find((device) => device.DeviceID.includes(targets[state.target].portHint));
  select.value = targetPort ? portFromName(targetPort.Name) : previous;
}

async function setTarget(target) {
  state.target = target;
  document.querySelectorAll('[data-target]').forEach((button) => button.classList.toggle('active', button.dataset.target === target));
  document.getElementById('targetName').textContent = targets[target].name;
  document.getElementById('targetMcu').textContent = targets[target].mcu;
  document.getElementById('programLabel').textContent = targets[target].program;
  document.getElementById('powerOrder').classList.toggle('hidden', target !== 'olimex');
  document.getElementById('quickActions').innerHTML = target === 'arduino'
    ? '<button data-action="arduino.detect"><i data-lucide="radar"></i>Detect</button><button data-action="arduino.monitor"><i data-lucide="activity"></i>Monitor</button>'
    : '<button data-action="olimex.signature"><i data-lucide="fingerprint"></i>Signature</button><button data-action="olimex.backup"><i data-lucide="archive"></i>Backup</button><button data-action="olimex.decompile"><i data-lucide="binary"></i>Reconstruct</button>';
  document.querySelectorAll('#quickActions button').forEach((button) => button.addEventListener('click', () => runAction(button.dataset.action)));
  lucide.createIcons();
  renderDevices();
  const preferred = state.files.find(fileMatchesTarget);
  if (preferred && !fileMatchesTarget(state.activeFile || '')) await openFile(preferred);
}

function actionPayload(action) {
  const payload = { action, port: currentPort() };
  if (action === 'olimex.flash') {
    const stem = (state.activeFile || '').split('/').pop().replace(/\.[^.]+$/, '');
    payload.path = `build/atmega128/${stem}.hex`;
  } else if (action === 'olimex.decompile') {
    payload.path = 'build/atmega128/atmega128-flash-backup.hex';
  } else if (action.includes('compile') || action === 'arduino.upload') {
    payload.path = state.activeFile;
  }
  if (action === 'arduino.monitor') payload.baudRate = 9600;
  return payload;
}

async function confirmDestructive(action) {
  const dialog = document.getElementById('confirmDialog');
  document.getElementById('confirmTitle').textContent = action === 'olimex.flash' ? 'Flash ATmega128?' : 'Upload to Arduino?';
  document.getElementById('confirmText').textContent = action === 'olimex.flash'
    ? 'Existing ATmega128 flash will be erased and replaced. Fuses are not changed.'
    : 'The compiled sketch will replace the program currently on the Uno.';
  dialog.showModal();
  return new Promise((resolve) => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true }));
}

async function runAction(action) {
  try {
    if (state.activeFile && editor.getValue() !== state.savedContent && (action.includes('compile') || action.includes('upload') || action.includes('flash'))) await saveFile();
    const destructive = action === 'arduino.upload' || action === 'olimex.flash';
    if (destructive && !(await confirmDestructive(action))) return;
    const payload = actionPayload(action);
    if (destructive) payload.confirmed = true;
    const job = await api('/api/jobs', { method: 'POST', body: JSON.stringify(payload) });
    state.activeJob = job.id;
    document.getElementById('consoleOutput').textContent = `Starting ${action}…\n`;
    document.getElementById('stopJob').disabled = false;
    await loadJobs();
    pollActiveJob();
  } catch (error) {
    toast(error.message);
    document.getElementById('consoleOutput').textContent += `\nError: ${error.message}\n`;
  }
}

async function pollActiveJob() {
  clearTimeout(state.pollTimer);
  if (!state.activeJob) return;
  const job = await api(`/api/jobs/${state.activeJob}`);
  displayJob(job);
  if (job.status === 'queued' || job.status === 'running') {
    state.pollTimer = setTimeout(pollActiveJob, 600);
  } else {
    document.getElementById('stopJob').disabled = true;
    await loadJobs();
    await loadFiles();
    if (job.status === 'succeeded' && job.action === 'olimex.decompile' && state.activeFile?.startsWith('reconstructed/')) {
      await openFile(state.activeFile);
    }
    toast(`${job.action} ${job.status}`);
  }
}

function displayJob(job) {
  const output = document.getElementById('consoleOutput');
  output.textContent = job.output || `${job.action} ${job.status}…`;
  output.scrollTop = output.scrollHeight;
  const badge = document.getElementById('jobState');
  badge.textContent = job.status;
  badge.className = `job-state ${job.status}`;
}

async function loadJobs() {
  const result = await api('/api/jobs');
  state.jobs = result.jobs;
  const select = document.getElementById('jobHistory');
  select.innerHTML = '<option value="">Job history</option>' + state.jobs.map((job) => `<option value="${job.id}">${job.action} · ${job.status}</option>`).join('');
}

document.querySelectorAll('.view-tab').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('.view-tab').forEach((tab) => tab.classList.toggle('active', tab === button));
  document.querySelectorAll('.view').forEach((view) => view.classList.remove('active'));
  document.getElementById(`${button.dataset.view}View`).classList.add('active');
  if (button.dataset.view === 'code') setTimeout(() => editor.refresh(), 0);
}));
document.querySelectorAll('[data-target]').forEach((button) => button.addEventListener('click', () => setTarget(button.dataset.target)));
document.querySelectorAll('#quickActions button').forEach((button) => button.addEventListener('click', () => runAction(button.dataset.action)));
document.getElementById('refreshFiles').addEventListener('click', () => loadFiles());
document.getElementById('refreshDevices').addEventListener('click', loadDevices);
document.getElementById('reloadSource').addEventListener('click', reloadSource);
document.getElementById('saveButton').addEventListener('click', saveFile);
document.getElementById('compileButton').addEventListener('click', () => runAction(`${state.target}.compile`));
document.getElementById('programButton').addEventListener('click', () => runAction(state.target === 'arduino' ? 'arduino.upload' : 'olimex.flash'));
document.getElementById('clearConsole').addEventListener('click', () => { document.getElementById('consoleOutput').textContent = ''; });
document.getElementById('stopJob').addEventListener('click', async () => {
  if (state.activeJob) await api(`/api/jobs/${state.activeJob}/stop`, { method: 'POST', body: '{}' });
});
document.getElementById('jobHistory').addEventListener('change', (event) => {
  const job = state.jobs.find((item) => item.id === event.target.value);
  if (job) displayJob(job);
});
document.getElementById('copyApi').addEventListener('click', async () => {
  await navigator.clipboard.writeText(document.getElementById('apiExample').textContent);
  toast('API request copied');
});
editor.on('change', updateDirty);
editor.on('cursorActivity', () => {
  const cursor = editor.getCursor();
  document.getElementById('cursorPosition').textContent = `Ln ${cursor.line + 1}, Col ${cursor.ch + 1}`;
  updateSelectedLineIndicators();
});
document.getElementById('findInput').addEventListener('input', refreshSearch);
document.getElementById('findInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') { event.preventDefault(); navigateMatch(event.shiftKey ? -1 : 1); }
  if (event.key === 'Escape') { event.preventDefault(); closeSearch(); }
});
document.getElementById('replaceInput').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') { event.preventDefault(); replaceCurrent(); }
  if (event.key === 'Escape') { event.preventDefault(); closeSearch(); }
});
document.getElementById('findNext').addEventListener('click', () => navigateMatch(1));
document.getElementById('findPrevious').addEventListener('click', () => navigateMatch(-1));
document.getElementById('matchCase').addEventListener('click', (event) => {
  state.matchCase = !state.matchCase;
  event.currentTarget.classList.toggle('active', state.matchCase);
  refreshSearch();
});
document.getElementById('wholeWord').addEventListener('click', (event) => {
  state.wholeWord = !state.wholeWord;
  event.currentTarget.classList.toggle('active', state.wholeWord);
  refreshSearch();
});
document.getElementById('toggleReplace').addEventListener('click', () => {
  const controls = document.getElementById('replaceControls');
  controls.classList.toggle('visible');
  document.getElementById('toggleReplace').classList.toggle('active', controls.classList.contains('visible'));
});
document.getElementById('closeSearch').addEventListener('click', closeSearch);
document.getElementById('replaceOne').addEventListener('click', replaceCurrent);
document.getElementById('replaceAll').addEventListener('click', replaceAllMatches);
window.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {
    event.preventDefault();
    showSearch(false);
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'h') {
    event.preventDefault();
    showSearch(true);
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    saveFile();
  }
});

Promise.all([loadFiles(true), loadDevices(), loadJobs()]).catch((error) => toast(error.message));
setInterval(loadDevices, 8000);