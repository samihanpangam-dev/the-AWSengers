(function () {
    "use strict";

    const MAX_FILES = 5;
    const MAX_FILE_BYTES = 25 * 1024 * 1024;
    const ALLOWED_EXTENSIONS = new Set([
        ".pdf", ".mp3", ".mp4", ".wav", ".m4a", ".aac", ".avi",
        ".mov", ".mkv", ".flac", ".ogg", ".jpg", ".jpeg", ".png"
    ]);

    // DOM Elements
    const sidebar = document.getElementById("sidebar");
    const dropzoneCard = document.getElementById("dropzoneCard");
    const fileInput = document.getElementById("fileInput");
    const fileCountBadge = document.getElementById("fileCountBadge");
    const assetsLoadedBadge = document.getElementById("assetsLoadedBadge");
    const emptyFilesState = document.getElementById("emptyFilesState");
    const filesList = document.getElementById("filesList");

    const statusDot = document.getElementById("statusDot");
    const statusText = document.getElementById("statusText");
    const offlineBanner = document.getElementById("offlineBanner");
    const retryButton = document.getElementById("retryButton");

    const chatContainer = document.getElementById("chatContainer");
    const chatMessages = document.getElementById("chatMessages");
    const chatForm = document.getElementById("chatForm");
    const chatInput = document.getElementById("chatInput");
    const sendButton = document.getElementById("sendButton");

    // Settings
    const settingsToggle = document.getElementById("settingsToggle");
    const settingsPanel = document.getElementById("settingsPanel");
    const apiUrlInput = document.getElementById("apiUrl");
    const authHeaderInput = document.getElementById("authHeader");
    const authTokenInput = document.getElementById("authToken");

    // Trim Modal Elements
    const trimModal = document.getElementById("trimModal");
    const trimTargetName = document.getElementById("trimTargetName");
    const closeTrimModal = document.getElementById("closeTrimModal");
    const cancelTrimBtn = document.getElementById("cancelTrimBtn");
    const applyTrimBtn = document.getElementById("applyTrimBtn");
    const trimVideoPreview = document.getElementById("trimVideoPreview");
    const trimAudioPreview = document.getElementById("trimAudioPreview");
    const audioWaveformVisual = document.getElementById("audioWaveformVisual");
    const audioTrackLabel = document.getElementById("audioTrackLabel");

    const startTimeInput = document.getElementById("startTimeInput");
    const endTimeInput = document.getElementById("endTimeInput");
    const trimmedDurationDisplay = document.getElementById("trimmedDurationDisplay");
    const setStartCurrentBtn = document.getElementById("setStartCurrentBtn");
    const setEndCurrentBtn = document.getElementById("setEndCurrentBtn");
    const previewTrimSelectionBtn = document.getElementById("previewTrimSelectionBtn");
    const playbackCurrentDisplay = document.getElementById("playbackCurrentDisplay");
    const startRange = document.getElementById("startRange");
    const endRange = document.getElementById("endRange");
    const rangeTrackHighlight = document.getElementById("rangeTrackHighlight");

    // App State
    const state = {
        uploadedFiles: [],
        isOnline: false,
        activeTrimFile: null,
        activeMediaElement: null,
        mediaDuration: 0,
        trimStart: 0,
        trimEnd: 0,
        previewPlaybackTimer: null
    };

    // Configuration
    const configured = window.AWSENGERS_AGENT_CONFIG || {};
    apiUrlInput.value = localStorage.getItem("awsengersAgentApiUrl") || configured.apiUrl || "http://localhost:8000";
    authHeaderInput.value = localStorage.getItem("awsengersAgentAuthHeader") || configured.authHeader || "";
    authTokenInput.value = localStorage.getItem("awsengersAgentAuthToken") || configured.authToken || "";

    function getBaseUrl() {
        return (apiUrlInput.value.trim() || "http://localhost:8000").replace(/\/+$/, "");
    }

    function getRequestHeaders() {
        const header = authHeaderInput.value.trim();
        let token = authTokenInput.value.trim();
        if (header.toLowerCase() === "authorization" && token && !/^Bearer\s/i.test(token)) {
            token = "Bearer " + token;
        }
        return header && token ? { [header]: token } : {};
    }

    // -------------------------------------------------------------------------
    // Health & Backend Status
    // -------------------------------------------------------------------------
    function setHealth(online) {
        state.isOnline = online;
        if (online) {
            statusDot.className = "status-dot online";
            statusText.textContent = "Backend online";
            offlineBanner.hidden = true;
        } else {
            statusDot.className = "status-dot offline";
            statusText.textContent = "Backend offline";
            offlineBanner.hidden = false;
        }
    }

    async function checkHealth() {
        try {
            const response = await fetch(getBaseUrl() + "/health", {
                headers: getRequestHeaders(),
                signal: AbortSignal.timeout(4000)
            });
            setHealth(response.ok);
        } catch (_) {
            setHealth(false);
        }
    }

    retryButton.addEventListener("click", () => {
        retryButton.textContent = "Checking…";
        checkHealth().finally(() => {
            retryButton.textContent = "Retry";
        });
    });

    // -------------------------------------------------------------------------
    // Settings Drawer
    // -------------------------------------------------------------------------
    settingsToggle.addEventListener("click", () => {
        const isHidden = settingsPanel.hidden;
        settingsPanel.hidden = !isHidden;
        settingsToggle.setAttribute("aria-expanded", String(isHidden));
    });

    [apiUrlInput, authHeaderInput, authTokenInput].forEach((input) => {
        input.addEventListener("change", () => {
            localStorage.setItem("awsengersAgentApiUrl", getBaseUrl());
            localStorage.setItem("awsengersAgentAuthHeader", authHeaderInput.value.trim());
            localStorage.setItem("awsengersAgentAuthToken", authTokenInput.value.trim());
            checkHealth();
        });
    });

    // -------------------------------------------------------------------------
    // File Management
    // -------------------------------------------------------------------------
    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    }

    function getFileExtension(filename) {
        const dot = filename.lastIndexOf(".");
        return dot >= 0 ? filename.slice(dot).toLowerCase() : "";
    }

    function isMediaFile(filename) {
        const ext = getFileExtension(filename);
        return [".mp3", ".mp4", ".wav", ".m4a", ".aac", ".avi", ".mov", ".mkv", ".flac", ".ogg"].includes(ext);
    }

    function getFileIcon(filename) {
        const ext = getFileExtension(filename);
        if (ext === ".pdf") return "📄";
        if ([".mp4", ".avi", ".mov", ".mkv"].includes(ext)) return "🎬";
        if ([".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"].includes(ext)) return "🎵";
        if ([".jpg", ".jpeg", ".png", ".webp"].includes(ext)) return "🖼️";
        return "📁";
    }

    function updateAssetCountUI() {
        const count = state.uploadedFiles.length;
        fileCountBadge.textContent = count;
        assetsLoadedBadge.textContent = `${count} asset${count === 1 ? "" : "s"} loaded`;

        if (count === 0) {
            emptyFilesState.hidden = false;
            filesList.hidden = true;
        } else {
            emptyFilesState.hidden = true;
            filesList.hidden = false;
        }
    }

    function renderFileList() {
        filesList.innerHTML = "";
        state.uploadedFiles.forEach((file, index) => {
            const li = document.createElement("li");
            li.className = "file-item";

            const iconSpan = document.createElement("span");
            iconSpan.className = "file-icon";
            iconSpan.textContent = getFileIcon(file.name);

            const infoDiv = document.createElement("div");
            infoDiv.className = "file-info";

            const nameDiv = document.createElement("div");
            nameDiv.className = "file-name";
            nameDiv.textContent = file.name;
            nameDiv.title = file.name;

            const metaDiv = document.createElement("div");
            metaDiv.className = "file-meta";
            metaDiv.textContent = formatBytes(file.size);

            infoDiv.appendChild(nameDiv);
            infoDiv.appendChild(metaDiv);

            const actionsDiv = document.createElement("div");
            actionsDiv.className = "file-actions";

            // If audio or video, show Trim button!
            if (isMediaFile(file.name)) {
                const trimBtn = document.createElement("button");
                trimBtn.type = "button";
                trimBtn.className = "trim-chip-btn";
                trimBtn.innerHTML = "✂️ Trim";
                trimBtn.title = "Open Trim tool for this file";
                trimBtn.addEventListener("click", () => openTrimDialog(file));
                actionsDiv.appendChild(trimBtn);
            }

            const removeBtn = document.createElement("button");
            removeBtn.type = "button";
            removeBtn.className = "remove-file-btn";
            removeBtn.innerHTML = "×";
            removeBtn.title = "Remove file";
            removeBtn.addEventListener("click", () => {
                state.uploadedFiles.splice(index, 1);
                renderFileList();
                updateAssetCountUI();
            });
            actionsDiv.appendChild(removeBtn);

            li.appendChild(iconSpan);
            li.appendChild(infoDiv);
            li.appendChild(actionsDiv);
            filesList.appendChild(li);
        });

        updateAssetCountUI();
    }

    function handleFilesAdded(files) {
        let addedCount = 0;
        for (const file of Array.from(files)) {
            if (state.uploadedFiles.length >= MAX_FILES) {
                appendBotMessage(`Maximum limit reached: You can upload up to ${MAX_FILES} files.`);
                break;
            }
            const ext = getFileExtension(file.name);
            if (!ALLOWED_EXTENSIONS.has(ext)) {
                appendBotMessage(`Unsupported file format for "${file.name}". Supported: PDF, MP4, MP3, WAV, JPG, etc.`);
                continue;
            }
            if (file.size > MAX_FILE_BYTES) {
                appendBotMessage(`"${file.name}" exceeds the 25 MB size limit.`);
                continue;
            }
            // Avoid duplicates
            if (!state.uploadedFiles.some((f) => f.name === file.name && f.size === file.size)) {
                state.uploadedFiles.push(file);
                addedCount++;
            }
        }
        if (addedCount > 0) {
            renderFileList();
        }
    }

    // Dropzone Events
    dropzoneCard.addEventListener("click", () => fileInput.click());
    dropzoneCard.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            fileInput.click();
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files.length) {
            handleFilesAdded(e.target.files);
            fileInput.value = "";
        }
    });

    ["dragenter", "dragover"].forEach((eventName) => {
        dropzoneCard.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzoneCard.classList.add("drag-over");
        });
        sidebar.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropzoneCard.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzoneCard.classList.remove("drag-over");
        });
    });

    dropzoneCard.addEventListener("drop", (e) => {
        if (e.dataTransfer && e.dataTransfer.files) {
            handleFilesAdded(e.dataTransfer.files);
        }
    });

    sidebar.addEventListener("drop", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer && e.dataTransfer.files) {
            handleFilesAdded(e.dataTransfer.files);
        }
    });

    // -------------------------------------------------------------------------
    // Trim Media Pop-up / Modal
    // -------------------------------------------------------------------------
    function formatTime(seconds) {
        if (isNaN(seconds) || seconds < 0) seconds = 0;
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        return [
            h > 0 ? String(h).padStart(2, "0") : null,
            String(m).padStart(2, "0"),
            String(s).padStart(2, "0")
        ].filter(Boolean).join(":");
    }

    function parseTimeToSeconds(str) {
        if (!str) return 0;
        const parts = str.trim().split(":").map(Number);
        if (parts.some(isNaN)) return 0;
        if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
        if (parts.length === 2) return parts[0] * 60 + parts[1];
        if (parts.length === 1) return parts[0];
        return 0;
    }

    function updateRangeHighlight() {
        const dur = state.mediaDuration || 1;
        const leftPercent = (state.trimStart / dur) * 100;
        const widthPercent = ((state.trimEnd - state.trimStart) / dur) * 100;
        rangeTrackHighlight.style.left = `${leftPercent}%`;
        rangeTrackHighlight.style.width = `${Math.max(0, widthPercent)}%`;

        startRange.value = state.trimStart;
        endRange.value = state.trimEnd;
        startTimeInput.value = formatTime(state.trimStart);
        endTimeInput.value = formatTime(state.trimEnd);
        trimmedDurationDisplay.textContent = formatTime(state.trimEnd - state.trimStart);
    }

    function openTrimDialog(file) {
        state.activeTrimFile = file;
        trimTargetName.textContent = `${file.name} (${formatBytes(file.size)})`;

        const ext = getFileExtension(file.name);
        const isVideo = [".mp4", ".avi", ".mov", ".mkv"].includes(ext);

        const objectUrl = URL.createObjectURL(file);

        if (isVideo) {
            trimVideoPreview.src = objectUrl;
            trimVideoPreview.hidden = false;
            trimAudioPreview.hidden = true;
            audioWaveformVisual.hidden = true;
            state.activeMediaElement = trimVideoPreview;
        } else {
            trimAudioPreview.src = objectUrl;
            trimAudioPreview.hidden = false;
            trimVideoPreview.hidden = true;
            audioWaveformVisual.hidden = false;
            audioTrackLabel.textContent = file.name;
            state.activeMediaElement = trimAudioPreview;
        }

        const media = state.activeMediaElement;

        const onLoaded = () => {
            const dur = media.duration || 60;
            state.mediaDuration = dur;
            state.trimStart = 0;
            state.trimEnd = Math.min(dur, 30); // default to 30s or full duration

            startRange.max = dur;
            endRange.max = dur;

            updateRangeHighlight();
            playbackCurrentDisplay.textContent = `Current: 00:00:00 / Total: ${formatTime(dur)}`;
            media.removeEventListener("loadedmetadata", onLoaded);
        };

        media.addEventListener("loadedmetadata", onLoaded);

        media.ontimeupdate = () => {
            playbackCurrentDisplay.textContent = `Current: ${formatTime(media.currentTime)} / Total: ${formatTime(state.mediaDuration)}`;
        };

        trimModal.showModal();
    }

    function closeTrimDialog() {
        if (state.activeMediaElement) {
            state.activeMediaElement.pause();
            state.activeMediaElement.src = "";
            state.activeMediaElement = null;
        }
        if (state.previewPlaybackTimer) {
            clearInterval(state.previewPlaybackTimer);
            state.previewPlaybackTimer = null;
        }
        trimModal.close();
    }

    closeTrimModal.addEventListener("click", closeTrimDialog);
    cancelTrimBtn.addEventListener("click", closeTrimDialog);

    // Range Sliders
    startRange.addEventListener("input", (e) => {
        let val = parseFloat(e.target.value);
        if (val >= state.trimEnd) {
            val = Math.max(0, state.trimEnd - 0.5);
            startRange.value = val;
        }
        state.trimStart = val;
        updateRangeHighlight();
        if (state.activeMediaElement) {
            state.activeMediaElement.currentTime = val;
        }
    });

    endRange.addEventListener("input", (e) => {
        let val = parseFloat(e.target.value);
        if (val <= state.trimStart) {
            val = Math.min(state.mediaDuration, state.trimStart + 0.5);
            endRange.value = val;
        }
        state.trimEnd = val;
        updateRangeHighlight();
        if (state.activeMediaElement) {
            state.activeMediaElement.currentTime = val;
        }
    });

    // Time Text Inputs
    startTimeInput.addEventListener("change", (e) => {
        let s = parseTimeToSeconds(e.target.value);
        s = Math.max(0, Math.min(s, state.trimEnd - 0.5));
        state.trimStart = s;
        updateRangeHighlight();
        if (state.activeMediaElement) state.activeMediaElement.currentTime = s;
    });

    endTimeInput.addEventListener("change", (e) => {
        let s = parseTimeToSeconds(e.target.value);
        s = Math.max(state.trimStart + 0.5, Math.min(s, state.mediaDuration));
        state.trimEnd = s;
        updateRangeHighlight();
        if (state.activeMediaElement) state.activeMediaElement.currentTime = s;
    });

    // Current position buttons
    setStartCurrentBtn.addEventListener("click", () => {
        if (state.activeMediaElement) {
            const cur = Math.min(state.activeMediaElement.currentTime, state.trimEnd - 0.5);
            state.trimStart = Math.max(0, cur);
            updateRangeHighlight();
        }
    });

    setEndCurrentBtn.addEventListener("click", () => {
        if (state.activeMediaElement) {
            const cur = Math.max(state.activeMediaElement.currentTime, state.trimStart + 0.5);
            state.trimEnd = Math.min(state.mediaDuration, cur);
            updateRangeHighlight();
        }
    });

    // Preview Selection
    previewTrimSelectionBtn.addEventListener("click", () => {
        const media = state.activeMediaElement;
        if (!media) return;

        media.currentTime = state.trimStart;
        media.play();

        if (state.previewPlaybackTimer) clearInterval(state.previewPlaybackTimer);
        state.previewPlaybackTimer = setInterval(() => {
            if (media.currentTime >= state.trimEnd) {
                media.pause();
                clearInterval(state.previewPlaybackTimer);
                state.previewPlaybackTimer = null;
            }
        }, 100);
    });

    // Apply Trim: sends instruction to Agent!
    applyTrimBtn.addEventListener("click", () => {
        const file = state.activeTrimFile;
        const start = formatTime(state.trimStart);
        const end = formatTime(state.trimEnd);
        closeTrimDialog();

        if (file) {
            const instruction = `Trim "${file.name}" from ${start} to ${end}.`;
            chatInput.value = instruction;
            submitChatPrompt(instruction);
        }
    });

    // -------------------------------------------------------------------------
    // Chat System & Intent Detection
    // -------------------------------------------------------------------------
    function appendUserMessage(text) {
        const row = document.createElement("div");
        row.className = "message-row user-row";

        const bubble = document.createElement("div");
        bubble.className = "msg-bubble user-bubble";
        bubble.textContent = text;

        row.appendChild(bubble);
        chatMessages.appendChild(row);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function appendBotMessage(text, downloadUrl = null) {
        const row = document.createElement("div");
        row.className = "message-row bot-row";

        const avatar = document.createElement("div");
        avatar.className = "msg-avatar";
        avatar.setAttribute("aria-hidden", "true");
        avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="12" x="3" y="8" rx="2"/><path d="M12 2v6"/><circle cx="8" cy="14" r="1"/><circle cx="16" cy="14" r="1"/><path d="M9 17h6"/></svg>`;

        const bubble = document.createElement("div");
        bubble.className = "msg-bubble bot-bubble";

        const p = document.createElement("p");
        p.textContent = text;
        bubble.appendChild(p);

        if (downloadUrl) {
            const dl = document.createElement("a");
            dl.className = "msg-download-btn";
            dl.href = new URL(downloadUrl, getBaseUrl()).href;
            dl.download = "";
            dl.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download Result`;
            bubble.appendChild(dl);
        }

        row.appendChild(avatar);
        row.appendChild(bubble);
        chatMessages.appendChild(row);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function showTypingIndicator() {
        const row = document.createElement("div");
        row.className = "message-row bot-row typing-row";
        row.id = "typingIndicator";

        const avatar = document.createElement("div");
        avatar.className = "msg-avatar";
        avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="12" x="3" y="8" rx="2"/><path d="M12 2v6"/><circle cx="8" cy="14" r="1"/><circle cx="16" cy="14" r="1"/><path d="M9 17h6"/></svg>`;

        const bubble = document.createElement("div");
        bubble.className = "msg-bubble bot-bubble";
        bubble.innerHTML = `<div class="typing-dots"><span></span><span></span><span></span></div>`;

        row.appendChild(avatar);
        row.appendChild(bubble);
        chatMessages.appendChild(row);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function hideTypingIndicator() {
        const indicator = document.getElementById("typingIndicator");
        if (indicator) indicator.remove();
    }

    // Check if user is asking for trim
    function isTrimRequest(prompt) {
        const lower = prompt.toLowerCase();
        return /\b(trim|cut|clip|crop\s*(audio|video))\b/i.test(lower);
    }

    async function submitChatPrompt(promptText) {
        const prompt = promptText.trim();
        if (!prompt) return;

        appendUserMessage(prompt);
        chatInput.value = "";

        // Detect Trim Intent
        if (isTrimRequest(prompt)) {
            const mediaFiles = state.uploadedFiles.filter((f) => isMediaFile(f.name));
            if (mediaFiles.length === 0) {
                appendBotMessage("To trim a file, please drop or upload an audio (.mp3, .wav) or video (.mp4, .mov) asset in the sidebar first.");
                return;
            } else {
                // If media files are present, open the trim modal!
                const target = mediaFiles[mediaFiles.length - 1]; // Pick latest media file
                appendBotMessage(`Opening interactive trim tool for "${target.name}"…`);
                setTimeout(() => openTrimDialog(target), 300);
                return;
            }
        }

        // Standard Agent Processing
        sendButton.disabled = true;
        showTypingIndicator();

        const body = new FormData();
        body.append("prompt", prompt);
        state.uploadedFiles.forEach((file) => {
            body.append("files", file, file.name);
        });

        try {
            const response = await fetch(getBaseUrl() + "/process", {
                method: "POST",
                headers: getRequestHeaders(),
                body: body
            });
            const data = await response.json().catch(() => ({}));
            hideTypingIndicator();

            if (!response.ok) {
                throw new Error(data.detail || `Request failed (${response.status})`);
            }

            setHealth(true);
            appendBotMessage(
                data.response || "The agent completed the operation.",
                data.download_url
            );
        } catch (error) {
            hideTypingIndicator();
            setHealth(false);
            appendBotMessage(
                `Agent error: ${error.message || "Network error"}. Please check backend connection.`
            );
        } finally {
            sendButton.disabled = false;
        }
    }

    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        submitChatPrompt(chatInput.value);
    });

    // Initialize
    updateAssetCountUI();
    checkHealth();
})();
