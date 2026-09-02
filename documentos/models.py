import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

EXTENSIONES_PERMITIDAS = [
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "jpg", "jpeg", "png", "webp", "dwg", "zip",
]
TAMANO_MAXIMO_MB = 20


def documento_upload_to(instance, filename):
    # Nombre único por archivo (no reutiliza el nombre original): evita choques
    # entre empresas/usuarios y que alguien adivine rutas de otros documentos.
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    nombre = uuid.uuid4().hex
    return f"documentos/{nombre}.{extension}" if extension else f"documentos/{nombre}"


def validar_tamano_archivo(archivo):
    limite = TAMANO_MAXIMO_MB * 1024 * 1024
    if archivo.size > limite:
        raise ValidationError(f"El archivo pesa más de {TAMANO_MAXIMO_MB} MB.")


class Documento(models.Model):
    CONTRATO = "contrato"
    PLANO = "plano"
    PERMISO = "permiso"
    FACTURA = "factura"
    OTRO = "otro"
    CATEGORIA_CHOICES = [
        (CONTRATO, "Contrato"),
        (PLANO, "Plano"),
        (PERMISO, "Permiso / licencia"),
        (FACTURA, "Factura / soporte"),
        (OTRO, "Otro"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    titulo = models.CharField(max_length=150)
    categoria = models.CharField(max_length=15, choices=CATEGORIA_CHOICES, default=OTRO)
    archivo = models.FileField(
        upload_to=documento_upload_to,
        validators=[FileExtensionValidator(allowed_extensions=EXTENSIONES_PERMITIDAS), validar_tamano_archivo],
        help_text=f"{', '.join(EXTENSIONES_PERMITIDAS)}. Máximo {TAMANO_MAXIMO_MB} MB.",
    )
    tamano_bytes = models.PositiveIntegerField(default=0, editable=False)
    proyecto = models.ForeignKey(
        "proyectos.Proyecto", on_delete=models.CASCADE, null=True, blank=True, related_name="documentos",
        help_text="Opcional: si este documento pertenece a una obra.",
    )
    cliente = models.ForeignKey(
        "ventas.Cliente", on_delete=models.CASCADE, null=True, blank=True, related_name="documentos",
        help_text="Opcional: si este documento pertenece a un cliente.",
    )
    descripcion = models.TextField(blank=True)
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="documentos_subidos"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Documento"
        verbose_name_plural = "Documentos"
        ordering = ["-creado_en"]

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        if self.archivo and not self.tamano_bytes:
            try:
                self.tamano_bytes = self.archivo.size
            except (OSError, ValueError):
                pass
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        archivo = self.archivo
        super().delete(*args, **kwargs)
        if archivo:
            archivo.delete(save=False)

    @property
    def extension(self):
        nombre = self.archivo.name
        return nombre.rsplit(".", 1)[-1].upper() if "." in nombre else ""

    @property
    def tamano_legible(self):
        valor = self.tamano_bytes
        for unidad in ("B", "KB", "MB", "GB"):
            if valor < 1024:
                return f"{valor:.0f} {unidad}" if unidad == "B" else f"{valor:.1f} {unidad}"
            valor /= 1024
        return f"{valor:.1f} TB"
