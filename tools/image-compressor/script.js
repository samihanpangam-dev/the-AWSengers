const fileInput = document.getElementById("fileInput");
const chooseBtn = document.getElementById("chooseBtn");
const dropZone = document.getElementById("dropZone");
const quality = document.getElementById("quality");
const qualityValue = document.getElementById("qualityValue");
const format = document.getElementById("format");
const compressBtn = document.getElementById("compressBtn");
const resultsSection = document.getElementById("resultsSection");
const results = document.getElementById("results");
const summary = document.getElementById("summary");
const clearBtn = document.getElementById("clearBtn");

let selectedFiles = [];
let compressedFiles = [];

chooseBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
    addFiles([...fileInput.files]);
    fileInput.value = "";
});

["dragenter", "dragover"].forEach(eventName => {
    dropZone.addEventListener(eventName, e => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });
});

["dragleave", "drop"].forEach(eventName => {
    dropZone.addEventListener(eventName, e => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
    });
});

dropZone.addEventListener("drop", e => {
    const files = [...e.dataTransfer.files].filter(file => file.type.startsWith("image/"));
    addFiles(files);
});

quality.addEventListener("input", () => {
    qualityValue.textContent = `${quality.value}%`;
});

function addFiles(files) {
    const valid = files.filter(file =>
        ["image/jpeg", "image/png", "image/webp"].includes(file.type)
    );

    valid.forEach(file => {
        if (!selectedFiles.some(existing => existing.name === file.name && existing.size === file.size)) {
            selectedFiles.push(file);
        }
    });

    compressBtn.disabled = selectedFiles.length === 0;
    if (selectedFiles.length) {
        compressBtn.textContent = `⚡ Compress ${selectedFiles.length} Image${selectedFiles.length > 1 ? "s" : ""}`;
    }
}

compressBtn.addEventListener("click", async () => {
    if (!selectedFiles.length) return;

    compressBtn.disabled = true;
    compressBtn.textContent = "⏳ Compressing...";
    results.innerHTML = "";
    compressedFiles = [];
    resultsSection.classList.remove("hidden");

    let totalOriginal = 0;
    let totalCompressed = 0;

    for (const file of selectedFiles) {
        try {
            const compressed = await compressImage(file);
            totalOriginal += file.size;
            totalCompressed += compressed.blob.size;
            compressedFiles.push(compressed);
            addResult(compressed);
        } catch (error) {
            console.error(error);
        }
    }

    const saved = totalOriginal - totalCompressed;
    const percent = totalOriginal ? Math.max(0, (saved / totalOriginal) * 100) : 0;

    summary.textContent =
        `${selectedFiles.length} image${selectedFiles.length > 1 ? "s" : ""} processed • ` +
        `${formatBytes(saved)} saved (${percent.toFixed(1)}%)`;

    compressBtn.disabled = false;
    compressBtn.textContent = `⚡ Compress ${selectedFiles.length} Image${selectedFiles.length > 1 ? "s" : ""}`;
});

async function compressImage(file) {
    const image = await loadImage(file);

    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;

    const ctx = canvas.getContext("2d", { alpha: true });

    // JPEG does not support transparency, so use a white background.
    const outputType = format.value === "original" ? file.type : format.value;

    if (outputType === "image/jpeg") {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
    }

    ctx.drawImage(image, 0, 0);

    const blob = await new Promise(resolve => {
        // PNG ignores quality in browser canvas APIs.
        const q = outputType === "image/png" ? undefined : Number(quality.value) / 100;
        canvas.toBlob(resolve, outputType, q);
    });

    if (!blob) throw new Error("Could not create compressed image.");

    URL.revokeObjectURL(image.src);

    const extension = outputType === "image/jpeg" ? "jpg" :
                      outputType === "image/webp" ? "webp" : "png";

    const originalBase = file.name.replace(/\.[^/.]+$/, "");

    return {
        blob,
        name: `${originalBase}-compressed.${extension}`,
        originalName: file.name,
        originalSize: file.size,
        preview: URL.createObjectURL(blob)
    };
}

function loadImage(file) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        const url = URL.createObjectURL(file);
        img.onload = () => resolve(Object.assign(img, { src: url }));
        img.onerror = () => {
            URL.revokeObjectURL(url);
            reject(new Error("Could not read image."));
        };
        img.src = url;
    });
}

function addResult(item) {
    const saved = item.originalSize - item.blob.size;
    const percent = item.originalSize ? Math.max(0, saved / item.originalSize * 100) : 0;

    const card = document.createElement("div");
    card.className = "result";

    card.innerHTML = `
        <img class="preview" src="${item.preview}" alt="Compressed preview">
        <div>
            <h3>${escapeHtml(item.originalName)}</h3>
            <div class="sizes">
                ${formatBytes(item.originalSize)} → ${formatBytes(item.blob.size)}
                • <span class="savings">${percent.toFixed(1)}% smaller</span>
            </div>
        </div>
        <button class="download-btn">Download</button>
    `;

    card.querySelector(".download-btn").addEventListener("click", () => {
        downloadBlob(item.blob, item.name);
    });

    results.appendChild(card);
}

clearBtn.addEventListener("click", () => {
    selectedFiles = [];
    compressedFiles.forEach(item => URL.revokeObjectURL(item.preview));
    compressedFiles = [];
    results.innerHTML = "";
    resultsSection.classList.add("hidden");
    compressBtn.disabled = true;
    compressBtn.textContent = "⚡ Compress Images";
});

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 2)} ${units[i]}`;
}

function escapeHtml(value) {
    return value.replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[char]));
}
