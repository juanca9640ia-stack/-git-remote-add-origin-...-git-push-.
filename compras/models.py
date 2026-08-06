from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from inventario.models import MovimientoInventario, Producto, registrar_movimiento


class Proveedor(models.Model):
    nombre = models.CharField(max_length=150)
    nit = models.CharField("NIT/Documento", max_length=30, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    direccion = models.CharField(max_length=200, blank=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        return reverse("compras:proveedor_editar", args=[self.pk])


class Compra(models.Model):
    BORRADOR = "borrador"
    CONFIRMADA = "confirmada"
    ANULADA = "anulada"
    ESTADO_CHOICES = [
        (BORRADOR, "Borrador"),
        (CONFIRMADA, "Confirmada"),
        (ANULADA, "Anulada"),
    ]

    numero = models.CharField(max_length=20, unique=True, blank=True)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="compras")
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=BORRADOR)
    impuesto_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="compras"
    )
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    confirmada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Compra"
        verbose_name_plural = "Compras"
        ordering = ["-creado_en"]

    def __str__(self):
        return self.numero or f"Compra borrador #{self.pk}"

    def get_absolute_url(self):
        return reverse("compras:compra_detalle", args=[self.pk])

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and not self.numero:
            self.numero = f"C-{self.pk:06d}"
            super().save(update_fields=["numero"])

    @property
    def subtotal(self):
        return sum((linea.subtotal for linea in self.lineas.all()), Decimal("0"))

    @property
    def impuesto_valor(self):
        return (self.subtotal * self.impuesto_porcentaje / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def total(self):
        return self.subtotal + self.impuesto_valor

    @property
    def editable(self):
        return self.estado == self.BORRADOR

    @transaction.atomic
    def confirmar(self, usuario=None):
        """Confirma la compra: recibe la mercancía y aumenta el stock en tiempo real."""
        if self.estado != self.BORRADOR:
            raise ValidationError("Solo una compra en borrador puede confirmarse.")

        lineas = list(self.lineas.select_related("producto"))
        if not lineas:
            raise ValidationError("La compra no tiene líneas.")

        for linea in lineas:
            producto = Producto.objects.select_for_update().get(pk=linea.producto_id)
            if producto.es_servicio:
                continue
            registrar_movimiento(
                producto=producto,
                tipo=MovimientoInventario.ENTRADA,
                cantidad=linea.cantidad,
                motivo=MovimientoInventario.MOTIVO_COMPRA,
                referencia=self.numero,
                usuario=usuario,
            )

        self.estado = self.CONFIRMADA
        self.confirmada_en = timezone.now()
        self.save(update_fields=["estado", "confirmada_en"])

    @transaction.atomic
    def anular(self, usuario=None):
        """Anula una compra confirmada y retira del inventario lo que había ingresado."""
        if self.estado != self.CONFIRMADA:
            raise ValidationError("Solo una compra confirmada puede anularse.")

        for linea in self.lineas.select_related("producto"):
            producto = Producto.objects.select_for_update().get(pk=linea.producto_id)
            if producto.es_servicio:
                continue
            registrar_movimiento(
                producto=producto,
                tipo=MovimientoInventario.SALIDA,
                cantidad=linea.cantidad,
                motivo=MovimientoInventario.MOTIVO_AJUSTE,
                referencia=self.numero,
                usuario=usuario,
            )

        self.estado = self.ANULADA
        self.save(update_fields=["estado"])


class LineaCompra(models.Model):
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name="lineas")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="lineas_compra")
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Línea de compra"
        verbose_name_plural = "Líneas de compra"

    def __str__(self):
        return f"{self.producto.sku} x{self.cantidad}"

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def clean(self):
        if self.compra_id and not self.compra.editable:
            raise ValidationError("No se puede modificar una compra confirmada o anulada.")
