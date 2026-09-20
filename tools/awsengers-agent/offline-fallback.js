/* Browser-safe fallback for text utilities when the API is unavailable. */
(() => {
    const form = document.querySelector("#agentForm");
    const prompt = document.querySelector("#prompt");
    const message = document.querySelector("#message");
    const health = document.querySelector("#healthStatus");
    if (!form || !prompt || !message) return;

    const tools = ["PDF", "CSV", "JSON", "image", "calculator", "text", "password", "URL", "date", "AI Agent"];
    const localResponse = (input) => {
        const text = input.trim();
        const lower = text.toLowerCase();
        if (lower.includes("word count") || lower.includes("count words")) {
            const count = text.replace(/.*(?:word count|count words)[: ]*/i, "").trim().split(/\\s+/).filter(Boolean).length;
            return `Browser fallback: ${count} word(s) found. For uploaded files or media, reconnect the hosted agent.`;
        }
        if (lower.includes("json") && (lower.includes("format") || lower.includes("pretty") || lower.includes("valid"))) {
            const candidate = text.slice(text.indexOf("{") >= 0 ? text.indexOf("{") : 0);
            try { return JSON.stringify(JSON.parse(candidate), null, 2); } catch (_) { return "Browser fallback: I could not find valid JSON in your prompt."; }
        }
        if (lower.includes("base64") && lower.includes("encode")) {
            const value = text.replace(/.*base64(?: encode|:)?/i, "").trim();
            return `Browser fallback result:\n${btoa(unescape(encodeURIComponent(value)))}`;
        }
        return `The hosted AI Agent is temporarily unavailable. You can still use the 209 browser tools below, including ${tools.slice(0, 5).join(", ")}, and retry this request when the agent service is online.`;
    };

    window.runOfflineAgentFallback = () => {
        if (health) { health.textContent = "Browser fallback"; health.className = "status status-unknown"; }
        message.textContent = localResponse(prompt.value);
        message.className = "message";
    };
})();
