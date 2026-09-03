from django.urls import path

from . import views

app_name = "bitacora"

urlpatterns = [
    path("", views.sede_lista, name="sede_lista"),
    path("nueva/", views.sede_form, name="sede_crear"),
    path("<int:pk>/editar/", views.sede_form, name="sede_editar"),
    path("<int:pk>/", views.sede_detalle, name="sede_detalle"),
    path("<int:pk>/items/nuevo/", views.item_crear, name="item_crear"),
    path("<int:pk>/items/<int:item_pk>/eliminar/", views.item_eliminar, name="item_eliminar"),
    path("<int:pk>/exportar/excel/", views.sede_exportar_excel, name="sede_exportar_excel"),
    path("<int:pk>/exportar/pdf/", views.sede_exportar_pdf, name="sede_exportar_pdf"),
    path("<int:pk>/generar/cuenta-cobro/", views.sede_generar_cuenta_cobro, name="sede_generar_cuenta_cobro"),
    path("<int:pk>/generar/cotizacion/", views.sede_generar_cotizacion, name="sede_generar_cotizacion"),
]
