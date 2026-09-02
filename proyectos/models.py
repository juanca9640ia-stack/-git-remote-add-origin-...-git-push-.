from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from rrhh.models import Empleado
from ventas.models import Cliente, CuentaCobro, Venta


class Proyecto(models.Model):
    """Una obra: desde que se planifica hasta que se entrega. Es el eje del
    módulo de Proyectos — hitos, gastos y equipo asignado cuelgan de aquí."""

    PLANIFICACION = "planificacion"
    EN_CURSO = "en_curso"
    PAUSADO = "pausado"
    FINALIZADO = "finalizado"
    CANCELADO = "cancelado"
    ESTADO_CHOICES = [
        (PLANIFICACION, "En planificación"),
        (EN_CURSO, "En curso"),
        (PAUSADO, "Pausado"),
        (FINALIZADO, "Finalizado"),
        (CANCELADO, "Cancelado"),
    ]
    ESTADOS_ACTIVOS = (PLANIFICACION, EN_CURSO, PAUSADO)

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    numero = models.CharField(max_length=20, blank=True)
    nombre = models.CharField("Nombre de la obra", max_length=150)
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="proyectos", null=True, blank=True,
        help_text="Opcional: a quién se le está construyendo.",
    )
    ubicacion = models.CharField("Ubicación / dirección de la obra", max_length=200, blank=True)
    descripcion = models.TextField("Descripción / alcance", blank=True)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default=PLANIFICACION)
    presupuesto = models.DecimalField(
        "Presupuesto", max_digits=14, decimal_places=2, default=Decimal("0"),
        help_text="Presupuesto total aprobado para la obra.",
    )
    fecha_inicio = models.DateField("Fecha de inicio", null=True, blank=True)
    fecha_fin_estimada = models.DateField("Fecha de entrega estimada", null=True, blank=True)
    fecha_fin_real = models.DateField("Fecha de entrega real", null=True, blank=True)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="proyectos_a_cargo", help_text="Quién dirige la obra.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Proyecto"
        verbose_name_plural = "Proyectos"
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(fields=["empresa", "numero"], name="proyecto_numero_unico_por_empresa"),
        ]

    def __str__(self):
        return self.numero or f"Proyecto borrador #{self.pk}"

    def get_absolute_url(self):
        return reverse("proyectos:proyecto_detalle", args=[self.pk])

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and not self.numero:
            self.numero = f"PROY-{self.pk:06d}"
            super().save(update_fields=["numero"])

    @property
    def activo(self):
        return self.estado in self.ESTADOS_ACTIVOS

    @property
    def gastado(self):
        return sum((g.valor for g in self.gastos.all()), Decimal("0"))

    @property
    def saldo_presupuesto(self):
        return self.presupuesto - self.gastado

    @property
    def porcentaje_gastado(self):
        if not self.presupuesto:
            return None
        return min(int(self.gastado / self.presupuesto * 100), 999)

    @property
    def sobre_presupuesto(self):
        return bool(self.presupuesto) and self.gastado > self.presupuesto

    @property
    def ingresos(self):
        """Lo realmente facturado/cobrado a esta obra: ventas confirmadas + cuentas de
        cobro pagadas que quedaron vinculadas a ella. No cuenta lo que todavía está
        solo cotizado o en borrador."""
        de_ventas = sum(
            (v.total for v in self.ventas.filter(estado=Venta.CONFIRMADA)), Decimal("0")
        )
        de_cuentas_cobro = sum(
            (c.valor for c in self.cuentas_cobro.filter(estado=CuentaCobro.PAGADA)), Decimal("0")
        )
        return de_ventas + de_cuentas_cobro

    @property
    def utilidad(self):
        return self.ingresos - self.gastado

    @property
    def margen_utilidad(self):
        if not self.ingresos:
            return None
        return round(self.utilidad / self.ingresos * 100, 1)

    @property
    def total_hitos(self):
        return self.hitos.count()

    @property
    def hitos_completados(self):
        return self.hitos.filter(completado=True).count()

    @property
    def porcentaje_avance(self):
        total = self.total_hitos
        if not total:
            return 0
        return int(self.hitos_completados / total * 100)


class HitoProyecto(models.Model):
    """Un hito o entregable dentro de la obra (ej. 'Cimentación', 'Entrega de acabados')."""

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="hitos")
    nombre = models.CharField(max_length=150)
    fecha_objetivo = models.DateField("Fecha objetivo", null=True, blank=True)
    completado = models.BooleanField(default=False)
    completado_en = models.DateTimeField(null=True, blank=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Hito"
        verbose_name_plural = "Hitos"
        ordering = ["orden", "fecha_objetivo", "id"]

    def __str__(self):
        return self.nombre

    @property
    def vencido(self):
        return bool(self.fecha_objetivo) and not self.completado and self.fecha_objetivo < timezone.localdate()

    def marcar_completado(self):
        self.completado = True
        self.completado_en = timezone.now()
        self.save(update_fields=["completado", "completado_en"])

    def marcar_pendiente(self):
        self.completado = False
        self.completado_en = None
        self.save(update_fields=["completado", "completado_en"])


class GastoProyecto(models.Model):
    """Un costo real cargado a la obra, para comparar contra el presupuesto.
    No reemplaza a Compras/Finanzas: es un registro simple del gasto de obra."""

    MATERIALES = "materiales"
    MANO_OBRA = "mano_obra"
    EQUIPOS = "equipos"
    OTROS = "otros"
    CATEGORIA_CHOICES = [
        (MATERIALES, "Materiales"),
        (MANO_OBRA, "Mano de obra"),
        (EQUIPOS, "Equipos y herramientas"),
        (OTROS, "Otros"),
    ]

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="gastos")
    concepto = models.CharField(max_length=200)
    categoria = models.CharField(max_length=15, choices=CATEGORIA_CHOICES, default=OTROS)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateField(default=timezone.localdate)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="gastos_proyecto"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gasto de obra"
        verbose_name_plural = "Gastos de obra"
        ordering = ["-fecha", "-creado_en"]

    def __str__(self):
        return f"{self.concepto} - ${self.valor}"

    def clean(self):
        if self.valor is not None and self.valor <= 0:
            raise ValidationError("El valor del gasto debe ser mayor a cero.")


class AsignacionEmpleado(models.Model):
    """Qué empleados están trabajando en cada obra."""

    empresa = models.ForeignKey(
        "core.Empresa", on_delete=models.PROTECT, default=1, related_name="+",
        help_text="Inquilino (empresa) al que pertenece este registro.",
    )
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="asignaciones")
    empleado = models.ForeignKey(Empleado, on_delete=models.PROTECT, related_name="asignaciones_proyecto")
    rol_en_obra = models.CharField(
        "Rol en la obra", max_length=100, blank=True,
        help_text="Ej. maestro de obra, oficial, ayudante (si difiere del cargo habitual).",
    )
    fecha_asignacion = models.DateField(default=timezone.localdate)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Asignación de empleado"
        verbose_name_plural = "Asignaciones de empleados"
        ordering = ["-activo", "empleado__nombre_completo"]
        constraints = [
            models.UniqueConstraint(fields=["proyecto", "empleado"], name="asignacion_unica_por_proyecto"),
        ]

    def __str__(self):
        return f"{self.empleado} en {self.proyecto}"
