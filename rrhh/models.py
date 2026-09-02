import datetime
import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

PERIODO_MES_RE = re.compile(r"^(\d{4})-(\d{2})$")
PERIODO_SEMANA_RE = re.compile(r"^(\d{4})-W(\d{2})$")


def rango_periodo(periodo):
    """Devuelve (fecha_inicio, fecha_fin) inclusive de un período AAAA-MM (mensual) o AAAA-Www (semana ISO)."""
    m = PERIODO_MES_RE.match(periodo)
    if m:
        anio, mes = int(m.group(1)), int(m.group(2))
        if not 1 <= mes <= 12:
            raise ValidationError(f"Mes inválido en el período '{periodo}'.")
        inicio = datetime.date(anio, mes, 1)
        siguiente_mes = datetime.date(anio + (mes == 12), (mes % 12) + 1, 1)
        return inicio, siguiente_mes - datetime.timedelta(days=1)

    m = PERIODO_SEMANA_RE.match(periodo)
    if m:
        anio, semana = int(m.group(1)), int(m.group(2))
        try:
            inicio = datetime.date.fromisocalendar(anio, semana, 1)
            fin = datetime.date.fromisocalendar(anio, semana, 7)
        except ValueError:
            raise ValidationError(f"Semana ISO inválida en el período '{periodo}'.")
        return inicio, fin

    raise ValidationError(
        f"Formato de período no reconocido: '{periodo}'. Usa AAAA-MM (mensual) o AAAA-Www (semanal)."
    )


class Departamento(models.Model):
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "nombre"], name="departamento_nombre_unico_por_empresa"),
        ]

    def __str__(self):
        return self.nombre


class Empleado(models.Model):
    PAGO_SALARIO = "salario"
    PAGO_DIA = "dia"
    TIPO_PAGO_CHOICES = [
        (PAGO_SALARIO, "Salario base (mensual)"),
        (PAGO_DIA, "Por día trabajado"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="empleado"
    )
    nombre_completo = models.CharField(max_length=150)
    documento = models.CharField("Cédula/Documento", max_length=30)
    cargo = models.CharField(max_length=100)
    departamento = models.ForeignKey(
        Departamento, on_delete=models.PROTECT, related_name="empleados", null=True, blank=True
    )
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=30)
    fecha_contratacion = models.DateField(default=timezone.localdate)
    tipo_pago = models.CharField(
        "Tipo de pago", max_length=10, choices=TIPO_PAGO_CHOICES, default=PAGO_SALARIO
    )
    salario_base = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_dia = models.DecimalField("Valor por día", max_digits=12, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre_completo"]
        permissions = [
            ("marcar_propia_asistencia", "Puede registrar su propia entrada/salida"),
            ("ver_propio_perfil", "Puede ver su propio perfil, asistencia, préstamos y recibos de nómina"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "documento"], name="empleado_documento_unico_por_empresa"),
        ]

    def __str__(self):
        return self.nombre_completo

    def get_absolute_url(self):
        return reverse("rrhh:empleado_detalle", args=[self.pk])


class Asistencia(models.Model):
    PRESENTE = "presente"
    TARDANZA = "tardanza"
    AUSENTE = "ausente"
    PERMISO = "permiso"
    VACACIONES = "vacaciones"
    ESTADO_CHOICES = [
        (PRESENTE, "Presente"),
        (TARDANZA, "Tardanza"),
        (AUSENTE, "Ausente"),
        (PERMISO, "Permiso"),
        (VACACIONES, "Vacaciones"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name="asistencias")
    fecha = models.DateField(default=timezone.localdate)
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_salida = models.TimeField(null=True, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=PRESENTE)
    notas = models.CharField(max_length=200, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Asistencia"
        verbose_name_plural = "Asistencias"
        unique_together = ("empleado", "fecha")
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.empleado} - {self.fecha} ({self.get_estado_display()})"

    def marcar_salida(self):
        if not self.hora_entrada:
            raise ValidationError("No se puede marcar salida sin haber marcado entrada.")
        if self.hora_salida:
            raise ValidationError("Ya se registró la salida de este día.")
        self.hora_salida = timezone.localtime().time()
        self.save(update_fields=["hora_salida"])


class Nomina(models.Model):
    BORRADOR = "borrador"
    PROCESADA = "procesada"
    ESTADO_CHOICES = [
        (BORRADOR, "Borrador"),
        (PROCESADA, "Procesada"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    periodo = models.CharField(
        max_length=8,
        help_text="Mensual: AAAA-MM (ej. 2026-08). Semanal: AAAA-Www (ej. 2026-W32).",
    )
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=BORRADOR)
    creado_en = models.DateTimeField(auto_now_add=True)
    procesada_en = models.DateTimeField(null=True, blank=True)
    procesada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="nominas_procesadas"
    )

    class Meta:
        verbose_name = "Nómina"
        verbose_name_plural = "Nóminas"
        ordering = ["-periodo"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "periodo"], name="nomina_periodo_unico_por_empresa"),
        ]

    def __str__(self):
        return f"Nómina {self.periodo}"

    def get_absolute_url(self):
        return reverse("rrhh:nomina_detalle", args=[self.pk])

    @property
    def editable(self):
        return self.estado == self.BORRADOR

    @property
    def total_pagar(self):
        return sum((detalle.total for detalle in self.detalles.all()), Decimal("0"))

    def generar_detalles(self):
        if not self.editable:
            raise ValidationError("Solo una nómina en borrador puede regenerar sus detalles.")
        for empleado in Empleado.objects.filter(activo=True):
            detalle, _ = DetalleNomina.objects.get_or_create(
                nomina=self, empleado=empleado,
                defaults={
                    "salario_base": (
                        empleado.salario_base if empleado.tipo_pago == Empleado.PAGO_SALARIO else Decimal("0")
                    ),
                    "valor_dia": (
                        empleado.valor_dia if empleado.tipo_pago == Empleado.PAGO_DIA else Decimal("0")
                    ),
                },
            )
            detalle.recalcular_dias_trabajados()

    @transaction.atomic
    def procesar(self, usuario=None):
        if self.estado != self.BORRADOR:
            raise ValidationError("Solo una nómina en borrador puede procesarse.")
        if not self.detalles.exists():
            raise ValidationError("La nómina no tiene empleados asignados.")

        self.estado = self.PROCESADA
        self.procesada_en = timezone.now()
        self.procesada_por = usuario
        self.save(update_fields=["estado", "procesada_en", "procesada_por"])

        for detalle in self.detalles.select_related("empleado").filter(descuento_prestamo__gt=0):
            aplicar_abono_prestamos(detalle.empleado, detalle.descuento_prestamo, nomina=self)


class DetalleNomina(models.Model):
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    nomina = models.ForeignKey(Nomina, on_delete=models.CASCADE, related_name="detalles")
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="detalles_nomina")
    salario_base = models.DecimalField(max_digits=12, decimal_places=2)
    valor_dia = models.DecimalField("Valor por día", max_digits=12, decimal_places=2, default=Decimal("0"))
    dias_trabajados = models.PositiveIntegerField("Días trabajados", default=0)
    horas_extra = models.DecimalField("Horas extra", max_digits=12, decimal_places=2, default=Decimal("0"))
    bonificaciones = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    deducciones = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    descuento_prestamo = models.DecimalField(
        "Abono a préstamo", max_digits=12, decimal_places=2, default=Decimal("0")
    )

    class Meta:
        verbose_name = "Detalle de nómina"
        verbose_name_plural = "Detalles de nómina"
        unique_together = ("nomina", "empleado")
        ordering = ["empleado__nombre_completo"]

    def __str__(self):
        return f"{self.empleado} - {self.nomina.periodo}"

    def recalcular_dias_trabajados(self):
        """Cuenta como día trabajado cada asistencia del período (mensual o semanal) con entrada marcada."""
        if self.empleado.tipo_pago != Empleado.PAGO_DIA:
            return
        inicio, fin = rango_periodo(self.nomina.periodo)
        dias = Asistencia.objects.filter(
            empleado=self.empleado, fecha__range=(inicio, fin), hora_entrada__isnull=False,
        ).count()
        if dias != self.dias_trabajados:
            self.dias_trabajados = dias
            self.save(update_fields=["dias_trabajados"])

    @property
    def pago_base(self):
        if self.empleado.tipo_pago == Empleado.PAGO_DIA:
            return self.dias_trabajados * self.valor_dia
        return self.salario_base

    @property
    def total(self):
        return (
            self.pago_base + self.horas_extra + self.bonificaciones
            - self.deducciones - self.descuento_prestamo
        )


class Prestamo(models.Model):
    ACTIVO = "activo"
    PAGADO = "pagado"
    ESTADO_CHOICES = [
        (ACTIVO, "Activo"),
        (PAGADO, "Pagado"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="prestamos")
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.CharField(max_length=200, blank=True)
    fecha_otorgado = models.DateField(default=timezone.localdate)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ACTIVO)
    otorgado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="prestamos_otorgados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Préstamo"
        verbose_name_plural = "Préstamos"
        ordering = ["-fecha_otorgado"]

    def __str__(self):
        return f"Préstamo {self.empleado} - ${self.monto}"

    def get_absolute_url(self):
        return reverse("rrhh:prestamo_detalle", args=[self.pk])

    def save(self, *args, **kwargs):
        if self._state.adding and not self.saldo_pendiente:
            self.saldo_pendiente = self.monto
        super().save(*args, **kwargs)

    def abonar(self, valor, nomina=None):
        """Reduce el saldo pendiente y registra el movimiento; marca el préstamo como pagado si llega a 0."""
        valor = min(valor, self.saldo_pendiente)
        if valor <= 0:
            return Decimal("0")
        self.saldo_pendiente -= valor
        if self.saldo_pendiente <= 0:
            self.saldo_pendiente = Decimal("0")
            self.estado = self.PAGADO
        self.save(update_fields=["saldo_pendiente", "estado"])
        AbonoPrestamo.objects.create(prestamo=self, valor=valor, nomina=nomina)
        return valor


class AbonoPrestamo(models.Model):
    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    prestamo = models.ForeignKey(Prestamo, on_delete=models.CASCADE, related_name="abonos")
    nomina = models.ForeignKey(
        Nomina, on_delete=models.SET_NULL, null=True, blank=True, related_name="abonos_prestamo"
    )
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Abono a préstamo"
        verbose_name_plural = "Abonos a préstamos"
        ordering = ["-fecha"]

    def __str__(self):
        return f"Abono ${self.valor} - {self.prestamo}"


def aplicar_abono_prestamos(empleado, valor, nomina=None):
    """Aplica `valor` como abono a los préstamos activos del empleado, del más antiguo al más reciente."""
    restante = valor
    for prestamo in empleado.prestamos.filter(estado=Prestamo.ACTIVO).order_by("fecha_otorgado"):
        if restante <= 0:
            break
        restante -= prestamo.abonar(restante, nomina=nomina)
