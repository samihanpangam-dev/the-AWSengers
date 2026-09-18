// ==============================================================================
// AWS Cedar Policy for Omni-File AI Agent
// ==============================================================================

// 1. Explicitly FORBID dangerous system commands, code injection, and arbitrary script execution.
forbid (
    principal,
    action == Action::"ExecuteSystemCommand",
    resource
);

// 2. Explicitly PERMIT standard media operations (audio/video conversion, trimming, audio extraction, compression).
permit (
    principal,
    action == Action::"ProcessMedia",
    resource
);

// 3. Explicitly PERMIT standard PDF operations (merging, splitting to zip, text extraction, compression).
permit (
    principal,
    action == Action::"ProcessPDF",
    resource
);

