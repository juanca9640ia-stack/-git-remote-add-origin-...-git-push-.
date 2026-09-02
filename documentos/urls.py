from django.urls import path

from . import views

app_name = "documentos"

urlpatterns = [
    path("", views.documento_lista, name="documento_lista"),
    path("subir/", views.documento_subir, name="documento_subir"),
    path("<int:pk>/eliminar/", views.documento_eliminar, name="documento_eliminar"),
]
