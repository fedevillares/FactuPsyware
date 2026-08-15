"""
Tests de las barreras de seguridad del panel de backup/restauración.

No tocan la base de datos real: la vista de importación se corta en las
validaciones (confirmación, extensión, magic bytes) antes de escribir nada.
"""
import base64
import io
from io import BytesIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from arca.admin import EmpresaConfigForm
from arca.crypto import cifrar, descifrar
from arca.models import EmpresaConfig


def archivo_sqlite_falso(nombre='backup_test.sqlite3', contenido=b'SQLite format 3\x00' + b'\x00' * 100):
    return SimpleUploadedFile(nombre, contenido, content_type='application/octet-stream')


class ImportarDbGuardasTests(TestCase):
    """La restauración de la base exige re-autenticación y confirmación explícita del servidor."""

    def setUp(self):
        self.password = 'clave-de-test'
        self.user = User.objects.create_user('tester', password=self.password)
        self.client.force_login(self.user)
        self.url = reverse('importar_db')

    def test_sin_login_redirige(self):
        self.client.logout()
        respuesta = self.client.post(self.url, {})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/accounts/login/', respuesta['Location'])

    def test_get_no_permitido(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 405)

    def test_sin_password_rechazado(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(),
            'confirmacion': 'RESTAURAR',
        }, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')

    def test_password_incorrecta_rechazada(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(),
            'confirmacion': 'RESTAURAR',
            'clave_confirmacion': 'no-es-la-clave',
        }, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')

    def test_sin_confirmacion_rechazado(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(),
            'clave_confirmacion': self.password,
        }, follow=True)
        self.assertContains(respuesta, 'RESTAURAR')

    def test_confirmacion_incorrecta_rechazada(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(),
            'confirmacion': 'restaurar ya',
            'clave_confirmacion': self.password,
        }, follow=True)
        self.assertContains(respuesta, 'RESTAURAR')

    def test_extension_invalida_rechazada(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(nombre='cualquiercosa.txt'),
            'confirmacion': 'RESTAURAR',
            'clave_confirmacion': self.password,
        }, follow=True)
        self.assertContains(respuesta, '.sqlite3')

    def test_contenido_no_sqlite_rechazado(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(contenido=b'no soy una base de datos'),
            'confirmacion': 'RESTAURAR',
            'clave_confirmacion': self.password,
        }, follow=True)
        self.assertContains(respuesta, 'no es una base de datos SQLite')


class ExportarDbGuardasTests(TestCase):
    """La descarga de la base exige re-autenticación."""

    def setUp(self):
        self.password = 'clave-de-test'
        self.user = User.objects.create_user('tester2', password=self.password)
        self.client.force_login(self.user)
        self.url = reverse('exportar_db')

    def test_sin_login_redirige(self):
        self.client.logout()
        respuesta = self.client.post(self.url, {})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/accounts/login/', respuesta['Location'])

    def test_get_no_permitido(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 405)

    def test_sin_password_rechazado(self):
        respuesta = self.client.post(self.url, {}, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')

    def test_password_incorrecta_rechazada(self):
        respuesta = self.client.post(self.url, {'clave_confirmacion': 'no-es-la-clave'}, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')

    def test_password_correcta_descarga(self):
        from django.conf import settings
        if not (settings.BASE_DIR / 'db.sqlite3').exists():
            self.skipTest('No hay db.sqlite3 en este entorno de test.')
        respuesta = self.client.post(self.url, {'clave_confirmacion': self.password})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/x-sqlite3')


class EliminarBackupGuardasTests(TestCase):
    """El borrado de backups no debe permitir path traversal."""

    def setUp(self):
        self.user = User.objects.create_user('tester', password='clave-de-test')
        self.client.force_login(self.user)
        self.url = reverse('eliminar_backup')

    def test_nombre_con_ruta_rechazado(self):
        for nombre in ['../db.sqlite3', 'backup_../../db.sqlite3', 'db.sqlite3', '']:
            respuesta = self.client.post(self.url, {'nombre': nombre}, follow=True)
            # Nunca debe reportar éxito de borrado para nombres inválidos
            self.assertNotContains(respuesta, 'eliminado')


class GuardarBackupLocalGuardasTests(TestCase):
    """Guardar una copia local exige re-autenticación, igual que exportar/importar."""

    def setUp(self):
        self.password = 'clave-de-test'
        self.user = User.objects.create_user('tester_guardar', password=self.password)
        self.client.force_login(self.user)
        self.url = reverse('guardar_backup_local')

    def test_sin_login_redirige(self):
        self.client.logout()
        respuesta = self.client.post(self.url, {})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/accounts/login/', respuesta['Location'])

    def test_get_no_permitido(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 405)

    def test_sin_password_rechazado(self):
        respuesta = self.client.post(self.url, {}, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')

    def test_password_incorrecta_rechazada(self):
        respuesta = self.client.post(self.url, {'clave_confirmacion': 'no-es-la-clave'}, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')


class DescargarBackupLocalGuardasTests(TestCase):
    """Descargar un backup local exige re-autenticación, igual que exportar la DB en vivo."""

    def setUp(self):
        self.password = 'clave-de-test'
        self.user = User.objects.create_user('tester_descargar', password=self.password)
        self.client.force_login(self.user)
        self.url = reverse('descargar_backup_local')

    def test_sin_login_redirige(self):
        self.client.logout()
        respuesta = self.client.post(self.url, {})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/accounts/login/', respuesta['Location'])

    def test_get_no_permitido(self):
        respuesta = self.client.get(self.url, {'nombre': 'backup_x.sqlite3'})
        self.assertEqual(respuesta.status_code, 405)

    def test_sin_password_rechazado(self):
        respuesta = self.client.post(self.url, {'nombre': 'backup_x.sqlite3'}, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')

    def test_password_incorrecta_rechazada(self):
        respuesta = self.client.post(self.url, {'nombre': 'backup_x.sqlite3', 'clave_confirmacion': 'no-es-la-clave'}, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')


class CifradoPasswordTests(TestCase):
    def test_roundtrip(self):
        self.assertEqual(descifrar(cifrar('mi-clave-secreta')), 'mi-clave-secreta')

    def test_cifrar_vacio_devuelve_vacio(self):
        self.assertEqual(cifrar(''), '')
        self.assertEqual(cifrar(None), '')

    def test_descifrar_vacio_devuelve_vacio(self):
        self.assertEqual(descifrar(''), '')
        self.assertEqual(descifrar(None), '')

    def test_descifrar_valor_invalido_devuelve_vacio(self):
        self.assertEqual(descifrar('esto-no-es-un-token-valido'), '')

    def test_dos_cifrados_del_mismo_texto_son_distintos(self):
        # Fernet incluye un IV aleatorio: no debe ser determinista.
        self.assertNotEqual(cifrar('hola'), cifrar('hola'))


class EmpresaConfigEmailPasswordTests(TestCase):
    def test_email_password_plano_descifra(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_password = cifrar('appsecret123')
        empresa.save(update_fields=['email_password'])
        self.assertEqual(empresa.email_password_plano, 'appsecret123')

    def test_email_password_plano_vacio_si_no_hay_password(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_password = ''
        empresa.save(update_fields=['email_password'])
        self.assertEqual(empresa.email_password_plano, '')

    def test_no_configurado_si_password_no_descifra(self):
        from arca.mailer import empresa_tiene_email_configurado
        empresa = EmpresaConfig.get_config()
        empresa.email_remitente = 'test@example.com'
        empresa.email_password = 'esto-no-es-un-token-fernet-valido'
        empresa.save(update_fields=['email_remitente', 'email_password'])
        self.assertFalse(empresa_tiene_email_configurado(empresa))


class EmpresaConfigFormPasswordTests(TestCase):
    def _datos_minimos(self, **overrides):
        datos = {
            'razon_social': 'Test SRL', 'cuit': '20111222339',
            'condicion_iva': 'IVA Responsable Inscripto',
            'domicilio': 'Calle Falsa 123', 'localidad': 'CABA',
            'punto_venta_defecto': 1, 'otros_impuestos_pct': '0',
        }
        datos.update(overrides)
        return datos

    def test_dejar_en_blanco_preserva_password_existente(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_password = cifrar('claveOriginal')
        empresa.save(update_fields=['email_password'])
        cifrado_original = empresa.email_password

        form = EmpresaConfigForm(data=self._datos_minimos(email_password=''), instance=empresa)
        self.assertTrue(form.is_valid(), form.errors)
        guardado = form.save()

        self.assertEqual(guardado.email_password, cifrado_original)
        self.assertEqual(guardado.email_password_plano, 'claveOriginal')

    def test_escribir_nueva_password_la_cifra(self):
        empresa = EmpresaConfig.get_config()
        form = EmpresaConfigForm(data=self._datos_minimos(email_password='claveNueva'), instance=empresa)
        self.assertTrue(form.is_valid(), form.errors)
        guardado = form.save()
        self.assertEqual(guardado.email_password_plano, 'claveNueva')
        self.assertNotEqual(guardado.email_password, 'claveNueva')


class LogoValidacionTests(TestCase):
    def _empresa_valida(self):
        # get_config() crea el singleton con domicilio/localidad vacios (campos
        # obligatorios, sin blank=True); full_clean() los rechaza siempre a menos
        # que se completen aca, lo que enmascararia si el rechazo viene del logo
        # o de estos otros campos.
        empresa = EmpresaConfig.get_config()
        empresa.domicilio = 'Calle Falsa 123'
        empresa.localidad = 'CABA'
        return empresa

    def test_extension_invalida_rechazada(self):
        empresa = self._empresa_valida()
        empresa.logo = SimpleUploadedFile('logo.html', b'<html></html>', content_type='text/html')
        with self.assertRaises(ValidationError):
            empresa.full_clean()

    def test_extension_valida_aceptada(self):
        png_1x1 = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
        )
        empresa = self._empresa_valida()
        empresa.logo = SimpleUploadedFile('logo.png', png_1x1, content_type='image/png')
        empresa.full_clean()  # no debe lanzar

    def test_archivo_muy_grande_rechazado(self):
        # Ruido aleatorio: no comprime bien en PNG, asegura que el archivo
        # resultante realmente supere el limite (una imagen de color solido
        # comprimiria a unos pocos KB y el test no probaria nada real).
        import os as os_module
        ruido = os_module.urandom(1600 * 1600 * 3)
        img = Image.frombytes('RGB', (1600, 1600), ruido)
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        contenido = buffer.getvalue()
        self.assertGreater(len(contenido), 5 * 1024 * 1024, "el PNG de prueba debe superar el limite para que el test tenga sentido")

        empresa = self._empresa_valida()
        empresa.logo = SimpleUploadedFile('logo.png', contenido, content_type='image/png')
        with self.assertRaises(ValidationError):
            empresa.full_clean()
