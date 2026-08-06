from django.urls import path

from . import views

app_name = "ventas"

urlpatterns = [
    path("clientes/", views.cliente_lista, name="cliente_lista"),
    path("clientes/nuevo/", views.cliente_form, name="cliente_crear"),
    path("clientes/nuevo-rapido/", views.cliente_crear_rapido, name="cliente_crear_rapido"),
    path("clientes/<int:pk>/editar/", views.cliente_form, name="cliente_editar"),
    path("ventas/", views.venta_lista, name="venta_lista"),
    path("ventas/nueva/", views.venta_crear, name="venta_crear"),
    path("ventas/<int:pk>/", views.venta_detalle, name="venta_detalle"),
    path("ventas/<int:pk>/editar/", views.venta_editar, name="venta_editar"),
    path("ventas/<int:pk>/confirmar/", views.venta_confirmar, name="venta_confirmar"),
    path("ventas/<int:pk>/anular/", views.venta_anular, name="venta_anular"),
    path("ventas/<int:pk>/facturar/", views.venta_facturar, name="venta_facturar"),
    path("ventas/<int:pk>/corregir-factura/", views.venta_corregir_factura, name="venta_corregir_factura"),
    path("cotizaciones/", views.cotizacion_lista, name="cotizacion_lista"),
    path("cotizaciones/nueva/", views.cotizacion_crear, name="cotizacion_crear"),
    path("cotizaciones/<int:pk>/", views.cotizacion_detalle, name="cotizacion_detalle"),
    path("cotizaciones/<int:pk>/editar/", views.cotizacion_editar, name="cotizacion_editar"),
    path("cotizaciones/<int:pk>/enviar/", views.cotizacion_marcar_enviada, name="cotizacion_marcar_enviada"),
    path("cotizaciones/<int:pk>/aceptar/", views.cotizacion_marcar_aceptada, name="cotizacion_marcar_aceptada"),
    path("cotizaciones/<int:pk>/rechazar/", views.cotizacion_marcar_rechazada, name="cotizacion_marcar_rechazada"),
    path("cotizaciones/<int:pk>/convertir/", views.cotizacion_convertir_venta, name="cotizacion_convertir_venta"),
    path("cotizaciones/<int:pk>/imprimir/", views.cotizacion_imprimir, name="cotizacion_imprimir"),
]
