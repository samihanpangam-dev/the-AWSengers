const categoryKey = document.body.dataset.category;
const category = (window.TOOL_CATALOG || []).find(item => item.key === categoryKey);
const grid = document.querySelector("#toolGrid");
const input = document.querySelector("#search");
const count = document.querySelector("#count");
const empty = document.querySelector("#empty");

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[character]));
}

function render() {
  if (!category) return;
  document.title = `${category.name} - Infinity Tool Box`;
  document.querySelector("#categoryName").textContent = category.name;
  document.querySelector("#categoryDescription").textContent = category.desc;
  grid.innerHTML = category.tools.map(tool => {
    const [name, url] = tool.split("|");
    return `<article class="card"><div class="top"><span class="icon">${category.icon}</span><span class="status">LIVE</span></div><h2>${escapeHtml(name)}</h2><p>Open ${escapeHtml(name)} and start working.</p><a class="open" href="../../${escapeHtml(url)}">Open Tool ?</a></article>`;
  }).join("");
  filter();
}

function filter() {
  const query = input.value.trim().toLowerCase(); let visible = 0;
  grid.querySelectorAll(".card").forEach(card => { const show = card.textContent.toLowerCase().includes(query); card.hidden = !show; if (show) visible++; });
  count.textContent = `${visible} ${visible === 1 ? "tool" : "tools"}`; empty.hidden = visible !== 0;
}
input.addEventListener("input", filter); document.addEventListener("keydown", event => { if (event.key === "/" && document.activeElement !== input) { event.preventDefault(); input.focus(); } }); render();
