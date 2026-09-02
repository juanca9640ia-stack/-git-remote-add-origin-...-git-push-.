from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


class Categoria(models.Model):
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    PRODUCTO = "producto"
    SERVICIO = "servicio"
    TIPO_CHOICES = [
        (PRODUCTO, "Producto"),
        (SERVICIO, "Servicio"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    sku = models.CharField("SKU", max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default=PRODUCTO)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="productos",
        null=True, blank=True,
    )
    precio_costo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    precio_venta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stock_actual = models.IntegerField(default=0)
    stock_minimo = models.IntegerField(default=0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.sku} - {self.nombre}"

    def get_absolute_url(self):
        return reverse("inventario:producto_detalle", args=[self.pk])

    @property
    def es_servicio(self):
        return self.tipo == self.SERVICIO

    @property
    def stock_bajo(self):
        if self.es_servicio:
            return False
        return self.stock_actual <= self.stock_minimo

    @property
    def valor_inventario(self):
        return self.stock_actual * self.precio_costo


class MovimientoInventario(models.Model):
    ENTRADA = "entrada"
    SALIDA = "salida"
    TIPO_CHOICES = [
        (ENTRADA, "Entrada"),
        (SALIDA, "Salida"),
    ]

    MOTIVO_COMPRA = "compra"
    MOTIVO_VENTA = "venta"
    MOTIVO_AJUSTE = "ajuste"
    MOTIVO_DEVOLUCION = "devolucion"
    MOTIVO_PRODUCCION = "produccion"
    MOTIVO_CHOICES = [
        (MOTIVO_COMPRA, "Compra a proveedor"),
        (MOTIVO_VENTA, "Venta a cliente"),
        (MOTIVO_AJUSTE, "Ajuste manual"),
        (MOTIVO_DEVOLUCION, "Devolución"),
        (MOTIVO_PRODUCCION, "Producción"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    motivo = models.CharField(max_length=15, choices=MOTIVO_CHOICES, default=MOTIVO_AJUSTE)
    cantidad = models.PositiveIntegerField()
    stock_resultante = models.IntegerField()
    referencia = models.CharField(max_length=100, blank=True, help_text="Ej: número de venta/compra")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Movimiento de inventario"
        verbose_name_plural = "Movimientos de inventario"
        ordering = ["-creado_en"]

    def __str__(self):
        signo = "+" if self.tipo == self.ENTRADA else "-"
        return f"{self.producto.sku} {signo}{self.cantidad} ({self.get_motivo_display()})"

    def clean(self):
        if self.tipo == self.SALIDA and self.producto_id:
            if self.cantidad > self.producto.stock_actual:
                raise ValidationError("No hay suficiente stock para esta salida.")


def registrar_movimiento(producto, tipo, cantidad, motivo, referencia="", usuario=None):
    """Aplica un movimiento de stock sobre un producto y deja trazabilidad.

    Debe llamarse dentro de una transacción con el producto bloqueado
    (select_for_update) cuando se invoca desde flujos concurrentes como ventas.
    """
    if cantidad <= 0:
        raise ValidationError("La cantidad debe ser mayor a cero.")

    if tipo == MovimientoInventario.SALIDA:
        if cantidad > producto.stock_actual:
            raise ValidationError(
                f"Stock insuficiente para {producto.nombre}: disponible {producto.stock_actual}, solicitado {cantidad}."
            )
        producto.stock_actual -= cantidad
    else:
        producto.stock_actual += cantidad

    producto.save(update_fields=["stock_actual", "actualizado_en"])

    return MovimientoInventario.objects.create(
        producto=producto,
        tipo=tipo,
        motivo=motivo,
        cantidad=cantidad,
        stock_resultante=producto.stock_actual,
        referencia=referencia,
        usuario=usuario,
    )
