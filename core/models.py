import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone


def logo_upload_to(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    # Nombre único por archivo (no por empresa): con multiempresa, varias empresas suben
    # logos a la vez y un nombre fijo como antes ("empresa/logo.png") haría que una le
    # pisara el archivo a la otra.
    return f"empresa/{uuid.uuid4().hex}.{extension}"


class Empresa(models.Model):
    """Una empresa (inquilino) de la plataforma.

    Cada empresa tiene su propia configuración, usuarios y datos de negocio,
    aislados del resto. Hasta la Fase 0 esto era un singleton (pk=1 fijo); ahora
    puede haber muchas filas, una por cliente de la plataforma.
    """

    MONEDA_CHOICES = [
        ("COP", "Peso colombiano (COP)"),
        ("USD", "Dólar estadounidense (USD)"),
        ("EUR", "Euro (EUR)"),
        ("MXN", "Peso mexicano (MXN)"),
    ]

    nombre = models.CharField(max_length=150, default="ERP Gestión")
    nit = models.CharField("NIT/Documento", max_length=30, blank=True)
    direccion = models.CharField(max_length=200, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    moneda = models.CharField(max_length=3, choices=MONEDA_CHOICES, default="COP")
    logo = models.ImageField(
        upload_to=logo_upload_to, blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "webp"])],
        help_text="PNG, JPG o WEBP. Máximo 2 MB.",
    )
    activa = models.BooleanField(
        "Activa", default=True,
        help_text="Una empresa inactiva no permite iniciar sesión a sus usuarios.",
    )
    creado_en = models.DateTimeField(default=timezone.now)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        permissions = [
            ("ver_dashboard", "Puede ver el dashboard general"),
        ]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if self.pk:
            anterior = Empresa.objects.filter(pk=self.pk).first()
            if anterior and anterior.logo and self.logo != anterior.logo:
                anterior.logo.delete(save=False)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Una empresa con datos de negocio asociados nunca se borra en cascada por
        # accidente; el ciclo de vida real (desactivar/dar de baja) se maneja aparte.
        pass

    @classmethod
    def get_solo(cls):
        """Compatibilidad retro (Fase 0, en migración a multiempresa).

        Antes del modelo multiempresa, esto era LA empresa. Hoy devuelve la empresa
        semilla (Inversiones Jasda, pk=1) para las vistas que todavía no se han
        actualizado a usar `request.empresa`. Se retira cuando la Fase 0.2 termine
        de recorrer todas las vistas.
        """
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class PerfilUsuario(models.Model):
    """A qué empresa pertenece cada usuario, y si puede operar la plataforma completa."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil",
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="usuarios")
    es_superadmin_plataforma = models.BooleanField(
        "Superadministrador de la plataforma", default=False,
        help_text="Puede operar y cambiar entre todas las empresas registradas (uso interno del operador de la plataforma, no de un cliente).",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Perfil de usuario"
        verbose_name_plural = "Perfiles de usuario"

    def __str__(self):
        return f"{self.usuario} · {self.empresa}"
