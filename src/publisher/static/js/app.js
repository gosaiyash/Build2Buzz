/**
 * GitHub LinkedIn AI Publisher - Complete Frontend Application Logic
 */

let currentProjectId = null;
let currentDraftId = null;
let currentDraftScreenshot = null;

document.addEventListener("DOMContentLoaded", () => {
    initNavigation();
    initCharCounter();
    initAiModeSelector();
    loadDashboardMetrics();
    loadProjectsList();
    loadAiSettings();
    loadIntegrationsStatus();
    loadHistoryList();

    // Check for query params (e.g. from OAuth callback)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has("linkedin_success")) {
        showNotification("LinkedIn account successfully connected via official OAuth!", "success");
        window.history.replaceState({}, document.title, window.location.pathname);
        loadIntegrationsStatus();
    } else if (urlParams.has("linkedin_error")) {
        showNotification("LinkedIn connection error: " + urlParams.get("linkedin_error"), "danger");
        window.history.replaceState({}, document.title, window.location.pathname);
    }
});

// Tab Navigation & Mobile Drawer
function toggleSidebar() {
    const sidebar = document.getElementById("app-sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    const toggleBtn = document.getElementById("mobile-nav-toggle");
    if (!sidebar) return;
    const isOpen = sidebar.classList.toggle("open");
    if (backdrop) backdrop.classList.toggle("active", isOpen);
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", isOpen ? "true" : "false");
    document.body.classList.toggle("sidebar-locked", isOpen);
}

function closeSidebar() {
    const sidebar = document.getElementById("app-sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    const toggleBtn = document.getElementById("mobile-nav-toggle");
    if (sidebar) sidebar.classList.remove("open");
    if (backdrop) backdrop.classList.remove("active");
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "false");
    document.body.classList.remove("sidebar-locked");
}

function initNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    const tabPanels = document.querySelectorAll(".tab-panel");
    const topbarTitle = document.getElementById("topbar-title");

    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const targetTab = item.getAttribute("data-tab");
            
            navItems.forEach(n => n.classList.remove("active"));
            tabPanels.forEach(p => p.classList.remove("active"));
            
            item.classList.add("active");
            const panel = document.getElementById(`tab-${targetTab}`);
            if (panel) panel.classList.add("active");

            const tabName = item.querySelector("span")?.textContent || "Dashboard";
            if (topbarTitle) topbarTitle.textContent = tabName;

            // Close mobile sidebar if open
            closeSidebar();

            if (targetTab === "editor" && !currentDraftId) {
                autoLoadActiveOrLatestDraft();
            }
        });
    });

    // Close sidebar on Escape key
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeSidebar();
            if (typeof closeMediaSelectorModal === "function") {
                closeMediaSelectorModal();
            }
        }
    });
}

function switchToTab(tabId) {
    const navItem = document.querySelector(`[data-tab='${tabId}']`);
    if (navItem) navItem.click();
}

// Character Counter
function initCharCounter() {
    const postBody = document.getElementById("post-body");
    const charCount = document.getElementById("char-count");
    if (postBody && charCount) {
        postBody.addEventListener("input", () => {
            const len = postBody.value.length;
            charCount.textContent = `${len} / 3000 characters`;
            if (len > 3000) {
                charCount.style.color = "var(--accent-rose)";
            } else {
                charCount.style.color = "var(--text-dim)";
            }
        });
    }
}

// AI Mode Selector (Exclusive radio toggle)
function initAiModeSelector() {
    const radioCloud = document.getElementById("ai-mode-cloud");
    const radioLocal = document.getElementById("ai-mode-local");
    const cardCloud = document.getElementById("card-mode-cloud");
    const cardLocal = document.getElementById("card-mode-local");
    const panelCloud = document.getElementById("ai-config-cloud");
    const panelLocal = document.getElementById("ai-config-local");

    function updateMode() {
        if (radioCloud && radioCloud.checked) {
            cardCloud?.classList.add("active");
            cardLocal?.classList.remove("active");
            if (panelCloud) panelCloud.style.display = "block";
            if (panelLocal) panelLocal.style.display = "none";
        } else if (radioLocal && radioLocal.checked) {
            cardLocal?.classList.add("active");
            cardCloud?.classList.remove("active");
            if (panelLocal) panelLocal.style.display = "block";
            if (panelCloud) panelCloud.style.display = "none";
        }
    }

    if (radioCloud) radioCloud.addEventListener("change", updateMode);
    if (radioLocal) radioLocal.addEventListener("change", updateMode);
    updateMode();
}

// Floating Toast Notifications (Always in viewport, no scrolling required)
function showNotification(message, type = "info", durationMs = 6000) {
    const container = document.getElementById("toast-container");
    if (!container) {
        const banner = document.getElementById("notification-banner");
        if (banner) {
            banner.className = `alert alert-${type}`;
            banner.textContent = message;
            banner.style.display = "flex";
            setTimeout(() => { banner.style.display = "none"; }, durationMs);
        }
        return;
    }

    const toast = document.createElement("div");
    toast.className = `toast-item toast-${type}`;

    const iconMap = {
        success: "✅",
        danger: "❌",
        warning: "⚠️",
        info: "ℹ️",
    };
    const icon = iconMap[type] || "ℹ️";

    toast.innerHTML = `
        <span style="font-size: 1.1rem; flex-shrink: 0;">${icon}</span>
        <div style="flex: 1; word-break: break-word; color: #f1f5f9; line-height: 1.4;">${escapeHtml(message)}</div>
        <button type="button" class="toast-close" style="background: none; border: none; color: var(--text-dim); cursor: pointer; font-size: 1rem; padding: 0 0.25rem;">✕</button>
    `;

    const closeBtn = toast.querySelector(".toast-close");
    closeBtn.addEventListener("click", () => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(50px)";
        setTimeout(() => toast.remove(), 250);
    });

    container.appendChild(toast);

    if (durationMs > 0) {
        setTimeout(() => {
            if (toast.isConnected) {
                toast.style.opacity = "0";
                toast.style.transform = "translateX(50px)";
                setTimeout(() => toast.remove(), 250);
            }
        }, durationMs);
    }
}

// AI Loading Modal / Overlay with Live Elapsed Timer
let loadingTimerInterval = null;
let loadingStartTime = null;

function showLoadingOverlay(title = "Generating LinkedIn Post Draft", message = "Synthesizing verified repository evidence with active AI engine...") {
    const overlay = document.getElementById("loading-overlay");
    const titleEl = document.getElementById("loading-title");
    const msgEl = document.getElementById("loading-message");
    const timerEl = document.getElementById("loading-timer");
    const hintEl = document.getElementById("loading-hint");

    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = message;

    const isLocal = document.getElementById("ai-mode-local")?.checked;
    if (hintEl) {
        hintEl.textContent = isLocal
            ? "Local GGUF model executing on-device via CPU (typically 15–35 seconds)."
            : "Cloud AI inference in progress via API.";
    }

    loadingStartTime = Date.now();
    if (timerEl) timerEl.textContent = "⏳ Elapsed: 0s";

    clearInterval(loadingTimerInterval);
    loadingTimerInterval = setInterval(() => {
        const elapsedSec = Math.floor((Date.now() - loadingStartTime) / 1000);
        if (timerEl) timerEl.textContent = `⏳ Elapsed: ${elapsedSec}s`;
    }, 1000);

    if (overlay) overlay.style.display = "flex";
}

function hideLoadingOverlay() {
    clearInterval(loadingTimerInterval);
    const overlay = document.getElementById("loading-overlay");
    if (overlay) overlay.style.display = "none";
}

// Dashboard Metrics
async function loadDashboardMetrics() {
    try {
        const res = await fetch("/api/health");
        if (res.ok) {
            const data = await res.json();
            const statusEl = document.getElementById("server-status-badge");
            if (statusEl) {
                statusEl.innerHTML = `<span class="status-dot"></span> Online (${data.host_binding})`;
            }
        }

        const histRes = await fetch("/api/history");
        if (histRes.ok) {
            const history = await histRes.json();
            const published = history.filter(h => h.status === "SUCCESS").length;
            const failed = history.filter(h => h.status === "FAILED").length;
            const pubEl = document.getElementById("metric-published-count");
            const failEl = document.getElementById("metric-failed-count");
            if (pubEl) pubEl.textContent = published;
            if (failEl) failEl.textContent = failed;
        }
    } catch (err) {
        console.error("Health check error:", err);
    }
}

// Projects Management
async function loadProjectsList() {
    try {
        const res = await fetch("/api/projects");
        if (res.ok) {
            const projects = await res.json();
            renderProjectsTable(projects);
            const totalEl = document.getElementById("metric-total-projects");
            if (totalEl) totalEl.textContent = projects.length || 0;
        }
    } catch (err) {
        console.warn("Failed to load projects:", err);
    }
}

function renderProjectsTable(projects) {
    const tbody = document.getElementById("projects-table-body");
    if (!tbody) return;

    if (!projects || projects.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 2rem;">No repositories analyzed yet. Enter a GitHub repository URL above to begin.</td></tr>`;
        return;
    }

    tbody.innerHTML = projects.map(p => `
        <tr>
            <td><strong>${escapeHtml(p.name || "Untitled")}</strong></td>
            <td><a href="${escapeHtml(p.repo_url)}" target="_blank" style="color: var(--accent-indigo); text-decoration: none;">${escapeHtml(p.repo_url)}</a></td>
            <td>${p.demo_url ? `<a href="${escapeHtml(p.demo_url)}" target="_blank" style="color: var(--accent-cyan);">Live Demo</a>` : '<span style="color:var(--text-dim);">-</span>'}</td>
            <td><span class="badge badge-${getBadgeClass(p.status)}">${escapeHtml(p.status || "CREATED")}</span></td>
            <td>
                <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                    <button class="btn btn-secondary btn-sm" onclick="viewProjectDetails(${p.id})">🔍 View Analysis</button>
                    <button class="btn btn-primary btn-sm" onclick="openProjectDraft(${p.id})">✍️ Post Editor</button>
                </div>
            </td>
        </tr>
    `).join("");
}

// Handle New Project Analysis Submission
async function handleAnalyzeSubmit(event) {
    event.preventDefault();
    const btn = document.getElementById("btn-start-analysis");
    const repoUrl = document.getElementById("project-repo-url").value.trim();
    const demoUrl = document.getElementById("project-demo-url").value.trim();
    const userNotes = document.getElementById("project-user-notes").value.trim();
    const postStyle = document.getElementById("project-post-style").value;
    const webResearch = document.getElementById("project-web-research").checked;

    if (!repoUrl) {
        showNotification("Please provide a valid GitHub repository URL.", "danger");
        return;
    }

    btn.disabled = true;
    btn.textContent = "⏳ Inspecting GitHub & Demo...";
    showLoadingOverlay("Analyzing Project Repository", "Fetching README.md, inspecting repository structure, and running demo safety checks...");

    try {
        const res = await fetch("/api/projects/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                repo_url: repoUrl,
                demo_url: demoUrl || null,
                user_notes: userNotes || null,
                enable_web_research: webResearch,
                post_style: postStyle,
            }),
        });

        const data = await res.json();
        if (!res.ok) {
            showNotification(data.detail || "Analysis failed.", "danger", 10000);
            return;
        }

        showNotification(`Analysis complete for repository '${data.name}'!`, "success");
        await loadProjectsList();
        await viewProjectDetails(data.project_id);
    } catch (err) {
        showNotification("Failed to analyze repository: " + err.message, "danger", 10000);
    } finally {
        hideLoadingOverlay();
        btn.disabled = false;
        btn.textContent = "🚀 Start Analysis & Evidence Extraction";
    }
}

// View Project Analysis
async function viewProjectDetails(projectId) {
    currentProjectId = projectId;
    try {
        const res = await fetch(`/api/projects/${projectId}`);
        if (!res.ok) {
            showNotification("Failed to fetch project details.", "danger");
            return;
        }
        const data = await res.json();
        window.currentProjectRepoUrl = data.repo_url || "";
        window.currentProjectDemoUrl = data.demo_url || "";
        const postGithub = document.getElementById("post-github-url");
        const postDemo = document.getElementById("post-demo-url");
        if (postGithub) {
            postGithub.value = window.currentProjectRepoUrl;
            postGithub.readOnly = true;
        }
        if (postDemo) {
            postDemo.value = window.currentProjectDemoUrl;
            postDemo.readOnly = true;
        }
        renderAnalysisReport(data);
        switchToTab("analysis");
    } catch (err) {
        showNotification("Error loading project: " + err.message, "danger");
    }
}

function renderAnalysisReport(data) {
    const titleEl = document.getElementById("analysis-view-title");
    const badgeEl = document.getElementById("analysis-status-badge");
    const emptyState = document.getElementById("analysis-empty-state");
    const content = document.getElementById("analysis-content");

    if (titleEl) titleEl.textContent = `Analysis Report: ${data.name}`;
    if (badgeEl) {
        badgeEl.textContent = data.status;
        badgeEl.className = `badge badge-${getBadgeClass(data.status)}`;
    }

    if (emptyState) emptyState.style.display = "none";
    if (content) content.style.display = "block";

    // README facts
    const readmeBox = document.getElementById("analysis-readme-summary");
    const demoBox = document.getElementById("analysis-demo-summary");
    const techBox = document.getElementById("analysis-tech-summary");
    const cautionsBox = document.getElementById("analysis-cautions-summary");

    const readmeFacts = data.evidence.filter(e => e.source_type === "readme");
    const demoFacts = data.evidence.filter(e => e.source_type === "demo");
    const techFacts = data.evidence.filter(e => e.category === "technology");

    if (readmeBox) {
        readmeBox.innerHTML = readmeFacts.length
            ? readmeFacts.map(f => `<div class="evidence-item">${escapeHtml(f.content)}</div>`).join("")
            : `<div style="color:var(--text-dim); padding: 1rem;">No documented facts extracted.</div>`;
    }

    if (demoBox) {
        demoBox.innerHTML = demoFacts.length
            ? demoFacts.map(f => `<div class="evidence-item" style="border-left-color: var(--accent-cyan);">${escapeHtml(f.content)}</div>`).join("")
            : `<div style="color:var(--text-dim); padding: 1rem;">No live demo observations available.</div>`;
    }

    if (techBox) {
        techBox.innerHTML = techFacts.length
            ? techFacts.map(t => `<div style="margin-bottom:0.4rem; font-size:0.85rem;">⚡ ${escapeHtml(t.content)}</div>`).join("")
            : `<div style="color:var(--text-dim);">No specific technologies tagged.</div>`;
    }

    if (cautionsBox) {
        cautionsBox.innerHTML = `
            <div style="font-size:0.85rem; color:var(--text-muted); line-height:1.5;">
                • Facts are strictly derived from official GitHub repository files and controlled Playwright inspection.<br>
                • No speculative benchmarks or user metrics are assumed without documented evidence.
            </div>
        `;
    }

    // Check drafts count
    const totalDraftsEl = document.getElementById("metric-total-drafts");
    if (totalDraftsEl && data.drafts) totalDraftsEl.textContent = data.drafts.length;

    // If project already has a draft, populate currentDraftId and load into editor
    if (data.drafts && data.drafts.length > 0) {
        const latestDraft = data.drafts[0];
        currentDraftId = latestDraft.id;
        latestDraft.repo_url = data.repo_url;
        latestDraft.demo_url = data.demo_url;
        populateDraftEditor(latestDraft);
    }
}

// Generate LinkedIn Draft
async function generateDraftFromCurrentProject() {
    if (!currentProjectId) {
        showNotification("Please select or analyze a project first.", "warning");
        return;
    }

    const isLocal = document.getElementById("ai-mode-local")?.checked;
    const msg = isLocal
        ? "Running local GGUF model on CPU. Synthesizing evidence into structured first-person post..."
        : "Calling Cloud AI provider. Synthesizing evidence into structured first-person post...";

    showLoadingOverlay("Generating LinkedIn Post Draft", msg);

    try {
        const res = await fetch(`/api/projects/${currentProjectId}/drafts`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });

        const data = await res.json();
        if (!res.ok) {
            showNotification(data.detail || "Draft generation failed.", "danger", 12000);
            return;
        }

        currentDraftId = data.draft_id;
        currentDraftScreenshot = data.screenshot_path;
        populateDraftEditor(data);
        showNotification("LinkedIn post draft successfully generated!", "success");
        switchToTab("editor");
    } catch (err) {
        showNotification("Failed to generate draft: " + err.message, "danger", 12000);
    } finally {
        hideLoadingOverlay();
    }
}

function populateDraftEditor(draftData) {
    const postBody = document.getElementById("post-body");
    const postGithub = document.getElementById("post-github-url");
    const postDemo = document.getElementById("post-demo-url");
    const badge = document.getElementById("draft-approval-badge");
    const btnPublish = document.getElementById("btn-publish-draft");

    if (postBody) {
        postBody.value = draftData.body;
        postBody.dispatchEvent(new Event("input"));
    }

    if (postGithub) {
        postGithub.value = draftData.repo_url || window.currentProjectRepoUrl || "";
        postGithub.readOnly = true;
    }

    if (postDemo) {
        postDemo.value = draftData.demo_url || window.currentProjectDemoUrl || "";
        postDemo.readOnly = true;
    }

    const state = draftData.state || draftData.status || "DRAFT";
    if (badge) {
        badge.textContent = `Draft: ${state}`;
        badge.className = `badge badge-${getBadgeClass(state)}`;
    }

    if (btnPublish) {
        btnPublish.disabled = (state !== "APPROVED");
    }

    // Evidence panel
    const evidenceList = document.getElementById("editor-evidence-list");
    if (evidenceList && draftData.metadata && draftData.metadata.evidence_references) {
        evidenceList.innerHTML = draftData.metadata.evidence_references.map(
            ref => `<div class="evidence-item">${escapeHtml(ref)}</div>`
        ).join("");
    }

    // Render media preview in Post Editor
    renderDraftMediaPreview(draftData.screenshot_path);
}

function renderDraftMediaPreview(screenshotPath) {
    const mediaPreview = document.getElementById("editor-media-preview");
    if (!mediaPreview) return;

    if (!screenshotPath) {
        mediaPreview.innerHTML = `
            <div class="empty-media-state">
                <div style="font-size: 1.75rem; margin-bottom: 0.35rem;">📷</div>
                <div style="font-weight: 600; color: #fff; margin-bottom: 0.25rem; font-size: 0.92rem;">No Media Attached</div>
                <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.75rem;">
                    Attach a screenshot, repo image, or demo video to preview before posting.
                </div>
                <div style="display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap;">
                    <button type="button" class="btn btn-primary btn-sm" onclick="triggerExternalMediaUpload()">
                        📁 Upload Photo / Video
                    </button>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="openMediaSelectorModal()">
                        🖼️ Choose from System / Repo
                    </button>
                </div>
            </div>
        `;
        return;
    }

    // Determine target media URL
    let mediaUrl = screenshotPath;
    if (!mediaUrl.startsWith("http://") && !mediaUrl.startsWith("https://") && !mediaUrl.startsWith("/")) {
        mediaUrl = "/" + mediaUrl;
    }

    const cleanPath = screenshotPath.split("?")[0].toLowerCase();
    const isVideo = cleanPath.endsWith(".mp4") || cleanPath.endsWith(".webm") || cleanPath.endsWith(".mov") || cleanPath.endsWith(".mkv");
    const mediaTypeLabel = isVideo ? "VIDEO" : "PHOTO";
    const fileName = screenshotPath.split("/").pop() || "media_asset";

    let mediaElement = "";
    if (isVideo) {
        mediaElement = `<video src="${escapeHtml(mediaUrl)}" controls class="media-preview-element" preload="metadata"></video>`;
    } else {
        mediaElement = `<img src="${escapeHtml(mediaUrl)}" alt="Attached media preview" class="media-preview-element" onclick="window.open('${escapeHtml(mediaUrl)}', '_blank')" title="Click to open full resolution image">`;
    }

    mediaPreview.innerHTML = `
        <div class="media-active-card">
            ${mediaElement}
            <div class="media-meta-bar">
                <div style="display:flex; align-items:center; gap:0.4rem; overflow:hidden;">
                    <span class="badge badge-${isVideo ? 'warning' : 'info'}" style="font-size:0.72rem;">${mediaTypeLabel}</span>
                    <span style="font-family:monospace; font-size:0.78rem; text-overflow:ellipsis; overflow:hidden; white-space:nowrap; max-width:180px;" title="${escapeHtml(screenshotPath)}">
                        ${escapeHtml(fileName)}
                    </span>
                </div>
                <a href="${escapeHtml(mediaUrl)}" target="_blank" style="color:var(--accent-cyan); font-size:0.78rem; text-decoration:none; flex-shrink:0;">
                    🔗 View Full
                </a>
            </div>
            <div class="media-actions-bar">
                <button type="button" class="btn btn-secondary btn-sm" style="flex:1;" onclick="openMediaSelectorModal()">
                    🔄 Change Media
                </button>
                <button type="button" class="btn btn-secondary btn-sm" style="flex:1;" onclick="triggerExternalMediaUpload()">
                    📁 Replace File
                </button>
                <button type="button" class="btn btn-danger btn-sm" onclick="removeAttachedMedia()" title="Detach media from post">
                    🗑️ Remove
                </button>
            </div>
        </div>
    `;
}

function triggerExternalMediaUpload() {
    const input = document.getElementById("media-file-input");
    if (input) input.click();
}

async function handleExternalMediaSelected(input) {
    if (!input || !input.files || input.files.length === 0) return;
    if (!currentDraftId) {
        showNotification("Please select or generate a post draft first.", "warning");
        input.value = "";
        return;
    }

    const file = input.files[0];
    const formData = new FormData();
    formData.append("file", file);

    showNotification(`Uploading media: ${file.name}...`, "info");

    try {
        const res = await fetch(`/api/drafts/${currentDraftId}/media/upload`, {
            method: "POST",
            body: formData,
        });
        const data = await res.json();
        if (res.ok) {
            currentDraftScreenshot = data.media_path;
            renderDraftMediaPreview(currentDraftScreenshot);
            const badge = document.getElementById("draft-approval-badge");
            const btnPublish = document.getElementById("btn-publish-draft");
            if (badge) {
                badge.textContent = `Draft: ${data.draft_state}`;
                badge.className = `badge badge-${getBadgeClass(data.draft_state)}`;
            }
            if (btnPublish) btnPublish.disabled = true;
            showNotification(`✅ Media uploaded and attached (${data.file_size_mb} MB).`, "success");
        } else {
            showNotification(data.detail || "Upload failed.", "danger");
        }
    } catch (err) {
        showNotification("Failed to upload media: " + err.message, "danger");
    } finally {
        input.value = "";
    }
}

async function removeAttachedMedia() {
    if (!currentDraftId) return;
    if (!confirm("Are you sure you want to remove the attached media from this LinkedIn post draft?")) {
        return;
    }

    try {
        const res = await fetch(`/api/drafts/${currentDraftId}/media`, {
            method: "DELETE",
        });
        const data = await res.json();
        if (res.ok) {
            currentDraftScreenshot = null;
            renderDraftMediaPreview(null);
            showNotification("Attached media detached from draft.", "info");
        } else {
            showNotification(data.detail || "Failed to remove media.", "danger");
        }
    } catch (err) {
        showNotification("Error detaching media: " + err.message, "danger");
    }
}

async function openMediaSelectorModal() {
    if (!currentProjectId) {
        showNotification("No active project selected.", "warning");
        return;
    }

    const modal = document.getElementById("media-selector-modal");
    const loading = document.getElementById("media-modal-loading");
    const empty = document.getElementById("media-modal-empty");
    const grid = document.getElementById("media-grid");

    if (modal) modal.style.display = "flex";
    if (loading) loading.style.display = "block";
    if (empty) empty.style.display = "none";
    if (grid) grid.innerHTML = "";

    try {
        const res = await fetch(`/api/projects/${currentProjectId}/available-media`);
        if (!res.ok) {
            if (loading) loading.style.display = "none";
            if (empty) empty.style.display = "block";
            return;
        }

        const items = await res.json();
        if (loading) loading.style.display = "none";

        if (!items || items.length === 0) {
            if (empty) empty.style.display = "block";
            return;
        }

        if (grid) {
            grid.innerHTML = items.map(item => {
                let mediaUrl = item.url;
                if (!mediaUrl.startsWith("http://") && !mediaUrl.startsWith("https://") && !mediaUrl.startsWith("/")) {
                    mediaUrl = "/" + mediaUrl;
                }
                const isVid = Boolean(item.is_video);
                const thumbHtml = isVid
                    ? `<div style="height:130px; display:flex; align-items:center; justify-content:center; background:#000; font-size:2rem;">🎬</div>`
                    : `<img src="${escapeHtml(mediaUrl)}" alt="${escapeHtml(item.title)}" class="media-gallery-thumb" onerror="this.src='/static/icons/image-placeholder.svg'">`;

                return `
                    <div class="media-gallery-card">
                        ${thumbHtml}
                        <div class="media-gallery-info">
                            <span class="badge badge-${item.source === 'Demo Screenshot' ? 'success' : (item.source === 'Uploaded Media' ? 'info' : 'neutral')}" style="font-size:0.7rem; align-self:flex-start;">
                                ${escapeHtml(item.source)}
                            </span>
                            <div class="media-gallery-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
                            <button type="button" class="btn btn-primary btn-sm" style="margin-top:0.5rem; width:100%;" onclick="selectMediaForDraft('${escapeHtml(item.url)}')">
                                ✅ Select Media
                            </button>
                        </div>
                    </div>
                `;
            }).join("");
        }
    } catch (err) {
        if (loading) loading.style.display = "none";
        showNotification("Failed to load available media: " + err.message, "danger");
    }
}

async function selectMediaForDraft(mediaPath) {
    if (!currentDraftId) {
        showNotification("No active draft to attach media to.", "warning");
        return;
    }

    try {
        const res = await fetch(`/api/drafts/${currentDraftId}/media`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ media_path: mediaPath }),
        });
        const data = await res.json();
        if (res.ok) {
            currentDraftScreenshot = data.media_path;
            renderDraftMediaPreview(currentDraftScreenshot);
            closeMediaSelectorModal();
            showNotification("Media attached to draft post!", "success");
        } else {
            showNotification(data.detail || "Failed to attach media.", "danger");
        }
    } catch (err) {
        showNotification("Error attaching media: " + err.message, "danger");
    }
}

function closeMediaSelectorModal() {
    const modal = document.getElementById("media-selector-modal");
    if (modal) modal.style.display = "none";
}

function handleModalBackdropClick(event) {
    if (event.target.id === "media-selector-modal") {
        closeMediaSelectorModal();
    }
}

async function openProjectDraft(projectId) {
    await viewProjectDetails(projectId);
    try {
        const res = await fetch(`/api/projects/${projectId}`);
        if (!res.ok) return;
        const proj = await res.json();
        if (proj.drafts && proj.drafts.length > 0) {
            await loadDraftById(proj.drafts[0].id);
        } else {
            showNotification("Generating first LinkedIn post draft for this project...", "info");
            await generateDraftFromCurrentProject();
        }
        switchToTab("editor");
    } catch (err) {
        showNotification("Error loading project draft: " + err.message, "danger");
    }
}

async function loadDraftById(draftId) {
    try {
        const res = await fetch(`/api/drafts/${draftId}`);
        if (!res.ok) {
            showNotification("Could not find draft #" + draftId, "danger");
            return;
        }
        const draft = await res.json();
        currentDraftId = draft.id;
        currentDraftScreenshot = draft.screenshot_path;
        currentProjectId = draft.project_id;
        if (draft.repo_url) window.currentProjectRepoUrl = draft.repo_url;
        if (draft.demo_url) window.currentProjectDemoUrl = draft.demo_url;
        populateDraftEditor(draft);
        switchToTab("editor");
    } catch (err) {
        showNotification("Failed to load draft: " + err.message, "danger");
    }
}

async function autoLoadActiveOrLatestDraft() {
    try {
        if (currentProjectId) {
            const res = await fetch(`/api/projects/${currentProjectId}`);
            if (res.ok) {
                const proj = await res.json();
                window.currentProjectRepoUrl = proj.repo_url || "";
                window.currentProjectDemoUrl = proj.demo_url || "";
                const postGithub = document.getElementById("post-github-url");
                if (postGithub) {
                    postGithub.value = window.currentProjectRepoUrl;
                    postGithub.readOnly = true;
                }
                if (proj.drafts && proj.drafts.length > 0) {
                    await loadDraftById(proj.drafts[0].id);
                }
            }
        } else {
            const res = await fetch("/api/projects");
            if (res.ok) {
                const projects = await res.json();
                if (projects.length > 0) {
                    const firstProj = projects[0];
                    currentProjectId = firstProj.id;
                    window.currentProjectRepoUrl = firstProj.repo_url || "";
                    window.currentProjectDemoUrl = firstProj.demo_url || "";
                    const postGithub = document.getElementById("post-github-url");
                    if (postGithub) {
                        postGithub.value = window.currentProjectRepoUrl;
                        postGithub.readOnly = true;
                    }
                    const projRes = await fetch(`/api/projects/${firstProj.id}`);
                    if (projRes.ok) {
                        const projData = await projRes.json();
                        if (projData.drafts && projData.drafts.length > 0) {
                            await loadDraftById(projData.drafts[0].id);
                        }
                    }
                }
            }
        }
    } catch (err) {
        console.warn("Auto-load draft error:", err);
    }
}

function insertRepoLinkIntoDraft() {
    const postBody = document.getElementById("post-body");
    const postGithub = document.getElementById("post-github-url");
    const repoUrl = (postGithub?.value || window.currentProjectRepoUrl || "").trim();
    if (!repoUrl) {
        showNotification("No repository link available for this project.", "warning");
        return;
    }
    if (postBody.value.includes(repoUrl)) {
        showNotification("GitHub repository link is already in the post text.", "info");
        return;
    }
    postBody.value = postBody.value.trim() + `\n\nGitHub Repository: ${repoUrl}`;
    postBody.dispatchEvent(new Event("input"));
    showNotification("GitHub repository link added to post.", "success");
}

// Save Draft Edits
async function saveDraftEdits() {
    if (!currentDraftId) {
        showNotification("No active draft to save.", "warning");
        return;
    }

    const postBody = document.getElementById("post-body").value;
    try {
        const res = await fetch(`/api/drafts/${currentDraftId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ body: postBody }),
        });
        const data = await res.json();
        if (res.ok) {
            showNotification("Draft saved. Any previous approval has been reset for safety.", "info");
            const badge = document.getElementById("draft-approval-badge");
            const btnPublish = document.getElementById("btn-publish-draft");
            if (badge) {
                badge.textContent = `Draft: ${data.state}`;
                badge.className = `badge badge-${getBadgeClass(data.state)}`;
            }
            if (btnPublish) btnPublish.disabled = true;
        }
    } catch (err) {
        showNotification("Failed to save draft: " + err.message, "danger");
    }
}

// Regenerate Draft
async function regenerateDraft() {
    if (!confirm("Regenerating will replace current draft text with a fresh version from the AI model. Proceed?")) {
        return;
    }
    await generateDraftFromCurrentProject();
}

// Validate Draft
async function validateCurrentDraft() {
    if (!currentDraftId) {
        showNotification("No active draft to validate.", "warning");
        return;
    }

    try {
        const res = await fetch(`/api/drafts/${currentDraftId}/validate`, { method: "POST" });
        const report = await res.json();

        const warnPanel = document.getElementById("editor-validation-warnings");
        if (warnPanel) {
            warnPanel.style.display = "block";
            let html = "";
            if (report.errors && report.errors.length > 0) {
                html += `<div class="alert alert-danger"><strong>Validation Errors:</strong><br>${report.errors.join("<br>")}</div>`;
            }
            if (report.warnings && report.warnings.length > 0) {
                html += `<div class="alert alert-warning"><strong>Warnings & Cautions:</strong><br>${report.warnings.join("<br>")}</div>`;
            }
            if (report.is_valid && (!report.warnings || report.warnings.length === 0)) {
                html += `<div class="alert alert-success">✅ Draft passed all length, secret, and URL validation checks!</div>`;
            }
            warnPanel.innerHTML = html;
        }

        if (report.is_valid) {
            showNotification("Draft passed safety validation.", "success");
        } else {
            showNotification("Draft has validation errors that must be resolved.", "danger");
        }
    } catch (err) {
        showNotification("Validation check error: " + err.message, "danger");
    }
}

// Approve Draft
async function approveCurrentDraft() {
    if (!currentDraftId) {
        showNotification("No active draft to approve.", "warning");
        return;
    }

    try {
        const res = await fetch(`/api/drafts/${currentDraftId}/approve`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            showNotification("Draft APPROVED. You may now publish to LinkedIn.", "success");
            const badge = document.getElementById("draft-approval-badge");
            const btnPublish = document.getElementById("btn-publish-draft");
            if (badge) {
                badge.textContent = "Draft: APPROVED";
                badge.className = "badge badge-success";
            }
            if (btnPublish) btnPublish.disabled = false;
        } else {
            showNotification(data.detail || "Approval failed.", "danger");
        }
    } catch (err) {
        showNotification("Approval error: " + err.message, "danger");
    }
}

// Publish to LinkedIn
async function publishCurrentDraft() {
    if (!currentDraftId) return;

    if (!confirm("Are you sure you want to publish this approved post to your official LinkedIn profile?")) {
        return;
    }

    const btn = document.getElementById("btn-publish-draft");
    btn.disabled = true;
    btn.textContent = "🚀 Publishing to LinkedIn...";

    try {
        const res = await fetch(`/api/drafts/${currentDraftId}/publish`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            showNotification(`🎉 Post published to LinkedIn! Identifier: ${data.linkedin_post_id}`, "success");
            const badge = document.getElementById("draft-approval-badge");
            if (badge) {
                badge.textContent = "Draft: PUBLISHED";
                badge.className = "badge badge-success";
            }
            await loadHistoryList();
            await loadDashboardMetrics();
        } else {
            showNotification(data.detail || "Publishing failed.", "danger");
            const badge = document.getElementById("draft-approval-badge");
            if (badge) {
                badge.textContent = "Draft: PUBLISH_FAILED";
                badge.className = "badge badge-danger";
            }
        }
    } catch (err) {
        showNotification("Publishing request failed: " + err.message, "danger");
    } finally {
        btn.textContent = "🚀 Publish to LinkedIn";
    }
}

// Load AI Settings and Preferences
async function loadAiSettings() {
    try {
        const res = await fetch("/api/settings");
        if (!res.ok) return;
        const data = await res.json();

        // 1. AI Mode
        const radioCloud = document.getElementById("ai-mode-cloud");
        const radioLocal = document.getElementById("ai-mode-local");
        const cardCloud = document.getElementById("card-mode-cloud");
        const cardLocal = document.getElementById("card-mode-local");
        const panelCloud = document.getElementById("ai-config-cloud");
        const panelLocal = document.getElementById("ai-config-local");
        const activeAiBadge = document.getElementById("active-ai-badge");
        const dashAiBadge = document.getElementById("dash-ai-mode");

        if (data.active_mode === "local") {
            if (radioLocal) radioLocal.checked = true;
            cardLocal?.classList.add("active");
            cardCloud?.classList.remove("active");
            if (panelLocal) panelLocal.style.display = "block";
            if (panelCloud) panelCloud.style.display = "none";
            if (activeAiBadge) activeAiBadge.textContent = "AI: Local GGUF Mode";
            if (dashAiBadge) dashAiBadge.textContent = "Local GGUF";
        } else {
            if (radioCloud) radioCloud.checked = true;
            cardCloud?.classList.add("active");
            cardLocal?.classList.remove("active");
            if (panelCloud) panelCloud.style.display = "block";
            if (panelLocal) panelLocal.style.display = "none";
            if (activeAiBadge) activeAiBadge.textContent = "AI: Cloud Mode";
            if (dashAiBadge) dashAiBadge.textContent = "Cloud API";
        }

        // 2. Cloud settings inputs
        const cloudProv = document.getElementById("cloud-provider-select");
        const cloudModel = document.getElementById("cloud-model-input");
        const cloudBaseUrl = document.getElementById("cloud-base-url-input");
        const cloudApiKey = document.getElementById("cloud-api-key-input");

        if (cloudProv && data.cloud_provider) cloudProv.value = data.cloud_provider;
        if (cloudModel && data.cloud_model) cloudModel.value = data.cloud_model;
        if (cloudBaseUrl && data.cloud_base_url) cloudBaseUrl.value = data.cloud_base_url;

        const keyStatus = document.getElementById("cloud-key-status");
        if (cloudApiKey) {
            if (data.has_cloud_api_key) {
                cloudApiKey.placeholder = "Key saved in Windows Credential Manager. Enter to replace.";
                if (keyStatus) keyStatus.textContent = `(Saved: ${data.masked_cloud_api_key})`;
            } else {
                cloudApiKey.placeholder = "Enter API key";
                if (keyStatus) keyStatus.textContent = "(Not configured)";
            }
        }

        const cloudTimeout = document.getElementById("cloud-timeout-input");
        if (cloudTimeout && data.preferences && data.preferences.cloud_timeout) {
            cloudTimeout.value = data.preferences.cloud_timeout;
        }

        // 3. Local settings inputs
        const localPath = document.getElementById("local-model-path");
        const localCtx = document.getElementById("local-context-length");
        const localGpu = document.getElementById("local-gpu-layers");

        if (localPath && data.local_model_path) localPath.value = data.local_model_path;
        if (localCtx && data.local_context_length) localCtx.value = data.local_context_length;
        if (localGpu && data.local_gpu_layers !== undefined) localGpu.value = data.local_gpu_layers;

        // 4. Preferences
        if (data.preferences) {
            const p = data.preferences;
            if (p.style) {
                const el = document.getElementById("gen-default-style");
                if (el) el.value = p.style;
            }
            if (p.language) {
                const el = document.getElementById("gen-language");
                if (el) el.value = p.language;
            }
            if (p.target_audience) {
                const el = document.getElementById("gen-target-audience");
                if (el) el.value = p.target_audience;
            }
            if (p.max_length) {
                const el = document.getElementById("gen-max-length");
                if (el) el.value = p.max_length;
            }
            if (p.custom_instructions) {
                const el = document.getElementById("gen-custom-instructions");
                if (el) el.value = p.custom_instructions;
            }
            if (p.hashtag_prefs) {
                const el = document.getElementById("gen-hashtag-prefs");
                if (el) el.value = p.hashtag_prefs;
            }
            if (p.include_links !== undefined) {
                const el = document.getElementById("gen-include-links");
                if (el) el.checked = Boolean(p.include_links);
            }
            if (p.include_screenshot !== undefined) {
                const el = document.getElementById("gen-include-screenshot");
                if (el) el.checked = Boolean(p.include_screenshot);
            }
            if (p.search_provider) {
                const el = document.getElementById("search-provider-select");
                if (el) el.value = p.search_provider;
            }
        }
    } catch (err) {
        console.warn("Failed to load AI settings:", err);
    }
}

// AI Settings Save & Test
async function saveCloudAiSettings() {
    const prov = document.getElementById("cloud-provider-select").value;
    const model = document.getElementById("cloud-model-input").value;
    const baseUrl = document.getElementById("cloud-base-url-input").value;
    const apiKey = document.getElementById("cloud-api-key-input").value;
    const timeoutVal = parseInt(document.getElementById("cloud-timeout-input")?.value || "120", 10);

    const btn = document.getElementById("btn-save-cloud");
    if (btn) btn.disabled = true;

    try {
        const res = await fetch("/api/settings/llm", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                mode: "cloud",
                cloud_provider: prov,
                cloud_model: model,
                cloud_base_url: baseUrl || null,
                cloud_api_key: apiKey.trim() || null,
                cloud_timeout: timeoutVal,
            }),
        });
        const data = await res.json();
        if (res.ok) {
            showNotification("Cloud AI settings saved successfully in Windows Credential Manager.", "success");
            const badge = document.getElementById("active-ai-badge");
            const dashBadge = document.getElementById("dash-ai-mode");
            if (badge) badge.textContent = "AI: Cloud Mode";
            if (dashBadge) dashBadge.textContent = "Cloud API";
            document.getElementById("cloud-api-key-input").value = "";
            await loadAiSettings();
        } else {
            showNotification(data.detail || "Failed to save settings.", "danger");
        }
    } catch (err) {
        showNotification("Error saving cloud settings: " + err.message, "danger");
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function testCloudAiConnection() {
    const btn = document.getElementById("btn-test-cloud");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "⏳ Testing Connection...";
    }
    showNotification("Testing cloud AI connectivity...", "info");
    try {
        const res = await fetch("/api/settings/llm/test", { method: "POST" });
        const data = await res.json();
        if (data.status === "success") {
            showNotification("✅ " + data.message, "success", 8000);
        } else {
            showNotification("❌ " + data.message, "danger", 12000);
        }
    } catch (err) {
        showNotification("Test request failed: " + err.message, "danger", 10000);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "Test Connection";
        }
    }
}

async function clearCloudApiKey() {
    if (!confirm("Are you sure you want to remove the stored Cloud AI API key from Windows Credential Manager?")) return;
    try {
        const res = await fetch("/api/settings/llm/key", { method: "DELETE" });
        const data = await res.json();
        showNotification(data.message || "API key cleared.", "info");
        document.getElementById("cloud-api-key-input").value = "";
        await loadAiSettings();
    } catch (err) {
        showNotification("Failed to delete key: " + err.message, "danger");
    }
}

function togglePasswordVisibility(elementId) {
    const input = document.getElementById(elementId);
    if (!input) return;
    input.type = input.type === "password" ? "text" : "password";
}

function handleCloudProviderChange() {
    const prov = document.getElementById("cloud-provider-select")?.value;
    const modelInput = document.getElementById("cloud-model-input");
    const baseUrlInput = document.getElementById("cloud-base-url-input");
    const presetDiv = document.getElementById("custom-provider-presets");

    if (prov === "openrouter") {
        if (modelInput && (!modelInput.value || modelInput.value === "gpt-4o-mini")) modelInput.value = "openai/gpt-4o-mini";
        if (baseUrlInput) baseUrlInput.value = "https://openrouter.ai/api/v1";
        if (presetDiv) presetDiv.style.display = "flex";
    } else if (prov === "openai") {
        if (modelInput) modelInput.value = "gpt-4o-mini";
        if (baseUrlInput) baseUrlInput.value = "https://api.openai.com/v1";
        if (presetDiv) presetDiv.style.display = "none";
    } else if (prov === "gemini") {
        if (modelInput) modelInput.value = "gemini-1.5-flash";
        if (baseUrlInput) baseUrlInput.value = "https://generativelanguage.googleapis.com/v1beta/openai";
        if (presetDiv) presetDiv.style.display = "none";
    } else if (prov === "anthropic") {
        if (modelInput) modelInput.value = "claude-3-5-sonnet-20241022";
        if (baseUrlInput) baseUrlInput.value = "https://api.anthropic.com/v1";
        if (presetDiv) presetDiv.style.display = "none";
    } else if (prov === "custom_openai") {
        if (presetDiv) presetDiv.style.display = "flex";
    }
}

function applyCloudPreset(name) {
    const prov = document.getElementById("cloud-provider-select");
    const modelInput = document.getElementById("cloud-model-input");
    const baseUrlInput = document.getElementById("cloud-base-url-input");

    if (name === "openrouter") {
        if (prov) prov.value = "openrouter";
        if (baseUrlInput) baseUrlInput.value = "https://openrouter.ai/api/v1";
        if (modelInput) modelInput.value = "openai/gpt-4o-mini";
        showNotification("Applied OpenRouter preset (https://openrouter.ai/api/v1)", "info");
    } else {
        if (prov) prov.value = "custom_openai";
        if (name === "nvidia") {
            if (baseUrlInput) baseUrlInput.value = "https://integrate.api.nvidia.com/v1";
            if (modelInput) modelInput.value = "meta/llama-3.1-8b-instruct";
            showNotification("Applied Nvidia NIM preset (https://integrate.api.nvidia.com/v1)", "info");
        } else if (name === "groq") {
            if (baseUrlInput) baseUrlInput.value = "https://api.groq.com/openai/v1";
            if (modelInput) modelInput.value = "llama-3.1-8b-instant";
            showNotification("Applied Groq preset", "info");
        } else if (name === "together") {
            if (baseUrlInput) baseUrlInput.value = "https://api.together.xyz/v1";
            if (modelInput) modelInput.value = "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo";
            showNotification("Applied Together AI preset", "info");
        } else if (name === "ollama") {
            if (baseUrlInput) baseUrlInput.value = "http://127.0.0.1:11434/v1";
            if (modelInput) modelInput.value = "llama3.1";
            showNotification("Applied Local Ollama preset (http://127.0.0.1:11434/v1)", "info");
        }
    }
}

async function saveLocalAiSettings() {
    const modelPath = document.getElementById("local-model-path").value.trim();
    const ctx = parseInt(document.getElementById("local-context-length").value, 10);
    const gpu = parseInt(document.getElementById("local-gpu-layers").value, 10);

    try {
        const res = await fetch("/api/settings/llm", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                mode: "local",
                local_model_path: modelPath,
                local_context_length: ctx,
                local_gpu_layers: gpu,
            }),
        });
        const data = await res.json();
        if (res.ok) {
            showNotification("Local GGUF model settings saved.", "success");
            const badge = document.getElementById("active-ai-badge");
            const dashBadge = document.getElementById("dash-ai-mode");
            if (badge) badge.textContent = "AI: Local GGUF Mode";
            if (dashBadge) dashBadge.textContent = "Local GGUF";
        } else {
            showNotification(data.detail || "Validation error for local model.", "danger");
        }
    } catch (err) {
        showNotification("Error saving local settings: " + err.message, "danger");
    }
}

async function testLocalModelLoad() {
    showNotification("Validating GGUF model file and estimating resources...", "info");
    try {
        const res = await fetch("/api/settings/llm/test", { method: "POST" });
        const data = await res.json();
        if (data.status === "success") {
            showNotification("✅ " + data.message, "success");
        } else {
            showNotification("❌ " + data.message, "danger");
        }
    } catch (err) {
        showNotification("Model validation failed: " + err.message, "danger");
    }
}

// Preferences
async function saveGenPreferences(event) {
    event.preventDefault();
    const style = document.getElementById("gen-default-style").value;
    const lang = document.getElementById("gen-language").value;
    const audience = document.getElementById("gen-target-audience").value;
    const maxLen = parseInt(document.getElementById("gen-max-length").value, 10);
    const instructions = document.getElementById("gen-custom-instructions").value;
    const hashtags = document.getElementById("gen-hashtag-prefs").value;
    const includeLinks = document.getElementById("gen-include-links").checked;
    const includeScreenshot = document.getElementById("gen-include-screenshot").checked;

    try {
        const res = await fetch("/api/settings/preferences", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                preferences: {
                    style,
                    language: lang,
                    target_audience: audience,
                    max_length: maxLen,
                    custom_instructions: instructions,
                    hashtag_prefs: hashtags,
                    include_links: includeLinks,
                    include_screenshot: includeScreenshot,
                },
            }),
        });
        if (res.ok) {
            showNotification("Preferences saved successfully.", "success");
        }
    } catch (err) {
        showNotification("Failed to save preferences: " + err.message, "danger");
    }
}

// Integrations
async function loadIntegrationsStatus() {
    // 1. Check LinkedIn Status
    try {
        const liRes = await fetch("/api/integrations/linkedin/status");
        if (liRes.ok) {
            const liData = await liRes.json();
            const dashLiBadge = document.getElementById("dash-linkedin-status");
            const liStatusBadge = document.getElementById("linkedin-status-badge");
            const liClientIdInput = document.getElementById("linkedin-client-id");
            const liAuthorUrnInput = document.getElementById("linkedin-author-urn");

            if (liData.connected) {
                const name = liData.member_name || "Connected Profile";
                if (dashLiBadge) {
                    dashLiBadge.textContent = "Connected";
                    dashLiBadge.className = "badge badge-success";
                }
                if (liStatusBadge) {
                    liStatusBadge.textContent = `Connected (${name})`;
                    liStatusBadge.className = "badge badge-success";
                }
            } else {
                if (dashLiBadge) {
                    dashLiBadge.textContent = "Not Connected";
                    dashLiBadge.className = "badge badge-neutral";
                }
                if (liStatusBadge) {
                    liStatusBadge.textContent = "Not Connected";
                    liStatusBadge.className = "badge badge-neutral";
                }
            }

            if (liData.client_id && liClientIdInput && !liClientIdInput.value) {
                liClientIdInput.value = liData.client_id;
            }
            if (liData.author_urn && liData.author_urn !== "urn:li:person:connected" && liAuthorUrnInput && !liAuthorUrnInput.value) {
                liAuthorUrnInput.value = liData.author_urn;
            }
        }
    } catch (err) {
        console.warn("Failed to load LinkedIn status:", err);
    }

    // 2. Check GitHub Status
    try {
        const ghRes = await fetch("/api/integrations/github/status");
        if (ghRes.ok) {
            const ghData = await ghRes.json();
            const dashGhBadge = document.getElementById("dash-github-status");
            const ghBadge = document.getElementById("github-auth-badge");
            const ghInput = document.getElementById("github-pat-token");

            if (ghData.has_token) {
                if (dashGhBadge) {
                    dashGhBadge.textContent = "Authenticated (PAT)";
                    dashGhBadge.className = "badge badge-success";
                }
                if (ghBadge) {
                    ghBadge.textContent = `PAT Active (${ghData.masked_token})`;
                    ghBadge.className = "badge badge-success";
                }
                if (ghInput) {
                    ghInput.placeholder = `Token saved securely (${ghData.masked_token})`;
                }
            } else {
                if (dashGhBadge) {
                    dashGhBadge.textContent = "Public (Unauth)";
                    dashGhBadge.className = "badge badge-neutral";
                }
                if (ghBadge) {
                    ghBadge.textContent = "Public Access";
                    ghBadge.className = "badge badge-neutral";
                }
                if (ghInput) {
                    ghInput.placeholder = "ghp_xxxxxxxxxxxx (stored in Windows Credential Manager)";
                }
            }
        }
    } catch (err) {
        console.warn("Failed to load GitHub status:", err);
    }
}

async function saveGitHubCredentials() {
    const token = document.getElementById("github-pat-token").value.trim();
    if (!token) {
        showNotification("Please enter a GitHub Personal Access Token to save.", "warning");
        return;
    }
    try {
        const res = await fetch("/api/integrations/github/token", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token }),
        });
        const data = await res.json();
        showNotification(data.message, "success");
        document.getElementById("github-pat-token").value = "";
        await loadIntegrationsStatus();
    } catch (err) {
        showNotification("Failed to save GitHub token: " + err.message, "danger");
    }
}

async function testGitHubConnection() {
    showNotification("Testing GitHub connection...", "info");
    try {
        const res = await fetch("/api/integrations/github/test", { method: "POST" });
        const data = await res.json();
        if (data.status === "success") {
            showNotification(data.message, "success");
            await loadIntegrationsStatus();
        } else {
            showNotification(data.message, "danger");
        }
    } catch (err) {
        showNotification("GitHub test failed: " + err.message, "danger");
    }
}

async function removeGitHubCredentials() {
    try {
        await fetch("/api/integrations/github/token", { method: "DELETE" });
        document.getElementById("github-pat-token").value = "";
        showNotification("GitHub token removed from Windows Credential Manager.", "info");
        await loadIntegrationsStatus();
    } catch (err) {
        showNotification("Failed to remove token: " + err.message, "danger");
    }
}

function copyRedirectUri() {
    const uriInput = document.getElementById("linkedin-redirect-uri");
    if (uriInput) {
        uriInput.select();
        navigator.clipboard.writeText(uriInput.value);
        showNotification("📋 Copied to clipboard! Paste this into your LinkedIn Developer App -> Auth tab -> Authorized redirect URLs.", "success");
    }
}

function setRedirectUriMode(host) {
    const uriInput = document.getElementById("linkedin-redirect-uri");
    if (uriInput) {
        uriInput.value = `http://${host}:8000/api/integrations/linkedin/callback`;
        showNotification("Redirect URI set to: " + uriInput.value, "info");
    }
}

function toggleLinkedInFlowFields() {
    const flowType = document.getElementById("linkedin-flow-type")?.value;
    const hint = document.getElementById("flow-hint");
    const secretLabel = document.getElementById("secret-optional-label");
    if (flowType === "native_pkce") {
        if (hint) hint.innerHTML = "PKCE requests only <code>w_member_social</code>, avoiding the <em>'Open ID permission is not supported for PKCE flows'</em> error.";
        if (secretLabel) secretLabel.textContent = "(Optional for PKCE)";
    } else {
        if (hint) hint.innerHTML = "Standard Web flow requests <code>openid profile w_member_social</code> to retrieve your name and profile automatically.";
        if (secretLabel) secretLabel.textContent = "(Required for Standard OAuth)";
    }
}

async function startLinkedInOAuth() {
    const clientId = document.getElementById("linkedin-client-id").value.trim();
    const clientSecret = document.getElementById("linkedin-client-secret").value.trim();
    const redirectUri = document.getElementById("linkedin-redirect-uri")?.value.trim();
    const flowType = document.getElementById("linkedin-flow-type")?.value || "native_pkce";
    const authorUrn = document.getElementById("linkedin-author-urn")?.value.trim();

    if (!clientId) {
        showNotification("LinkedIn Client ID is required.", "danger");
        return;
    }

    if (flowType === "standard" && !clientSecret) {
        showNotification("LinkedIn Client Secret is required for Standard Web OAuth.", "warning");
        return;
    }

    try {
        const res = await fetch("/api/integrations/linkedin/connect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                client_id: clientId,
                client_secret: clientSecret || null,
                redirect_uri: redirectUri || null,
                flow_type: flowType,
                author_urn: authorUrn || null,
            }),
        });
        const data = await res.json();
        if (res.ok && data.authorization_url) {
            window.location.href = data.authorization_url;
        } else {
            showNotification(data.detail || "Failed to initiate LinkedIn OAuth.", "danger");
        }
    } catch (err) {
        showNotification("LinkedIn OAuth error: " + err.message, "danger");
    }
}

async function saveLinkedInAuthorUrn() {
    const authorUrn = document.getElementById("linkedin-author-urn")?.value.trim();
    try {
        const res = await fetch("/api/integrations/linkedin/author-urn", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ author_urn: authorUrn || "" }),
        });
        const data = await res.json();
        if (res.ok) {
            showNotification(data.message, "success");
            await loadIntegrationsStatus();
        } else {
            showNotification(data.detail || "Failed to save Author URN.", "danger");
        }
    } catch (err) {
        showNotification("Failed to save Author URN: " + err.message, "danger");
    }
}

async function testLinkedInConnection() {
    showNotification("Testing LinkedIn connection...", "info");
    try {
        const res = await fetch("/api/integrations/linkedin/status");
        const data = await res.json();
        if (data.connected) {
            showNotification(`Connected to LinkedIn as: ${data.member_name}`, "success");
            await loadIntegrationsStatus();
        } else {
            showNotification("LinkedIn is not connected." + (data.error ? ` (${data.error})` : ""), "warning");
            await loadIntegrationsStatus();
        }
    } catch (err) {
        showNotification("Error checking LinkedIn status: " + err.message, "danger");
    }
}

async function disconnectLinkedIn() {
    try {
        await fetch("/api/integrations/linkedin/disconnect", { method: "POST" });
        showNotification("LinkedIn credentials removed.", "info");
        await loadIntegrationsStatus();
    } catch (err) {
        showNotification("Failed to disconnect: " + err.message, "danger");
    }
}

async function saveSearchSettings() {
    const prov = document.getElementById("search-provider-select").value;
    const apiKey = document.getElementById("search-api-key").value.trim();

    try {
        await fetch("/api/integrations/search/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ provider: prov, api_key: apiKey || null }),
        });
        showNotification("Web search settings saved.", "success");
    } catch (err) {
        showNotification("Error saving search settings: " + err.message, "danger");
    }
}

// History
async function loadHistoryList() {
    try {
        const res = await fetch("/api/history");
        if (res.ok) {
            const data = await res.json();
            renderHistoryTable(data);
        }
    } catch (err) {
        console.warn("History endpoint error:", err);
    }
}

function renderHistoryTable(items) {
    const tbody = document.getElementById("history-table-body");
    if (!tbody) return;

    if (!items || items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim); padding: 2rem;">No publishing history recorded yet.</td></tr>`;
        return;
    }

    tbody.innerHTML = items.map(h => `
        <tr>
            <td>#${h.draft_id}</td>
            <td><strong>${escapeHtml(h.project_name || "Project")}</strong></td>
            <td><span class="badge badge-info">${escapeHtml(h.ai_mode || "cloud")}</span></td>
            <td><span class="badge badge-${getBadgeClass(h.status)}">${escapeHtml(h.status)}</span></td>
            <td>${new Date(h.created_at).toLocaleString()}</td>
            <td>${h.linkedin_post_id ? `<span style="color:var(--accent-emerald); font-family:monospace;">${escapeHtml(h.linkedin_post_id)}</span>` : (h.error_category ? `<span style="color:var(--accent-rose);">${escapeHtml(h.error_category)}</span>` : '<span style="color:var(--text-dim);">-</span>')}</td>
            <td><button class="btn btn-secondary btn-sm" onclick="loadDraftById(${h.draft_id})">✍️ View Draft</button></td>
        </tr>
    `).join("");
}

function getBadgeClass(status) {
    if (!status) return "neutral";
    const s = status.toUpperCase();
    if (s.includes("PUBLISHED") || s.includes("APPROVED") || s.includes("ANALYZED") || s.includes("SUCCESS")) return "success";
    if (s.includes("FAIL") || s.includes("REJECTED")) return "danger";
    if (s.includes("REVIEW") || s.includes("WAIT") || s.includes("VALIDATED") || s.includes("PENDING")) return "warning";
    return "info";
}

function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
