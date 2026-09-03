from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Sede(models.Model):
    """Una sede o ubicación física de un cliente (ej. una sucursal, una obra,
    un punto de atención). Un mismo cliente puede tener varias, y cada una
    lleva su propia bitácora de trabajo diario."""

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    cliente = models.ForeignKey(
        "ventas.Cliente", on_delete=models.PROTECT, related_name="sedes",
    )
    nombre = models.CharField(max_length=150)
    direccion = models.CharField(max_length=200, blank=True)
    activa = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Sede"
        verbose_name_plural = "Sedes"
        ordering = ["cliente__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["cliente", "nombre"], name="sede_nombre_unica_por_cliente"),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.cliente})"

    def get_absolute_url(self):
        return reverse("bitacora:sede_detalle", args=[self.pk])


class ItemBitacora(models.Model):
    """Una entrada de la hoja de trabajo diario: algo que se presentó en el
    día a día en una sede y hay que dejar registrado, para luego facturarlo
    o cotizarlo sin tener que reconstruir la lista de memoria."""

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    sede = models.ForeignKey(Sede, on_delete=models.CASCADE, related_name="items")
    fecha = models.DateField(default=timezone.localdate)
    descripcion = models.CharField("Descripción del trabajo", max_length=300)
    unidad = models.CharField(max_length=20, blank=True, default="un")
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1"))
    valor_unitario = models.DecimalField("Valor unitario", max_digits=12, decimal_places=2, default=Decimal("0"))
    notas = models.CharField(
        "Notas", max_length=300, blank=True,
        help_text="Ej. estado de la factura, observaciones internas.",
    )
    cotizacion = models.ForeignKey(
        "ventas.Cotizacion", on_delete=models.SET_NULL, null=True, blank=True, related_name="items_bitacora",
    )
    cuenta_cobro = models.ForeignKey(
        "ventas.CuentaCobro", on_delete=models.SET_NULL, null=True, blank=True, related_name="items_bitacora",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="items_bitacora"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ítem de bitácora"
        verbose_name_plural = "Ítems de bitácora"
        ordering = ["-fecha", "-creado_en"]

    def __str__(self):
        return f"{self.descripcion} ({self.sede})"

    # IVA de referencia para la vista previa del ítem (misma tarifa general fija
    # que usan las facturas/cotizaciones). No se cobra aquí: es solo para que la
    # hoja muestre de una vez cuánto daría el ítem si termina en una factura,
    # igual que la columna IVA del formato de la hoja de cálculo original.
    IVA_PORCENTAJE = Decimal("19")

    @property
    def subtotal(self):
        return self.cantidad * self.valor_unitario

    @property
    def iva(self):
        return (self.subtotal * self.IVA_PORCENTAJE / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def valor_total(self):
        return self.subtotal + self.iva

    @property
    def facturado(self):
        return bool(self.cotizacion_id or self.cuenta_cobro_id)
