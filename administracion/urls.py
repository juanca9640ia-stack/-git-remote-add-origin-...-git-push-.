from django.urls import path

from . import views

app_name = "administracion"

urlpatterns = [
    path("empresa/", views.empresa_editar, name="empresa_editar"),
    path("cambiar-empresa/", views.cambiar_empresa, name="cambiar_empresa"),
    path("usuarios/", views.usuario_lista, name="usuario_lista"),
    path("usuarios/nuevo/", views.usuario_crear, name="usuario_crear"),
    path("usuarios/<int:pk>/editar/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/activar/", views.usuario_toggle_activo, name="usuario_toggle_activo"),
    path("usuarios/<int:pk>/password/", views.usuario_cambiar_password, name="usuario_cambiar_password"),
    path("auditoria/", views.auditoria_lista, name="auditoria_lista"),
    path("roles/", views.rol_lista, name="rol_lista"),
    path("roles/nuevo/", views.rol_form, name="rol_crear"),
    path("roles/<int:pk>/editar/", views.rol_form, name="rol_editar"),
    path("roles/<int:pk>/eliminar/", views.rol_eliminar, name="rol_eliminar"),
]
