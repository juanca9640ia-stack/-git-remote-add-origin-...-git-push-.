from django.conf import settings
from django.db import models


class Comunicado(models.Model):
    """Cartelera interna de la empresa: anuncios visibles para todos los
    usuarios autenticados, independientemente del módulo al que tengan
    acceso (a diferencia del resto del sistema, esto es a propósito)."""

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    titulo = models.CharField(max_length=200)
    cuerpo = models.TextField()
    fijado = models.BooleanField(
        "Fijado", default=False, help_text="Los comunicados fijados siempre aparecen primero.",
    )
    publicado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="comunicados_publicados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comunicado"
        verbose_name_plural = "Comunicados"
        ordering = ["-fijado", "-creado_en"]

    def __str__(self):
        return self.titulo
