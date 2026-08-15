import json
import base64
import qrcode
import io
from . import config


def generar_qr_base64(factura):
    """Genera el QR exigido por ARCA (RG 4291) y devuelve la imagen en base64 para insertar en HTML."""
    cliente = factura.cliente
    doc_tipo = int(cliente.tipo_documento)

    if doc_tipo == 99:
        doc_nro = 0
    else:
        doc_nro_str = cliente.numero_documento.replace('-', '').replace('.', '').strip()
        doc_nro = int(doc_nro_str) if doc_nro_str else 0

    datos = {
        "ver": 1,
        "fecha": factura.fecha_emision.strftime('%Y-%m-%d'),
        "cuit": int(config.CUIT),
        "ptoVta": factura.punto_venta,
        "tipoCmp": int(factura.tipo_comprobante),
        "nroCmp": factura.numero,
        "importe": float(factura.total),
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": doc_tipo,
        "nroDocRec": doc_nro,
        "tipoCodAut": "E",
        "codAut": int(factura.cae),
    }

    json_str = json.dumps(datos)
    b64 = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    url = f"https://www.afip.gob.ar/fe/qr/?p={b64}"

    img = qrcode.make(url)
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return img_b64