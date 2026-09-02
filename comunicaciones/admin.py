from django.contrib import admin

from .models import Comunicado


@admin.register(Comunicado)
class ComunicadoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "fijado", "publicado_por", "empresa", "creado_en")
    list_filter = ("fijado", "empresa")
    search_fields = ("titulo", "cuerpo")
