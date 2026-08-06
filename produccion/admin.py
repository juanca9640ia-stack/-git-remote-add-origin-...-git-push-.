from django.contrib import admin

from .models import ComponenteBOM, ComponenteOrdenProduccion, ListaMateriales, OrdenProduccion


class ComponenteBOMInline(admin.TabularInline):
    model = ComponenteBOM
    extra = 1


@admin.register(ListaMateriales)
class ListaMaterialesAdmin(admin.ModelAdmin):
    list_display = ("producto", "creado_en")
    search_fields = ("producto__sku", "producto__nombre")
    inlines = [ComponenteBOMInline]


class ComponenteOrdenProduccionInline(admin.TabularInline):
    model = ComponenteOrdenProduccion
    extra = 0
    readonly_fields = ("insumo", "cantidad_requerida")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrdenProduccion)
class OrdenProduccionAdmin(admin.ModelAdmin):
    list_display = ("numero", "producto", "cantidad", "estado", "responsable", "creado_en")
    list_filter = ("estado",)
    search_fields = ("numero", "producto__sku", "producto__nombre")
    date_hierarchy = "creado_en"
    inlines = [ComponenteOrdenProduccionInline]
    readonly_fields = ("numero", "completada_en")
