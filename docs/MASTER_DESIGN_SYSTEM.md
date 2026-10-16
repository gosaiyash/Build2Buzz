# Build2Buzz Design System Master Specification
**Standard:** UI/UX Pro Max 2.15.0 & UI/UX Designer Guidelines  
**Target Platform:** Web (Desktop & Mobile Responsive, 320px - 2560px)  
**Theme:** Dark Mode (OLED / Slate) + Precision Glassmorphism  
**Accessibility:** WCAG 2.2 AA / AAA Compliant (Contrast >= 4.5:1 text, >= 3:1 controls)

---

## 1. Core Visual Philosophy
- **Identity:** High-performance, secure, local-first developer productivity suite.
- **Mood:** Cinematic dark, technical precision, clean, professional, high-end utility (inspired by Raycast, Linear, Vercel, Supabase).
- **Surface Elevation:** Layered z-depth with frosted glassmorphism (`backdrop-filter: blur(16px)`), subtle translucent borders (`rgba(255, 255, 255, 0.08)`), and soft outer glow shadows.
- **Iconography Policy:** 100% SVG inline icons (Phosphor / Lucide geometry, stroke-width: 2.0px). **Zero raw emojis as UI icons.**

---

## 2. Design Tokens

### Color Palette (OLED Slate & Modern Accents)
| Token | Value | Semantic Purpose | WCAG Contrast |
|---|---|---|---|
| `--bg-canvas` | `#080c14` | Deepest root canvas | Background |
| `--bg-sidebar` | `#0d131f` | Sidebar navigation drawer | Base Surface |
| `--bg-topbar` | `rgba(13, 19, 31, 0.85)` | Glassmorphic floating header | Translucent |
| `--bg-surface` | `#111927` | Standard card surface | 16:1 against white |
| `--bg-surface-elevated`| `#172236` | Elevated cards, dropdowns, popovers | 14:1 against white |
| `--bg-surface-recessed`| `#0a0f19` | Inset panels, code blocks, evidence | Recessed |
| `--border-subtle` | `rgba(255, 255, 255, 0.07)`| Subtle card & divider borders | Structural |
| `--border-medium` | `rgba(255, 255, 255, 0.14)`| Interactive inputs, hover borders | Input borders |
| `--border-focus` | `#6366f1` | Focus ring with outer glow | AA 3:1 indicator |
| `--accent-primary` | `#6366f1` | Primary CTA, active nav, key metrics | Vibrant Indigo |
| `--accent-primary-hover`| `#4f46e5` | Primary CTA hover state | Deep Indigo |
| `--accent-cyan` | `#06b6d4` | Live inspection, links, tooltips | Electric Cyan |
| `--accent-emerald` | `#10b981` | Published, verified, online status | Mint Emerald |
| `--accent-amber` | `#f59e0b` | Pending review, warning alerts | Warm Amber |
| `--accent-rose` | `#f43f5e` | Cautions, destructive actions | Crimson Rose |
| `--text-primary` | `#f8fafc` | Headings, active states, key data | 15.2:1 (AAA) |
| `--text-secondary` | `#cbd5e1` | Main body copy, descriptions | 11.4:1 (AAA) |
| `--text-muted` | `#94a3b8` | Labels, hints, captions, icons | 5.8:1 (AA) |
| `--text-dim` | `#64748b` | Placeholders, inactive counts | 3.5:1 |

### Typography
- **Primary Interface Font:** `Inter`, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
  - Display / Title: 600 / 700 weight, `-0.02em` letter spacing
  - Body: 400 / 500 weight, `1.55` line height
- **Code & Monospace Font:** `JetBrains Mono`, monospace
  - Counters, URLs, Git hashes, API keys, JSON evidence: 500 weight, `0.88rem`

### Spacing Scale (4pt/8dp incremental system)
- `--space-1`: `4px`
- `--space-2`: `8px`
- `--space-3`: `12px`
- `--space-4`: `16px`
- `--space-6`: `24px`
- `--space-8`: `32px`
- `--space-12`: `48px`

### Border Radii
- `--radius-sm`: `6px` (chips, badges, buttons-sm)
- `--radius-md`: `10px` (inputs, buttons, select, pills)
- `--radius-lg`: `14px` (cards, dialogs, bento panels)
- `--radius-xl`: `20px` (modal frames)
- `--radius-full`: `9999px` (status dots, avatars)

---

## 3. Component Architecture & Improvements

### A. Bento Grid Dashboard
- 5 Key Metric Cards with animated glow on hover, custom Lucide SVG icons, and micro-trend indicators.
- Live Infrastructure Pulse Bar: Visual online pulse (`#10b981`) with real-time status pills for AI Mode, GitHub API rate limits, and LinkedIn OAuth token validity.

### B. Repository Ingestion & Evidence Matrix
- Ingestion form with dual-action input fields, clear visual requirements, and instant style presets.
- 4-Quadrant Evidence Dashboard:
  - README Facts: Indigo theme, bulleted clean layout.
  - Demo Findings: Cyan theme with browser viewport indicators.
  - Verified Tech: Emerald theme with checkmark badges.
  - Unverified Cautions: Rose theme with cautionary alerts to prevent hallucinations.
- Simulated Browser Frame for demo screenshot: Mac-style top window controls (red/yellow/green dots), URL address bar pill, and high-fidelity image wrapper.

### C. Human-in-the-Loop Post Composer (Hero Studio)
- Triple-view switcher: Split View, Compose Only, Feed Preview Only.
- Character Capacity Monitor: Interactive SVG circular ring or high-contrast progress bar showing exact remaining characters out of 3,000.
- Media Sequence Manager: Reorderable thumbnail cards with sequential `#1`, `#2`, `#3` badges and remove actions.
- **Pixel-Perfect LinkedIn Feed Simulator**:
  - Exact typography, avatar ring, verified degree badge (`• 1st`), headline, and public globe icon.
  - Authentic multi-image collage grid handling 1, 2, 3, or 4+ images.
  - Official LinkedIn interaction buttons: Like, Comment, Repost, Send with accurate SVG glyphs.

### D. Settings & Integrations
- Mutually exclusive AI Mode radio cards with glowing active borders.
- One-click quick preset chips (OpenRouter, Groq, Ollama, Nvidia, Together).
- Secure Windows Credential Manager integration visual cues.
- LinkedIn OAuth 2-step setup wizard with instant copy button for Redirect URIs.

### E. Modals, Toasts, and Feedback
- Glassmorphic modal overlay with background blur and escape-key handling.
- Fixed floating toast notifications with slide-up animations and distinct SVG iconography.
- Fullscreen AI generation loading card with live timer pill and reassuring step descriptions.
