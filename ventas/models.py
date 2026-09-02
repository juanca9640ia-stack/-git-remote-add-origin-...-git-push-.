import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from inventario.models import MovimientoInventario, Producto, registrar_movimiento


def _fecha_validez_por_defecto():
    return timezone.localdate() + datetime.timedelta(days=15)


class Cliente(models.Model):
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    nombre = models.CharField(max_length=150)
    documento = models.CharField("NIT/Documento", max_length=30, blank=True)
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
        return reverse("ventas:cliente_editar", args=[self.pk])


class Venta(models.Model):
    BORRADOR = "borrador"
    CONFIRMADA = "confirmada"
    ANULADA = "anulada"
    ESTADO_CHOICES = [
        (BORRADOR, "Borrador"),
        (CONFIRMADA, "Confirmada"),
        (ANULADA, "Anulada"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    numero = models.CharField(max_length=20, unique=True, blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="ventas")
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=BORRADOR)
    impuesto_porcentaje = models.DecimalField(
        "IVA (%)", max_digits=5, decimal_places=2, default=Decimal("19"),
        help_text="Tarifa general de IVA en Colombia: 19%.",
    )
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ventas"
    )
    notas = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    confirmada_en = models.DateTimeField(null=True, blank=True)
    numero_factura = models.CharField(
        "N° de factura", max_length=30, null=True, blank=True, unique=True,
        help_text="Consecutivo de tu propia numeración de facturación.",
    )
    facturada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return self.numero or f"Venta borrador #{self.pk}"

    def get_absolute_url(self):
        return reverse("ventas:venta_detalle", args=[self.pk])

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and not self.numero:
            self.numero = f"V-{self.pk:06d}"
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
        """Confirma la venta: valida y descuenta stock en tiempo real y bloquea la edición."""
        if self.estado != self.BORRADOR:
            raise ValidationError("Solo una venta en borrador puede confirmarse.")

        lineas = list(self.lineas.select_related("producto"))
        if not lineas:
            raise ValidationError("La venta no tiene líneas.")

        for linea in lineas:
            producto = Producto.objects.select_for_update().get(pk=linea.producto_id)
            if producto.es_servicio:
                continue
            registrar_movimiento(
                producto=producto,
                tipo=MovimientoInventario.SALIDA,
                cantidad=linea.cantidad,
                motivo=MovimientoInventario.MOTIVO_VENTA,
                referencia=self.numero,
                usuario=usuario,
            )

        self.estado = self.CONFIRMADA
        self.confirmada_en = timezone.now()
        self.save(update_fields=["estado", "confirmada_en"])

    @transaction.atomic
    def anular(self, usuario=None):
        """Anula una venta confirmada y devuelve el stock al inventario."""
        if self.estado != self.CONFIRMADA:
            raise ValidationError("Solo una venta confirmada puede anularse.")

        for linea in self.lineas.select_related("producto"):
            producto = Producto.objects.select_for_update().get(pk=linea.producto_id)
            if producto.es_servicio:
                continue
            registrar_movimiento(
                producto=producto,
                tipo=MovimientoInventario.ENTRADA,
                cantidad=linea.cantidad,
                motivo=MovimientoInventario.MOTIVO_DEVOLUCION,
                referencia=self.numero,
                usuario=usuario,
            )

        self.estado = self.ANULADA
        self.save(update_fields=["estado"])

    @classmethod
    def siguiente_numero_factura_sugerido(cls):
        """Sugiere el siguiente consecutivo a partir de la última factura numérica emitida.

        Si aún no se ha facturado nada (o el último número no es puramente numérico),
        no hay nada que sugerir: el usuario debe indicar el consecutivo de arranque.
        """
        ultima = (
            cls.objects.exclude(numero_factura__isnull=True).exclude(numero_factura="")
            .order_by("-facturada_en").first()
        )
        if ultima and ultima.numero_factura.isdigit():
            return str(int(ultima.numero_factura) + 1)
        return ""

    @transaction.atomic
    def facturar(self, numero_factura):
        if self.estado != self.CONFIRMADA:
            raise ValidationError("Solo una venta confirmada puede facturarse.")
        if self.numero_factura:
            raise ValidationError("Esta venta ya fue facturada.")
        numero_factura = (numero_factura or "").strip()
        if not numero_factura:
            raise ValidationError("Ingresa el número de factura.")
        if Venta.objects.filter(numero_factura=numero_factura).exclude(pk=self.pk).exists():
            raise ValidationError(f"Ya existe una factura con el número '{numero_factura}'.")
        self.numero_factura = numero_factura
        self.facturada_en = timezone.now()
        self.save(update_fields=["numero_factura", "facturada_en"])

    def corregir_factura(self, numero_factura):
        if not self.numero_factura:
            raise ValidationError("Esta venta todavía no ha sido facturada.")
        numero_factura = (numero_factura or "").strip()
        if not numero_factura:
            raise ValidationError("Ingresa el número de factura.")
        if Venta.objects.filter(numero_factura=numero_factura).exclude(pk=self.pk).exists():
            raise ValidationError(f"Ya existe una factura con el número '{numero_factura}'.")
        self.numero_factura = numero_factura
        self.save(update_fields=["numero_factura"])


class LineaVenta(models.Model):
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name="lineas")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="lineas_venta")
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Línea de venta"
        verbose_name_plural = "Líneas de venta"

    def __str__(self):
        return f"{self.producto.sku} x{self.cantidad}"

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def clean(self):
        if self.venta_id and not self.venta.editable:
            raise ValidationError("No se puede modificar una venta confirmada o anulada.")


class Cotizacion(models.Model):
    BORRADOR = "borrador"
    ENVIADA = "enviada"
    ACEPTADA = "aceptada"
    RECHAZADA = "rechazada"
    ESTADO_CHOICES = [
        (BORRADOR, "Borrador"),
        (ENVIADA, "Enviada"),
        (ACEPTADA, "Aceptada"),
        (RECHAZADA, "Rechazada"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    numero = models.CharField(max_length=20, unique=True, blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="cotizaciones")
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=BORRADOR)
    impuesto_porcentaje = models.DecimalField(
        "IVA (%)", max_digits=5, decimal_places=2, default=Decimal("19"),
        help_text="Tarifa general de IVA en Colombia: 19%.",
    )
    fecha_validez = models.DateField("Válida hasta", default=_fecha_validez_por_defecto)
    sede = models.CharField("Sede", max_length=150, blank=True, help_text="Sede o sucursal que atiende la cotización.")
    vendedor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="cotizaciones"
    )
    notas = models.TextField(
        "Condiciones comerciales", blank=True,
        help_text="Ej. forma de pago, tiempo de entrega, garantía.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    enviada_en = models.DateTimeField(null=True, blank=True)
    firmado_por = models.CharField("Firmado por", max_length=150, blank=True)
    firmado_en = models.DateTimeField(null=True, blank=True)
    venta = models.OneToOneField(
        Venta, on_delete=models.SET_NULL, null=True, blank=True, related_name="cotizacion_origen"
    )

    class Meta:
        verbose_name = "Cotización"
        verbose_name_plural = "Cotizaciones"
        ordering = ["-creado_en"]

    def __str__(self):
        return self.numero or f"Cotización borrador #{self.pk}"

    def get_absolute_url(self):
        return reverse("ventas:cotizacion_detalle", args=[self.pk])

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and not self.numero:
            self.numero = f"COT-{self.pk:06d}"
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

    @property
    def vencida(self):
        return self.fecha_validez < timezone.localdate() and self.estado in (self.BORRADOR, self.ENVIADA)

    def marcar_enviada(self):
        if self.estado != self.BORRADOR:
            raise ValidationError("Solo una cotización en borrador puede marcarse como enviada.")
        if not self.lineas.exists():
            raise ValidationError("La cotización no tiene líneas.")
        self.estado = self.ENVIADA
        self.enviada_en = timezone.now()
        self.save(update_fields=["estado", "enviada_en"])

    def marcar_aceptada(self, firmado_por=""):
        if self.estado != self.ENVIADA:
            raise ValidationError("Solo una cotización enviada puede marcarse como aceptada.")
        if not firmado_por:
            raise ValidationError("Se requiere el nombre de quien firma para aceptar la cotización.")
        self.estado = self.ACEPTADA
        self.firmado_por = firmado_por
        self.firmado_en = timezone.now()
        self.save(update_fields=["estado", "firmado_por", "firmado_en"])

    def marcar_rechazada(self):
        if self.estado != self.ENVIADA:
            raise ValidationError("Solo una cotización enviada puede marcarse como rechazada.")
        self.estado = self.RECHAZADA
        self.save(update_fields=["estado"])

    @transaction.atomic
    def convertir_a_venta(self, usuario=None):
        """Crea una venta en borrador con las mismas líneas, lista para confirmar."""
        if self.venta_id:
            raise ValidationError("Esta cotización ya fue convertida en una venta.")
        if not self.lineas.exists():
            raise ValidationError("La cotización no tiene líneas.")

        venta = Venta.objects.create(
            cliente=self.cliente, impuesto_porcentaje=self.impuesto_porcentaje, vendedor=usuario,
            notas=f"Generada desde la cotización {self.numero}.",
        )
        for linea in self.lineas.select_related("producto"):
            LineaVenta.objects.create(
                venta=venta, producto=linea.producto, cantidad=linea.cantidad, precio_unitario=linea.precio_unitario,
            )
        self.venta = venta
        self.save(update_fields=["venta"])
        return venta


class LineaCotizacion(models.Model):
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, related_name="lineas")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="lineas_cotizacion")
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Línea de cotización"
        verbose_name_plural = "Líneas de cotización"

    def __str__(self):
        return f"{self.producto.sku} x{self.cantidad}"

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def clean(self):
        if self.cotizacion_id and not self.cotizacion.editable:
            raise ValidationError("No se puede modificar una cotización que ya fue enviada.")


class CuentaCobro(models.Model):
    """Documento de cobro alternativo a la factura, para clientes que no la requieren.

    A diferencia de la Venta (que descuenta stock y factura con el NIT de la empresa),
    la cuenta de cobro es un documento simple e independiente: no toca inventario y se
    puede emitir a nombre de la empresa o de una persona natural (ej. un contratista).
    """

    EMPRESA = "empresa"
    PERSONA_NATURAL = "persona_natural"
    EMISOR_CHOICES = [
        (EMPRESA, "La empresa"),
        (PERSONA_NATURAL, "Persona natural"),
    ]

    BORRADOR = "borrador"
    EMITIDA = "emitida"
    PAGADA = "pagada"
    ANULADA = "anulada"
    ESTADO_CHOICES = [
        (BORRADOR, "Borrador"),
        (EMITIDA, "Emitida"),
        (PAGADA, "Pagada"),
        (ANULADA, "Anulada"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    numero = models.CharField(max_length=20, unique=True, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=BORRADOR)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="cuentas_cobro")
    venta = models.ForeignKey(
        Venta, on_delete=models.SET_NULL, null=True, blank=True, related_name="cuentas_cobro",
        help_text="Opcional: si esta cuenta de cobro corresponde a una venta ya registrada.",
    )
    emisor_tipo = models.CharField(max_length=16, choices=EMISOR_CHOICES, default=EMPRESA)
    emisor_nombre = models.CharField(
        "Nombre de quien cobra", max_length=150, blank=True,
        help_text="Solo si se emite a nombre de una persona natural.",
    )
    emisor_documento = models.CharField(
        "Cédula de quien cobra", max_length=30, blank=True,
        help_text="Solo si se emite a nombre de una persona natural.",
    )
    concepto = models.TextField("Concepto", help_text="Descripción del servicio o motivo del cobro.")
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateField("Fecha de expedición", default=timezone.localdate)
    forma_pago = models.CharField(
        max_length=100, blank=True, help_text="Ej. transferencia, efectivo, consignación.",
    )
    datos_pago = models.CharField(
        "Datos de pago", max_length=200, blank=True,
        help_text="Ej. banco, tipo y número de cuenta, si aplica.",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="cuentas_cobro"
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    emitida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Cuenta de cobro"
        verbose_name_plural = "Cuentas de cobro"
        ordering = ["-creado_en"]

    def __str__(self):
        return self.numero or f"Cuenta de cobro borrador #{self.pk}"

    def get_absolute_url(self):
        return reverse("ventas:cuenta_cobro_detalle", args=[self.pk])

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and not self.numero:
            self.numero = f"CC-{self.pk:06d}"
            super().save(update_fields=["numero"])

    @property
    def editable(self):
        return self.estado == self.BORRADOR

    def clean(self):
        if self.emisor_tipo == self.PERSONA_NATURAL and not (self.emisor_nombre and self.emisor_documento):
            raise ValidationError(
                "Ingresa el nombre y la cédula de la persona natural que emite la cuenta de cobro."
            )

    def emitir(self):
        if self.estado != self.BORRADOR:
            raise ValidationError("Solo una cuenta de cobro en borrador puede emitirse.")
        self.full_clean()
        self.estado = self.EMITIDA
        self.emitida_en = timezone.now()
        self.save(update_fields=["estado", "emitida_en"])

    def marcar_pagada(self):
        if self.estado != self.EMITIDA:
            raise ValidationError("Solo una cuenta de cobro emitida puede marcarse como pagada.")
        self.estado = self.PAGADA
        self.save(update_fields=["estado"])

    def anular(self):
        if self.estado not in (self.BORRADOR, self.EMITIDA):
            raise ValidationError("Esta cuenta de cobro ya no se puede anular.")
        self.estado = self.ANULADA
        self.save(update_fields=["estado"])
