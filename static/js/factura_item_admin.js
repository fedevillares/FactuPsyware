(function() {
    function actualizarFila(select) {
        const servicioId = select.value;
        if (!servicioId) return;

        const fila = select.closest('tr');
        if (!fila) return;

        const inputPrecio = fila.querySelector('input[name$="-precio_unitario"]');
        const selectIva = fila.querySelector('select[name$="-alicuota_iva"]');

        // Moneda y cotización de la factura (si están en el formulario): el
        // servidor convierte el precio cuando el servicio está en la otra moneda.
        const moneda = document.getElementById('id_moneda');
        const cotizacion = document.getElementById('id_cotizacion');
        const params = new URLSearchParams();
        if (moneda && moneda.value) params.set('moneda', moneda.value);
        if (moneda && moneda.value !== 'ARS' && cotizacion && cotizacion.value) params.set('cotizacion', cotizacion.value);

        fetch('/servicios/datos/' + servicioId + '/?' + params.toString())
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