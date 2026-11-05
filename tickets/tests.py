from datetime import datetime, timezone as dt_tz
from email.message import EmailMessage as PyEmailMessage
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from arca.crypto import cifrar
from arca.models import EmpresaConfig
from clientes.models import Cliente

from . import correo_entrante
from .correo_entrante import procesar_mensaje, revisar_bandeja, debe_iniciar_hilo
from .emailing import enviar_acuse_recibo, ASUNTO_ACUSE
from .models import Ticket


def correo(asunto="TICKET DE SOPORTE", remitente="Ana Soporte <soporte@cliente.com>",
           cuerpo="La impresora no imprime.", fecha="Wed, 04 Nov 2026 15:30:00 -0300",
           message_id="<abc123@cliente.com>", html=None, extra=None):
    msg = PyEmailMessage()
    msg['Subject'] = asunto
    msg['From'] = remitente
    msg['To'] = 'soporte@psyware.com'
    if fecha:
        msg['Date'] = fecha
    if message_id:
        msg['Message-ID'] = message_id
    for k, v in (extra or {}).items():
        msg[k] = v
    msg.set_content(cuerpo)
    if html:
        msg.add_alternative(html, subtype='html')
    return msg.as_bytes()


EMAIL_BACKEND_MEM = 'django.core.mail.backends.locmem.EmailBackend'


class BaseCorreo(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre_completo='Clínica Norte', numero_documento='30111222333', tipo_documento='80',
            contacto_soporte_nombre='Ana', contacto_soporte_email='Soporte@Cliente.com',
        )
        empresa = EmpresaConfig.get_config()
        empresa.soporte_email = 'soporte@psyware.com'
        empresa.soporte_password = cifrar('clave-app')
        empresa.soporte_nombre_remitente = 'Soporte Psyware'
        empresa.save()


class ProcesarMensajeTests(BaseCorreo):
    def test_abre_ticket_con_contenido_y_fecha_del_correo(self):
        estado, ticket = procesar_mensaje(correo())
        self.assertEqual(estado, 'creado')
        ticket.refresh_from_db()
        self.assertEqual(ticket.cliente, self.cliente)
        self.assertEqual(ticket.titulo, 'TICKET DE SOPORTE')
        self.assertEqual(ticket.descripcion, 'La impresora no imprime.')
        self.assertEqual(ticket.origen, 'EMAIL')
        self.assertEqual(ticket.contacto_email, 'soporte@cliente.com')
        self.assertEqual(ticket.contacto_nombre, 'Ana')
        self.assertEqual(ticket.estado, 'PENDIENTE')
        # La fecha/hora del correo (15:30 -03:00) se usa como inicio del ticket.
        self.assertEqual(ticket.fecha_inicio, datetime(2026, 11, 4, 18, 30, tzinfo=dt_tz.utc))
        self.assertEqual(ticket.email_fecha, ticket.fecha_inicio)

    def test_asunto_insensible_a_mayusculas_y_con_texto_extra(self):
        estado, ticket = procesar_mensaje(correo(asunto='RE: ticket de soporte - no anda el wifi'))
        self.assertEqual(estado, 'creado')
        self.assertEqual(ticket.titulo, 'RE: ticket de soporte - no anda el wifi')

    def test_asunto_distinto_no_abre(self):
        self.assertEqual(procesar_mensaje(correo(asunto='Consulta'))[0], 'ignorado')
        self.assertFalse(Ticket.objects.exists())

    def test_remitente_no_registrado_no_abre(self):
        estado, motivo = procesar_mensaje(correo(remitente='otro@desconocido.com'))
        self.assertEqual(estado, 'ignorado')
        self.assertIn('otro@desconocido.com', motivo)
        self.assertFalse(Ticket.objects.exists())

    def test_email_general_del_cliente_no_alcanza(self):
        self.cliente.email = 'general@cliente.com'
        self.cliente.save()
        self.assertEqual(procesar_mensaje(correo(remitente='general@cliente.com'))[0], 'ignorado')

    def test_mismo_correo_dos_veces_no_duplica(self):
        self.assertEqual(procesar_mensaje(correo())[0], 'creado')
        self.assertEqual(procesar_mensaje(correo())[0], 'duplicado')
        self.assertEqual(Ticket.objects.count(), 1)

    def test_sin_message_id_tampoco_duplica(self):
        self.assertEqual(procesar_mensaje(correo(message_id=None))[0], 'creado')
        self.assertEqual(procesar_mensaje(correo(message_id=None))[0], 'duplicado')

    def test_respuesta_automatica_no_abre(self):
        raw = correo(extra={'Auto-Submitted': 'auto-replied'})
        self.assertEqual(procesar_mensaje(raw)[0], 'ignorado')

    def test_dmarc_fail_no_abre(self):
        raw = correo(extra={'Authentication-Results': 'mx.google.com; dmarc=fail (p=NONE) header.from=cliente.com'})
        estado, motivo = procesar_mensaje(raw)
        self.assertEqual(estado, 'ignorado')
        self.assertIn('DMARC', motivo)

    def test_correo_de_la_propia_cuenta_no_abre(self):
        raw = correo(remitente='soporte@psyware.com')
        self.assertEqual(procesar_mensaje(raw, cuenta_propia='soporte@psyware.com')[0], 'ignorado')

    def test_solo_html_se_convierte_a_texto(self):
        msg = PyEmailMessage()
        msg['Subject'] = 'TICKET DE SOPORTE'
        msg['From'] = 'soporte@cliente.com'
        msg['Message-ID'] = '<html1@cliente.com>'
        msg.set_content('<p>Hola</p><p>Se cayó el <b>servidor</b></p>', subtype='html')
        estado, ticket = procesar_mensaje(msg.as_bytes())
        self.assertEqual(estado, 'creado')
        self.assertIn('Se cayó el servidor', ticket.descripcion)
        self.assertNotIn('<', ticket.descripcion)

    def test_fecha_desfasada_usa_hora_actual(self):
        estado, ticket = procesar_mensaje(correo(fecha='Mon, 01 Jan 2001 10:00:00 -0300'))
        self.assertEqual(estado, 'creado')
        self.assertEqual(ticket.fecha_inicio.year, datetime.now().year)


@override_settings(EMAIL_BACKEND=EMAIL_BACKEND_MEM)
class AcuseTests(BaseCorreo):
    def test_acuse_ticket_recibido_con_numero(self):
        _, ticket = procesar_mensaje(correo())
        with patch('tickets.emailing.conexion_smtp_cuenta', return_value=mail.get_connection()):
            exito, _ = enviar_acuse_recibo(ticket)
        self.assertTrue(exito)
        self.assertEqual(len(mail.outbox), 1)
        enviado = mail.outbox[0]
        self.assertEqual(enviado.subject, ASUNTO_ACUSE)
        self.assertEqual(enviado.subject, 'TICKET recibido')
        self.assertEqual(enviado.to, ['soporte@cliente.com'])
        self.assertIn(f'Ticket recibido N° {ticket.numero}', enviado.body)
        self.assertIn('04/11/2026 a las 15:30', enviado.body)
        self.assertEqual(enviado.from_email, 'Soporte Psyware <soporte@psyware.com>')
        self.assertEqual(enviado.extra_headers['In-Reply-To'], '<abc123@cliente.com>')
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.acuse_enviado)


class CuentaSoporteTests(TestCase):
    def test_sin_cuenta_de_soporte_usa_la_de_facturas(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_remitente = 'facturas@psyware.com'
        empresa.email_password = cifrar('x')
        empresa.save()
        cuenta = empresa.cuenta_soporte()
        self.assertEqual(cuenta.usuario, 'facturas@psyware.com')
        self.assertEqual(cuenta.password, 'x')
        self.assertEqual(cuenta.imap_host, 'imap.gmail.com')

    def test_con_cuenta_de_soporte_propia(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_remitente = 'facturas@psyware.com'
        empresa.soporte_email = 'soporte@psyware.com'
        empresa.soporte_password = cifrar('y')
        empresa.save()
        cuenta = empresa.cuenta_soporte()
        self.assertEqual(cuenta.usuario, 'soporte@psyware.com')
        self.assertEqual(cuenta.password, 'y')
        self.assertTrue(cuenta.configurada)


def imap_falso(mensajes):
    """IMAP4_SSL simulado con {uid: bytes} sin leer."""
    imap = MagicMock()
    imap.login.return_value = ('OK', [b''])
    imap.select.return_value = ('OK', [b'1'])
    marcados = []

    def uid(cmd, *args):
        if cmd == 'search':
            return 'OK', [b' '.join(mensajes.keys())]
        if cmd == 'fetch':
            return 'OK', [(b'1 (BODY[] {n}', mensajes[args[0]]), b')']
        if cmd == 'store':
            marcados.append(args[0])
            return 'OK', [b'']
        raise AssertionError(cmd)

    imap.uid.side_effect = uid
    imap.marcados = marcados
    return imap


@override_settings(EMAIL_BACKEND=EMAIL_BACKEND_MEM)
class RevisarBandejaTests(BaseCorreo):
    def test_flujo_completo(self):
        imap = imap_falso({
            b'10': correo(),
            b'11': correo(remitente='spam@x.com', message_id='<2@x.com>'),
        })
        with patch('tickets.correo_entrante.imaplib.IMAP4_SSL', return_value=imap) as ctor, \
             patch('tickets.emailing.conexion_smtp_cuenta', return_value=mail.get_connection()):
            resultado = revisar_bandeja()

        self.assertEqual(resultado.error, '')
        self.assertEqual(len(resultado.creados), 1)
        self.assertEqual(resultado.ignorados, 1)
        ctor.assert_called_once()
        imap.login.assert_called_once_with('soporte@psyware.com', 'clave-app')
        # Solo el correo válido se marca como leído; el desconocido queda sin leer.
        self.assertEqual(imap.marcados, [b'10'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'TICKET recibido')

    def test_acuse_fallido_se_reintenta_en_la_siguiente_revision(self):
        imap = imap_falso({b'10': correo()})
        conexion_rota = MagicMock()
        conexion_rota.send_messages.side_effect = OSError('sin internet')
        with patch('tickets.correo_entrante.imaplib.IMAP4_SSL', return_value=imap), \
             patch('tickets.emailing.conexion_smtp_cuenta', return_value=conexion_rota):
            resultado = revisar_bandeja()
        self.assertEqual(resultado.acuses_fallidos, 1)
        self.assertIsNone(Ticket.objects.get().acuse_enviado)

        with patch('tickets.correo_entrante.imaplib.IMAP4_SSL', return_value=imap_falso({})), \
             patch('tickets.emailing.conexion_smtp_cuenta', return_value=mail.get_connection()):
            resultado = revisar_bandeja()
        self.assertEqual(resultado.acuses_fallidos, 0)
        self.assertIsNotNone(Ticket.objects.get().acuse_enviado)
        self.assertEqual(len(mail.outbox), 1)

    def test_error_imap_no_lanza(self):
        with patch('tickets.correo_entrante.imaplib.IMAP4_SSL', side_effect=OSError('conexión rechazada')):
            resultado = revisar_bandeja()
        self.assertIn('conexión rechazada', resultado.error)

    def test_sin_cuenta_configurada(self):
        empresa = EmpresaConfig.get_config()
        empresa.soporte_email = ''
        empresa.email_remitente = ''
        empresa.save()
        self.assertIn('No hay una cuenta de soporte', revisar_bandeja().error)

    def test_boton_revisar_correo(self):
        User.objects.create_user('admin', password='x')
        self.client.login(username='admin', password='x')
        with patch('tickets.correo_entrante.imaplib.IMAP4_SSL', return_value=imap_falso({b'1': correo()})), \
             patch('tickets.emailing.conexion_smtp_cuenta', return_value=mail.get_connection()):
            resp = self.client.post(reverse('revisar_correo_tickets'), follow=True)
        self.assertContains(resp, '1 ticket(s) nuevo(s)')
        self.assertContains(resp, 'TICKET DE SOPORTE')


class HiloTests(TestCase):
    def test_solo_en_el_proceso_hijo_de_runserver(self):
        self.assertFalse(debe_iniciar_hilo(['manage.py', 'migrate'], {}))
        self.assertFalse(debe_iniciar_hilo(['manage.py', 'test'], {}))
        self.assertFalse(debe_iniciar_hilo(['manage.py', 'runserver', '127.0.0.1:8000'], {}))
        self.assertTrue(debe_iniciar_hilo(['manage.py', 'runserver', '127.0.0.1:8000'], {'RUN_MAIN': 'true'}))
        self.assertTrue(debe_iniciar_hilo(['manage.py', 'runserver', '--noreload'], {}))
        self.assertFalse(debe_iniciar_hilo(['manage.py', 'runserver', '--noreload'], {'FACTUPSYWARE_SIN_CORREO': '1'}))

    def test_lock_evita_revisiones_simultaneas(self):
        correo_entrante._lock.acquire()
        try:
            self.assertIn('Ya se está revisando', revisar_bandeja().error)
        finally:
            correo_entrante._lock.release()


class ErroresImapTests(TestCase):
    def _cuenta(self, host='imap.gmail.com'):
        from arca.mailer import CuentaCorreo
        return CuentaCorreo('fernando@psyware.ar', 'x', 'F', 'smtp.gmail.com', 587, True, host, 993)

    def test_lookup_failed_en_gmail_sugiere_servidor_del_hosting(self):
        from .correo_entrante import explicar_error_imap
        import imaplib
        ayuda = explicar_error_imap(imaplib.IMAP4.error("b'Lookup failed 956f'"), self._cuenta())
        self.assertIn('mail.psyware.ar', ayuda)

    def test_smtp_465_usa_ssl_directo(self):
        from arca.mailer import CuentaCorreo, conexion_smtp_cuenta
        c = conexion_smtp_cuenta(CuentaCorreo('a@b.ar', 'x', '', 'mail.b.ar', 465, True, 'mail.b.ar', 993))
        self.assertTrue(c.use_ssl)
        self.assertFalse(c.use_tls)
        c = conexion_smtp_cuenta(CuentaCorreo('a@b.ar', 'x', '', 'mail.b.ar', 587, True, 'mail.b.ar', 993))
        self.assertTrue(c.use_tls)
        self.assertFalse(c.use_ssl)
