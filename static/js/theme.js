(function () {
    const saved = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);

    window.toggleTheme = function () {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
        const btn = document.querySelector('.theme-toggle');
        if (btn) btn.textContent = next === 'dark' ? '☀️' : '🌙';
    };

    document.addEventListener('DOMContentLoaded', function () {
        const btn = document.querySelector('.theme-toggle');
        if (btn) btn.textContent = saved === 'dark' ? '☀️' : '🌙';
    });
})();