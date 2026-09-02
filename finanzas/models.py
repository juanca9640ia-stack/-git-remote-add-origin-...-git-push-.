from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from compras.models import Compra
from rrhh.models import Nomina
from ventas.models import Venta

METODO_PAGO_CHOICES = [
    ("efectivo", "Efectivo"),
    ("transferencia", "Transferencia"),
    ("tarjeta", "Tarjeta"),
    ("otro", "Otro"),
]


class CuentaPorCobrar(models.Model):
    PENDIENTE = "pendiente"
    PARCIAL = "parcial"
    PAGADA = "pagada"
    ANULADA = "anulada"
    ESTADO_CHOICES = [
        (PENDIENTE, "Pendiente"),
        (PARCIAL, "Pago parcial"),
        (PAGADA, "Pagada"),
        (ANULADA, "Anulada"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    venta = models.OneToOneField(Venta, on_delete=models.PROTECT, related_name="cuenta_por_cobrar")
    monto_total = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=PENDIENTE)
    fecha_vencimiento = models.DateField("Fecha de vencimiento", null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cuenta por cobrar"
        verbose_name_plural = "Cuentas por cobrar"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"CxC {self.venta.numero}"

    def get_absolute_url(self):
        return reverse("finanzas:cxc_detalle", args=[self.pk])

    @property
    def vencida(self):
        return (
            self.fecha_vencimiento is not None
            and self.fecha_vencimiento < timezone.localdate()
            and self.estado in (self.PENDIENTE, self.PARCIAL)
        )

    @transaction.atomic
    def registrar_pago(self, monto, metodo, referencia="", usuario=None):
        if self.estado == self.ANULADA:
            raise ValidationError("No se pueden registrar pagos sobre una cuenta anulada.")
        if monto is None or monto <= 0:
            raise ValidationError("El monto debe ser mayor a cero.")
        if monto > self.saldo_pendiente:
            raise ValidationError(f"El monto excede el saldo pendiente (${self.saldo_pendiente}).")

        pago = PagoCliente.objects.create(
            empresa=self.empresa, cuenta=self, monto=monto, metodo=metodo,
            referencia=referencia, registrado_por=usuario,
        )
        self.saldo_pendiente -= monto
        self.estado = self.PAGADA if self.saldo_pendiente == 0 else self.PARCIAL
        self.save(update_fields=["saldo_pendiente", "estado"])
        return pago


class PagoCliente(models.Model):
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    cuenta = models.ForeignKey(CuentaPorCobrar, on_delete=models.PROTECT, related_name="pagos")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES, default="efectivo")
    referencia = models.CharField(max_length=100, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pago de cliente"
        verbose_name_plural = "Pagos de clientes"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Pago ${self.monto} - {self.cuenta}"


class CuentaPorPagar(models.Model):
    PENDIENTE = "pendiente"
    PARCIAL = "parcial"
    PAGADA = "pagada"
    ANULADA = "anulada"
    ESTADO_CHOICES = [
        (PENDIENTE, "Pendiente"),
        (PARCIAL, "Pago parcial"),
        (PAGADA, "Pagada"),
        (ANULADA, "Anulada"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    compra = models.OneToOneField(
        Compra, on_delete=models.PROTECT, related_name="cuenta_por_pagar", null=True, blank=True
    )
    nomina = models.OneToOneField(
        Nomina, on_delete=models.PROTECT, related_name="cuenta_por_pagar", null=True, blank=True
    )
    monto_total = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2)
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=PENDIENTE)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cuenta por pagar"
        verbose_name_plural = "Cuentas por pagar"
        ordering = ["-creado_en"]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(compra__isnull=False, nomina__isnull=True)
                    | models.Q(compra__isnull=True, nomina__isnull=False)
                ),
                name="cuenta_por_pagar_origen_unico",
            )
        ]

    def __str__(self):
        return f"CxP {self.origen}"

    def get_absolute_url(self):
        return reverse("finanzas:cxp_detalle", args=[self.pk])

    @property
    def origen(self):
        return self.compra.numero if self.compra_id else f"Nómina {self.nomina.periodo}"

    @property
    def contraparte(self):
        return str(self.compra.proveedor) if self.compra_id else "Nómina de personal"

    @transaction.atomic
    def registrar_pago(self, monto, metodo, referencia="", usuario=None):
        if self.estado == self.ANULADA:
            raise ValidationError("No se pueden registrar pagos sobre una cuenta anulada.")
        if monto is None or monto <= 0:
            raise ValidationError("El monto debe ser mayor a cero.")
        if monto > self.saldo_pendiente:
            raise ValidationError(f"El monto excede el saldo pendiente (${self.saldo_pendiente}).")

        pago = PagoProveedor.objects.create(
            empresa=self.empresa, cuenta=self, monto=monto, metodo=metodo,
            referencia=referencia, registrado_por=usuario,
        )
        self.saldo_pendiente -= monto
        self.estado = self.PAGADA if self.saldo_pendiente == 0 else self.PARCIAL
        self.save(update_fields=["saldo_pendiente", "estado"])
        return pago


class PagoProveedor(models.Model):
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    cuenta = models.ForeignKey(CuentaPorPagar, on_delete=models.PROTECT, related_name="pagos")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES, default="efectivo")
    referencia = models.CharField(max_length=100, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pago a proveedor"
        verbose_name_plural = "Pagos a proveedores"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Pago ${self.monto} - {self.cuenta}"
