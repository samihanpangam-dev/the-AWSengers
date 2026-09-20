const fs = require("fs");
const path = require("path");
const vm = require("vm");
const root = path.resolve(__dirname, "..");
const required = ["index.html", "js/catalogue.js", "js/script.js", "tools/awsengers-agent/index.html", "tools/awsengers-agent/script.js", "tools/awsengers-agent/style.css", "backend/main.py", "backend/config.py", "backend/media_tools.py"];
const missing = required.filter((file) => !fs.existsSync(path.join(root, file)));
if (missing.length) { console.error(`Missing required integration files:\n${missing.join("\n")}`); process.exit(1); }
const catalogueSource = fs.readFileSync(path.join(root, "js/catalogue.js"), "utf8");
if (!catalogueSource.includes("tools/awsengers-agent/index.html")) { console.error("AI Agent page is not registered in the toolbox catalog."); process.exit(1); }
const page = fs.readFileSync(path.join(root, "tools/awsengers-agent/index.html"), "utf8");
for (const marker of ["apiUrl", "agentForm", "files"]) { if (!page.includes(`id="${marker}"`)) { console.error(`AI Agent page is missing #${marker}.`); process.exit(1); } }

const files = [];
function walk(dir) { for (const entry of fs.readdirSync(dir, { withFileTypes: true })) { const full = path.join(dir, entry.name); if (entry.isDirectory() && ![".git", "node_modules"].includes(entry.name)) walk(full); else if (entry.isFile() && entry.name.endsWith(".html")) files.push(full); } }
walk(root);
const errors = [];
for (const file of files) {
  const html = fs.readFileSync(file, "utf8");
  for (const match of html.matchAll(/(?:href|src)=["']([^"'#?]+)["']/gi)) {
    const target = match[1];
    if (/^(?:[a-z]+:|\/\/|data:|mailto:|javascript:)/i.test(target)) continue;
    const resolved = path.resolve(path.dirname(file), target);
    if (!fs.existsSync(resolved)) errors.push(`${path.relative(root, file)} -> ${target}`);
  }
}
const catalog = fs.readFileSync(path.join(root, "js/catalogue.js"), "utf8").match(/tools\/[a-z0-9-]+\/index\.html/g) || [];
for (const target of new Set(catalog)) if (!fs.existsSync(path.join(root, target))) errors.push(`catalogue -> ${target}`);
if (errors.length) { console.error(`Broken static links (${errors.length}):\n${errors.join("\n")}`); process.exit(1); }
const scripts = [];
function walkScripts(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory() && ![".git", "node_modules", "vendor"].includes(entry.name)) walkScripts(full);
    else if (entry.isFile() && entry.name.endsWith(".js")) scripts.push(full);
  }
}
walkScripts(root);
for (const script of scripts) {
  try {
    new vm.Script(fs.readFileSync(script, "utf8"), { filename: script });
  } catch (error) {
    errors.push(`${path.relative(root, script)}: ${error.message}`);
  }
}
for (const htmlFile of files) {
  const html = fs.readFileSync(htmlFile, "utf8");
  if (html.includes("unpkg.com") || html.includes("jsdelivr.net") || html.includes("cdnjs.cloudflare.com")) {
    errors.push(`${path.relative(root, htmlFile)}: unpinned CDN dependency`);
  }
}
if (errors.length) { console.error(`Static validation errors (${errors.length}):\n${errors.join("\n")}`); process.exit(1); }
console.log(`Static integration, link, and JavaScript syntax checks passed (${files.length} HTML files, ${new Set(catalog).size} catalogue links, ${scripts.length} scripts).`);
