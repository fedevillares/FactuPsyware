(function() {
    // Moneda y cotización de la factura que se está cargando. En "Nueva
    // factura" salen del formulario (#moneda / #cotizacion); en "Editar nota"
    // son fijas y vienen como data-* en la tabla de ítems.
    function contextoMoneda() {
        const tabla = document.getElementById('tabla-items');
        const selectMoneda = document.getElementById('moneda');
        const inputCotizacion = document.getElementById('cotizacion');
        const moneda = selectMoneda ? selectMoneda.value : (tabla && tabla.dataset.moneda) || '';
        let cotizacion = '';
        if (moneda && moneda !== 'ARS') {
            cotizacion = inputCotizacion ? inputCotizacion.value : (tabla && tabla.dataset.cotizacion) || '';
        }
        return { moneda: moneda, cotizacion: cotizacion };
    }

    function formato(valor) {
        return window.formatoImporteAr ? window.formatoImporteAr(parseFloat(valor).toFixed(2)) : valor;
    }

    function mostrarAviso(inputPrecio, texto) {
        let aviso = inputPrecio.parentNode.querySelector('.aviso-conversion');
        if (!texto) {
            if (aviso) aviso.remove();
            return;
        }
        if (!aviso) {
            aviso = document.createElement('div');
            aviso.className = 'field-hint aviso-conversion';
            aviso.style.cssText = 'margin-top:4px; font-size:11px;';
            inputPrecio.parentNode.appendChild(aviso);
        }
        aviso.textContent = texto;
    }

    function autocompletarFila(select) {
        const servicioId = select.value;
        if (!servicioId) return;

        const fila = select.closest('tr');
        if (!fila) return;

        const inputPrecio = fila.querySelector('input[name="nuevo_precio[]"]');
        const selectIva = fila.querySelector('select[name="nueva_alicuota[]"]');

        // El servidor convierte el precio si el servicio está cargado en una
        // moneda distinta a la de la factura.
        const contexto = contextoMoneda();
        const params = new URLSearchParams();
        if (contexto.moneda) params.set('moneda', contexto.moneda);
        if (contexto.cotizacion) params.set('cotizacion', contexto.cotizacion);

        fetch('/servicios/datos/' + servicioId + '/?' + params.toString())
            .then(response => response.json())
            .then(data => {
                if (data.error) return;
                if (selectIva) selectIva.value = data.alicuota_iva;
                if (!inputPrecio) return;
                inputPrecio.value = data.precio_unitario;
                // Recuerda el precio puesto automáticamente: si después cambia
                // la moneda o la cotización solo se reconvierte si el usuario
                // no lo tocó a mano.
                inputPrecio.dataset.precioAuto = inputPrecio.value;
                if (data.convertido) {
                    const simbolo = data.moneda === 'USD' ? 'US$ ' : '$ ';
                    mostrarAviso(inputPrecio, 'Convertido de ' + simbolo + formato(data.precio_original) +
                        ' (cotización $ ' + formato(data.cotizacion) + ')');
                } else {
                    mostrarAviso(inputPrecio, data.aviso || '');
                }
                inputPrecio.dispatchEvent(new Event('input', { bubbles: true }));
            });
    }

    // Cambió la moneda o la cotización de la factura: reconvertir los precios
    // que salieron del catálogo y no fueron editados a mano.
    function reconvertirFilas() {
        document.querySelectorAll('#tabla-items select.select-nuevo-servicio').forEach(function(select) {
            if (!select.value) return;
            const inputPrecio = select.closest('tr').querySelector('input[name="nuevo_precio[]"]');
            if (inputPrecio && inputPrecio.dataset.precioAuto === inputPrecio.value) {
                autocompletarFila(select);
            }
        });
    }

    document.addEventListener('change', function(e) {
        if (e.target.matches('select.select-nuevo-servicio')) {
            autocompletarFila(e.target);
        }
    });

    // Si el usuario edita el precio a mano, el aviso de conversión ya no aplica.
    document.addEventListener('input', function(e) {
        if (e.isTrusted && e.target.matches('input[name="nuevo_precio[]"]')) {
            mostrarAviso(e.target, '');
        }
    });

    // Lo dispara static/js/factura_totales.js.
    document.addEventListener('cotizacion-cambiada', reconvertirFilas);

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
