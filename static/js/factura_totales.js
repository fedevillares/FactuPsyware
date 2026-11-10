/*
 * Totales en vivo del formulario de factura y bloque de cotización del dólar.
 *
 * calcularTotalesFactura() replica EXACTAMENTE el algoritmo del servidor
 * (facturas/moneda.py: calcular_totales). Para eso no usa números de punto
 * flotante: trabaja con enteros (BigInt) y redondea "half up" igual que
 * Decimal ROUND_HALF_UP. El servidor sigue siendo la fuente de verdad: lo que
 * se guarda y se emite se recalcula allá; esto es solo para mostrar.
 * Hay un test (facturas/tests_moneda.py) que compara ambos resultados.
 */
(function (global) {
    'use strict';

    const ESCALA = 6;                       // decimales que se leen de cada campo
    const DIEZ_A_LA_6 = 10n ** 6n;
    // Código AFIP de alícuota -> porcentaje × 10
    const PORCENTAJES_X10 = { '3': 0n, '4': 105n, '5': 210n, '6': 270n, '8': 50n, '9': 25n };
    const ORDEN_ALICUOTAS = ['6', '5', '4', '8', '9', '3'];   // de mayor a menor
    const ETIQUETAS = { '3': '0%', '4': '10,5%', '5': '21%', '6': '27%', '8': '5%', '9': '2,5%' };

    /* "12,5" / "12.5" -> BigInt escalado a 6 decimales. null si no es un número. */
    function aEntero(texto) {
        const limpio = String(texto == null ? '' : texto).trim().replace(',', '.');
        const partes = /^(-?)(\d*)(?:\.(\d*))?$/.exec(limpio);
        if (!partes || (partes[2] === '' && !partes[3])) return null;
        const decimales = partes[3] || '';
        if (decimales.length > ESCALA) return null;
        const valor = BigInt((partes[2] || '0') + decimales.padEnd(ESCALA, '0'));
        return partes[1] ? -valor : valor;
    }

    /* División entera redondeando "half up" (como Decimal ROUND_HALF_UP). */
    function dividir(numerador, divisor) {
        const negativo = numerador < 0n;
        const n = negativo ? -numerador : numerador;
        const cociente = (2n * n + divisor) / (2n * divisor);
        return negativo ? -cociente : cociente;
    }

    /* Centavos (BigInt) -> "1234.56" */
    function aTexto(centavos) {
        const negativo = centavos < 0n;
        const abs = (negativo ? -centavos : centavos).toString().padStart(3, '0');
        return (negativo ? '-' : '') + abs.slice(0, -2) + '.' + abs.slice(-2);
    }

    /* "1234.56" -> "1.234,56" (formato argentino) */
    function formatoAr(texto) {
        const partes = String(texto).split('.');
        const negativo = partes[0].startsWith('-');
        const entero = partes[0].replace('-', '').replace(/\B(?=(\d{3})+(?!\d))/g, '.');
        return (negativo ? '-' : '') + entero + ',' + (partes[1] || '00');
    }

    /*
     * items: [{cantidad, precio_unitario, alicuota_iva}] (textos, como vienen de los inputs)
     * cotizacion: texto (pesos por 1 unidad de la moneda del comprobante; "1" para pesos)
     * Devuelve los importes como texto con 2 decimales, o null si algún dato no es válido.
     */
    function calcularTotalesFactura(items, cotizacion) {
        const cot = aEntero(cotizacion);
        if (cot === null) return null;

        const agrupado = {};
        ORDEN_ALICUOTAS.forEach(function (codigo) { agrupado[codigo] = { base: 0n, iva: 0n }; });

        for (const item of items) {
            const cantidad = aEntero(item.cantidad);
            const precio = aEntero(item.precio_unitario);
            if (cantidad === null || precio === null || !(item.alicuota_iva in PORCENTAJES_X10)) return null;
            // cantidad × precio está escalado a 12 decimales: a centavos son 10 menos.
            const subtotal = dividir(cantidad * precio, 10n ** 10n);
            agrupado[item.alicuota_iva].base += subtotal;
            agrupado[item.alicuota_iva].iva += dividir(subtotal * PORCENTAJES_X10[item.alicuota_iva], 1000n);
        }

        let neto = 0n, iva = 0n, ivaArs = 0n;
        const alicuotas = ORDEN_ALICUOTAS.map(function (codigo) {
            const ivaAlicuotaArs = dividir(agrupado[codigo].iva * cot, DIEZ_A_LA_6);
            neto += agrupado[codigo].base;
            iva += agrupado[codigo].iva;
            ivaArs += ivaAlicuotaArs;
            return {
                codigo: codigo,
                base: aTexto(agrupado[codigo].base),
                iva: aTexto(agrupado[codigo].iva),
                iva_ars: aTexto(ivaAlicuotaArs),
            };
        });
        const total = neto + iva;
        const totalArs = dividir(total * cot, DIEZ_A_LA_6);

        return {
            neto: aTexto(neto), iva: aTexto(iva), total: aTexto(total),
            neto_ars: aTexto(totalArs - ivaArs), iva_ars: aTexto(ivaArs), total_ars: aTexto(totalArs),
            alicuotas: alicuotas,
        };
    }

    global.calcularTotalesFactura = calcularTotalesFactura;
    global.formatoImporteAr = formatoAr;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { calcularTotalesFactura: calcularTotalesFactura, formatoAr: formatoAr };
    }
    if (typeof document === 'undefined') return;

    // ── Pantalla ────────────────────────────────────────────────────────────

    const bloque = document.getElementById('bloque-cotizacion');
    if (!bloque) return;

    const selectMoneda = document.getElementById('moneda');           // no existe en el detalle
    const inputCotizacion = document.getElementById('cotizacion');
    const infoCotizacion = document.getElementById('cotizacion-info');
    const avisoDesvio = document.getElementById('aviso-desvio');
    const textoDesvio = document.getElementById('aviso-desvio-texto');
    const botonActualizar = document.getElementById('btn-actualizar-cotizacion');
    const panelTotales = document.getElementById('totales-vivo');
    const desvioMaximo = parseFloat(bloque.dataset.desvioMaximo || '10');
    let automatica = null;      // última respuesta OK del endpoint

    function monedaActual() {
        return selectMoneda ? selectMoneda.value : (bloque.dataset.moneda || 'USD');
    }
    function modoActual() {
        const marcado = bloque.querySelector('input[name=cotizacion_modo]:checked');
        return marcado ? marcado.value : 'auto';
    }
    function elegirModo(modo) {
        const radio = bloque.querySelector('input[name=cotizacion_modo][value=' + modo + ']');
        if (radio) radio.checked = true;
    }

    function revisarDesvio() {
        let mostrar = false;
        if (monedaActual() !== 'ARS' && modoActual() === 'manual' && automatica) {
            const manual = parseFloat(String(inputCotizacion.value).replace(',', '.'));
            const referencia = parseFloat(automatica.valor);
            if (manual > 0 && referencia > 0) {
                const desvio = Math.abs(manual - referencia) / referencia * 100;
                if (desvio > desvioMaximo) {
                    mostrar = true;
                    textoDesvio.textContent = 'La cotización manual se desvía un ' + desvio.toFixed(1).replace('.', ',') +
                        '% de la automática (' + formatoAr(parseFloat(automatica.valor).toFixed(2)) + ').';
                }
            }
        }
        // Si el servidor ya pidió la confirmación, no se oculta.
        if (avisoDesvio && !avisoDesvio.dataset.forzado) avisoDesvio.style.display = mostrar ? 'block' : 'none';
    }

    function aplicarModo() {
        const extranjera = monedaActual() !== 'ARS';
        const manual = modoActual() === 'manual';
        bloque.style.display = extranjera ? 'block' : 'none';
        inputCotizacion.readOnly = !manual;
        inputCotizacion.required = extranjera && manual;
        if (extranjera && !manual && automatica) inputCotizacion.value = automatica.valor;
        revisarDesvio();
        actualizarTotales();
    }

    function pedirCotizacion(forzar) {
        if (botonActualizar) { botonActualizar.disabled = true; botonActualizar.classList.add('loading'); }
        return fetch(bloque.dataset.url + (forzar ? '?forzar=1' : ''), { credentials: 'same-origin' })
            .then(function (respuesta) { return respuesta.json(); })
            .then(function (datos) {
                if (!datos.ok) throw new Error(datos.error);
                automatica = datos;
                infoCotizacion.textContent = 'Dólar ' + datos.tipo + ' (' + datos.campo + '): $ ' +
                    formatoAr(parseFloat(datos.valor).toFixed(2)) + ' — ' + datos.fecha_texto +
                    ' — fuente: ' + datos.fuente.replace('api:', '') +
                    (datos.desactualizada ? ' — ATENCIÓN: no se pudo actualizar, es el último valor obtenido' : '');
                infoCotizacion.style.color = datos.desactualizada ? 'var(--danger)' : '';
            })
            .catch(function () {
                automatica = null;
                infoCotizacion.textContent = 'No se pudo obtener la cotización automática. Cargala manualmente.';
                infoCotizacion.style.color = 'var(--danger)';
                elegirModo('manual');
            })
            .then(function () {
                if (botonActualizar) { botonActualizar.disabled = false; botonActualizar.classList.remove('loading'); }
                aplicarModo();
            });
    }

    function filaTotal(etiqueta, valor, fuerte) {
        return '<div style="display:flex; justify-content:space-between; gap:24px;' + (fuerte ? ' font-weight:700;' : '') + '">' +
            '<span>' + etiqueta + '</span><span class="mono">' + valor + '</span></div>';
    }

    function actualizarTotales() {
        if (!panelTotales) return;
        const items = [];
        document.querySelectorAll('#tabla-items tbody tr').forEach(function (fila) {
            const cantidad = fila.querySelector('input[name="nueva_cantidad[]"]');
            const precio = fila.querySelector('input[name="nuevo_precio[]"]');
            const alicuota = fila.querySelector('select[name="nueva_alicuota[]"]');
            if (cantidad && precio && alicuota) {
                items.push({ cantidad: cantidad.value, precio_unitario: precio.value, alicuota_iva: alicuota.value });
            }
        });
        const extranjera = monedaActual() !== 'ARS';
        const simbolo = extranjera ? 'US$ ' : '$ ';
        const totales = calcularTotalesFactura(items, '1');
        if (!totales) {
            panelTotales.innerHTML = '<span class="faint">Completá cantidad y precio de todos los ítems para ver los totales.</span>';
            return;
        }
        let html = filaTotal('Neto gravado', simbolo + formatoAr(totales.neto));
        totales.alicuotas.forEach(function (a) {
            if (a.iva !== '0.00') html += filaTotal('IVA ' + ETIQUETAS[a.codigo], simbolo + formatoAr(a.iva));
        });
        html += filaTotal('Total', simbolo + formatoAr(totales.total), true);

        if (extranjera) {
            const enPesos = calcularTotalesFactura(items, inputCotizacion.value);
            html += '<div style="margin-top:10px; padding-top:10px; border-top:1px solid var(--border);">';
            if (enPesos && parseFloat(String(inputCotizacion.value).replace(',', '.')) > 0) {
                html += '<div class="faint" style="font-size:12px; margin-bottom:4px;">Equivalente en pesos (cotización $ ' +
                    formatoAr(parseFloat(String(inputCotizacion.value).replace(',', '.')).toFixed(2)) + ')</div>';
                html += filaTotal('Neto gravado', '$ ' + formatoAr(enPesos.neto_ars));
                enPesos.alicuotas.forEach(function (a) {
                    if (a.iva !== '0.00') html += filaTotal('IVA ' + ETIQUETAS[a.codigo], '$ ' + formatoAr(a.iva_ars));
                });
                html += filaTotal('Total', '$ ' + formatoAr(enPesos.total_ars), true);
            } else {
                html += '<span class="faint">Falta la cotización para calcular el equivalente en pesos.</span>';
            }
            html += '</div>';
        }
        panelTotales.innerHTML = html;
    }

    if (selectMoneda) {
        selectMoneda.addEventListener('change', function () {
            if (monedaActual() !== 'ARS' && !automatica) pedirCotizacion(false); else aplicarModo();
        });
    }
    bloque.querySelectorAll('input[name=cotizacion_modo]').forEach(function (radio) {
        radio.addEventListener('change', aplicarModo);
    });
    inputCotizacion.addEventListener('input', function () { revisarDesvio(); actualizarTotales(); });
    if (botonActualizar) botonActualizar.addEventListener('click', function () { pedirCotizacion(true); });

    // Ítems: cualquier cambio en la tabla (incluye filas agregadas/quitadas y
    // el autocompletado de precio al elegir un servicio).
    document.addEventListener('input', function (e) { if (e.target.closest('#tabla-items')) actualizarTotales(); });
    document.addEventListener('change', function (e) {
        if (e.target.closest('#tabla-items')) { actualizarTotales(); setTimeout(actualizarTotales, 600); }
    });
    document.addEventListener('click', function (e) {
        if (e.target.closest('#btn-agregar-producto, .btn-quitar-fila-nueva')) setTimeout(actualizarTotales, 0);
    });

    if (monedaActual() !== 'ARS') pedirCotizacion(false); else aplicarModo();
})(typeof window !== 'undefined' ? window : globalThis);
