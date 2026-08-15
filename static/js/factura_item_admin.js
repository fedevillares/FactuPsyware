(function() {
    function actualizarFila(select) {
        const servicioId = select.value;
        if (!servicioId) return;

        const fila = select.closest('tr');
        if (!fila) return;

        const inputPrecio = fila.querySelector('input[name$="-precio_unitario"]');
        const selectIva = fila.querySelector('select[name$="-alicuota_iva"]');

        fetch('/servicios/datos/' + servicioId + '/')
            .then(response => response.json())
            .then(data => {
                if (data.error) return;
                if (inputPrecio) inputPrecio.value = data.precio_unitario;
                if (selectIva) selectIva.value = data.alicuota_iva;
            });
    }

    document.addEventListener('change', function(e) {
        if (e.target.matches('select[name$="-servicio"]')) {
            actualizarFila(e.target);
        }
    });
})();