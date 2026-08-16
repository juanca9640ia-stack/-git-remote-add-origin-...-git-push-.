from django.core.validators import FileExtensionValidator
from django.db import models


def logo_upload_to(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    return f"empresa/logo.{extension}"


class Empresa(models.Model):
    """Configuración general de la empresa. Modelo singleton: siempre hay una única fila (pk=1)."""

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
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Datos de la empresa"
        verbose_name_plural = "Datos de la empresa"
        permissions = [
            ("ver_dashboard", "Puede ver el dashboard general"),
        ]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.pk = 1
        anterior = Empresa.objects.filter(pk=1).first()
        if anterior and anterior.logo and self.logo != anterior.logo:
            anterior.logo.delete(save=False)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
