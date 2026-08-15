from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.contrib.auth import views as auth_views


class CustomLoginView(auth_views.LoginView):
    template_name = 'registration/login.html'

    def get_success_url(self):
        return '/admin/'


admin.site.login = CustomLoginView.as_view()

urlpatterns = [
    path('admin/', admin.site.urls),
    path('facturas/', include('facturas.urls')),
    path('servicios/', include('servicios.urls')),
    path('arca/', include('arca.urls')),
    path('accounts/login/', CustomLoginView.as_view(), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login', http_method_names=['get', 'post']), name='logout'),
    path('', RedirectView.as_view(url='admin/', permanent=False)),
]