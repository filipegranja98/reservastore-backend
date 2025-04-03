from django.contrib import admin
from .models import Loja, Categoria, Produto  # Importa os modelos

# Registra os modelos no admin para poder manipulá-los pela interface administrativa
admin.site.register(Loja)
admin.site.register(Categoria)
admin.site.register(Produto)
