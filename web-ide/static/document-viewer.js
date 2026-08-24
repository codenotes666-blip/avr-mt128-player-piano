const root = document.documentElement;
const documentId = root.dataset.document;
const currentPage = Number(root.dataset.page);
const pageCount = Number(root.dataset.pages);
const stage = document.getElementById('pageStage');
const renderedPage = document.getElementById('renderedPage');
const image = renderedPage.querySelector('img');
let zoom = 100;

function pageUrl(page) {
  return `page-${String(Math.max(1, Math.min(pageCount, page))).padStart(3, '0')}.html`;
}

function navigate(page) {
  location.href = pageUrl(page);
}

function setZoom(value) {
  zoom = Math.max(40, Math.min(250, value));
  renderedPage.classList.add('manual-zoom');
  image.style.width = `${zoom}%`;
  document.getElementById('zoomValue').value = `${zoom}%`;
}

async function loadManifest() {
  const manifest = await fetch('/docs-html/manifest.json').then((response) => response.json());
  const metadata = manifest.documents.find((item) => item.id === documentId);
  if (!metadata) return;
  const list = document.getElementById('thumbnailList');
  metadata.pages.forEach((page) => {
    const link = document.createElement('a');
    link.className = `thumbnail${page.number === currentPage ? ' active' : ''}`;
    link.href = pageUrl(page.number);
    link.innerHTML = `<img loading="lazy" src="${page.image}" alt="Page ${page.number}"><span>Page ${page.number}</span>`;
    list.appendChild(link);
  });
  list.querySelector('.active')?.scrollIntoView({ block: 'center' });
  window.AVRDocument = {
    metadata,
    currentPage,
    annotationLayer: document.querySelector('[data-hook="annotations"]'),
    navigate,
  };
  document.dispatchEvent(new CustomEvent('avr-document-ready', { detail: window.AVRDocument }));
}

async function searchDocument() {
  const query = document.getElementById('documentSearch').value.trim().toLowerCase();
  const results = document.getElementById('searchResults');
  results.innerHTML = '';
  if (!query || !window.AVRDocument) return;
  const matches = [];
  for (const page of window.AVRDocument.metadata.pages) {
    const text = await fetch(page.text).then((response) => response.text());
    const index = text.toLowerCase().indexOf(query);
    if (index >= 0) {
      const start = Math.max(0, index - 45);
      matches.push({ number: page.number, excerpt: text.slice(start, index + query.length + 80).replace(/\s+/g, ' ') });
    }
  }
  if (!matches.length) {
    results.textContent = 'No matching pages';
    return;
  }
  matches.forEach((match) => {
    const link = document.createElement('a');
    link.className = 'search-result';
    link.href = pageUrl(match.number);
    link.innerHTML = `<strong>Page ${match.number}</strong><span>${match.excerpt}</span>`;
    results.appendChild(link);
  });
}

document.getElementById('pageNumber').addEventListener('change', (event) => navigate(Number(event.target.value)));
document.getElementById('zoomIn').addEventListener('click', () => setZoom(zoom + 20));
document.getElementById('zoomOut').addEventListener('click', () => setZoom(zoom - 20));
document.getElementById('fitPage').addEventListener('click', () => {
  zoom = 100;
  image.style.width = '';
  renderedPage.classList.remove('manual-zoom');
  document.getElementById('zoomValue').value = '100%';
  stage.scrollTo(0, 0);
});
document.getElementById('toggleText').addEventListener('click', () => {
  document.getElementById('textPanel').classList.toggle('open');
  document.querySelector('.document-shell').classList.toggle('text-open');
});
document.getElementById('copyText').addEventListener('click', () => navigator.clipboard.writeText(document.querySelector('.text-panel pre').textContent));
document.getElementById('searchButton').addEventListener('click', searchDocument);
document.getElementById('documentSearch').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') searchDocument();
});
document.addEventListener('keydown', (event) => {
  if (event.target.matches('input')) return;
  if (event.key === 'ArrowLeft') navigate(currentPage - 1);
  if (event.key === 'ArrowRight') navigate(currentPage + 1);
  if (event.key === '+' || event.key === '=') setZoom(zoom + 20);
  if (event.key === '-') setZoom(zoom - 20);
});

loadManifest();