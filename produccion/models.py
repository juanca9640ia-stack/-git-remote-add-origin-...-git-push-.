from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from inventario.models import MovimientoInventario, Producto, registrar_movimiento


class ListaMateriales(models.Model):
    """Receta: qué insumos y en qué cantidad se necesitan para producir 1 unidad del producto terminado."""

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    producto = models.OneToOneField(Producto, on_delete=models.CASCADE, related_name="lista_materiales")
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lista de materiales"
        verbose_name_plural = "Listas de materiales"

    def __str__(self):
        return f"BOM de {self.producto}"

    def get_absolute_url(self):
        return reverse("produccion:bom_editar", args=[self.pk])


class ComponenteBOM(models.Model):
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    lista = models.ForeignKey(ListaMateriales, on_delete=models.CASCADE, related_name="componentes")
    insumo = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="usado_en_recetas")
    cantidad_por_unidad = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Componente de la receta"
        verbose_name_plural = "Componentes de la receta"
        unique_together = ("lista", "insumo")

    def __str__(self):
        return f"{self.cantidad_por_unidad} x {self.insumo.sku}"

    def clean(self):
        if self.lista_id and self.insumo_id and self.lista.producto_id == self.insumo_id:
            raise ValidationError("Un producto no puede ser insumo de sí mismo.")


class OrdenProduccion(models.Model):
    PLANIFICADA = "planificada"
    COMPLETADA = "completada"
    ANULADA = "anulada"
    ESTADO_CHOICES = [
        (PLANIFICADA, "Planificada"),
        (COMPLETADA, "Completada"),
        (ANULADA, "Anulada"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    numero = models.CharField(max_length=20, blank=True)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="ordenes_produccion")
    cantidad = models.PositiveIntegerField(default=1)
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=PLANIFICADA)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ordenes_produccion"
    )
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    completada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Orden de producción"
        verbose_name_plural = "Órdenes de producción"
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "numero"], name="ordenproduccion_numero_unico_por_empresa"),
        ]

    def __str__(self):
        return self.numero or f"Orden borrador #{self.pk}"

    def get_absolute_url(self):
        return reverse("produccion:orden_detalle", args=[self.pk])

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and not self.numero:
            self.numero = f"OP-{self.pk:06d}"
            super().save(update_fields=["numero"])

    @property
    def editable(self):
        return self.estado == self.PLANIFICADA

    def sincronizar_componentes_desde_receta(self):
        """Recalcula el consumo de insumos requerido según la receta y la cantidad a producir."""
        if not self.editable:
            raise ValidationError("Solo una orden planificada puede recalcular sus componentes.")
        try:
            lista = self.producto.lista_materiales
        except ListaMateriales.DoesNotExist:
            raise ValidationError(f"'{self.producto}' no tiene una lista de materiales definida.")

        self.componentes.all().delete()
        componentes = [
            ComponenteOrdenProduccion(
                empresa=self.empresa, orden=self, insumo=c.insumo,
                cantidad_requerida=c.cantidad_por_unidad * self.cantidad,
            )
            for c in lista.componentes.select_related("insumo")
        ]
        if not componentes:
            raise ValidationError(f"La lista de materiales de '{self.producto}' no tiene componentes.")
        ComponenteOrdenProduccion.objects.bulk_create(componentes)

    @transaction.atomic
    def completar(self, usuario=None):
        """Consume los insumos de la receta y da entrada al producto terminado en el inventario."""
        if self.estado != self.PLANIFICADA:
            raise ValidationError("Solo una orden planificada puede completarse.")

        componentes = list(self.componentes.select_related("insumo"))
        if not componentes:
            raise ValidationError("La orden no tiene componentes definidos.")

        for componente in componentes:
            insumo = Producto.objects.select_for_update().get(pk=componente.insumo_id)
            registrar_movimiento(
                producto=insumo,
                tipo=MovimientoInventario.SALIDA,
                cantidad=componente.cantidad_requerida,
                motivo=MovimientoInventario.MOTIVO_PRODUCCION,
                referencia=self.numero,
                usuario=usuario,
            )

        producto_terminado = Producto.objects.select_for_update().get(pk=self.producto_id)
        registrar_movimiento(
            producto=producto_terminado,
            tipo=MovimientoInventario.ENTRADA,
            cantidad=self.cantidad,
            motivo=MovimientoInventario.MOTIVO_PRODUCCION,
            referencia=self.numero,
            usuario=usuario,
        )

        self.estado = self.COMPLETADA
        self.completada_en = timezone.now()
        self.save(update_fields=["estado", "completada_en"])

    @transaction.atomic
    def anular(self, usuario=None):
        """Anula una orden completada: retira el producto terminado y devuelve los insumos consumidos."""
        if self.estado != self.COMPLETADA:
            raise ValidationError("Solo una orden completada puede anularse.")

        producto_terminado = Producto.objects.select_for_update().get(pk=self.producto_id)
        registrar_movimiento(
            producto=producto_terminado,
            tipo=MovimientoInventario.SALIDA,
            cantidad=self.cantidad,
            motivo=MovimientoInventario.MOTIVO_PRODUCCION,
            referencia=self.numero,
            usuario=usuario,
        )

        for componente in self.componentes.select_related("insumo"):
            insumo = Producto.objects.select_for_update().get(pk=componente.insumo_id)
            registrar_movimiento(
                producto=insumo,
                tipo=MovimientoInventario.ENTRADA,
                cantidad=componente.cantidad_requerida,
                motivo=MovimientoInventario.MOTIVO_PRODUCCION,
                referencia=self.numero,
                usuario=usuario,
            )

        self.estado = self.ANULADA
        self.save(update_fields=["estado"])


class ComponenteOrdenProduccion(models.Model):
    """Snapshot del consumo de insumos requerido por una orden, tomado de la receta al crearla."""

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    orden = models.ForeignKey(OrdenProduccion, on_delete=models.CASCADE, related_name="componentes")
    insumo = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="consumido_en_ordenes")
    cantidad_requerida = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Componente de la orden"
        verbose_name_plural = "Componentes de la orden"

    def __str__(self):
        return f"{self.insumo.sku} x{self.cantidad_requerida}"

    @property
    def stock_suficiente(self):
        return self.insumo.stock_actual >= self.cantidad_requerida
