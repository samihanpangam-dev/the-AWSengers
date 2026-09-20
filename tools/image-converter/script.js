const fileInput = document.getElementById("fileInput");
const dropZone = document.getElementById("dropZone");
const workspace = document.getElementById("workspace");
const fileList = document.getElementById("fileList");
const fileCount = document.getElementById("fileCount");
const totalSize = document.getElementById("totalSize");
const formatSelect = document.getElementById("format");
const quality = document.getElementById("quality");
const qualityValue = document.getElementById("qualityValue");
const qualityGroup = document.getElementById("qualityGroup");
const convertBtn = document.getElementById("convertBtn");
const clearBtn = document.getElementById("clearBtn");
const resultArea = document.getElementById("resultArea");
const resultList = document.getElementById("resultList");
const resultSummary = document.getElementById("resultSummary");
const downloadAllBtn = document.getElementById("downloadAllBtn");

let files = [];
let results = [];

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, index)).toFixed(index ? 2 : 0)} ${units[index]}`;
}

function extensionFor(type) {
  return {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp"
  }[type];
}

function addFiles(selected) {
  const valid = [...selected].filter(file =>
    ["image/jpeg", "image/png", "image/webp"].includes(file.type)
  );

  files = [...files, ...valid];
  renderFiles();
}

function renderFiles() {
  if (!files.length) {
    workspace.classList.add("hidden");
    return;
  }

  workspace.classList.remove("hidden");

  fileList.innerHTML = files.map((file, index) => `
    <div class="file-item">
      <div class="file-icon">🖼️</div>
      <div class="file-info">
        <div class="file-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</div>
        <div class="file-meta">${formatBytes(file.size)} · ${file.type.split("/")[1].toUpperCase()}</div>
      </div>
      <button class="remove-btn" data-index="${index}" type="button">Remove</button>
    </div>
  `).join("");

  fileCount.textContent = `${files.length} ${files.length === 1 ? "image" : "images"}`;
  totalSize.textContent = formatBytes(files.reduce((sum, file) => sum + file.size, 0));

  fileList.querySelectorAll(".remove-btn").forEach(button => {
    button.addEventListener("click", () => {
      files.splice(Number(button.dataset.index), 1);
      results = [];
      resultArea.classList.add("hidden");
      renderFiles();
    });
  });
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, char => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[char]));
}

function updateQualityVisibility() {
  const isPng = formatSelect.value === "image/png";
  qualityGroup.style.opacity = isPng ? ".45" : "1";
  quality.disabled = isPng;
}

function convertFile(file, outputType, qualityValue) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);

    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;

      const ctx = canvas.getContext("2d");

      if (outputType === "image/jpeg") {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      }

      ctx.drawImage(image, 0, 0);

      canvas.toBlob(blob => {
        URL.revokeObjectURL(url);

        if (!blob) {
          reject(new Error("This image could not be converted."));
          return;
        }

        resolve(blob);
      }, outputType, outputType === "image/png" ? undefined : qualityValue / 100);
    };

    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Could not read this image."));
    };

    image.src = url;
  });
}

function safeBaseName(filename) {
  return filename.replace(/\.[^/.]+$/, "");
}

async function convertImages() {
  if (!files.length) return;

  convertBtn.disabled = true;
  convertBtn.textContent = "Converting...";

  results = [];
  const outputType = formatSelect.value;
  const extension = extensionFor(outputType);
  const qualityNumber = Number(quality.value);

  try {
    for (const file of files) {
      const blob = await convertFile(file, outputType, qualityNumber);

      results.push({
        originalName: file.name,
        name: `${safeBaseName(file.name)}-converted.${extension}`,
        originalSize: file.size,
        size: blob.size,
        blob,
        url: URL.createObjectURL(blob),
        type: outputType
      });
    }

    renderResults();
  } catch (error) {
    alert(error.message || "Something went wrong while converting the images.");
  } finally {
    convertBtn.disabled = false;
    convertBtn.textContent = "⚡ Convert Images";
  }
}

function renderResults() {
  resultArea.classList.remove("hidden");

  const totalOriginal = results.reduce((sum, item) => sum + item.originalSize, 0);
  const totalConverted = results.reduce((sum, item) => sum + item.size, 0);
  const difference = totalOriginal
    ? ((1 - totalConverted / totalOriginal) * 100).toFixed(1)
    : "0.0";

  resultSummary.textContent =
    `${results.length} ${results.length === 1 ? "image" : "images"} converted · ` +
    `${formatBytes(totalOriginal)} → ${formatBytes(totalConverted)} · ` +
    `${difference >= 0 ? difference + "% smaller" : Math.abs(difference) + "% larger"}`;

  resultList.innerHTML = results.map((item, index) => `
    <div class="result-item">
      <div class="file-icon">✅</div>
      <div class="result-info">
        <div class="result-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
        <div class="result-meta">${formatBytes(item.originalSize)} → ${formatBytes(item.size)}</div>
      </div>
      <button class="download-btn" data-index="${index}" type="button">Download</button>
    </div>
  `).join("");

  resultList.querySelectorAll(".download-btn").forEach(button => {
    button.addEventListener("click", () => {
      downloadResult(results[Number(button.dataset.index)]);
    });
  });
}

function downloadResult(result) {
  const link = document.createElement("a");
  link.href = result.url;
  link.download = result.name;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

downloadAllBtn.addEventListener("click", () => {
  results.forEach((result, index) => {
    setTimeout(() => downloadResult(result), index * 150);
  });
});

fileInput.addEventListener("change", event => {
  addFiles(event.target.files);
  event.target.value = "";
});

["dragenter", "dragover"].forEach(eventName => {
  dropZone.addEventListener(eventName, event => {
    event.preventDefault();
    dropZone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach(eventName => {
  dropZone.addEventListener(eventName, event => {
    event.preventDefault();
    dropZone.classList.remove("dragover");
  });
});

dropZone.addEventListener("drop", event => {
  addFiles(event.dataTransfer.files);
});

formatSelect.addEventListener("change", updateQualityVisibility);

quality.addEventListener("input", () => {
  qualityValue.textContent = `${quality.value}%`;
});

convertBtn.addEventListener("click", convertImages);

clearBtn.addEventListener("click", () => {
  results.forEach(result => URL.revokeObjectURL(result.url));
  results = [];
  files = [];
  resultList.innerHTML = "";
  resultArea.classList.add("hidden");
  fileInput.value = "";
  renderFiles();
});

updateQualityVisibility();
