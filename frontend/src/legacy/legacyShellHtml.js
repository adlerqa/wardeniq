// Legacy shell markup (canonical — app/static/index.html was removed).
// Contains: #login, #invite-gate, #app-shell (sidebar/header/all views), modals, #toast host.
// Delete sections from here as views are refactored into idiomatic React.
export const LEGACY_SHELL_HTML = `
<div id="login" hidden>
  <div class="box">
    <div class="login-logo">
      <svg width="42" height="42" viewBox="0 0 100 80" fill="none" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;">
        <rect x="22" y="10" width="12" height="60" fill="#1c7ec2" />
        <rect x="44" y="10" width="12" height="60" fill="#1c7ec2" />
        <rect x="66" y="10" width="12" height="60" fill="#1c7ec2" />
        <path d="M 5,38 C 15,38 15,48 25,48 H 36 C 44,48 44,40 50,40 C 56,40 56,48 64,48 H 75 C 85,48 85,62 95,62" stroke="#1ce5b2" stroke-width="5" fill="none" stroke-linecap="round" />
        <circle cx="5" cy="38" r="5" fill="#1ce5b2" />
        <circle cx="5" cy="38" r="2.2" fill="#141a24" />
        <circle cx="95" cy="62" r="5" fill="#1ce5b2" />
        <circle cx="95" cy="62" r="2.2" fill="#141a24" />
        <circle cx="50" cy="40" r="10" fill="#141a24" stroke="#1ce5b2" stroke-width="5" />
      </svg>
      <div class="logo-text">
        <span class="logo-title">Warden<span>IQ</span></span>
        <span class="logo-subtitle">Engineering Intelligence</span>
      </div>
    </div>
    <p id="login-intro">Sign in with a one-time code sent to your email. No password needed.</p>
    <div id="login-step1">
      <label>Email</label>
      <input id="login-email" type="email" placeholder="you@company.com" autocomplete="email"/>
      <button class="go" id="login-send">Send code</button>
    </div>
    <div id="login-step2" hidden>
      <div class="login-sent-badge" id="login-sent-badge"><span id="login-sent-text">We emailed a 6-digit code to </span><b id="login-to"></b></div>
      <label>Enter the code</label>
      <div id="login-code" class="otp-boxes">
        <input class="otp-box" type="text" inputmode="numeric" maxlength="1" aria-label="Digit 1"/>
        <input class="otp-box" type="text" inputmode="numeric" maxlength="1" aria-label="Digit 2"/>
        <input class="otp-box" type="text" inputmode="numeric" maxlength="1" aria-label="Digit 3"/>
        <input class="otp-box" type="text" inputmode="numeric" maxlength="1" aria-label="Digit 4"/>
        <input class="otp-box" type="text" inputmode="numeric" maxlength="1" aria-label="Digit 5"/>
        <input class="otp-box" type="text" inputmode="numeric" maxlength="1" aria-label="Digit 6"/>
      </div>
      <button class="go" id="login-verify">Verify &amp; sign in</button>
      <button class="link" id="login-back">← use a different email</button>
    </div>
    <div id="login-password" hidden>
      <label>Username / Email</label>
      <input id="login-username" type="text" placeholder="admin" autocomplete="username"/>
      <label style="margin-top:10px">Password</label>
      <input id="login-pw" type="password" placeholder="••••••••" autocomplete="current-password"/>
      <button class="go" id="login-signin" style="margin-top:15px">Sign in</button>
    </div>
    <div class="muted ok" id="login-msg" style="margin-top:10px"></div>
    <div class="err" id="login-err"></div>
  </div>
</div>
<!-- Invite banner: shown after login when the user has a pending invite. -->
<div id="invite-gate" hidden>
  <div class="box invite-box">
    <div class="invite-icon">
      <svg width="34" height="34" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M3 7l9 6 9-6" stroke="#1ce5b2" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <rect x="3" y="5" width="18" height="14" rx="2.5" stroke="#1ce5b2" stroke-width="1.8"/>
      </svg>
    </div>
    <h2 style="margin:6px 0 2px">You've been invited</h2>
    <p class="muted" id="invite-sub" style="margin-top:0">You've been invited to join <b id="invite-workspace">WardenIQ</b>.</p>
    <div class="invite-meta" id="invite-meta"></div>
    <div class="invite-actions">
      <button class="go" id="invite-accept">Accept invitation</button>
      <button class="ghost" id="invite-decline">Decline</button>
    </div>
    <div class="err" id="invite-err"></div>
  </div>
</div>
<div class="app" id="app-shell">
  <aside class="sidebar">
    <div class="logo-row">
      <div class="sidebar-logo">
        <svg width="36" height="36" viewBox="0 0 100 80" fill="none" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0;">
          <rect x="22" y="10" width="12" height="60" fill="#1c7ec2" />
          <rect x="44" y="10" width="12" height="60" fill="#1c7ec2" />
          <rect x="66" y="10" width="12" height="60" fill="#1c7ec2" />
          <path d="M 5,38 C 15,38 15,48 25,48 H 36 C 44,48 44,40 50,40 C 56,40 56,48 64,48 H 75 C 85,48 85,62 95,62" stroke="#1ce5b2" stroke-width="5" fill="none" stroke-linecap="round" />
          <circle cx="5" cy="38" r="5" fill="#1ce5b2" />
          <circle cx="5" cy="38" r="2.2" fill="#121826" />
          <circle cx="95" cy="62" r="5" fill="#1ce5b2" />
          <circle cx="95" cy="62" r="2.2" fill="#121826" />
          <circle cx="50" cy="40" r="10" fill="#121826" stroke="#1ce5b2" stroke-width="5" />
        </svg>
        <div class="logo-text">
          <span class="logo-title">Warden<span>IQ</span></span>
          <span class="logo-subtitle">Engineering Intelligence</span>
        </div>
      </div>
      <button class="sidebar-toggle" id="sidebar-toggle" title="Collapse sidebar">‹</button>
    </div>
    <div class="muted brand-subtitle" style="font-size:10.5px;padding:0 10px 10px">Test Intelligence Platform</div>
    <nav>
      <button data-view="dashboard" title="Dashboard" class="active"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg><span class="nav-label">Dashboard</span></button>
      <button data-view="projects" title="Projects & Repos"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg><span class="nav-label">Projects &amp; Repos</span></button>
      <button data-view="cases" title="Test Cases"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg><span class="nav-label">Test Cases</span></button>
      <button data-view="cycles" title="Code Analysis & Cycles"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9 9 0 0 0-7 3.5M3 4v4h4"/></svg><span class="nav-label">Code Analysis &amp; Cycles</span></button>
      <button data-view="mindmap" title="Mind Map"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.2 10.9l7.6-3.8M8.2 13.1l7.6 3.8"/></svg><span class="nav-label">Mind Map</span></button>
      <button data-view="steps" title="Step Library"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/></svg><span class="nav-label">Step Library</span></button>
      <button data-view="usage" title="LLM Usage &amp; Cost"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/></svg><span class="nav-label">Usage &amp; Cost</span></button>
      <button data-view="users" title="Users" data-admin="1" hidden><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0"/><path d="M16 5.5a3 3 0 0 1 0 5.5M21 20a5.5 5.5 0 0 0-4-5.3"/></svg><span class="nav-label">Users</span></button>
      <button data-view="config" title="Configuration" data-admin="1"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg><span class="nav-label">Configuration</span></button>
    </nav>
  </aside>
  <div class="content">
    <header>
      <h1 id="view-title">Dashboard</h1>
      <div style="display:flex;align-items:center;gap:16px">
        <div id="status"><span class="muted">loading…</span></div>
        <div class="usermenu" id="usermenu" hidden>
          <div class="user-id">
            <span id="user-email" class="user-email"></span>
            <span id="user-role" class="rolebadge viewer"></span>
          </div>
          <button class="ghost" id="change-pw-btn" title="Change your local admin password" hidden>
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>
            <span>Change password</span>
          </button>
          <button class="ghost signout-btn" id="logout-btn" title="Sign out">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/></svg>
            <span>Sign out</span>
          </button>
        </div>
      </div>
    </header>
    <main>
      <div class="ro-banner" id="ro-banner" hidden>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="5" y="11" width="14" height="9" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M8 11V8a4 4 0 0 1 8 0v3" stroke="currentColor" stroke-width="1.8"/></svg>
        <span>You're viewing in <b>read-only</b> mode. Your Viewer role can browse everything but can't create, edit, or delete. Ask an admin for Editor access to make changes.</span>
      </div>
      <div class="backbar" id="backbar"><button class="ghost" id="backbar-btn">Back</button><span class="crumb" id="backbar-label"></span></div>
      <!-- DASHBOARD -->
      <section id="view-dashboard" class="view">
        <div class="dash" id="dash-root"></div>
      </section>

      <!-- PROJECTS & REPOS -->
      <section id="view-projects" class="view" hidden>
        <div id="project-list-page" class="stage-page">
          <div class="page-toolbar" id="project-list-toolbar">
            <div><h2>Projects</h2></div>
            <button class="go" id="proj-new-btn">+ New project</button>
          </div>
          <div id="proj-create-card" class="card create-project-card" style="display:none">
            <div class="page-toolbar" style="margin-bottom:18px">
              <button class="ghost" id="proj-create-back" type="button">Back</button>
              <div></div>
            </div>
            <h2 style="font-size:17px">Create project</h2>
            <div class="sub">Configure the project's basics, optional Jira/Confluence association, and connect repositories. Only the project name is required — everything else can be configured later.</div>

            <div class="cp-grid">
              <div class="cp-step">
                <div class="cp-step-head"><span class="cp-step-num">1</span><h3>Project name</h3><span class="cp-required">*</span></div>
                <input id="new-proj-name" placeholder="E.g. WardenIQ Core"/>
                <div class="muted cp-err" id="new-proj-name-err"></div>
              </div>

              <div class="cp-step">
                <div class="cp-step-head"><span class="cp-step-num">2</span><h3>Description</h3><span class="muted">(optional)</span></div>
                <textarea id="new-proj-desc" rows="3" placeholder="What this project is about (optional)"></textarea>
              </div>

              <div class="cp-step">
                <div class="cp-step-head"><span class="cp-step-num">3</span><h3>Jira project</h3><span class="muted">(optional)</span></div>
                <div class="sub" style="margin:0 0 8px">Pick from the Jira projects this workspace can see. Configure Jira in <b>Settings → Jira &amp; Confluence</b> first to populate this dropdown.</div>
                <div class="cp-jira-row">
                  <select id="new-proj-jira"><option value="">— none —</option></select>
                  <button class="ghost" id="new-proj-jira-refresh" type="button">Reload</button>
                </div>
                <div class="muted" id="new-proj-jira-status" style="font-size:11px;margin-top:6px"></div>
              </div>

              <div class="cp-step">
                <div class="cp-step-head"><span class="cp-step-num">4</span><h3>Confluence space</h3><span class="muted">(optional)</span></div>
                <div class="sub" style="margin:0 0 8px">Link a Confluence space to pull design/spec context for this project.</div>
                <div class="cp-jira-row">
                  <select id="new-proj-confluence"><option value="">— none —</option></select>
                  <button class="ghost" id="new-proj-confluence-refresh" type="button">Reload</button>
                </div>
                <div class="muted" id="new-proj-confluence-status" style="font-size:11px;margin-top:6px"></div>
              </div>

              <div class="cp-step cp-full">
                <div class="cp-step-head"><span class="cp-step-num">5</span><h3>Git provider &amp; PAT</h3><span class="muted">(optional)</span></div>
                <div class="cp-provider-toggle">
                  <button type="button" data-provider="github" class="cp-prov active">GitHub</button>
                  <button type="button" data-provider="gitlab" class="cp-prov">GitLab</button>
                </div>
                <div class="sub" style="margin:0 0 8px">Provide a fine-grained PAT scoped to PR + contents read. wardenIQ stores it encrypted at rest, registers webhooks on the repos you pick below, and uses it to read PR diffs for coverage analysis.</div>
                <input type="password" id="new-proj-pat" placeholder="ghp_..."/>
                <div style="margin-top:8px"><button class="ghost" type="button" id="new-proj-load-repos">Load my repositories</button> <span class="muted" id="new-proj-pat-status" style="font-size:11px;margin-left:8px"></span></div>
              </div>

              <div class="cp-step">
                <div class="cp-step-head"><span class="cp-step-num">6</span><h3>App repositories</h3><span class="muted">(optional)</span></div>
                <div class="sub" style="margin:0 0 8px">Repositories that contain your application code. Webhooks are registered on these so PRs trigger coverage automatically.</div>
                <div class="cp-repo-picker" id="new-proj-app-picker">
                  <div class="muted cp-repo-empty">Load repositories above to pick.</div>
                </div>
                <div class="muted" style="margin-top:8px;font-size:12px">Selected: <span id="new-proj-app-count">0</span></div>
              </div>

              <div class="cp-step">
                <div class="cp-step-head"><span class="cp-step-num">7</span><h3>Test repositories</h3><span class="muted">(optional)</span></div>
                <div class="sub" style="margin:0 0 8px">Repositories that contain your automated tests (Playwright, Cypress, etc.). wardenIQ scans them for existing coverage — no webhook is added.</div>
                <div class="cp-repo-picker" id="new-proj-test-picker">
                  <div class="muted cp-repo-empty">Load repositories above to pick.</div>
                </div>
                <div class="muted" style="margin-top:8px;font-size:12px">Selected: <span id="new-proj-test-count">0</span></div>
              </div>

              <div class="cp-step cp-full" style="border-bottom:none">
                <div class="cp-actions">
                  <button class="go" id="proj-create-save">Create project</button>
                  <button class="ghost" id="proj-create-cancel" type="button">Cancel</button>
                  <span class="muted" id="proj-create-status" style="font-size:12px;margin-left:8px"></span>
                </div>
              </div>
            </div>
          </div>
          <div id="project-cards-container" class="entity-grid"></div>
        </div>

        <div id="project-detail-page" class="stage-page stage-shell" hidden>
          <div class="stage-header">
            <button class="ghost" id="project-detail-back">← All projects</button>
            <div class="stage-header-actions"><button class="go" id="proj-features-btn">View features</button><button class="ghost" id="proj-rename-btn">Rename</button><button class="danger" id="proj-del-btn">Delete project</button></div>
          </div>
          <div class="card">
            <h2 id="active-proj-title" style="font-size:21px">Project</h2>
            <div class="sub" id="active-proj-stats"></div>
            <div class="project-summary">
              <div class="summary-box"><b id="project-feature-count">0</b><span>Features</span></div>
              <div class="summary-box"><b id="project-repo-count">0</b><span>Repositories</span></div>
              <div class="summary-box"><b id="project-case-count">—</b><span>Linked test cases</span></div>
            </div>
            <div class="card" style="background:var(--panel2);margin-bottom:16px">
              <h3 style="margin:0;font-size:14px">Connect repository</h3>
              <div class="sub">Add code to monitor pull requests, analyze changes, and map coverage. Repositories are connected via this project's own GitHub/GitLab PAT.</div>
              <div style="display:flex;gap:12px;align-items:center;margin:4px 0 14px;flex-wrap:wrap">
                <label style="margin:0;font-size:12px;color:var(--muted)">Git provider for this project:</label>
                <div class="cp-provider-toggle" style="margin:0">
                  <button type="button" data-pd-provider="github" class="cp-prov active">GitHub</button>
                  <button type="button" data-pd-provider="gitlab" class="cp-prov">GitLab</button>
                </div>
                <span class="muted" id="pd-pat-status" style="font-size:11px"></span>
              </div>
              <div class="row" style="margin-bottom:10px">
                <div style="flex:2"><label>Project PAT <span class="muted" style="font-weight:400">(saved encrypted; leave blank to keep current)</span></label><input id="pd-pat" type="password" placeholder="ghp_..."/></div>
                <div style="flex:0 0 auto;align-self:flex-end;display:flex;gap:8px;padding-bottom:0">
                  <button class="ghost" id="pd-pat-save" type="button">Save PAT</button>
                  <button class="ghost" id="pd-pat-clear" type="button">Clear</button>
                </div>
              </div>
              <div style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
                <div style="flex:2;min-width:220px"><label>Repository URL or Owner/Name</label><input id="repo-url" placeholder="https://github.com/org/backend-api" list="myrepos"/><datalist id="myrepos"></datalist></div>
                <div style="width:115px"><label>Type</label><select id="repo-type"><option value="app">App (with webhook)</option><option value="test">Test (no webhook)</option></select></div>
                <div style="width:135px"><label>Kind</label><select id="repo-kind"><option value="BE">Backend</option><option value="FE">Frontend</option><option value="infra">Infrastructure</option><option value="other">Other</option></select></div>
                <button class="go" id="repo-add">Connect</button>
              </div>
              <button class="ghost" id="repo-pick" style="margin-top:10px">Load my repositories</button>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px"><h3 style="margin:0;font-size:14px">Repositories</h3><div class="muted" id="sync-status"></div></div>
            <div id="repo-list" style="display:flex;flex-direction:column;gap:8px"></div>
          </div>
        </div>
      </section>

      <!-- FEATURES -->
      <section id="view-features" class="view" hidden>
        <div id="feature-list-page" class="stage-page">
          <div class="page-toolbar">
            <div><button class="ghost" id="features-back-project" style="margin-bottom:12px">Back to projects</button><h2 id="features-page-title">Features</h2><div class="sub" id="features-project-context"></div></div>
            <button class="go" id="feature-new-btn">+ New feature</button>
          </div>
          <div id="feat-list" class="entity-grid"></div>
        </div>

        <div id="feature-create-page" class="stage-page create-feature-form" hidden>
          <div class="stage-header"><button class="ghost" id="feature-create-back">All features</button></div>
          <div class="card"><h2>New feature</h2>
            <div class="sub">Upload requirement, design, API, or architecture docs and/or paste text. All sources are embedded for RAG; the pipeline generates business, end-to-end, API, UI-validation, and edge/reliability coverage.</div>
            <select id="f-project" hidden></select>
            <div class="feature-create-fields">
              <div><label>Feature name</label><input id="f-name" placeholder="Checkout — Apply Promo Code"/></div>
              <div><label>Ticket key (optional)</label><select id="f-key"><option value="">No Jira ticket</option></select></div><div><label>PR match tag (optional)</label><input id="f-match-key" placeholder="e.g. HOLDS"/></div>
            </div>
            <div class="feature-create-jira-status" id="f-key-status">A linked Jira ticket lets PRs auto-link by branch/title.</div>
            <label>Upload documents <span class="muted" style="font-weight:400">(PRD, HLD, LLD, architecture — PDF, DOCX, MD, TXT · you can select several)</span></label><input type="file" id="f-file" accept=".pdf,.docx,.md,.txt,.markdown" multiple/>
            <div class="muted" id="f-filelist" style="font-size:11px"></div>
            <div class="muted" style="font-size:11px;margin-top:4px">Links inside PDFs (and their sub-links) are fetched automatically — public web only.</div>
            <label>Or paste requirement text <span class="muted" style="font-weight:400">(optional)</span></label><textarea id="f-text" placeholder="Paste requirements, acceptance criteria, or extra context here…"></textarea>
            <label style="margin-top:14px">Confluence page link <span class="muted" style="font-weight:400">(optional · one URL per line · uses your Jira/Atlassian token; child pages included)</span></label>
            <textarea id="f-confluence" rows="2" placeholder="https://your-org.atlassian.net/wiki/spaces/…/pages/123456/…&#10;https://your-org.atlassian.net/wiki/spaces/…/pages/789012/…"></textarea>
            <label style="margin-top:10px">Figma design link <span class="muted" style="font-weight:400">(optional · one URL per line · needs a Figma token in Configuration)</span></label>
            <textarea id="f-figma" rows="2" placeholder="https://www.figma.com/file/&lt;key&gt;/…&#10;https://www.figma.com/design/&lt;key&gt;/…"></textarea>
            <label style="margin-top:14px">Import test sheet <span class="muted" style="font-weight:400">(optional · CSV / XLSX)</span></label>
            <input type="file" id="f-sheet" accept=".csv,.xlsx,.xlsm,.tsv"/>
            <div class="muted" style="font-size:11px;margin-top:4px">Already keep test cases in a spreadsheet? Attach it — wardenIQ scores every row against this feature, promotes matches into the generated suite, and keeps the rest in your project library for other features to reuse. <a href="#" id="f-sheet-template">Download template</a></div>
            <label style="margin-top:10px">Test type mix <span class="muted" style="font-weight:400">— how much emphasis each category gets (not a fixed count)</span></label>
            <div id="focus-ctrl" class="focus-panel">
              <div class="focus-row"><span>Functional</span><input class="focus-range" type="range" min="0" max="100" value="25" id="foc-functional"/><b class="focus-value" id="foc-functional-v">25%</b></div>
              <div class="focus-row"><span>End-to-end</span><input class="focus-range" type="range" min="0" max="100" value="25" id="foc-e2e"/><b class="focus-value" id="foc-e2e-v">25%</b></div>
              <div class="focus-row"><span>API</span><input class="focus-range" type="range" min="0" max="100" value="25" id="foc-api"/><b class="focus-value" id="foc-api-v">25%</b></div>
              <div class="focus-row"><span>Edge &amp; reliability</span><input class="focus-range" type="range" min="0" max="100" value="25" id="foc-nfr"/><b class="focus-value" id="foc-nfr-v">25%</b></div>
              <div class="focus-total"><span>Changing one category adjusts the largest other category first.</span><span>Total <b id="foc-total">100%</b></span></div>
            </div>
            <button class="go" id="f-go" style="margin-top:12px">Generate test cases</button>
            <div class="feature-create-live">
              <div class="muted" id="f-status"></div>
              <div class="job-log" id="f-log"></div>
            </div>
          </div>
        </div>

        <div class="card stage-page" id="detail-card" hidden>
          <div class="feature-workspace-head">
            <div><button class="ghost" id="d-close" style="margin-bottom:10px">Back to features</button><h2 id="d-name">Feature</h2></div>
            <div class="workspace-actions">
              <span class="version-combo"><span class="version-chip" id="d-version-chip">Version 1</span><button class="new-version-btn" id="d-newver" title="Create new version">+</button></span>
              <select id="d-version" style="display:none"></select>
              <button class="ghost" id="d-reuse-imports" type="button" title="Reuse imported sheet tests">↺ Reuse imported</button>
              <button id="d-export" class="export-btn">Export PDF</button><button id="d-export-csv" class="export-btn" type="button">Export CSV</button>
              <button class="ghost" id="d-regen" style="display:none">Regenerate</button>
              <button class="ghost" id="d-jira" style="display:none">Sync to Jira</button>
              <button class="ghost" id="d-rename" style="display:none">Rename</button>
              <button class="danger" id="d-del" style="display:none">Delete feature</button>
            </div>
          </div>
          <div class="muted" id="d-meta"></div><div id="d-match-key" class="muted" style="margin:6px 0"></div><div id="d-coverage"></div><div id="d-overview"></div><div id="d-verinfo"></div><div id="d-genbanner"></div>
          <div class="case-bulk-toolbar" data-bulk-scope="feature">
            <div class="case-bulk-left"><span class="case-bulk-count" data-bulk-count="feature">0 selected</span></div>
            <div class="case-bulk-actions"><button class="ghost bulk-pass" onclick="bulkSetCaseResult('passed')">Pass selected</button><button class="ghost bulk-fail" onclick="bulkSetCaseResult('failed')">Fail selected</button><button class="ghost" onclick="bulkSetCaseResult('untested')">Clear status</button><button class="ghost" onclick="bulkExportSelected('pdf')">Export selected</button><button class="testcase-delete" onclick="bulkDeleteSelected()">Delete selected</button></div>
          </div>
          <div id="d-cases"></div>
          <div class="case-bulk-toolbar bulk-floating" data-bulk-scope="feature-floating">
            <div class="case-bulk-left"><span class="badge" data-bulk-count="feature-floating">0</span><span class="case-bulk-count">selected</span></div>
            <div class="case-bulk-actions"><button class="ghost" onclick="bulkExportSelected('pdf')">Export selected</button><button class="testcase-delete" onclick="bulkDeleteSelected()">Delete selected</button></div>
          </div></div>
      </section>

      <!-- TEST CASES -->
      <section id="view-cases" class="view" hidden>
        <div class="card"><div style="display:flex;justify-content:space-between;align-items:center"><h2 style="margin:0">Test cases</h2><button class="go" id="tc-new">+ New test case</button></div><div class="sub">Open a title to review its full specification. Editing is a separate action; shared-step changes are called out before saving.</div>
          <div class="case-filter-panel">
          <div class="case-filter-primary">
            <div><label>Project</label><select id="tc-proj"><option value="">All projects</option></select></div>
            <div><label>Feature</label><select id="tc-feat"><option value="">All features</option></select></div>
            <div><label>Category</label><select id="tc-type"><option value="">All categories</option><option value="functional">Business / functional</option><option value="e2e">End-to-end</option><option value="api">API</option><option value="ui">UI validations</option><option value="nfr">Edge &amp; reliability</option></select></div>
            <div><label>Search</label><input id="tc-q" placeholder="Title or ID, e.g. NEA-LOG-121…"/></div>
            <div class="filter-actions"><button class="go" id="tc-apply">Apply</button><button class="ghost" id="tc-reset">Reset</button></div>
          </div>
          <details class="case-filter-more">
            <summary>More filters</summary>
            <div class="case-filter-grid">
              <div><label>Tag</label><select id="tc-tag"><option value="">Any tag</option></select></div>
              <div><label>Status</label><select id="tc-status"><option value="active" selected>Active test cases</option><option value="deprecated">Deprecated only</option><option value="all">Active + deprecated</option></select></div>
              <div><label>Execution result</label><select id="tc-result"><option value="">Any result</option><option value="untested">Untested</option><option value="passed">Passed</option><option value="failed">Failed</option><option value="blocked">Blocked</option></select></div>
              <div><label>Reuse</label><select id="tc-lineage"><option value="">Generated + reused</option><option value="inherited">Inherited / reused only</option><option value="created">Created in selected feature</option></select></div>
            </div>
          </details>
          </div>
          <div class="filter-summary" id="tc-summary"></div>
          <div class="case-bulk-toolbar" data-bulk-scope="cases">
            <div class="case-bulk-left"><span class="case-bulk-count" data-bulk-count="cases">0 selected</span></div>
            <div class="case-bulk-actions"><button class="ghost bulk-pass" onclick="bulkSetCaseResult('passed')">Pass selected</button><button class="ghost bulk-fail" onclick="bulkSetCaseResult('failed')">Fail selected</button><button class="ghost" onclick="bulkSetCaseResult('untested')">Clear status</button><button class="ghost" onclick="bulkExportSelected('pdf')">Export selected</button><button class="testcase-delete" onclick="bulkDeleteSelected()">Delete selected</button></div>
          </div>
          <div id="tc-list" style="margin-top:12px"></div>
          <div class="case-bulk-toolbar bulk-floating" data-bulk-scope="cases-floating">
            <div class="case-bulk-left"><span class="badge" data-bulk-count="cases-floating">0</span><span class="case-bulk-count">selected</span></div>
            <div class="case-bulk-actions"><button class="ghost" onclick="bulkExportSelected('pdf')">Export selected</button><button class="testcase-delete" onclick="bulkDeleteSelected()">Delete selected</button></div>
          </div>
          <div class="pager" id="tc-pager"></div></div>
      </section>

      <!-- TEST CYCLES -->
      <section id="view-cycles" class="view" hidden>
        <div class="mindmap-shell">
          <div class="mindmap-hero">
            <div class="mindmap-toolbar">
              <div>
                <h2>Change impact analysis</h2>
                <div class="sub">Review recent implementation changes, map them to affected test cases, and turn the result into a release regression cycle. Pick any of the project's repos below to include in the analysis.</div>
                <div class="view-explainer">Answers <b>“which test cases do recent commits touch?”</b> — a change-driven view. To see whether the codebase actually implements each case, use the <b>Implementation coverage map</b>.</div>
              </div>
              <div class="mindmap-hero-actions">
                <button class="ghost mindmap-refresh-btn" id="cyc-refresh"><span class="icon">↻</span><span>Refresh</span></button>
              </div>
            </div>
            <div class="mindmap-controls">
              <div class="mindmap-control-project"><label>Project</label><select id="cyc-proj" style="height:38px"></select></div>
              <div style="flex:0 0 140px"><label>Lookback (days)</label><input id="cyc-days" type="number" value="14" min="1" max="180" style="height:38px"/></div>
              <button class="go mindmap-primary-btn" id="cyc-analyze">Analyze changes</button>
            </div>
            <label style="margin-top:8px">Repos &amp; branches <span class="muted" style="font-weight:400">— uncheck any to exclude; set a branch per repo (blank = its default)</span></label>
            <div id="cyc-repos" class="mindmap-panel" style="display:flex;flex-direction:column;gap:8px"></div>
            <button class="ghost" id="cyc-add-git" style="margin-top:8px;padding:5px 12px;align-self:flex-start">+ Add a repo from GitHub</button>
            <div class="muted" id="cyc-status" style="margin-top:8px"></div>
          </div>
          <div id="cyc-impacted"></div>
          <div class="mindmap-summary-card cycles-create-card" id="cyc-create" style="display:none">
            <div class="mindmap-summary-head">
              <h2>Create a test cycle</h2>
              <div class="mindmap-chip-row"><span class="badge">selected impacted cases</span></div>
            </div>
            <div class="sub">Pick the impacted cases you want to retest, name the cycle, and save it for execution.</div>
            <div class="row" style="margin-top:12px"><input id="cyc-name" placeholder="Cycle name (for example: Sprint 12 regression)"/>
              <button class="go" id="cyc-make" style="flex:0 0 auto">Create cycle</button></div>
          </div>
          <div class="card"><h2>Cycle templates</h2><div class="sub">Reusable case sets — save any cycle as a template, then spin up new cycles from it.</div><div id="cyc-templates"></div></div>
          <div class="card"><h2>Test cycles</h2><div class="sub">Saved release regression cycles for the selected project.</div><div id="cyc-list"></div></div>
          <div class="card" id="cyc-detail-card" style="display:none">
            <div style="display:flex;justify-content:space-between;align-items:center"><h2 id="cyc-d-name" style="margin:0">Cycle</h2>
              <div style="display:flex;gap:6px"><button class="ghost" id="cyc-d-rename">Rename</button><button class="danger" id="cyc-d-del">Delete cycle</button><button class="ghost" id="cyc-d-close">Close</button></div></div>
            <div id="cyc-d-items"></div>
          </div>
        </div>
      </section>

      <!-- MIND MAP -->
      <section id="view-mindmap" class="view" hidden>
        <div class="mindmap-shell">
        <div class="mindmap-hero">
          <div class="mindmap-toolbar">
            <div>
              <h2>Implementation coverage map</h2>
              <div class="sub">Review how much of each feature is actually implemented in code. wardenIQ reads the selected repositories, compares implementation paths against active test cases, and classifies each area as covered, partial, or uncovered.</div>
              <div class="view-explainer">Answers <b>“does the code actually build this test case?”</b> — <i>not</i> whether an automated test exists, and <i>not</i> what recent commits touched (that’s <b>Change impact analysis</b>).</div>
            </div>
            <div class="mindmap-hero-actions">
              <button class="ghost mindmap-refresh-btn" id="mm-refresh"><span class="icon">↻</span><span>Refresh</span></button>
            </div>
          </div>
          <div class="mindmap-controls">
            <div class="mindmap-control-project"><label>Project</label><select id="mm-proj"></select></div>
            <button class="go mindmap-primary-btn" id="mm-analyze">Analyze codebase</button>
          </div>
          <label style="margin-top:8px">Repos &amp; branches <span class="muted" style="font-weight:400">— uncheck any to exclude; set a branch per repo (blank = its default)</span></label>
          <div id="mm-repos" class="mindmap-panel" style="display:flex;flex-direction:column;gap:8px"></div>
          <button class="ghost" id="mm-add-git" style="margin-top:8px;padding:5px 12px;align-self:flex-start">+ Add a repo from GitHub</button>
          <div class="muted" id="mm-status" style="margin-top:8px"></div>
        </div>
        <div id="mm-diag"></div>
        <div id="mm-map"></div>
        </div>
      </section>

      <!-- STEP LIBRARY -->
      <section id="view-steps" class="view" hidden>
        <div style="display:flex;gap:18px;align-items:stretch;min-height:calc(100vh - 140px)">
          <!-- Left Main Step Management Pane -->
          <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:16px">
            <div class="card" style="margin-bottom:0">
              <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
                <div>
                  <h2 style="margin:0;display:inline-flex;align-items:center;gap:8px">Step library <span class="badge" id="s-count" style="font-size:12px;background:rgba(255,255,255,0.06);color:var(--text)"></span></h2>
                  <div class="sub" style="margin-top:4px">Shared building blocks for test cases — write a step once and reuse it everywhere instead of duplicating it. Near-duplicate steps are auto-merged, and editing a step here updates every test case that references it.</div>
                </div>
                <button class="go" id="s-new" type="button" style="margin:0">+ New step</button>
              </div>
              
              <!-- Search, Filter & Sort Bar -->
              <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap;align-items:center">
                <input type="text" id="s-search" placeholder="Search steps by action or expected result..." style="flex:1;min-width:240px;height:38px;padding:8px 12px;background:#0d1728;border:1px solid #1E2A40;border-radius:6px;color:#e2e8f0;font-size:13.5px" />
                <select id="s-filter-type" style="width:140px;height:38px;padding:0 8px;background:#0d1728;border:1px solid #1E2A40;border-radius:6px;color:#e2e8f0;font-size:13.5px">
                  <option value="">All Types</option>
                  <option value="Given">Given</option>
                  <option value="When">When</option>
                  <option value="Then">Then</option>
                  <option value="And">And/But</option>
                  <option value="Other">Other / Action</option>
                </select>
                <select id="s-filter-usage" style="width:140px;height:38px;padding:0 8px;background:#0d1728;border:1px solid #1E2A40;border-radius:6px;color:#e2e8f0;font-size:13.5px">
                  <option value="">All Usages</option>
                  <option value="used">Used steps</option>
                  <option value="unused">Unused steps</option>
                </select>
              </div>
            </div>

            <!-- Steps list card -->
            <div class="card" style="flex:1;padding:0;overflow:hidden;border:1px solid #1E2A40;background:#07111f;border-radius:10px;display:flex;flex-direction:column">
              <div style="flex:1;overflow-y:auto;max-height:650px">
                <div id="s-list-body"><!-- Loaded dynamically --></div>
              </div>
            </div>
          </div>

          <!-- Right Collapsible Detail/Usage Drawer (1/3 width) -->
          <div id="s-detail-pane" style="width:360px;display:none;flex-direction:column;gap:16px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px">
            <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #1E2A40;padding-bottom:12px">
              <h3 style="margin:0;font-size:14px;color:#e2e8f0">Step Detail</h3>
              <button class="ghost" id="s-detail-close" type="button" style="padding:2px 6px">Close</button>
            </div>
            
            <div style="display:flex;flex-direction:column;gap:14px">
              <div>
                <span class="muted" style="font-size:10px;text-transform:uppercase;letter-spacing:0.05em">Type</span>
                <div id="s-detail-type" style="margin-top:4px"></div>
              </div>
              <div>
                <span class="muted" style="font-size:10px;text-transform:uppercase;letter-spacing:0.05em">Action / Description</span>
                <div id="s-detail-action" style="margin-top:4px;font-size:13.5px;color:#e2e8f0;font-weight:500;line-height:1.4;word-break:break-word"></div>
              </div>
              <div>
                <span class="muted" style="font-size:10px;text-transform:uppercase;letter-spacing:0.05em">Expected Result</span>
                <div id="s-detail-expected" style="margin-top:4px;font-size:13px;color:#cbd5e1;line-height:1.4;word-break:break-word"></div>
              </div>
              <div style="border-top:1px solid #1E2A40;padding-top:12px">
                <span id="s-detail-cases-title" style="font-size:11.5px;font-weight:600;color:#94a3b8;display:flex;align-items:center;gap:6px">Used in Cases (0)</span>
                <div id="s-detail-cases-list" style="margin-top:8px;max-height:300px;overflow-y:auto;display:flex;flex-direction:column;gap:6px">
                  <!-- Mapped cases loaded dynamically -->
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- LLM USAGE & COST -->
      <section id="view-usage" class="view" hidden>
        <div class="mindmap-shell">
          <div class="mindmap-hero usage-hero">
            <div class="mindmap-toolbar">
              <div>
                <h2>LLM usage &amp; cost</h2>
                <div class="sub">Monitor and control AI spend. Every process — test-case generation, PR coverage, commit &amp; Mind-Map analysis, and ingestion — reports the tokens it consumed and which model it used. This dashboard rolls that up into total tokens, spend by model, spend by project, and a per-process breakdown so you can see exactly where cost comes from.</div>
              </div>
              <div class="mindmap-hero-actions">
                <button class="ghost mindmap-refresh-btn" id="usage-refresh"><span class="icon">↻</span><span>Refresh</span></button>
              </div>
            </div>
            <div id="usage-totals" class="usage-stats"></div>
            <div class="usage-formula">Cost = (input tokens ÷ 1,000,000 × input price) + (output tokens ÷ 1,000,000 × output price), per model, summed per process. Prices use built-in per-model defaults; local Ollama models are free.</div>
          </div>

          <div class="card">
            <h3 style="margin:0 0 8px;font-size:14px">Recent processes</h3>
            <input id="usage-recent-search" class="usage-search" placeholder="Search process, project, or feature…"/>
            <div id="usage-recent"></div>
          </div>

          <details class="card usage-collapse" open>
            <summary><span class="usage-collapse-title">By model</span><span class="usage-collapse-hint muted">tokens &amp; cost per model</span></summary>
            <div class="usage-filter-row"><label class="muted">Model</label>
              <select id="usage-model-filter" class="usage-select"><option value="">All models</option></select></div>
            <div id="usage-by-model"></div>
          </details>

          <details class="card usage-collapse">
            <summary><span class="usage-collapse-title">By project</span><span class="usage-collapse-hint muted">tokens &amp; cost per project</span></summary>
            <div class="usage-filter-row"><label class="muted">Project</label>
              <select id="usage-project-filter" class="usage-select"><option value="">All projects</option></select></div>
            <div id="usage-by-project"></div>
          </details>
        </div>
      </section>

      <!-- CONFIGURATION -->
      <section id="view-config" class="view" hidden>
        <div class="cfg-grid">
          <div class="card cfg-card">
            <div class="cfg-head"><div class="cfg-head-left"><span class="cfg-step">1</span><h2>LLM</h2></div><span class="cfg-badge req">Required</span></div>
            <div class="sub"><b>Ollama (built-in)</b> runs the AI inside this Docker stack — free, private, no API key, nothing to install (this is the default). Or pick a hosted provider — OpenAI, Anthropic (Claude), Google Gemini, Mistral, or any OpenAI-compatible endpoint — with your own API key. Or <b>AWS Bedrock</b> for enterprise / air-gapped deployments. Every provider uses the same fields below — just fill the ones it needs (hover each <b>i</b> for guidance). Used for all generation, code review, coverage, and impact analysis.</div>
            <div class="cfg-field">
              <label>Provider <span class="fi" tabindex="0" data-tip="Ollama — free local AI (open-source, no key). OpenAI / Anthropic / Gemini / Mistral / Groq — hosted APIs (need an API key). AWS Bedrock — enterprise / air-gapped: uses an AWS region plus an IAM role or access keys.">i</span></label>
              <select id="cfg-llm-provider"><option value="ollama">Ollama (built-in)</option><option value="groq">Groq (fast · free tier)</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic (Claude)</option><option value="gemini">Google Gemini</option><option value="mistral">Mistral</option><option value="openai-compatible">OpenAI-compatible (custom)</option><option value="bedrock">AWS Bedrock (enterprise)</option></select>
            </div>
            <div class="cfg-field">
              <label>Model <span class="fi" tabindex="0" data-tip="The model identifier. Ollama: qwen2.5:7b. OpenAI: gpt-4o. Anthropic: claude-sonnet-4-6. AWS Bedrock: the full model ID or inference-profile ARN, e.g. anthropic.claude-3-5-sonnet-20241022-v2:0.">i</span></label>
              <select id="cfg-llm-model-select"></select>
              <input id="cfg-llm-model" placeholder="Enter model name / Bedrock model ID..." style="display:none;margin-top:6px"/>
            </div>
            <div class="cfg-field" id="cfg-llm-endpoint-field">
              <label>Endpoint URL <span class="muted" style="font-weight:400">(optional)</span> <span class="fi" tabindex="0" data-tip="Leave blank for the provider default. Ollama: where Ollama runs (bundled Docker, your computer, or a remote host). OpenAI-compatible: your custom base URL. AWS Bedrock: an optional private VPC / PrivateLink endpoint for air-gapped networks.">i</span></label>
              <input id="cfg-llm-endpoint" placeholder="leave blank for the provider default"/>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px" id="cfg-ollama-presets">
                <button type="button" class="ghost" id="cfg-ollama-native" style="font-size:11.5px;padding:5px 10px">Use Ollama on my computer</button>
                <button type="button" class="ghost" id="cfg-ollama-bundled" style="font-size:11.5px;padding:5px 10px">Use bundled (Docker) Ollama</button>
              </div>
              <div class="muted" id="cfg-ollama-hint" style="font-size:11px;margin-top:6px"></div>
            </div>
            <div class="cfg-field" id="cfg-llm-region-field">
              <label>AWS region <span class="muted" style="font-weight:400">(AWS Bedrock only)</span> <span class="fi" tabindex="0" data-tip="AWS Bedrock only. The AWS region your Bedrock models are enabled in, e.g. us-east-1. Leave blank for every other provider.">i</span></label>
              <input id="cfg-llm-region" placeholder="e.g. us-east-1"/>
            </div>
            <div class="cfg-field">
              <label>API key / secret <span class="fi" tabindex="0" data-tip="Ollama: usually blank (only for a secured/remote Ollama behind a token). Hosted providers: your API key. AWS Bedrock: leave blank to use the machine's IAM role (recommended for air-gapped), or enter accessKeyId:secretAccessKey.">i</span></label>
              <input type="password" id="cfg-llm-key" placeholder="leave blank to keep current"/>
            </div>
            <div class="cfg-status muted" id="cfg-llm-status"></div>
            <div class="cfg-actions">
              <button class="go" id="cfg-llm-save">Save</button>
            </div>
          </div>

          <div class="card cfg-card">
            <div class="cfg-head"><div class="cfg-head-left"><span class="cfg-step">2</span><h2>Embedding model</h2></div><span class="cfg-badge glob">Global</span></div>
            <div class="sub">Controls how documents and test cases are vectorised for search, dedup, and Mind-Map retrieval.</div>
            <div class="warn" style="margin-top:8px">
              <b>⚠ Switching affects the whole system — read before changing:</b>
              <ul style="margin:6px 0 0;padding-left:18px;line-height:1.6">
                <li>This is a <b>global, one-time migration</b> — it re-embeds <b>every project's</b> vectors (features, documents, test steps &amp; cases) and rebuilds the search indexes at the new model's dimension.</li>
                <li><b>Search, dedup and Mind-Map are degraded until it finishes</b> — run it when the system is idle.</li>
                <li>Time and token cost scale with your total corpus size; hosted models spend tokens on the new provider (see Usage &amp; Cost).</li>
                <li>Your test cases, steps, documents and coverage are <b>not changed</b> — only their numeric embedding vectors are recomputed.</li>
                <li>Pick once at setup if you can; avoid switching repeatedly.</li>
              </ul>
            </div>
            <div class="cfg-field">
              <label>Provider <span class="fi" tabindex="0" data-tip="Ollama — free local embeddings (no key). OpenAI / Gemini / Voyage — hosted (need an API key). AWS Bedrock — Titan or Cohere embeddings; uses an AWS region plus an IAM role or access keys.">i</span></label>
              <select id="cfg-embed-provider"><option value="ollama">Ollama (built-in)</option><option value="openai">OpenAI</option><option value="gemini">Google Gemini</option><option value="voyage">Voyage AI</option><option value="openai-compatible">OpenAI-compatible (custom)</option><option value="bedrock">AWS Bedrock (enterprise)</option></select>
            </div>
            <div class="cfg-field">
              <label>Model <span class="fi" tabindex="0" data-tip="The embedding model. Ollama: nomic-embed-text. OpenAI: text-embedding-3-small. AWS Bedrock: amazon.titan-embed-text-v2:0 or cohere.embed-english-v3.">i</span></label>
              <select id="cfg-embed-model-select"></select>
              <input id="cfg-embed-model" placeholder="Enter model name / Bedrock model ID..." style="display:none;margin-top:6px"/>
            </div>
            <div class="cfg-field" id="cfg-embed-region-field">
              <label>AWS region <span class="muted" style="font-weight:400">(AWS Bedrock only)</span> <span class="fi" tabindex="0" data-tip="AWS Bedrock only. The AWS region your Bedrock embedding model is enabled in, e.g. us-east-1. Leave blank for every other provider.">i</span></label>
              <input id="cfg-embed-region" placeholder="e.g. us-east-1"/>
            </div>
            <div class="cfg-field">
              <label>API key / secret <span class="fi" tabindex="0" data-tip="Hosted providers: your API key. AWS Bedrock: leave blank to use the machine's IAM role, or enter accessKeyId:secretAccessKey. Ollama: leave blank.">i</span></label>
              <input type="password" id="cfg-embed-key" placeholder="leave blank to keep current"/>
            </div>
            <div class="cfg-field">
              <label>Endpoint URL <span class="muted" style="font-weight:400">(optional)</span> <span class="fi" tabindex="0" data-tip="Leave blank for the provider default. OpenAI-compatible: your custom base URL. AWS Bedrock: an optional private VPC / PrivateLink endpoint for air-gapped networks.">i</span></label>
              <input id="cfg-embed-base" placeholder="leave blank for the provider default"/>
            </div>
            <div class="cfg-status muted" id="cfg-embed-status"></div>
            <div id="cfg-embed-log" class="cfg-log" style="display:none;white-space:pre-wrap;font-family:monospace;font-size:11px;margin-top:8px;max-height:160px;overflow:auto"></div>
            <div class="cfg-actions"><button class="go" id="cfg-embed-save">Switch &amp; re-embed</button></div>
          </div>

          <div class="card cfg-card">
            <div class="cfg-head"><div class="cfg-head-left"><span class="cfg-step">3</span><h2>Jira &amp; Confluence (Atlassian Cloud)</h2></div><span class="cfg-badge opt">Optional</span></div>
            <div class="sub">One Atlassian account for the whole workspace. wardenIQ uses it to read issues, list Jira projects/Confluence spaces when you create a project, and write coverage updates as comments. Create an API token at <code>id.atlassian.com → Security → API tokens</code>.</div>
            <div class="cfg-field">
              <label>Base URL <span class="fi" tabindex="0" data-tip="Your Atlassian Cloud site URL, e.g. https://your-org.atlassian.net (no trailing path).">i</span></label>
              <input id="cfg-jira-base" placeholder="https://your-org.atlassian.net"/>
            </div>
            <div class="cfg-field">
              <label>Email <span class="fi" tabindex="0" data-tip="The Atlassian account email that owns the API token below. Used with the token for Basic auth.">i</span></label>
              <input id="cfg-jira-email" placeholder="you@org.com"/>
            </div>
            <div class="cfg-field">
              <label>API token <span class="fi" tabindex="0" data-tip="An Atlassian API token (not your password). Create one at id.atlassian.com → Security → API tokens. Stored encrypted; leave blank to keep the current one.">i</span></label>
              <input type="password" id="cfg-jira-token" placeholder="leave blank to keep current"/>
            </div>
            <div class="cfg-status muted" id="cfg-jira-status"></div>
            <div class="cfg-actions">
              <button class="go" id="cfg-jira-save">Save</button>
            </div>
            <div class="muted" style="font-size:11px;margin-top:10px">Webhook: <code>/api/integrations/jira/webhook?token=&lt;WEBHOOK_SECRET&gt;</code> auto-creates features from new issues.</div>
          </div>

          <div class="card cfg-card">
            <div class="cfg-head"><div class="cfg-head-left"><span class="cfg-step">4</span><h2>Figma</h2></div><span class="cfg-badge opt">Optional</span></div>
            <div class="sub">A Figma <b>personal access token</b> lets features extract design screens &amp; text from a Figma link (Figma's API requires a token). <a href="https://www.figma.com/developers/api#access-tokens" target="_blank" rel="noopener noreferrer">Create one</a>. Stored encrypted.</div>
            <div class="cfg-field"><label>Access token <span class="fi" tabindex="0" data-tip="A Figma personal access token (figma.com → Settings → Personal access tokens). Lets features pull screens and text from a Figma link. Stored encrypted; leave blank to keep the current one.">i</span></label><input type="password" id="cfg-figma-token" placeholder="leave blank to keep current"/></div>
            <div class="cfg-status muted" id="cfg-figma-status"></div>
            <div class="cfg-actions"><button class="go" id="cfg-figma-save">Save</button></div>
          </div>

          <div class="card cfg-card cfg-card-wide">
            <div class="cfg-head"><div class="cfg-head-left"><span class="cfg-step">5</span><h2>Email (SMTP)</h2></div><span class="cfg-badge opt">Optional</span></div>
            <div class="sub">Used to deliver sign-in codes. Until this is configured, the first admin's one-time code is printed to the server log (e.g. <code>docker logs wardeniq</code>) so you can sign in and set it up here. Password stored encrypted.</div>
            <div class="sub" style="margin-top:-2px"><b>Gmail:</b> host <code>smtp.gmail.com</code>, port <code>587</code> (STARTTLS) <i>or</i> <code>465</code> (SSL), username = your full Gmail address, password = a 16-character <b>App Password</b> (needs 2-Step Verification; spaces are optional). Save first, then use <b>Send test email</b> to confirm.</div>
            <div class="cfg-row">
              <div class="cfg-field" style="flex:2"><label>SMTP host <span class="fi" tabindex="0" data-tip="Your mail server's hostname, e.g. smtp.gmail.com or smtp.sendgrid.net. Until SMTP is set, the first admin's sign-in code is printed to the server log.">i</span></label><input id="cfg-smtp-host" placeholder="smtp.example.com"/></div>
              <div class="cfg-field" style="flex:0 0 130px"><label>Port <span class="fi" tabindex="0" data-tip="587 for STARTTLS (most common) or 465 for SSL. Match the checkbox on the right.">i</span></label><input id="cfg-smtp-port" type="number" placeholder="587"/></div>
            </div>
            <div class="cfg-row">
              <div class="cfg-field"><label>Username <span class="fi" tabindex="0" data-tip="The SMTP login. For Gmail use your full address; for SendGrid it is literally the word 'apikey'. Some relays allow blank.">i</span></label><input id="cfg-smtp-user" placeholder="apikey / user (optional)"/></div>
              <div class="cfg-field"><label>Password <span class="fi" tabindex="0" data-tip="The SMTP password or app password. Gmail needs a 16-character App Password (2-Step Verification on). Stored encrypted; leave blank to keep the current one.">i</span></label><input type="password" id="cfg-smtp-pass" placeholder="leave blank to keep current"/></div>
            </div>
            <div class="cfg-row">
              <div class="cfg-field" style="flex:2"><label>From address <span class="fi" tabindex="0" data-tip="The sender shown on sign-in emails, e.g. wardenIQ &lt;no-reply@example.com&gt;. Must be a sender your SMTP account is allowed to send as.">i</span></label><input id="cfg-smtp-from" placeholder="wardenIQ &lt;no-reply@example.com&gt;"/></div>
              <div class="cfg-field" style="flex:0 0 auto;align-self:flex-end">
                <label style="visibility:hidden">_</label>
                <div style="display:flex;gap:14px;align-items:center;padding:8px 0">
                  <label style="display:flex;gap:5px;align-items:center;font-size:12px;margin:0;color:var(--muted)"><input type="checkbox" id="cfg-smtp-tls" style="width:auto"/> STARTTLS</label>
                  <label style="display:flex;gap:5px;align-items:center;font-size:12px;margin:0;color:var(--muted)"><input type="checkbox" id="cfg-smtp-ssl" style="width:auto"/> SSL</label>
                  <span class="fi" tabindex="0" data-tip="STARTTLS = upgrade a plaintext connection to TLS (port 587). SSL = TLS from the start (port 465). Pick the one matching your port; don't enable both.">i</span>
                </div>
              </div>
            </div>
            <div class="cfg-status muted" id="cfg-smtp-status"></div>
            <div class="cfg-actions">
              <button class="go" id="cfg-smtp-save">Save</button>
              <button class="ghost" id="cfg-smtp-test">Send test email</button>
            </div>
          </div>

          <div class="card cfg-card">
            <div class="cfg-head"><div class="cfg-head-left"><span class="cfg-step">6</span><h2>Database</h2></div><span class="cfg-badge glob">Global</span></div>
            <div class="sub">Connect wardenIQ to a search-capable MongoDB (Atlas, or self-managed with mongot). Enter the connection string below. It is saved to <code>.env</code> and never shown again.</div>
            <div id="cfg-db-body" class="db-panel"><span class="muted">Loading database status…</span></div>
            <div id="cfg-db-switch" style="margin-top:16px;border-top:1px solid rgba(255,255,255,.06);padding-top:14px;display:none">
              <div class="muted" style="font-size:12px;line-height:1.55;margin-bottom:12px">
                Enter the database you'd like to use. wardenIQ copies your data into it and switches over — your current database is left untouched until you restart, so nothing is lost.
              </div>
              <div class="cfg-field">
                <label>Database connection string <span class="fi" tabindex="0" data-tip="A search-capable MongoDB URI (Atlas mongodb+srv://… or a self-managed replica set with mongot). wardenIQ copies your data into it and switches over. Saved to .env, encrypted, and never shown again.">i</span></label>
                <input type="password" id="cfg-db-uri" placeholder="mongodb+srv://user:pass@cluster…" autocomplete="off"/>
              </div>
              <div class="cfg-status muted" id="cfg-db-status"></div>
              <div class="cfg-actions" style="border:none;padding:0;margin:0"><button class="go" id="cfg-db-switch-go">Switch to this database</button></div>
            </div>

            <div class="cfg-actions"><button class="ghost" id="cfg-db-refresh">Refresh</button></div>
          </div>
        </div>
      </section>

      <!-- USERS -->
      <section id="view-users" class="view" hidden>
        <div class="card"><h2>Invite a user</h2><div class="sub">New users sign in passwordlessly with an emailed one-time code. <b>Viewer</b> = read-only, <b>Editor</b> = create/edit/generate, <b>Admin</b> = also manage users &amp; configuration.</div>
          <div class="row" style="align-items:flex-end">
            <div style="flex:2"><label>Email</label><input id="u-email" type="email" placeholder="teammate@company.com"/></div>
            <div><label>Name</label><input id="u-name" placeholder="optional"/></div>
            <div style="flex:0 0 140px"><label>Role</label><select id="u-role"><option value="viewer">Viewer</option><option value="editor">Editor</option><option value="admin">Admin</option></select></div>
            <button class="go" id="u-invite" style="margin:0">Invite</button>
          </div>
          <div class="proj-access" id="u-proj-access" style="margin-top:14px">
            <label style="display:block;margin-bottom:6px">Project access</label>
            <div class="proj-access-toggle">
              <label class="radio-inline"><input type="radio" name="u-scope" value="all" checked/> All projects</label>
              <label class="radio-inline"><input type="radio" name="u-scope" value="some"/> Specific projects</label>
            </div>
            <div id="u-proj-list" class="proj-checklist" hidden></div>
            <div class="muted" id="u-proj-hint" style="font-size:11.5px;margin-top:4px">Admins always have access to all projects.</div>
          </div>
          <div class="muted" id="u-msg" style="margin-top:8px"></div>
        </div>
        <div class="card"><h2>Users</h2>
          <div class="u-filters" id="u-filters">
            <input id="u-search" type="search" placeholder="Search name or email…" style="flex:1;min-width:180px"/>
            <select id="u-filter-status" style="width:auto"><option value="">All statuses</option><option value="active">Active</option><option value="disabled">Disabled</option><option value="pending">Invite pending</option></select>
            <select id="u-filter-role" style="width:auto"><option value="">All roles</option><option value="admin">Admin</option><option value="editor">Editor</option><option value="viewer">Viewer</option></select>
            <span class="muted" id="u-count" style="font-size:12px;margin-left:auto"></span>
          </div>
          <div id="u-list"></div></div>
        <div class="card"><h2>Audit log</h2>
          <div class="sub">Recent security-relevant actions (invites, role changes, deletes, settings, denied access).</div>
          <div id="audit-list"><span class="muted">Loading…</span></div>
        </div>
      </section>

      <!-- MCQ VALIDATOR -->
      <section id="view-validator" class="view" hidden>
        <div style="display:flex;gap:8px;margin-bottom:12px"><button class="ghost feature-workspace-back">Feature workspace</button><button class="ghost feature-workspace-cases">Test Cases</button></div>
        <div class="card" id="val-no-feature">
          <h2>MCQ Validator</h2>
          <div class="muted">Please select a feature first to run the requirements validator.</div>
        </div>
        <div class="card" id="val-workspace" style="display:none">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h2 id="val-feat-title">MCQ Validator</h2>
            <div style="display:flex;gap:6px">
              <button class="go" id="val-generate-btn">Generate Validator</button>
              <button class="ghost" id="val-retake-btn">↻ Retake Validator</button>
            </div>
          </div>
          <div class="sub">Resolve requirement ambiguity, validate business intent, and detect gaps before QA begins.</div>
          <div id="val-progress" class="progress" style="display:none"><div class="pbar" id="val-bar"></div></div>
          <div class="job-log" id="val-log"></div>
          <div id="val-status" class="muted" style="margin-bottom:12px"></div>
          
          <div id="val-qa-container"></div>
          
          <div id="val-results" style="display:none">
            <div class="kpis" style="margin-bottom:20px">
              <div class="kpi"><div class="v accent" id="val-score">-</div><div class="l">Clarity Score</div></div>
              <div class="kpi"><div class="v" id="val-rating">-</div><div class="l">Rating</div></div>
              <div class="kpi"><div class="v" id="val-weak-count">-</div><div class="l">Weak Categories</div></div>
            </div>
            
            <h3 style="margin-top:20px;font-size:14px;color:var(--accent);border-bottom:1px solid var(--line);padding-bottom:6px">Weak Requirement Areas</h3>
            <div id="val-weak-list" class="muted" style="margin:10px 0"></div>
            
            <h3 style="margin-top:20px;font-size:14px;color:var(--accent);border-bottom:1px solid var(--line);padding-bottom:6px">Detailed Question Results</h3>
            <div id="val-details-list" style="margin-top:10px"></div>
          </div>
        </div>
      </section>

      <!-- TEST PLAN -->
      <section id="view-testplan" class="view" hidden>
        <div style="display:flex;gap:8px;margin-bottom:12px"><button class="ghost feature-workspace-back">Feature workspace</button><button class="ghost feature-workspace-cases">Test Cases</button></div>
        <div class="card" id="tp-no-feature">
          <h2>Test Plan</h2>
          <div class="muted">Please select a feature first to generate a test plan.</div>
        </div>
        <div class="card" id="tp-workspace" style="display:none">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <h2 id="tp-feat-title">Test Plan</h2>
            <div style="display:flex;gap:6px">
              <button class="go" id="tp-generate-btn">Generate Test Plan</button>
              <a class="ghost" id="tp-export-csv" style="display:none;text-decoration:none">Export CSV</a>
              <a class="ghost" id="tp-export-pdf" style="display:none;text-decoration:none">Export PDF</a>
            </div>
          </div>
          <div class="sub">Comprehensive feature-specific QA test plan, generated dynamically from requirements.</div>
          
          <div id="tp-progress" class="progress" style="display:none"><div class="pbar" id="tp-bar"></div></div>
          <div id="tp-status" class="muted" style="margin-bottom:12px"></div>
          
          <div id="tp-content" class="muted" style="margin-top:15px;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:16px;overflow-y:auto;max-height:600px;font-family:monospace;white-space:pre-wrap;line-height:1.6;color:var(--text)"></div>
        </div>
      </section>

      <!-- GAP ANALYSIS -->
      <section id="view-gap" class="view" hidden>
        <div style="display:flex;gap:8px;margin-bottom:12px">
          <button class="ghost feature-workspace-back">Feature workspace</button>
          <button class="ghost feature-workspace-cases">Test Cases</button>
        </div>
        <div class="card" id="gap-no-feature">
          <h2>Gap Analysis</h2>
          <div class="muted">Please select a feature first to view gap analysis.</div>
        </div>
        <div id="gap-workspace" style="display:none">
          <div class="card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding:14px 18px">
            <h2 id="gap-feat-title" style="margin:0;font-size:15px">Gap Analysis</h2>
            <div class="cp-provider-toggle" style="margin:0">
              <button type="button" class="cp-prov active" data-gap-tab="pr">PR Code Coverage</button>
              <button type="button" class="cp-prov" data-gap-tab="auto">Automation Test Coverage</button>
            </div>
          </div>

          <!-- PR Code Coverage tab -->
          <div id="gap-tab-pr">
            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
                <h3 style="margin:0;font-size:14px">PR Coverage runs <span id="gap-pr-live" style="margin-left:6px;font-weight:400"></span></h3>
                <div style="display:flex;gap:8px;align-items:center">
                  <button class="ghost" id="gap-pr-export-csv" type="button" title="Export PR coverage as CSV">Export CSV</button><button class="ghost" id="gap-pr-export-pdf" type="button" title="Export PR coverage as PDF">Export PDF</button><button class="ghost" id="gap-pr-refresh" type="button">Refresh</button>
                  <button class="go" id="gap-pr-manual" type="button">+ Run on a PR</button>
                </div>
              </div>
              <div class="sub" style="margin:6px 0 12px">Webhooks register on App repos at project setup. Each PR open/sync/reopen creates a run. You can also trigger a one-off run by PR number below.</div>
              <div id="gap-pr-list" class="muted">No runs yet — connect a repo on this project and open a PR (or click <b>+ Run on a PR</b>).</div>
            </div>
            <div class="card" id="gap-pr-detail" style="display:none">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
                <h3 style="margin:0;font-size:14px" id="gap-pr-detail-title">Run detail</h3>
                <button class="ghost" id="gap-pr-detail-close" type="button">Close</button>
              </div>
              <div id="gap-pr-detail-body"></div>
            </div>
          </div>

          <!-- Automation Coverage tab -->
          <div id="gap-tab-auto" style="display:none">
            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
                <h3 style="margin:0;font-size:14px">Automation Test Coverage</h3>
                <div style="display:flex;gap:8px;align-items:center">
                  <span class="muted" id="gap-auto-summary" style="font-size:12px"></span>
                  <button class="ghost" id="gap-auto-export-csv" type="button" title="Export automation coverage as CSV">Export CSV</button><button class="ghost" id="gap-auto-export-pdf" type="button" title="Export automation coverage as PDF">Export PDF</button><button class="ghost" id="gap-auto-refresh" type="button">Refresh</button>
                </div>
              </div>
              <div class="sub" style="margin:6px 0 12px">For each generated test case, wardenIQ finds the best-matching test in your connected <b>Test</b> repos (Playwright, Cypress, Cucumber, Jest, Pytest, Markdown, JSON, etc.) using a Jaccard prefilter + LLM verifier. Covered tests link to the exact file at the scanned commit.</div>
              <div id="gap-auto-repos" style="display:flex;flex-direction:column;gap:8px;margin-bottom:14px"></div>
              <div id="gap-auto-stats" style="display:none">
                <div class="kpis" style="margin-bottom:14px">
                  <div class="kpi"><div class="v accent" id="gap-auto-pct">—</div><div class="l">Automation Test Coverage</div></div>
                  <div class="kpi"><div class="v" id="gap-auto-covered">—</div><div class="l">Covered</div></div>
                  <div class="kpi"><div class="v" id="gap-auto-missing">—</div><div class="l">Missing</div></div>
                  <div class="kpi"><div class="v" id="gap-auto-total">—</div><div class="l">Generated cases</div></div>
                </div>
                <div id="gap-auto-items"></div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</div>

<!-- CASE EDITOR MODAL -->
<div class="modal" id="modal"><div class="box editor-box">
  <div class="editor-head"><div><h2 id="m-heading" style="margin:0;font-size:17px">Edit test case</h2><div class="muted" style="margin-top:3px">Keep the action and its expected result together. Drag rows to reorder them.</div></div><button class="ghost" id="m-close">close</button></div>
  <div class="editor-body">
    <label>Title</label><input id="m-title"/>
    <div class="editor-grid"><div><label>Category</label><select id="m-type"><option value="functional">Business / functional</option><option value="e2e">End-to-end</option><option value="api">API</option><option value="ui">UI validation</option><option value="nfr">Edge &amp; reliability</option></select></div>
      <div><label>Priority</label><select id="m-prio"><option>High</option><option>Medium</option><option>Low</option></select></div></div>
    <div class="editor-grid"><div><label>Preconditions</label><input id="m-pre"/></div><div><label>Tags (comma separated)</label><input id="m-tags"/></div></div>
    <label>Steps</label>
    <div class="editor-steps"><div class="editor-step-head"><span></span><span>Action</span><span>Expected result</span><span></span></div><div id="m-steps"></div></div>
    <button class="ghost" id="m-addstep" style="margin-top:9px">+ Add step</button>
    <div id="m-warn" class="muted" style="margin-top:9px"></div>
    <div id="m-msg" class="muted" style="margin-top:8px"></div>
  </div>
  <div class="editor-foot"><button class="danger" id="m-del" style="margin-right:auto;display:none">Delete testcase</button><button class="ghost" id="m-cancel">Cancel</button><button class="go" id="m-save">Review changes</button></div>
</div></div>

<div class="modal" id="case-confirm"><div class="box confirm-box">
  <h2 id="cc-title" style="margin:0;font-size:17px">Confirm testcase update</h2>
  <div id="cc-copy" class="muted" style="margin-top:5px"></div>
  <div id="cc-summary" class="confirm-summary"></div>
  <div id="cc-error" class="err"></div>
  <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px"><button class="danger" id="cc-secondary" style="display:none;margin-right:auto"></button><button class="ghost" id="cc-cancel">Cancel</button><button class="go" id="cc-confirm">Update testcase</button></div>
</div></div>

<!-- GENERIC CONFIRM MODAL (replaces native window.confirm) -->
<div class="modal" id="confirm-modal"><div class="box confirm-box" style="max-width:460px">
  <h2 id="confirm-title" style="margin:0;font-size:17px">Please confirm</h2>
  <div id="confirm-body" class="muted" style="margin-top:8px;line-height:1.5;white-space:pre-wrap"></div>
  <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:18px"><button class="ghost" id="confirm-cancel">Cancel</button><button class="go" id="confirm-ok">Continue</button></div>
</div></div>

<!-- CHANGE PASSWORD MODAL (local admin account only). In mandatory mode (first
     sign-in on the default password) the Cancel/close controls are hidden by JS
     and the modal can't be dismissed until a new password is saved. -->
<div class="modal" id="pwd-modal"><div class="box" style="max-width:420px">
  <div class="editor-head"><h2 id="pwd-title" style="margin:0;font-size:17px">Change password</h2><button class="ghost" id="pwd-x">close</button></div>
  <div style="padding:16px 0 4px">
    <p class="muted" id="pwd-intro" style="margin:0 0 12px;font-size:12.5px">Update the local admin password.</p>
    <label>Current password</label>
    <input id="pwd-current" type="password" autocomplete="current-password"/>
    <label style="margin-top:10px">New password</label>
    <input id="pwd-new" type="password" autocomplete="new-password"/>
    <label style="margin-top:10px">Confirm new password</label>
    <input id="pwd-confirm" type="password" autocomplete="new-password"/>
    <div class="muted" style="font-size:11px;margin-top:6px">At least 8 characters, with a letter and a number.</div>
    <div class="err" id="pwd-err" style="margin-top:8px"></div>
  </div>
  <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px">
    <button class="ghost" id="pwd-cancel">Cancel</button>
    <button class="go" id="pwd-save">Save password</button>
  </div>
</div></div>

<!-- NEW VERSION MODAL -->
<div class="modal" id="vmodal"><div class="box" style="max-width:540px">
  <h2 style="margin:0 0 4px;font-size:16px">Upload new version</h2>
  <div class="muted" id="vm-feat"></div>
  <label>Modified documents (multiple)</label><input type="file" id="vm-file" multiple accept=".pdf,.docx,.md,.txt,.markdown"/>
  <div class="muted" style="font-size:11px;margin-top:4px">Links inside PDFs (and their sub-links) are fetched automatically — public web only.</div>
  <label>…and/or paste updated requirement text</label><textarea id="vm-text" style="min-height:90px"></textarea>
  <label style="margin-top:12px">Confluence page links <span class="muted" style="font-weight:400">(optional · one per line · child pages included)</span></label>
  <textarea id="vm-confluence" rows="2" placeholder="https://your-org.atlassian.net/wiki/spaces/…/pages/123456/…"></textarea>
  <label style="margin-top:10px">Figma design links <span class="muted" style="font-weight:400">(optional · one per line · needs a Figma token in Configuration)</span></label>
  <textarea id="vm-figma" rows="2" placeholder="https://www.figma.com/file/&lt;key&gt;/…"></textarea>
  <div style="display:flex;gap:8px;align-items:center;margin-top:12px"><input type="checkbox" id="vm-replace" style="width:auto"/><label style="margin:0">Override: replace the current version instead of bumping</label></div>
  <div class="warn" style="margin-top:6px">New version → the LLM keeps still-valid cases, retires obsolete ones, and adds new ones (history preserved). Replace → regenerates this version from scratch.</div>
  <div style="margin-top:14px;display:flex;gap:8px"><button class="go" id="vm-go">Create version</button><button class="ghost" id="vm-cancel">Cancel</button></div>
  <div id="vm-msg" class="muted" style="margin-top:8px"></div>
</div></div>

<!-- EXPORT MODAL -->
<div class="modal" id="export-modal"><div class="box" style="max-width:820px">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
    <div><h2 style="margin:0">Export test-case report</h2><div class="muted" id="export-sub" style="margin-top:4px"></div></div>
    <button class="ghost" id="export-close">Close</button>
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px;flex-wrap:wrap">
    <label style="display:flex;align-items:center;gap:8px;margin:0;color:var(--text)"><input type="checkbox" id="export-select-all" style="width:auto" checked/> Select all visible test cases</label>
    <span class="muted" id="export-count"></span>
  </div>
  <div class="export-list" id="export-list"></div>
  <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px;flex-wrap:wrap">
    <button class="ghost" id="export-csv">Download CSV</button>
    <button class="go" id="export-pdf">Download PDF report</button>
  </div>
</div></div>

<!-- GENERIC PROMPT MODAL -->
<div class="modal" id="pmodal"><div class="box" style="max-width:420px">
  <h2 id="pm-title" style="margin:0 0 6px;font-size:16px">Input</h2>
  <label id="pm-label">Value</label><input id="pm-input"/>
  <div style="margin-top:14px;display:flex;gap:8px;justify-content:flex-end"><button class="ghost" id="pm-cancel">Cancel</button><button class="go" id="pm-ok">OK</button></div>
</div></div>

<!-- STEP LIBRARY EDITOR MODAL -->
<div class="modal" id="step-modal">
  <div class="box editor-box" style="max-width: 500px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h2 id="step-modal-heading" style="margin:0;font-size:16px">Create Step</h2>
      <button class="ghost" id="step-modal-close" type="button" style="padding:4px 8px;font-size:16px">×</button>
    </div>
    <div style="display:flex;flex-direction:column;gap:12px">
      <div>
        <label>Step Type / Prefix</label>
        <select id="step-modal-prefix" style="width:100%">
          <option value="Given">Given</option>
          <option value="When">When</option>
          <option value="Then">Then</option>
          <option value="And">And</option>
          <option value="But">But</option>
          <option value="">None / Custom</option>
        </select>
      </div>
      <div>
        <label>Action / Description</label>
        <textarea id="step-modal-action" placeholder="e.g. user is on login page" style="width:100%;height:70px;font-family:inherit;font-size:13px;padding:8px" required></textarea>
      </div>
      <div>
        <label>Expected Result</label>
        <textarea id="step-modal-expected" placeholder="e.g. login form is displayed" style="width:100%;height:70px;font-family:inherit;font-size:13px;padding:8px"></textarea>
      </div>
      <div id="step-modal-warn" style="font-size:12px;color:var(--amber);margin-top:4px;display:none"></div>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">
        <button class="ghost" id="step-modal-cancel" type="button">Cancel</button>
        <button class="go" id="step-modal-save" type="button">Save</button>
      </div>
    </div>
  </div>
</div>

<!-- JOBS LOG MODAL -->
<div class="modal" id="jlogmodal"><div class="box" style="max-width:700px; width:90%">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
    <h2 style="margin:0;font-size:16px">Job execution logs</h2>
    <button class="ghost" id="jlm-close">close</button>
  </div>
  <div id="jlm-meta" class="muted" style="font-size:12px;margin-bottom:8px"></div>
  <pre id="jlm-logs" style="background:var(--panel2);border:1px solid var(--line);padding:12px;border-radius:6px;font-family:monospace;font-size:12px;height:350px;overflow-y:auto;white-space:pre-wrap;margin:0"></pre>
  <div style="margin-top:14px;display:flex;justify-content:flex-end">
    <button class="ghost" id="jlm-cancel">Close</button>
  </div>
</div></div>

<div id="toast" style="position:fixed;bottom:20px;right:20px;z-index:50;display:flex;flex-direction:column;gap:8px"></div>

<!-- Import Sheet modal -->
<div class="modal sheet-modal" id="imp-modal"><div class="box">
  <div class="editor-head">
    <div class="sheet-head-left">
      <div class="sheet-icon">XLS</div>
      <div class="sheet-title">
        <h2 id="imp-heading">Import test cases</h2>
        <div class="muted" id="imp-subtitle">Upload a spreadsheet and link tests to this feature.</div>
      </div>
    </div>
    <button class="ghost sheet-close" id="imp-close">Close</button>
  </div>
  <div class="sheet-body">
    <div class="muted" style="font-size:14px;max-width:720px">Upload a CSV or XLSX spreadsheet containing your test cases. WardenIQ will automatically extract and link them to this feature.</div>
    <div class="sheet-template-panel">
      <div>
        <b>Need a template?</b>
        <div class="muted">Download our system-shaped starter template to format your testcases.</div>
      </div>
      <div class="sheet-template-actions">
        <button class="ghost" id="imp-template-csv" type="button">CSV Template</button>
        <button class="ghost" id="imp-template-xlsx" type="button">XLSX Template</button>
      </div>
    </div>
    <div class="sheet-upload-panel">
      <div class="sheet-file-row">
        <input type="file" id="imp-file" accept=".csv,.xlsx,.xlsm,.tsv"/>
        <button class="ghost sheet-file-btn" id="imp-file-pick" type="button">Choose file</button>
        <button class="ghost" id="imp-file-clear" type="button">Clear</button>
        <span class="sheet-selected" id="imp-selected">Selected: none</span>
      </div>
      <div class="muted" style="margin-top:14px">Imported test cases are saved as feature memory to be inherited by future versions.</div>
      <div class="sheet-progress" id="imp-progress" hidden><span></span></div>
      <div id="imp-status" class="sheet-status"></div>
    </div>
    <div id="imp-summary"></div>
  </div>
  <div class="sheet-footer">
    <button class="ghost" id="imp-cancel" type="button">Cancel</button>
    <button class="go sheet-primary" id="imp-upload">Upload and analyse</button>
  </div>
</div></div>

<!-- Imported Sheet Library modal -->
<div class="modal sheet-modal" id="implib-modal"><div class="box">
  <div class="editor-head">
    <div class="sheet-head-left">
      <div class="sheet-icon">DOC</div>
      <div class="sheet-title">
        <h2>Reuse imported sheets</h2>
        <div class="muted">Expand an imported sheet and add rows into this feature. Existing rows are reused automatically, so duplicates stay out of the generated list.</div>
      </div>
    </div>
    <button class="ghost sheet-close" id="implib-close">Close</button>
  </div>
  <div class="sheet-body">
    <div id="implib-stats"></div>
    <div class="sheet-section-head">
      <div>
        <div class="typehdr">Project imported sheets</div>
        <div class="muted">Expand any uploaded sheet and toggle rows. Click Save changes when done.</div>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end">
        <span class="badge" id="implib-loaded-count">0 rows loaded</span>
        <button class="ghost" id="implib-refresh" type="button">Refresh / rescore</button>
      </div>
    </div>
    <div id="implib-list" class="sheet-list"></div>
  </div>
  <div class="sheet-footer">
    <button class="ghost" id="implib-cancel" type="button">Cancel</button>
    <button class="go sheet-primary" id="implib-save" type="button" disabled>Save changes</button>
  </div>
</div></div>
`;
