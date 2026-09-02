from django.contrib import admin

from .models import Documento


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "categoria", "proyecto", "cliente", "empresa", "creado_en")
    search_fields = ("titulo",)
    list_filter = ("categoria", "empresa")
