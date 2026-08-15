(function () {
    const saved = localStorage.getItem('theme')
        || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', saved);

    window.toggleTheme = function () {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('theme', next);
    };

    // Marca el botón de submit como "cargando" al enviar el form, para dar
    // feedback visual en request lentos (LAN/celular). Uso: onsubmit="return marcarCargando(this)"
    window.marcarCargando = function (form) {
        const boton = form.querySelector('button[type="submit"]');
        if (boton) {
            boton.classList.add('loading');
            boton.disabled = true;
        }
        return true;
    };
})();
