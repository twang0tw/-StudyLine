(() => {
  const sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;
  const shell = document.querySelector('.shell');
  const button = document.createElement('button');
  button.className = 'sidebar-toggle';
  button.type = 'button';
  const nav = sidebar.querySelector('.nav');
  nav.id = 'workspace-navigation';
  button.setAttribute('aria-controls', nav.id);
  const svg = (paths) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
  const icons = [
    svg('<path d="m2 9 10-5 10 5-10 5-10-5Z"/><path d="M6 11v6c4 3 8 3 12 0v-6M22 9v7"/>'),
    svg('<rect x="8" y="3" width="14" height="12" rx="2"/><path d="M15 15v5m-3 0h6M12 7h6"/><circle cx="5" cy="13" r="3"/><path d="M1 22v-2a4 4 0 0 1 8 0v2"/>'),
    '⚙', '↗',
  ];
  sidebar.querySelectorAll('.nav-item').forEach((link, index) => {
    const label = link.textContent;
    link.title = label;
    link.setAttribute('aria-label', label);
    link.innerHTML = `<span class="nav-icon" aria-hidden="true">${icons[index]}</span><span class="nav-label">${label}</span>`;
    if (link.classList.contains('active')) link.setAttribute('aria-current', 'page');
  });
  const apply = (collapsed) => {
    shell.classList.toggle('sidebar-collapsed', collapsed);
    button.textContent = collapsed ? '›' : '‹';
    button.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
    button.setAttribute('aria-label', button.title);
    button.setAttribute('aria-expanded', String(!collapsed));
  };
  let collapsed = false;
  try { collapsed = localStorage.getItem('studyline_sidebar_collapsed') === 'true'; } catch {}
  apply(collapsed);
  button.addEventListener('click', () => {
    collapsed = !collapsed;
    apply(collapsed);
    try { localStorage.setItem('studyline_sidebar_collapsed', String(collapsed)); } catch {}
  });
  sidebar.prepend(button);
})();
