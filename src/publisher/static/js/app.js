/**
 * GitHub LinkedIn AI Publisher - Complete Frontend Application Logic
 */

let currentProjectId = null;
let currentDraftId = null;
let currentDraftScreenshot = null;
let currentDraftMediaPaths = []; // Ordered array of media paths for upload
let modalAvailableMedia = [];    // All scanned media items {url, title, is_video, source}
let modalSelectedMedia = [];     // Array of items in chosen upload sequence order
let modalActiveFilter = "all";   // Active media filter in modal ('all', 'image', 'video', 'repo', 'demo')
let modalSearchQuery = "";
let currentPreviewSlide = 0;     // Slide index for multi-image preview carousel

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

            const tabName = item.querySelector(".nav-label")?.textContent || item.querySelector("span")?.textContent || "Dashboard";
            if (topbarTitle) topbarTitle.textContent = tabName;
            const breadcrumbEl = document.getElementById("topbar-breadcrumb-title");
            if (breadcrumbEl) breadcrumbEl.textContent = tabName;

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

// Character Counter & Live LinkedIn Post Sync
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
            updateLivePostPreview();
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
    toast.className = `toast toast-item toast-${type}`;

    const iconMap = {
        success: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
        danger: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fb7185" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`,
        warning: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
        info: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#818cf8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`,
    };
    const icon = iconMap[type] || iconMap.info;

    toast.innerHTML = `
        <span style="display: flex; align-items: center; justify-content: center; flex-shrink: 0;">${icon}</span>
        <div style="flex: 1; word-break: break-word; color: #f8fafc; line-height: 1.45; font-size: 0.88rem;">${escapeHtml(message)}</div>
        <button type="button" class="toast-close" aria-label="Close notification" style="background: none; border: none; color: var(--text-dim); cursor: pointer; display: flex; align-items: center; padding: 2px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
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
    if (timerEl) {
        timerEl.innerHTML = `
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10"></circle>
                <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
            <span>Elapsed: 0s</span>
        `;
    }

    clearInterval(loadingTimerInterval);
    loadingTimerInterval = setInterval(() => {
        const elapsedSec = Math.floor((Date.now() - loadingStartTime) / 1000);
        if (timerEl) {
            timerEl.innerHTML = `
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <circle cx="12" cy="12" r="10"></circle>
                    <polyline points="12 6 12 12 16 14"></polyline>
                </svg>
                <span>Elapsed: ${elapsedSec}s</span>
            `;
        }
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
                    <button class="btn btn-secondary btn-sm" onclick="viewProjectDetails(${p.id})">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        <span>View Analysis</span>
                    </button>
                    <button class="btn btn-primary btn-sm" onclick="openProjectDraft(${p.id})">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
                        <span>Post Editor</span>
                    </button>
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

    // Update media sequence state
    currentDraftScreenshot = draftData.screenshot_path || (draftData.media_paths && draftData.media_paths.length ? draftData.media_paths[0] : null);
    if (draftData.media_paths && draftData.media_paths.length > 0) {
        currentDraftMediaPaths = [...draftData.media_paths];
    } else if (currentDraftScreenshot) {
        currentDraftMediaPaths = [currentDraftScreenshot];
    } else {
        currentDraftMediaPaths = [];
    }

    // Render media in Post Editor & Live LinkedIn Feed Preview
    renderDraftMediaPreview(currentDraftScreenshot, currentDraftMediaPaths);
    updateLivePostPreview();
}

// Editor View Modes Switcher: 'split' | 'editor' | 'preview'
function switchEditorView(viewMode) {
    const leftPane = document.getElementById("editor-left-pane");
    const rightPane = document.getElementById("editor-right-pane");
    const grid = document.querySelector(".editor-split-grid");
    const buttons = document.querySelectorAll(".editor-view-switcher .view-switch-btn");

    buttons.forEach(btn => {
        const onclickAttr = btn.getAttribute("onclick") || "";
        if (onclickAttr.includes(`'${viewMode}'`)) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });

    if (viewMode === "split") {
        if (leftPane) leftPane.style.display = "block";
        if (rightPane) rightPane.style.display = "block";
        if (grid) grid.style.gridTemplateColumns = "";
    } else if (viewMode === "editor") {
        if (leftPane) leftPane.style.display = "block";
        if (rightPane) rightPane.style.display = "none";
        if (grid) grid.style.gridTemplateColumns = "1fr";
    } else if (viewMode === "preview") {
        if (leftPane) leftPane.style.display = "none";
        if (rightPane) rightPane.style.display = "block";
        if (grid) grid.style.gridTemplateColumns = "1fr";
    }
}

// Live LinkedIn Post Feed Preview
function updateLivePostPreview() {
    const bodyEl = document.getElementById("li-preview-body");
    const mediaContainer = document.getElementById("li-preview-media-container");
    const postBodyInput = document.getElementById("post-body");

    // 1. Format and display post body text
    if (bodyEl && postBodyInput) {
        const rawText = postBodyInput.value.trim();
        if (!rawText) {
            bodyEl.innerHTML = `<span style="color: #64748b; font-style: italic;">Start typing your post or load a draft to see your live LinkedIn feed preview here...</span>`;
        } else {
            let formatted = escapeHtml(postBodyInput.value);
            // Replace URLs with clickable styled links
            formatted = formatted.replace(
                /(https?:\/\/[^\s<]+)/g,
                '<a class="li-link" href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
            );
            // Replace #hashtags with styled hashtag spans
            formatted = formatted.replace(
                /(^|\s)(#[a-zA-Z0-9_\u00c0-\u017e]+)/g,
                '$1<span class="li-hashtag">$2</span>'
            );
            // Convert newlines to HTML breaks
            formatted = formatted.replace(/\n/g, "<br>");
            bodyEl.innerHTML = formatted;
        }
    }

    // 2. Render Media Section (photos, grid, or video)
    if (mediaContainer) {
        const mediaList = (currentDraftMediaPaths && currentDraftMediaPaths.length > 0)
            ? currentDraftMediaPaths
            : (currentDraftScreenshot ? [currentDraftScreenshot] : []);

        if (mediaList.length === 0) {
            mediaContainer.innerHTML = `
                <div style="background: rgba(0,0,0,0.25); border: 1px dashed rgba(255,255,255,0.12); border-radius: var(--radius-sm); padding: 1.25rem 1rem; text-align: center; margin: 0.5rem 1rem 0.75rem 1rem;">
                    <div style="font-size: 1.5rem; margin-bottom: 0.25rem;">📷</div>
                    <div style="font-size: 0.82rem; color: #94a3b8; font-weight: 500;">No media attached to this post</div>
                    <div style="font-size: 0.74rem; color: #64748b; margin-top: 0.25rem;">Posts with images/videos receive up to 2x higher engagement on LinkedIn feed.</div>
                </div>
            `;
            return;
        }

        function formatMediaUrl(url) {
            if (!url) return "";
            if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("/")) {
                return url;
            }
            return "/" + url;
        }

        function isVideoUrl(url) {
            const clean = url.split("?")[0].toLowerCase();
            return clean.endsWith(".mp4") || clean.endsWith(".webm") || clean.endsWith(".mov") || clean.endsWith(".mkv");
        }

        // Single media (video or single photo)
        if (mediaList.length === 1) {
            const itemUrl = formatMediaUrl(mediaList[0]);
            const isVid = isVideoUrl(mediaList[0]);
            if (isVid) {
                mediaContainer.innerHTML = `
                    <div style="background: #000; position: relative;">
                        <video src="${escapeHtml(itemUrl)}" controls class="li-media-single-vid" preload="metadata" style="width: 100%; max-height: 380px; display: block; object-fit: contain;"></video>
                        <div style="position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.75); padding: 3px 8px; border-radius: 4px; font-size: 0.7rem; color: #fff; font-weight: 600; display: flex; align-items: center; gap: 4px;">
                            <span>🎬</span> VIDEO POST
                        </div>
                    </div>
                `;
            } else {
                mediaContainer.innerHTML = `
                    <div style="background: #000; overflow: hidden; position: relative;">
                        <img src="${escapeHtml(itemUrl)}" alt="Post preview image" class="li-media-single-img" style="width: 100%; max-height: 420px; object-fit: contain; display: block; cursor: pointer;" onclick="window.open('${escapeHtml(itemUrl)}', '_blank')">
                    </div>
                `;
            }
            return;
        }

        // 2 items: Side-by-side split grid
        if (mediaList.length === 2) {
            const u1 = formatMediaUrl(mediaList[0]);
            const u2 = formatMediaUrl(mediaList[1]);
            mediaContainer.innerHTML = `
                <div class="li-grid-2">
                    <img src="${escapeHtml(u1)}" alt="Image 1" onclick="window.open('${escapeHtml(u1)}', '_blank')">
                    <img src="${escapeHtml(u2)}" alt="Image 2" onclick="window.open('${escapeHtml(u2)}', '_blank')">
                </div>
                <div class="li-carousel-bar">
                    <span>🖼️ Multi-Image Post (2 photos in upload sequence [1, 2])</span>
                    <span>Order preserved</span>
                </div>
            `;
            return;
        }

        // 3 items: 1 large left, 2 stacked right
        if (mediaList.length === 3) {
            const u1 = formatMediaUrl(mediaList[0]);
            const u2 = formatMediaUrl(mediaList[1]);
            const u3 = formatMediaUrl(mediaList[2]);
            mediaContainer.innerHTML = `
                <div class="li-grid-3">
                    <img src="${escapeHtml(u1)}" alt="Image 1" class="li-grid-large" onclick="window.open('${escapeHtml(u1)}', '_blank')">
                    <div class="li-grid-stack">
                        <img src="${escapeHtml(u2)}" alt="Image 2" onclick="window.open('${escapeHtml(u2)}', '_blank')">
                        <img src="${escapeHtml(u3)}" alt="Image 3" onclick="window.open('${escapeHtml(u3)}', '_blank')">
                    </div>
                </div>
                <div class="li-carousel-bar">
                    <span>🖼️ Multi-Image Post (3 photos in upload sequence [1, 2, 3])</span>
                    <span>Order preserved</span>
                </div>
            `;
            return;
        }

        // 4+ items: 2x2 grid with overflow +N badge on 4th item, plus interactive carousel slider
        const u1 = formatMediaUrl(mediaList[0]);
        const u2 = formatMediaUrl(mediaList[1]);
        const u3 = formatMediaUrl(mediaList[2]);
        const u4 = formatMediaUrl(mediaList[3]);
        const overflowCount = mediaList.length - 4;

        if (currentPreviewSlide >= mediaList.length) currentPreviewSlide = 0;
        if (currentPreviewSlide < 0) currentPreviewSlide = mediaList.length - 1;

        mediaContainer.innerHTML = `
            <div class="li-grid-4">
                <img src="${escapeHtml(u1)}" alt="Image 1" onclick="setPreviewSlide(0)">
                <img src="${escapeHtml(u2)}" alt="Image 2" onclick="setPreviewSlide(1)">
                <img src="${escapeHtml(u3)}" alt="Image 3" onclick="setPreviewSlide(2)">
                <div class="li-grid-overflow-box" onclick="setPreviewSlide(3)">
                    <img src="${escapeHtml(u4)}" alt="Image 4">
                    ${overflowCount > 0 ? `<div class="li-grid-overflow-badge">+${overflowCount}</div>` : ''}
                </div>
            </div>
            <div class="li-carousel-bar">
                <button type="button" class="btn btn-secondary btn-sm" style="padding: 1px 8px; font-size: 0.75rem;" onclick="prevPreviewSlide()">◀ Prev</button>
                <span>Viewing photo <strong>#${currentPreviewSlide + 1}</strong> of ${mediaList.length} (Upload order: [${mediaList.map((_, i) => i + 1).join(', ')}])</span>
                <button type="button" class="btn btn-secondary btn-sm" style="padding: 1px 8px; font-size: 0.75rem;" onclick="nextPreviewSlide()">Next ▶</button>
            </div>
        `;
    }
}

function setPreviewSlide(index) {
    if (!currentDraftMediaPaths || currentDraftMediaPaths.length === 0) return;
    currentPreviewSlide = index;
    const itemUrl = currentDraftMediaPaths[currentPreviewSlide];
    if (itemUrl) {
        const fullUrl = itemUrl.startsWith("/") || itemUrl.startsWith("http") ? itemUrl : "/" + itemUrl;
        window.open(fullUrl, "_blank");
    }
}

function nextPreviewSlide() {
    if (!currentDraftMediaPaths || currentDraftMediaPaths.length === 0) return;
    currentPreviewSlide = (currentPreviewSlide + 1) % currentDraftMediaPaths.length;
    updateLivePostPreview();
}

function prevPreviewSlide() {
    if (!currentDraftMediaPaths || currentDraftMediaPaths.length === 0) return;
    currentPreviewSlide = (currentPreviewSlide - 1 + currentDraftMediaPaths.length) % currentDraftMediaPaths.length;
    updateLivePostPreview();
}

// Post Editor Left Pane Media Preview & Ordered Sequence Manager
function renderDraftMediaPreview(screenshotPath, mediaPaths) {
    const mediaPreview = document.getElementById("editor-media-preview");
    if (!mediaPreview) return;

    const list = (mediaPaths && mediaPaths.length > 0)
        ? mediaPaths
        : (screenshotPath ? [screenshotPath] : []);

    if (list.length === 0) {
        mediaPreview.innerHTML = `
            <div class="empty-media-state" style="text-align: center; padding: 1.5rem 1rem; border: 1px dashed var(--border-medium); border-radius: var(--radius-md); background: rgba(0,0,0,0.2);">
                <div style="color: var(--text-dim); margin-bottom: 0.5rem;">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                        <circle cx="8.5" cy="8.5" r="1.5"></circle>
                        <polyline points="21 15 16 10 5 21"></polyline>
                    </svg>
                </div>
                <div style="font-weight: 600; color: #fff; margin-bottom: 0.25rem; font-size: 0.92rem;">No Media Attached</div>
                <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.85rem; max-width: 340px; margin-left: auto; margin-right: auto;">
                    Attach photos, demo videos, or repository assets. Your selected upload order is preserved for LinkedIn.
                </div>
                <div style="display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap;">
                    <button type="button" class="btn btn-primary btn-sm" onclick="openMediaSelectorModal()">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
                        <span>Select & Order Media</span>
                    </button>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="triggerExternalMediaUpload()">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                        <span>Upload from Computer</span>
                    </button>
                </div>
            </div>
        `;
        return;
    }

    function formatUrl(p) {
        if (!p.startsWith("http://") && !p.startsWith("https://") && !p.startsWith("/")) return "/" + p;
        return p;
    }

    function isVidPath(p) {
        const c = p.split("?")[0].toLowerCase();
        return c.endsWith(".mp4") || c.endsWith(".webm") || c.endsWith(".mov") || c.endsWith(".mkv");
    }

    const itemsHtml = list.map((path, idx) => {
        const url = formatUrl(path);
        const isVid = isVidPath(path);
        const filename = path.split("/").pop() || `item_${idx + 1}`;
        const isFirst = (idx === 0);
        const isLast = (idx === list.length - 1);

        const thumb = isVid
            ? `<div style="width: 48px; height: 48px; background: #000; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: var(--accent-amber); flex-shrink: 0;"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg></div>`
            : `<img src="${escapeHtml(url)}" alt="Thumb" style="width: 48px; height: 48px; object-fit: cover; border-radius: 4px; flex-shrink: 0;" onerror="this.onerror=null; this.src='/static/icons/image-placeholder.svg'">`;

        return `
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; background: var(--bg-surface-elevated); padding: 0.5rem 0.75rem; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle);">
                <div style="display: flex; align-items: center; gap: 0.6rem; overflow: hidden;">
                    <span class="media-order-badge" style="position: static; width: 22px; height: 22px; font-size: 0.7rem; flex-shrink: 0; box-shadow: none; background: var(--accent-primary); color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700;">#${idx + 1}</span>
                    ${thumb}
                    <div style="overflow: hidden;">
                        <div style="font-size: 0.82rem; font-weight: 600; color: #fff; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;" title="${escapeHtml(filename)}">
                            ${escapeHtml(filename)}
                        </div>
                        <div style="font-size: 0.7rem; color: var(--text-muted); display: flex; gap: 0.4rem; align-items: center;">
                            <span class="badge badge-${isVid ? 'warning' : 'info'}" style="font-size: 0.65rem; padding: 1px 4px;">${isVid ? 'VIDEO' : 'IMAGE'}</span>
                            <a href="${escapeHtml(url)}" target="_blank" style="color: var(--accent-cyan); text-decoration: none;">View ↗</a>
                        </div>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 0.25rem; flex-shrink: 0;">
                    <button type="button" class="btn btn-secondary btn-sm" style="padding: 2px 7px; font-size: 0.75rem;" onclick="moveEditorMedia(${idx}, -1)" ${isFirst ? 'disabled' : ''} title="Move earlier in upload sequence">◀</button>
                    <button type="button" class="btn btn-secondary btn-sm" style="padding: 2px 7px; font-size: 0.75rem;" onclick="moveEditorMedia(${idx}, 1)" ${isLast ? 'disabled' : ''} title="Move later in upload sequence">▶</button>
                    <button type="button" class="btn btn-danger btn-sm" style="padding: 2px 7px; font-size: 0.75rem;" onclick="removeEditorMediaItem(${idx})" title="Remove this item">✕</button>
                </div>
            </div>
        `;
    }).join("");

    mediaPreview.innerHTML = `
        <div class="media-active-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <div style="font-size: 0.85rem; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 0.4rem;">
                    <span>Upload Sequence</span>
                    <span class="badge badge-info badge-sm">${list.length} item${list.length > 1 ? 's' : ''}</span>
                </div>
                <span style="font-size: 0.72rem; color: var(--text-muted);">Exact order: [${list.map((_, i) => i + 1).join(', ')}]</span>
            </div>

            <div style="display: flex; flex-direction: column; gap: 0.4rem; max-height: 240px; overflow-y: auto;">
                ${itemsHtml}
            </div>

            <div class="media-actions-bar" style="border-top: 1px solid var(--border-subtle); padding-top: 0.65rem; margin-top: 0.65rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
                <button type="button" class="btn btn-primary btn-sm" style="flex: 1;" onclick="openMediaSelectorModal()">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
                    <span>Manage & Order Media</span>
                </button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="triggerExternalMediaUpload()" title="Upload additional file from computer">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
                    <span>Upload More</span>
                </button>
                <button type="button" class="btn btn-danger btn-sm" onclick="removeAttachedMedia()" title="Remove all media from this post">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    <span>Remove All</span>
                </button>
            </div>
        </div>
    `;
}

// Reordering and removing media directly in editor
async function moveEditorMedia(index, direction) {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= currentDraftMediaPaths.length) return;
    const item = currentDraftMediaPaths.splice(index, 1)[0];
    currentDraftMediaPaths.splice(newIndex, 0, item);
    currentDraftScreenshot = currentDraftMediaPaths[0] || null;

    await persistCurrentMediaOrder();
}

async function removeEditorMediaItem(index) {
    currentDraftMediaPaths.splice(index, 1);
    currentDraftScreenshot = currentDraftMediaPaths[0] || null;

    await persistCurrentMediaOrder();
}

async function persistCurrentMediaOrder() {
    if (!currentDraftId) return;
    try {
        const res = await fetch(`/api/drafts/${currentDraftId}/media`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                media_path: currentDraftScreenshot,
                media_paths: currentDraftMediaPaths,
            }),
        });
        const data = await res.json();
        if (res.ok) {
            currentDraftScreenshot = data.media_path;
            currentDraftMediaPaths = (data.media_paths && data.media_paths.length) ? data.media_paths : currentDraftMediaPaths;
            renderDraftMediaPreview(currentDraftScreenshot, currentDraftMediaPaths);
            updateLivePostPreview();
        }
    } catch (err) {
        showNotification("Failed to update media order: " + err.message, "danger");
    }
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
            if (!currentDraftMediaPaths) currentDraftMediaPaths = [];
            currentDraftMediaPaths.push(data.media_path);

            // Persist the updated sequence list
            await fetch(`/api/drafts/${currentDraftId}/media`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    media_path: currentDraftScreenshot,
                    media_paths: currentDraftMediaPaths,
                }),
            });

            renderDraftMediaPreview(currentDraftScreenshot, currentDraftMediaPaths);
            updateLivePostPreview();

            const badge = document.getElementById("draft-approval-badge");
            const btnPublish = document.getElementById("btn-publish-draft");
            if (badge) {
                badge.textContent = `Draft: ${data.draft_state}`;
                badge.className = `badge badge-${getBadgeClass(data.draft_state)}`;
            }
            if (btnPublish) btnPublish.disabled = true;
            showNotification(`✅ Media uploaded and appended to upload sequence (${data.file_size_mb} MB).`, "success");
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
    if (!confirm("Are you sure you want to remove all attached media from this LinkedIn post draft?")) {
        return;
    }

    try {
        const res = await fetch(`/api/drafts/${currentDraftId}/media`, {
            method: "DELETE",
        });
        const data = await res.json();
        if (res.ok) {
            currentDraftScreenshot = null;
            currentDraftMediaPaths = [];
            renderDraftMediaPreview(null, []);
            updateLivePostPreview();
            showNotification("All attached media detached from draft.", "info");
        } else {
            showNotification(data.detail || "Failed to remove media.", "danger");
        }
    } catch (err) {
        showNotification("Error detaching media: " + err.message, "danger");
    }
}

// Media Selector Modal: Multi-Select & Custom Ordering Engine
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
        modalAvailableMedia = items || [];
        if (loading) loading.style.display = "none";

        // Prepopulate modalSelectedMedia based on currentDraftMediaPaths
        modalSelectedMedia = [];
        if (currentDraftMediaPaths && currentDraftMediaPaths.length > 0) {
            for (const path of currentDraftMediaPaths) {
                const found = modalAvailableMedia.find(m => m.url === path);
                if (found) {
                    modalSelectedMedia.push(found);
                } else {
                    const clean = path.split("?")[0].toLowerCase();
                    const isVid = clean.endsWith(".mp4") || clean.endsWith(".webm") || clean.endsWith(".mov") || clean.endsWith(".mkv");
                    modalSelectedMedia.push({
                        url: path,
                        title: path.split("/").pop() || "Selected Media",
                        is_video: isVid,
                        source: "Current Post",
                    });
                }
            }
        }

        // BY DEFAULT: Auto-select all fetched repository media if no custom multi-selection exists yet
        if (modalSelectedMedia.length <= 1 && modalAvailableMedia.length > 0) {
            const repoItems = modalAvailableMedia.filter(m => m.source && (m.source.toLowerCase().includes("repo") || m.source.toLowerCase().includes("asset") || m.source.toLowerCase().includes("demo") || m.source.toLowerCase().includes("screenshot")));
            if (repoItems.length > 0) {
                modalSelectedMedia = [...repoItems];
            } else {
                modalSelectedMedia = [...modalAvailableMedia];
            }
        }

        // Update counts
        const allCount = modalAvailableMedia.length;
        const imgCount = modalAvailableMedia.filter(m => !m.is_video).length;
        const vidCount = modalAvailableMedia.filter(m => m.is_video).length;

        const cAll = document.getElementById("filter-count-all");
        const cImg = document.getElementById("filter-count-image");
        const cVid = document.getElementById("filter-count-video");
        if (cAll) cAll.textContent = allCount;
        if (cImg) cImg.textContent = imgCount;
        if (cVid) cVid.textContent = vidCount;

        // Render tray and grid
        renderModalSequenceTray();
        renderModalMediaGrid();
    } catch (err) {
        if (loading) loading.style.display = "none";
        showNotification("Failed to load available media: " + err.message, "danger");
    }
}

// Multi-select batch actions
function selectAllRepoMedia() {
    const repoItems = modalAvailableMedia.filter(m => m.source && (m.source.toLowerCase().includes("repo") || m.source.toLowerCase().includes("asset")));
    const toSelect = repoItems.length > 0 ? repoItems : modalAvailableMedia;

    modalSelectedMedia = [...toSelect];
    renderModalSequenceTray();
    renderModalMediaGrid();
    showNotification(`Selected ${modalSelectedMedia.length} repository media item(s) in order!`, "info");
}

function selectAllVisibleModalMedia() {
    const visible = getCurrentlyFilteredModalMedia();
    for (const item of visible) {
        if (!modalSelectedMedia.some(m => m.url === item.url)) {
            modalSelectedMedia.push(item);
        }
    }
    renderModalSequenceTray();
    renderModalMediaGrid();
    showNotification(`Selected ${modalSelectedMedia.length} media item(s)!`, "info");
}

function getCurrentlyFilteredModalMedia() {
    return modalAvailableMedia.filter(item => {
        // Filter Type
        if (modalActiveFilter === "image" && item.is_video) return false;
        if (modalActiveFilter === "video" && !item.is_video) return false;
        if (modalActiveFilter === "repo" && (!item.source || !item.source.toLowerCase().includes("repo"))) return false;
        if (modalActiveFilter === "demo" && (!item.source || (!item.source.toLowerCase().includes("demo") && !item.source.toLowerCase().includes("screenshot")))) return false;

        // Search Query
        if (modalSearchQuery) {
            const titleMatch = (item.title || "").toLowerCase().includes(modalSearchQuery);
            const urlMatch = (item.url || "").toLowerCase().includes(modalSearchQuery);
            if (!titleMatch && !urlMatch) return false;
        }

        return true;
    });
}

function filterModalMedia(filterType, btnEl) {
    modalActiveFilter = filterType;
    const buttons = document.querySelectorAll(".media-filter-btn");
    buttons.forEach(b => b.classList.remove("active"));
    if (btnEl) btnEl.classList.add("active");
    renderModalMediaGrid();
}

function handleModalMediaSearch(query) {
    modalSearchQuery = (query || "").toLowerCase().trim();
    renderModalMediaGrid();
}

function toggleModalMediaSelection(mediaUrl) {
    const existingIndex = modalSelectedMedia.findIndex(m => m.url === mediaUrl);
    if (existingIndex !== -1) {
        // Deselect and remove from sequence; subsequent items shift down
        modalSelectedMedia.splice(existingIndex, 1);
    } else {
        // Add to sequence in the exact order selected
        const item = modalAvailableMedia.find(m => m.url === mediaUrl) || {
            url: mediaUrl,
            title: mediaUrl.split("/").pop() || "Media Item",
            is_video: false,
            source: "Selected",
        };
        modalSelectedMedia.push(item);
    }

    renderModalSequenceTray();
    renderModalMediaGrid();
}

function toggleModalMediaByIndex(index) {
    if (index < 0 || index >= modalAvailableMedia.length) return;
    const item = modalAvailableMedia[index];
    if (item) {
        toggleModalMediaSelection(item.url);
    }
}

function moveModalMediaSequence(index, direction) {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= modalSelectedMedia.length) return;
    const item = modalSelectedMedia.splice(index, 1)[0];
    modalSelectedMedia.splice(newIndex, 0, item);
    renderModalSequenceTray();
    renderModalMediaGrid();
}

function removeModalMediaSequence(index) {
    modalSelectedMedia.splice(index, 1);
    renderModalSequenceTray();
    renderModalMediaGrid();
}

function clearModalMediaSelection() {
    modalSelectedMedia = [];
    renderModalSequenceTray();
    renderModalMediaGrid();
}

function renderModalSequenceTray() {
    const tray = document.getElementById("modal-selection-tray");
    const countEl = document.getElementById("modal-selected-count");
    const chipsContainer = document.getElementById("modal-sequence-chips");
    const applyBtn = document.getElementById("btn-apply-modal-media");
    const footerHint = document.getElementById("modal-footer-hint");

    const totalSelected = modalSelectedMedia.length;

    if (totalSelected === 0) {
        if (tray) tray.style.display = "none";
        if (applyBtn) applyBtn.textContent = "Apply Selection (0)";
        if (footerHint) footerHint.textContent = "Click cards to select items in the exact order you want them uploaded.";
        return;
    }

    if (tray) tray.style.display = "flex";
    if (countEl) countEl.textContent = `${totalSelected} item${totalSelected > 1 ? 's' : ''} in upload sequence`;
    if (applyBtn) applyBtn.textContent = `✅ Apply Selection (${totalSelected})`;
    if (footerHint) footerHint.textContent = `Items will upload in order: [${modalSelectedMedia.map((_, i) => i + 1).join(', ')}]`;

    if (chipsContainer) {
        chipsContainer.innerHTML = modalSelectedMedia.map((item, idx) => {
            const isFirst = (idx === 0);
            const isLast = (idx === totalSelected - 1);
            const icon = item.is_video ? "🎬" : "📷";
            const shortTitle = item.title.length > 20 ? item.title.slice(0, 17) + "..." : item.title;

            return `
                <div class="media-sequence-chip">
                    <span class="seq-number">#${idx + 1}</span>
                    <span>${icon}</span>
                    <span style="font-weight: 500;" title="${escapeHtml(item.title)}">${escapeHtml(shortTitle)}</span>
                    <button type="button" class="seq-btn" onclick="moveModalMediaSequence(${idx}, -1)" ${isFirst ? 'disabled style="opacity:0.3;"' : ''} title="Move Earlier">◀</button>
                    <button type="button" class="seq-btn" onclick="moveModalMediaSequence(${idx}, 1)" ${isLast ? 'disabled style="opacity:0.3;"' : ''} title="Move Later">▶</button>
                    <button type="button" class="seq-btn btn-remove" onclick="removeModalMediaSequence(${idx})" title="Remove from sequence">✕</button>
                </div>
            `;
        }).join("");
    }
}

function renderModalMediaGrid() {
    const grid = document.getElementById("media-grid");
    const empty = document.getElementById("media-modal-empty");
    if (!grid) return;

    const filtered = getCurrentlyFilteredModalMedia();

    if (filtered.length === 0) {
        grid.innerHTML = "";
        if (empty) empty.style.display = "block";
        return;
    }

    if (empty) empty.style.display = "none";

    grid.innerHTML = filtered.map(item => {
        let mediaUrl = item.url;
        if (!mediaUrl.startsWith("http://") && !mediaUrl.startsWith("https://") && !mediaUrl.startsWith("/")) {
            mediaUrl = "/" + mediaUrl;
        }

        // Check if selected and find its sequence position
        const selectedIndex = modalSelectedMedia.findIndex(m => m.url === item.url);
        const isSelected = (selectedIndex !== -1);
        const orderNumber = selectedIndex + 1;

        const isVid = Boolean(item.is_video);
        const thumbHtml = isVid
            ? `<div style="height:130px; display:flex; flex-direction:column; align-items:center; justify-content:center; background:#000; font-size:2rem; position:relative;">
                 <span>🎬</span>
                 <span style="font-size:0.7rem; color:#94a3b8; margin-top:4px;">MP4 / Video Asset</span>
               </div>`
            : `<img src="${escapeHtml(mediaUrl)}" alt="${escapeHtml(item.title)}" class="media-gallery-thumb" onerror="this.onerror=null; this.src='/static/icons/image-placeholder.svg'">`;

        const badgeHtml = isSelected
            ? `<div class="media-order-badge" title="Upload Order Position #${orderNumber}">#${orderNumber}</div>`
            : "";

        const checkboxHtml = `
            <div class="media-checkbox-box ${isSelected ? 'checked' : ''}" title="${isSelected ? 'Deselect item' : 'Select item for upload'}">
                ${isSelected ? '✓' : ''}
            </div>
        `;

        const globalIndex = modalAvailableMedia.findIndex(m => m.url === item.url);

        return `
            <div class="media-gallery-card ${isSelected ? 'is-selected' : ''}" onclick="toggleModalMediaByIndex(${globalIndex})">
                ${checkboxHtml}
                ${badgeHtml}
                ${thumbHtml}
                <div class="media-gallery-info">
                    <div style="display: flex; justify-content: space-between; align-items: center; width: 100%;">
                        <span class="badge badge-${item.source === 'Demo Screenshot' ? 'success' : (item.source === 'Uploaded Media' ? 'info' : 'neutral')}" style="font-size:0.68rem;">
                            ${escapeHtml(item.source)}
                        </span>
                        <span style="font-size: 0.7rem; color: var(--text-muted);">${isVid ? 'Video' : 'Image'}</span>
                    </div>
                    <div class="media-gallery-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
                    <button type="button" class="btn ${isSelected ? 'btn-success' : 'btn-secondary'} btn-sm" style="margin-top:0.4rem; width:100%; font-size:0.75rem;" onclick="event.stopPropagation(); toggleModalMediaByIndex(${globalIndex})">
                        ${isSelected ? `✓ Selected (#${orderNumber})` : '+ Add to Sequence'}
                    </button>
                </div>
            </div>
        `;
    }).join("");
}

async function applyModalMediaSelection() {
    if (!currentDraftId) {
        showNotification("No active draft to attach media to.", "warning");
        return;
    }

    const orderedUrls = modalSelectedMedia.map(m => m.url);
    const primaryUrl = orderedUrls.length > 0 ? orderedUrls[0] : null;

    try {
        const res = await fetch(`/api/drafts/${currentDraftId}/media`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                media_path: primaryUrl,
                media_paths: orderedUrls,
            }),
        });
        const data = await res.json();
        if (res.ok) {
            currentDraftScreenshot = data.media_path;
            currentDraftMediaPaths = (data.media_paths && data.media_paths.length) ? data.media_paths : orderedUrls;
            renderDraftMediaPreview(currentDraftScreenshot, currentDraftMediaPaths);
            updateLivePostPreview();
            closeMediaSelectorModal();
            showNotification(`Attached ${orderedUrls.length} media item(s) in custom upload sequence!`, "success");
        } else {
            showNotification(data.detail || "Failed to attach media sequence.", "danger");
        }
    } catch (err) {
        showNotification("Error attaching media sequence: " + err.message, "danger");
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
        currentDraftMediaPaths = (draft.media_paths && draft.media_paths.length > 0)
            ? [...draft.media_paths]
            : (draft.screenshot_path ? [draft.screenshot_path] : []);
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
                // Sync Live Feed Preview author info
                const previewName = document.getElementById("li-preview-name");
                const previewAvatar = document.getElementById("li-preview-avatar");
                const previewReactions = document.getElementById("li-preview-reactions");
                if (previewName) previewName.textContent = name;
                if (previewAvatar) {
                    const initials = name.split(" ").filter(Boolean).map(w => w[0]).join("").slice(0, 2).toUpperCase() || "LI";
                    previewAvatar.innerHTML = `<span>${escapeHtml(initials)}</span>`;
                }
                if (previewReactions) {
                    previewReactions.textContent = `${escapeHtml(name)} and 24 others`;
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
            <td>
                <button class="btn btn-secondary btn-sm" onclick="loadDraftById(${h.draft_id})">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
                    <span>View Draft</span>
                </button>
            </td>
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
