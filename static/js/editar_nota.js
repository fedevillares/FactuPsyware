(function() {
    function autocompletarFila(select) {
        const servicioId = select.value;
        if (!servicioId) return;

        const fila = select.closest('tr');
        if (!fila) return;

        const inputPrecio = fila.querySelector('input[name="nuevo_precio[]"]');
        const selectIva = fila.querySelector('select[name="nueva_alicuota[]"]');

        fetch('/servicios/datos/' + servicioId + '/')
            .then(response => response.json())
            .then(data => {
                if (data.error) return;
                if (inputPrecio) inputPrecio.value = data.precio_unitario;
                if (selectIva) selectIva.value = data.alicuota_iva;
            });
    }

    document.addEventListener('change', function(e) {
        if (e.target.matches('select.select-nuevo-servicio')) {
            autocompletarFila(e.target);
        }
    });

    document.addEventListener('click', function(e) {
        if (e.target.matches('#btn-agregar-producto')) {
            const template = document.getElementById('template-fila-nueva');
            const tbody = document.querySelector('#tabla-items tbody');
            tbody.appendChild(template.content.cloneNode(true));
        }
        if (e.target.matches('.btn-quitar-fila-nueva')) {
            e.target.closest('tr').remove();
        }
    });
})();
