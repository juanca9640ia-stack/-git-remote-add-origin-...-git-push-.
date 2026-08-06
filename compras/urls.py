from django.urls import path

from . import views

app_name = "compras"

urlpatterns = [
    path("proveedores/", views.proveedor_lista, name="proveedor_lista"),
    path("proveedores/nuevo/", views.proveedor_form, name="proveedor_crear"),
    path("proveedores/nuevo-rapido/", views.proveedor_crear_rapido, name="proveedor_crear_rapido"),
    path("proveedores/<int:pk>/editar/", views.proveedor_form, name="proveedor_editar"),
    path("compras/", views.compra_lista, name="compra_lista"),
    path("compras/nueva/", views.compra_crear, name="compra_crear"),
    path("compras/<int:pk>/", views.compra_detalle, name="compra_detalle"),
    path("compras/<int:pk>/editar/", views.compra_editar, name="compra_editar"),
    path("compras/<int:pk>/confirmar/", views.compra_confirmar, name="compra_confirmar"),
    path("compras/<int:pk>/anular/", views.compra_anular, name="compra_anular"),
]
