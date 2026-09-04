"""
PDF comprobante AFIP — replica exacta del layout oficial de ARCA.
Posiciones basadas en medición directa del PDF real emitido por ARCA.
"""
import io, os, base64

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

# ── Dimensiones del PDF real medido con pdfplumber ──────────────────────────
# Página A4: 595 × 842 pt
# Márgenes: izquierdo=14pt, derecho=14pt  → UW=567pt
# Columna divisora izq/centro: x=268pt
# Columna divisora centro/der: x=327pt
# ────────────────────────────────────────────────────────────────────────────

PW, PH = 595.28, 841.89
ML = 14.0
UW = 567.0
X_C = 268.0   # inicio columna central (letra A/B/C)
X_R = 327.0   # inicio columna derecha (datos comprobante)


def _fmt(v):
    """Formato argentino: punto miles, coma decimal."""
    try:
        f = float(v)
        neg = f < 0
        f = abs(f)
        ent = int(f)
        dec = round((f - ent) * 100)
        if dec == 100:
            ent += 1; dec = 0
        s = f"{ent:,}".replace(",", ".")
        return ("-" if neg else "") + f"{s},{dec:02d}"
    except Exception:
        return str(v)


def _t(c, x, y_from_top, txt, sz=8, bold=False, italic=False,
       col=colors.black, align="L"):
    """Texto con coordenada y medida desde arriba (como pdfplumber)."""
    if not txt:
        return
    fn = {(False, False): "Helvetica",
          (True, False): "Helvetica-Bold",
          (False, True): "Helvetica-Oblique",
          (True, True): "Helvetica-BoldOblique"}[bold, italic]
    rl_y = PH - y_from_top - sz * 0.85
    c.setFont(fn, sz)
    c.setFillColor(col)
    s = str(txt)
    if align == "C":
        c.drawCentredString(x, rl_y, s)
    elif align == "R":
        c.drawRightString(x, rl_y, s)
    else:
        c.drawString(x, rl_y, s)


def _lv(c, x, y, label, value, sz=8, gap=5, bold_val=False, val_col=colors.black):
    """Dibuja el 'label' en negrita y el 'value' justo después, calculando el
    ancho real del label para que nunca se solapen (a diferencia de las
    posiciones fijas medidas a mano, que se pisaban con textos largos)."""
    _t(c, x, y, label, sz=sz, bold=True)
    lw = c.stringWidth(label, "Helvetica-Bold", sz)
    if value not in (None, ""):
        _t(c, x + lw + gap, y, str(value), sz=sz, bold=bold_val, col=val_col)
    return x + lw + gap


def _hline(c, x, y_from_top, w, lw=0.4, col=colors.black):
    rl_y = PH - y_from_top
    c.setLineWidth(lw); c.setStrokeColor(col)
    c.line(x, rl_y, x + w, rl_y)


def _vline(c, x, y_from_top, h, lw=0.4, col=colors.black):
    rl_y_top = PH - y_from_top
    c.setLineWidth(lw); c.setStrokeColor(col)
    c.line(x, rl_y_top, x, rl_y_top - h)


def _box(c, x, y_top, w, h, lw=0.5, fill=None):
    rl_y = PH - y_top - h
    c.setLineWidth(lw); c.setStrokeColor(colors.black)
    if fill:
        c.setFillColor(fill)
        c.rect(x, rl_y, w, h, stroke=1, fill=1)
        c.setFillColor(colors.black)
    else:
        c.rect(x, rl_y, w, h, stroke=1, fill=0)


def _wrap_by_width(c, txt, max_w, font_name, sz):
    """Parte texto en líneas que caben en max_w, midiendo el ancho real de
    la fuente (stringWidth) en vez de estimarlo por cantidad de caracteres.
    Esto evita que descripciones con palabras anchas o mayúsculas se
    desborden de su columna y se superpongan con la columna vecina."""
    lines = []
    for sub in str(txt).split("\n"):
        words = sub.split(" ")
        cur = ""
        for word in words:
            # Palabra individual más ancha que la columna: se corta a la fuerza.
            while c.stringWidth(word, font_name, sz) > max_w:
                lo, hi = 1, len(word)
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if c.stringWidth(word[:mid], font_name, sz) <= max_w:
                        lo = mid
                    else:
                        hi = mid - 1
                cut = max(lo, 1)
                if cur:
                    lines.append(cur)
                    cur = ""
                lines.append(word[:cut])
                word = word[cut:]
            candidate = f"{cur} {word}".strip() if cur else word
            if c.stringWidth(candidate, font_name, sz) <= max_w:
                cur = candidate
            else:
                if cur:
                    lines.append(cur)
                cur = word
        lines.append(cur)
    return lines or [""]


def _wrap_text(c, x, y_top, max_w, txt, sz=8, bold=False, line_h=10):
    fn = "Helvetica-Bold" if bold else "Helvetica"
    lines = _wrap_by_width(c, txt, max_w, fn, sz)
    for i, ln in enumerate(lines):
        _t(c, x, y_top + i * line_h, ln, sz=sz, bold=bold)
    return y_top + (len(lines) - 1) * line_h


def generar_pdf(factura, empresa, otros_impuestos=0,
                qr_b64=None, es_preview=False) -> bytes:
    """
    Genera el PDF del comprobante replicando el layout exacto de ARCA.
    """
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)

    tipo = ("NOTA DE CRÉDITO" if factura.es_nota_credito
            else "NOTA DE DÉBITO" if factura.es_nota_debito
            else "FACTURA")

    c.setTitle(f"{tipo} {factura.numero_completo}")
    c.setAuthor(empresa.razon_social)

    # ══════════════════════════════════════════════════════════════════
    # 1. BANDA "ORIGINAL"
    # Medido del PDF real: y_top=14, height=27
    # ══════════════════════════════════════════════════════════════════
    _box(c, ML, 14, UW, 27, lw=0.75)
    _t(c, PW / 2, 14 + 6, "ORIGINAL", sz=11, bold=True, align="C")

    # ══════════════════════════════════════════════════════════════════
    # 2. ENCABEZADO (3 columnas)
    # Medido: y_top=41, height=124
    # ══════════════════════════════════════════════════════════════════
    _box(c, ML, 41, UW, 124, lw=0.75)
    _vline(c, X_C, 41, 124, lw=1.0)
    _vline(c, X_R, 41, 124, lw=0.75)

    # ── Columna izquierda: EMISOR ──
    # El logo de la empresa (EmpresaConfig.logo) tiene prioridad; si no está
    # cargado, se usa el logo estático por defecto del proyecto.
    logo_reader = None
    if getattr(empresa, "logo", None):
        try:
            logo_reader = ImageReader(empresa.logo.path)
        except Exception:
            logo_reader = None
    if logo_reader is None:
        logo_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static", "img", "logo.png")
        if os.path.exists(logo_path):
            logo_reader = ImageReader(logo_path)
    if logo_reader is not None:
        try:
            # Logo arriba a la izquierda; el nombre va DEBAJO para no pisarlo.
            logo_h = 46
            rl_logo_y = PH - 45 - logo_h
            c.drawImage(logo_reader, ML + 4, rl_logo_y,
                        width=150, height=logo_h,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    nombre_comercial = (empresa.nombre_fantasia or empresa.razon_social).upper()
    _t(c, ML + 7, 90, nombre_comercial, sz=9, bold=True)

    _t(c, ML + 7, 103, "Razón Social:", sz=8, bold=True)
    _t(c, ML + 72, 103, empresa.razon_social, sz=8)

    _t(c, ML + 7, 127, "Domicilio Comercial:", sz=8, bold=True)
    dom_val = f"{empresa.domicilio}, {empresa.localidad}"
    _wrap_text(c, ML + 102, 127, X_C - ML - 110, dom_val, sz=8, line_h=10)

    _t(c, ML + 7, 152, "Condición frente al IVA:", sz=8, bold=True)
    _t(c, ML + 120, 152, empresa.condicion_iva, sz=8)

    # ── Columna central: letra ──
    letra = factura.letra_comprobante
    rl_letra_y = PH - 41 - 55
    c.setFont("Helvetica-Bold", 46)
    c.setFillColor(colors.black)
    c.drawCentredString(X_C + (X_R - X_C) / 2, rl_letra_y, letra)
    _t(c, X_C + (X_R - X_C) / 2, 146,
       f"COD. {int(factura.tipo_comprobante):02d}", sz=7, align="C")

    # ── Columna derecha: datos comprobante ──
    _t(c, X_R + 14, 57, tipo, sz=14, bold=True)

    _t(c, X_R + 14, 86, "Punto de Venta:", sz=8, bold=True)
    _t(c, X_R + 90, 86, f"{factura.punto_venta:05d}", sz=8)
    _t(c, X_R + 134, 86, "Comp. Nro:", sz=8, bold=True)
    _t(c, X_R + 190, 86, f"{factura.numero or 0:08d}", sz=8)

    _t(c, X_R + 14, 102, "Fecha de Emisión:", sz=8, bold=True)
    fecha = (factura.fecha_emision.strftime("%d/%m/%Y")
             if factura.fecha_emision else "-")
    _t(c, X_R + 101, 102, fecha, sz=8)

    _hline(c, X_R + 5, 114, PW - X_R - 5 - ML, lw=0.5)

    _t(c, X_R + 14, 125, "CUIT:", sz=8, bold=True)
    _t(c, X_R + 46, 125, empresa.cuit, sz=8)

    _t(c, X_R + 14, 137, "Ingresos Brutos:", sz=8, bold=True)
    _t(c, X_R + 92, 137, empresa.ingresos_brutos or "EXENTO", sz=8)

    _t(c, X_R + 14, 149, "Fecha de Inicio de Actividades:", sz=8, bold=True)
    ini = (empresa.inicio_actividades.strftime("%d/%m/%Y")
           if empresa.inicio_actividades else "-")
    _t(c, X_R + 155, 149, ini, sz=8)

    # ══════════════════════════════════════════════════════════════════
    # 3. PERÍODO FACTURADO
    # Medido: y_top=165, height=18
    # ══════════════════════════════════════════════════════════════════
    _box(c, ML, 165, UW, 18, lw=0.75)
    Y_PER = 172
    _t(c, ML + 7, Y_PER, "Período Facturado Desde:", sz=8, bold=True)
    if factura.periodo_desde:
        _t(c, ML + 145, Y_PER, factura.periodo_desde.strftime("%d/%m/%Y"), sz=8)
    _t(c, ML + 218, Y_PER, "Hasta:", sz=8, bold=True)
    if factura.periodo_hasta:
        _t(c, ML + 248, Y_PER, factura.periodo_hasta.strftime("%d/%m/%Y"), sz=8)
    vto_pago = (factura.fecha_vto_pago.strftime("%d/%m/%Y")
                if factura.fecha_vto_pago else "")
    _lv(c, ML + 349, Y_PER, "Fecha de Vto. para el pago:", vto_pago, sz=8)

    # ══════════════════════════════════════════════════════════════════
    # 4. DATOS DEL RECEPTOR
    # Medido: y_top=183, height=56. Si la razón social es muy larga para
    # su columna, se parte en varias líneas y el resto de las filas (y la
    # caja) se corre hacia abajo lo que haga falta.
    # ══════════════════════════════════════════════════════════════════
    cli = factura.cliente
    X_REC_R = ML + 295   # inicio de la columna derecha del receptor
    NOMBRE_LINE_H = 9

    nombre_label = "Apellido y Nombre / Razón Social:"
    nombre_val_x = X_REC_R + c.stringWidth(
        nombre_label, "Helvetica-Bold", 8) + 5
    nombre_max_w = (ML + UW) - nombre_val_x - 7
    nombre_lines = _wrap_by_width(
        c, cli.nombre_completo, nombre_max_w, "Helvetica", 8)
    extra_h = (len(nombre_lines) - 1) * NOMBRE_LINE_H

    box_h_rec = 56 + extra_h
    _box(c, ML, 183, UW, box_h_rec, lw=0.75)

    # Fila 1: documento (tipo dinámico) + razón social
    doc_label = cli.get_tipo_documento_display() + ":"
    _lv(c, ML + 7, 191, doc_label, cli.numero_documento or "-", sz=8)
    _t(c, X_REC_R, 191, nombre_label, sz=8, bold=True)
    for i, ln in enumerate(nombre_lines):
        _t(c, nombre_val_x, 191 + i * NOMBRE_LINE_H, ln, sz=8)

    # Fila 2: condición IVA + domicilio
    y_fila2 = 208 + extra_h
    _lv(c, ML + 7, y_fila2, "Condición frente al IVA:",
        cli.get_condicion_iva_display(), sz=8)
    dom_x = _lv(c, X_REC_R, y_fila2, "Domicilio Comercial:", "", sz=8)
    _wrap_text(c, dom_x, y_fila2, UW + ML - dom_x - 7, cli.direccion or "-",
               sz=8, line_h=9)

    # Fila 3: condición de venta
    y_fila3 = 225 + extra_h
    _lv(c, ML + 7, y_fila3, "Condición de venta:",
        factura.get_condicion_venta_display(), sz=8)

    # ══════════════════════════════════════════════════════════════════
    # 5. COMPROBANTE ASOCIADO (NC / ND)
    # ══════════════════════════════════════════════════════════════════
    y_after_rec = 183 + box_h_rec
    if factura.factura_asociada:
        asoc = factura.factura_asociada
        asoc_txt = (f"{asoc.get_tipo_comprobante_display()}  "
                    f"N° {asoc.numero_completo}  —  "
                    f"{asoc.fecha_emision.strftime('%d/%m/%Y')}")

        box_h = 17
        _box(c, ML, y_after_rec, UW, box_h, lw=0.75)
        _t(c, ML + 7, y_after_rec + 5, "Comprobante Asociado:", sz=8, bold=True)
        _t(c, ML + 130, y_after_rec + 5, asoc_txt, sz=8)
        y_after_rec += box_h

    # ══════════════════════════════════════════════════════════════════
    # 6. TABLA DE ÍTEMS
    # Columnas comprimidas para dar lugar a "Importe IVA" (pt, ancho):
    # Código  Descripción  Cantidad  U.medida  Precio Unit.  %Bonif
    # Subtotal  Alicuota IVA  Importe IVA  Subtotal c/IVA
    # ══════════════════════════════════════════════════════════════════
    DESC_W = 170
    CW = [32, DESC_W, 46, 40, 56, 32, 52, 34, 46, 59]
    CX = [ML]
    for w in CW[:-1]:
        CX.append(CX[-1] + w)

    CHEADS = [
        ("Código",               "C"),
        ("Producto / Servicio",  "L"),
        ("Cantidad",             "C"),
        ("U. medida",            "C"),
        ("Precio Unit.",         "C"),
        ("% Bonif",              "C"),
        ("Subtotal",             "C"),
        ("Alícuota\nIVA",        "C"),
        ("Importe\nIVA",         "C"),
        ("Subtotal c/IVA",       "C"),
    ]

    y_table_top = y_after_rec + 31
    THEAD_H = 25
    TROW_H = 18
    MIN_EMPTY_ROWS = 7

    items = list(factura.items.all())

    DESC_MAX_W = DESC_W - 4  # margen interno de 2pt a cada lado

    item_rows = []
    for item in items:
        txt = item.nombre_mostrado or ""
        desc_lines = _wrap_by_width(c, txt, DESC_MAX_W, "Helvetica", 7.5)
        if item.servicio_id and item.servicio.descripcion:
            desc_lines += _wrap_by_width(
                c, item.servicio.descripcion, DESC_MAX_W, "Helvetica", 7)
        row_h = max(TROW_H, len(desc_lines) * 9 + 4)
        item_rows.append((item, desc_lines, row_h))

    items_h = sum(rh for _, _, rh in item_rows)
    blank_h = max(MIN_EMPTY_ROWS * TROW_H - items_h, 0)
    TABLE_H = THEAD_H + items_h + blank_h

    _box(c, ML, y_table_top, UW, TABLE_H, lw=0.75)
    _box(c, ML, y_table_top, UW, THEAD_H, lw=0.75,
         fill=colors.HexColor("#EEEEEE"))
    _hline(c, ML, y_table_top + THEAD_H, UW, lw=0.75)

    for xi in CX[1:]:
        _vline(c, xi, y_table_top, THEAD_H, lw=0.3,
               col=colors.HexColor("#999999"))

    for i, ((lbl, al), xi, wi) in enumerate(zip(CHEADS, CX, CW)):
        lines = lbl.split("\n")
        lh = 8
        y0 = y_table_top + (THEAD_H - len(lines) * lh) / 2
        for li, ln in enumerate(lines):
            ty = y0 + li * lh
            if al == "C":
                _t(c, xi + wi / 2, ty, ln, sz=7, bold=True, align="C")
            elif al == "R":
                _t(c, xi + wi - 2, ty, ln, sz=7, bold=True, align="R")
            else:
                _t(c, xi + 2, ty, ln, sz=7, bold=True)

    row_y = y_table_top + THEAD_H
    for item, desc_lines, rh in item_rows:
        _hline(c, ML, row_y + rh, UW, lw=0.3,
               col=colors.HexColor("#999999"))
        for xi in CX[1:]:
            _vline(c, xi, row_y, rh, lw=0.3,
                   col=colors.HexColor("#999999"))

        vy_center = row_y + rh / 2 - 1
        vals = [
            (str(item.servicio_id) if item.servicio_id else "", "C"),
            (None, "L"),
            (_fmt(item.cantidad), "C"),
            ("unidades", "C"),
            (_fmt(item.precio_unitario), "C"),
            ("0,00", "C"),
            (_fmt(item.subtotal), "C"),
            (item.get_alicuota_iva_display(), "C"),
            (_fmt(item.iva_monto), "C"),
            (_fmt(item.total), "C"),
        ]
        for i, ((val, al), xi, wi) in enumerate(zip(vals, CX, CW)):
            if i == 1:
                for li, ln in enumerate(desc_lines):
                    sz_d = 7.5 if li == 0 else 7
                    cl = colors.black if li == 0 else colors.HexColor("#444444")
                    _t(c, xi + 2, row_y + 2 + li * 9, ln, sz=sz_d, col=cl)
            elif val:
                if al == "C":
                    _t(c, xi + wi / 2, vy_center, val, sz=7.5, align="C")
                elif al == "R":
                    _t(c, xi + wi - 2, vy_center, val, sz=7.5, align="R")
                else:
                    _t(c, xi + 2, vy_center, val, sz=7.5)
        row_y += rh

    y_after_items = y_table_top + TABLE_H

    # ══════════════════════════════════════════════════════════════════
    # 6.5 NOTAS (texto libre, opcional)
    # ══════════════════════════════════════════════════════════════════
    if factura.observaciones:
        notas_max_w = UW - 14
        notas_lines = []
        for parrafo in factura.observaciones.splitlines() or [factura.observaciones]:
            notas_lines += _wrap_by_width(c, parrafo, notas_max_w, "Helvetica", 8)
        NOTAS_H = 14 + len(notas_lines) * 10
        _box(c, ML, y_after_items, UW, NOTAS_H, lw=0.75)
        _t(c, ML + 7, y_after_items + 5, "Notas:", sz=8, bold=True)
        for i, ln in enumerate(notas_lines):
            _t(c, ML + 7, y_after_items + 5 + 10 * (i + 1), ln, sz=8)
        y_after_items += NOTAS_H

    # ══════════════════════════════════════════════════════════════════
    # 7. TOTALES
    # Separador izq/der a x=ML+UW*0.52
    # Filas lado derecho: 13pt cada una (medido del PDF real)
    # ══════════════════════════════════════════════════════════════════
    # ── Discriminación de IVA según tipo de comprobante (regla AFIP) ──
    # Sólo el tipo A discrimina el IVA en la impresión. Los tipos B y C
    # muestran únicamente los totales (IVA incluido), sin desglose.
    if letra == "A":
        desglose = factura.desglose_iva
        iva_map = {float(a["porcentaje"]): a["importe"] for a in desglose}
        right_rows = [
            ("Importe Neto Gravado: $",   _fmt(factura.subtotal),          False),
            ("IVA 27%: $",                _fmt(iva_map.get(27,   0.0)),    False),
            ("IVA 21%: $",                _fmt(iva_map.get(21,   0.0)),    False),
            ("IVA 10.5%: $",              _fmt(iva_map.get(10.5, 0.0)),    False),
            ("IVA 5%: $",                 _fmt(iva_map.get(5,    0.0)),    False),
            ("IVA 2.5%: $",               _fmt(iva_map.get(2.5,  0.0)),    False),
            ("IVA 0%: $",                 _fmt(iva_map.get(0,    0.0)),    False),
            ("Importe Otros Tributos: $", _fmt(otros_impuestos),            False),
            ("Importe Total: $",          _fmt(factura.total),              True),
        ]
    else:
        # Tipos B y C: sin discriminación de IVA por alícuota, pero se
        # informa el subtotal de IVA total del comprobante.
        right_rows = [
            ("Subtotal: $",               _fmt(factura.subtotal),           False),
            ("Subtotal IVA: $",           _fmt(factura.total_iva),          False),
            ("Importe Otros Tributos: $", _fmt(otros_impuestos),            False),
            ("Importe Total: $",          _fmt(factura.total),              True),
        ]

    TOT_ROW_H = 13
    TOT_H = len(right_rows) * TOT_ROW_H
    X_TOT_DIV = ML + UW * 0.52

    _box(c, ML, y_after_items, UW, TOT_H, lw=0.75)
    _vline(c, X_TOT_DIV, y_after_items, TOT_H, lw=0.5)

    left_center_y = y_after_items + TOT_H / 2 - 4
    _t(c, ML + 7, left_center_y, "Importe Otros Tributos: $", sz=8)
    _t(c, X_TOT_DIV - 30, left_center_y, _fmt(otros_impuestos), sz=8, align="R")

    RX_LABEL = PW - ML - 95
    RX_VALUE = PW - ML - 2
    for ri, (lbl, val, is_total) in enumerate(right_rows):
        ry = y_after_items + ri * TOT_ROW_H + TOT_ROW_H / 2 - 4
        sz = 9 if is_total else 8
        _t(c, RX_LABEL, ry, lbl, sz=sz, bold=is_total, align="R")
        _t(c, RX_VALUE, ry, val, sz=sz, bold=is_total, align="R")
        if ri < len(right_rows) - 1:
            _hline(c, X_TOT_DIV, y_after_items + (ri + 1) * TOT_ROW_H,
                   UW - UW * 0.52, lw=0.3, col=colors.HexColor("#999999"))

    y_after_tot = y_after_items + TOT_H

    # ══════════════════════════════════════════════════════════════════
    # 8. LEYENDA
    # Medido del PDF real: height≈20, texto en itálica centrado
    # ══════════════════════════════════════════════════════════════════
    if empresa.leyenda:
        LEY_H = 20
        _box(c, ML, y_after_tot, UW, LEY_H, lw=0.75)
        _t(c, PW / 2, y_after_tot + 6,
           f'"{empresa.leyenda}"', sz=8, italic=True, align="C")
        y_after_tot += LEY_H

    # ══════════════════════════════════════════════════════════════════
    # 9. PIE: QR | logo ARCA | Pág. 1/1 | CAE
    # Medido: height≈90
    # ══════════════════════════════════════════════════════════════════
    PIE_H = 90
    _box(c, ML, y_after_tot, UW, PIE_H, lw=0.75)

    if es_preview:
        _t(c, PW / 2, y_after_tot + PIE_H / 2 - 8,
           "VISTA PREVIA - sin validez fiscal - no tiene CAE",
           sz=10, bold=True, col=colors.HexColor("#AA0000"), align="C")
        _t(c, PW / 2, y_after_tot + PIE_H / 2 + 6,
           "Este comprobante aun no fue autorizado por ARCA.",
           sz=8, col=colors.HexColor("#880000"), align="C")
        c.saveState()
        c.setFont("Helvetica-Bold", 72)
        c.setFillColor(colors.Color(0.85, 0, 0, alpha=0.08))
        c.translate(PW / 2, PH / 2); c.rotate(45)
        c.drawCentredString(0, 0, "VISTA PREVIA")
        c.restoreState()
    else:
        QR_SZ = 78
        if qr_b64:
            try:
                qr_img = ImageReader(io.BytesIO(base64.b64decode(qr_b64)))
                rl_qr_y = PH - y_after_tot - PIE_H + 5
                c.drawImage(qr_img, ML + 2, rl_qr_y,
                            width=QR_SZ, height=QR_SZ)
            except Exception:
                pass

        arca_logo = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static", "img", "arca_logo.png")
        arca_logo_x = ML + QR_SZ + 6
        if os.path.exists(arca_logo):
            try:
                rl_al_y = PH - y_after_tot - PIE_H + 35
                c.drawImage(ImageReader(arca_logo),
                            arca_logo_x, rl_al_y,
                            width=50, height=35,
                            preserveAspectRatio=True, mask="auto")
            except Exception:
                pass

        pie_center_x = ML + QR_SZ + 6 + 50 + 30
        _t(c, pie_center_x, y_after_tot + 25, "Pág. 1/1", sz=8, bold=True)

        _t(c, ML + QR_SZ + 8, y_after_tot + 55,
           "Comprobante Autorizado", sz=8, bold=True, italic=True)
        _t(c, ML + QR_SZ + 8, y_after_tot + 67,
           "Esta Agencia no se responsabiliza por los datos ingresados"
           " en el detalle de la operación",
           sz=6, italic=True)

        cae_label_x = ML + 372          # etiquetas alineadas a la izquierda
        cae_val_x = PW - ML - 4          # valores alineados a la derecha (dentro del box)
        _t(c, cae_label_x, y_after_tot + 20, "CAE N°:", sz=8, bold=True)
        _t(c, cae_val_x, y_after_tot + 20, str(factura.cae or "-"),
           sz=8, bold=True, align="R")
        _t(c, cae_label_x, y_after_tot + 34, "Fecha de Vto. de CAE:",
           sz=8, bold=True)
        vto = (factura.cae_vencimiento.strftime("%d/%m/%Y")
               if factura.cae_vencimiento else "-")
        _t(c, cae_val_x, y_after_tot + 34, vto, sz=8, bold=True, align="R")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
