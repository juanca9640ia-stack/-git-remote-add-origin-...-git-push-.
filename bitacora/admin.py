from django.contrib import admin

from .models import ItemBitacora, Sede


@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ["nombre", "cliente", "activa", "creado_en"]
    list_filter = ["activa"]
    search_fields = ["nombre", "cliente__nombre"]


@admin.register(ItemBitacora)
class ItemBitacoraAdmin(admin.ModelAdmin):
    list_display = ["descripcion", "sede", "fecha", "cantidad", "valor_unitario", "facturado"]
    list_filter = ["fecha"]
    search_fields = ["descripcion", "sede__nombre"]
