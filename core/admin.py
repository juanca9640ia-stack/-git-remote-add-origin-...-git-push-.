from django.contrib import admin

from .models import Empresa


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "nit", "moneda", "actualizado_en")

    def has_add_permission(self, request):
        return not Empresa.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
