from .models import EmpresaConfig


def empresa(request):
    return {'empresa_config': EmpresaConfig.get_config()}
