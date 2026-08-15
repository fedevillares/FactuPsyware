from django.contrib import admin
from django.urls import path, re_path, include
from django.views.generic import RedirectView
from django.contrib.staticfiles.views import serve as serve_static
from django.views.static import serve as serve_media
from django.contrib.auth import views as auth_views
from django.conf import settings


class CustomLoginView(auth_views.LoginView):
    template_name = 'registration/login.html'

    def get_success_url(self):
        return self.get_redirect_url() or '/facturas/'


urlpatterns = [
    path('admin/', admin.site.urls),
    path('facturas/', include('facturas.urls')),
    path('clientes/', include('clientes.urls')),
    path('servicios/', include('servicios.urls')),
    path('tickets/', include('tickets.urls')),
    path('crm/', include('crm.urls')),
    path('arca/', include('arca.urls')),
    path('accounts/login/', CustomLoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(
        next_page='login', http_method_names=['get', 'post']
    ), name='logout'),
    path('', RedirectView.as_view(url='facturas/', permanent=False)),
]

# Archivos estáticos (sin autenticación: CSS, JS, imágenes de la UI)
# Necesario porque DEBUG=False y no hay servidor web delante.
urlpatterns += [
    re_path(r'^static/(?P<path>.*)$', serve_static, {'insecure': True}),
]

# Archivos de media (logo de EmpresaConfig) — sin autenticación, igual que los
# estáticos: el logo se muestra en la pantalla de login (antes de estar
# autenticado), así que no puede requerir sesión o el navegador lo pide,
# recibe el redirect a /accounts/login/ y muestra el texto alternativo en su
# lugar (además de desacomodar el layout de la tarjeta de login).
urlpatterns += [
    re_path(
        r'^media/(?P<path>.*)$',
        serve_media,
        {'document_root': settings.MEDIA_ROOT},
    ),
]
