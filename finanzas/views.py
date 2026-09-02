import json
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from compras.models import Compra
from rrhh.models import Nomina
from ventas.models import Cliente, Venta

from .forms import RegistrarPagoForm
from .models import CuentaPorCobrar, CuentaPorPagar

MESES_ABREV = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}

# Buckets estándar de antigüedad de cartera (días de vencida).
AGING_BUCKETS = [
    ("Al día", None, 0),
    ("1-30 días", 1, 30),
    ("31-60 días", 31, 60),
    ("61-90 días", 61, 90),
    ("Más de 90 días", 91, None),
]


def _bucket_antiguedad(cuenta, hoy):
    """Etiqueta del bucket de antigüedad al que pertenece una cuenta por cobrar."""
    dias_vencida = (hoy - cuenta.fecha_vencimiento).days if cuenta.fecha_vencimiento else -1
    if dias_vencida <= 0:
        return AGING_BUCKETS[0][0]
    for nombre, desde, hasta in AGING_BUCKETS:
        if desde is not None and dias_vencida >= desde and (hasta is None or dias_vencida <= hasta):
            return nombre
    return AGING_BUCKETS[0][0]


def _agrupar_por_antiguedad(cxc_pendientes_qs, hoy):
    """Clasifica cada cuenta por cobrar pendiente en un bucket de antigüedad,
    devolviendo un resumen {etiqueta, cantidad, total} por bucket, en orden."""
    resumen = {etiqueta: {"etiqueta": etiqueta, "cantidad": 0, "total": Decimal("0")} for etiqueta, _, _ in AGING_BUCKETS}
    for cuenta in cxc_pendientes_qs:
        etiqueta = _bucket_antiguedad(cuenta, hoy)
        resumen[etiqueta]["cantidad"] += 1
        resumen[etiqueta]["total"] += cuenta.saldo_pendiente
    return [resumen[etiqueta] for etiqueta, _, _ in AGING_BUCKETS]


def _serie_flujo_caja(empresa, meses=6):
    """Ingresos (ventas confirmadas) vs egresos (compras + nómina) por mes,
    para los últimos `meses` meses incluyendo el actual."""
    hoy = timezone.localdate()
    inicio = hoy.replace(day=1)
    for _ in range(meses - 1):
        inicio = (inicio - timedelta(days=1)).replace(day=1)

    ventas = Venta.objects.filter(estado=Venta.CONFIRMADA, empresa=empresa, confirmada_en__date__gte=inicio)
    compras = Compra.objects.filter(estado=Compra.CONFIRMADA, empresa=empresa, creado_en__date__gte=inicio)
    nominas = Nomina.objects.filter(estado=Nomina.PROCESADA, empresa=empresa, creado_en__date__gte=inicio)

    ingresos_por_mes, egresos_por_mes = {}, {}
    for v in ventas:
        bucket = timezone.localtime(v.confirmada_en).date().replace(day=1)
        ingresos_por_mes[bucket] = ingresos_por_mes.get(bucket, Decimal("0")) + v.total
    for c in compras:
        bucket = timezone.localtime(c.creado_en).date().replace(day=1)
        egresos_por_mes[bucket] = egresos_por_mes.get(bucket, Decimal("0")) + c.total
    for n in nominas:
        bucket = timezone.localtime(n.creado_en).date().replace(day=1)
        egresos_por_mes[bucket] = egresos_por_mes.get(bucket, Decimal("0")) + n.total_pagar

    etiquetas, ingresos, egresos, cursor = [], [], [], inicio
    while cursor <= hoy:
        etiquetas.append(MESES_ABREV[cursor.month])
        ingresos.append(float(ingresos_por_mes.get(cursor, Decimal("0"))))
        egresos.append(float(egresos_por_mes.get(cursor, Decimal("0"))))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return etiquetas, ingresos, egresos


@login_required
def resumen(request):
    total_por_cobrar = CuentaPorCobrar.objects.filter(empresa=request.empresa).exclude(
        estado=CuentaPorCobrar.ANULADA
    ).aggregate(total=Sum("saldo_pendiente"))["total"] or Decimal("0")
    total_por_pagar = CuentaPorPagar.objects.filter(empresa=request.empresa).exclude(
        estado=CuentaPorPagar.ANULADA
    ).aggregate(total=Sum("saldo_pendiente"))["total"] or Decimal("0")

    ventas_confirmadas = Venta.objects.filter(estado=Venta.CONFIRMADA, empresa=request.empresa)
    compras_confirmadas = Compra.objects.filter(estado=Compra.CONFIRMADA, empresa=request.empresa)
    nominas_procesadas = Nomina.objects.filter(estado=Nomina.PROCESADA, empresa=request.empresa)
    ingresos_totales = sum((v.total for v in ventas_confirmadas), Decimal("0"))
    egresos_totales = (
        sum((c.total for c in compras_confirmadas), Decimal("0"))
        + sum((n.total_pagar for n in nominas_procesadas), Decimal("0"))
    )

    cxc_pendientes_qs = CuentaPorCobrar.objects.filter(
        empresa=request.empresa, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL]
    ).select_related("venta", "venta__cliente")
    cxc_pendientes = cxc_pendientes_qs[:8]
    cxp_pendientes = CuentaPorPagar.objects.filter(
        empresa=request.empresa, estado__in=[CuentaPorPagar.PENDIENTE, CuentaPorPagar.PARCIAL]
    ).select_related("compra", "compra__proveedor", "nomina")[:8]

    hoy = timezone.localdate()
    cxc_vencidas_qs = cxc_pendientes_qs.filter(fecha_vencimiento__lt=hoy)
    cxc_vencidas_count = cxc_vencidas_qs.count()
    cxc_vencidas_total = cxc_vencidas_qs.aggregate(total=Sum("saldo_pendiente"))["total"] or Decimal("0")

    aging = _agrupar_por_antiguedad(cxc_pendientes_qs, hoy)
    chart_labels, chart_ingresos, chart_egresos = _serie_flujo_caja(request.empresa)

    context = {
        "total_por_cobrar": total_por_cobrar,
        "total_por_pagar": total_por_pagar,
        "ingresos_totales": ingresos_totales,
        "egresos_totales": egresos_totales,
        "balance": ingresos_totales - egresos_totales,
        "cxc_pendientes": cxc_pendientes,
        "cxp_pendientes": cxp_pendientes,
        "cxc_vencidas_count": cxc_vencidas_count,
        "cxc_vencidas_total": cxc_vencidas_total,
        "aging": aging,
        "chart_labels": json.dumps(chart_labels),
        "chart_ingresos": json.dumps(chart_ingresos),
        "chart_egresos": json.dumps(chart_egresos),
    }
    return render(request, "finanzas/resumen.html", context)


@login_required
def cxc_lista(request):
    cuentas = CuentaPorCobrar.objects.select_related("venta", "venta__cliente").filter(empresa=request.empresa)
    estado = request.GET.get("estado", "")
    if estado:
        cuentas = cuentas.filter(estado=estado)

    cliente_id = request.GET.get("cliente", "")
    if cliente_id:
        cuentas = cuentas.filter(venta__cliente_id=cliente_id)

    solo_vencidas = request.GET.get("vencidas") == "1"
    hoy = timezone.localdate()
    if solo_vencidas:
        cuentas = cuentas.filter(
            fecha_vencimiento__lt=hoy, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
        )

    saldo_por_cliente = list(
        CuentaPorCobrar.objects.filter(empresa=request.empresa).exclude(estado=CuentaPorCobrar.ANULADA)
        .values("venta__cliente__id", "venta__cliente__nombre")
        .annotate(saldo=Sum("saldo_pendiente"))
        .filter(saldo__gt=0)
        .order_by("-saldo")
    )
    saldo_maximo = saldo_por_cliente[0]["saldo"] if saldo_por_cliente else Decimal("0")
    for fila in saldo_por_cliente:
        fila["porcentaje"] = int(fila["saldo"] / saldo_maximo * 100) if saldo_maximo else 0

    vencidas_qs = CuentaPorCobrar.objects.filter(
        empresa=request.empresa,
        fecha_vencimiento__lt=hoy, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
    )
    vencidas_count = vencidas_qs.count()
    vencidas_total = vencidas_qs.aggregate(total=Sum("saldo_pendiente"))["total"] or Decimal("0")

    cuentas = list(cuentas)
    for cuenta in cuentas:
        cuenta.bucket_antiguedad = _bucket_antiguedad(cuenta, hoy) if cuenta.estado in (
            CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL
        ) else None

    aging_pendientes_qs = CuentaPorCobrar.objects.filter(
        empresa=request.empresa, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
    )
    aging = _agrupar_por_antiguedad(aging_pendientes_qs, hoy)

    return render(request, "finanzas/cxc_lista.html", {
        "cuentas": cuentas, "estado": estado,
        "clientes": Cliente.objects.filter(
            empresa=request.empresa, ventas__cuenta_por_cobrar__isnull=False
        ).distinct().order_by("nombre"),
        "cliente_id": cliente_id, "solo_vencidas": solo_vencidas,
        "saldo_por_cliente": saldo_por_cliente,
        "vencidas_count": vencidas_count, "vencidas_total": vencidas_total,
        "aging": aging,
    })


@login_required
def cxc_detalle(request, pk):
    cuenta = get_object_or_404(
        CuentaPorCobrar.objects.select_related("venta", "venta__cliente"), pk=pk, empresa=request.empresa
    )
    if request.method == "POST":
        form = RegistrarPagoForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    cuenta_bloqueada = CuentaPorCobrar.objects.select_for_update().get(pk=cuenta.pk)
                    cuenta_bloqueada.registrar_pago(
                        monto=form.cleaned_data["monto"],
                        metodo=form.cleaned_data["metodo"],
                        referencia=form.cleaned_data["referencia"],
                        usuario=request.user,
                    )
                messages.success(request, "Pago registrado correctamente.")
                return redirect("finanzas:cxc_detalle", pk=cuenta.pk)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        else:
            messages.error(request, "Revisa los datos del pago.")
    else:
        form = RegistrarPagoForm()
    pagos = cuenta.pagos.select_related("registrado_por")
    return render(request, "finanzas/cxc_detalle.html", {"cuenta": cuenta, "form": form, "pagos": pagos})


@login_required
def cxp_lista(request):
    cuentas = (
        CuentaPorPagar.objects.select_related("compra", "compra__proveedor", "nomina")
        .filter(empresa=request.empresa)
    )
    estado = request.GET.get("estado", "")
    if estado:
        cuentas = cuentas.filter(estado=estado)
    return render(request, "finanzas/cxp_lista.html", {"cuentas": cuentas, "estado": estado})


@login_required
def cxp_detalle(request, pk):
    cuenta = get_object_or_404(
        CuentaPorPagar.objects.select_related("compra", "compra__proveedor", "nomina"),
        pk=pk, empresa=request.empresa,
    )
    if request.method == "POST":
        form = RegistrarPagoForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    cuenta_bloqueada = CuentaPorPagar.objects.select_for_update().get(pk=cuenta.pk)
                    cuenta_bloqueada.registrar_pago(
                        monto=form.cleaned_data["monto"],
                        metodo=form.cleaned_data["metodo"],
                        referencia=form.cleaned_data["referencia"],
                        usuario=request.user,
                    )
                messages.success(request, "Pago registrado correctamente.")
                return redirect("finanzas:cxp_detalle", pk=cuenta.pk)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        else:
            messages.error(request, "Revisa los datos del pago.")
    else:
        form = RegistrarPagoForm()
    pagos = cuenta.pagos.select_related("registrado_por")
    return render(request, "finanzas/cxp_detalle.html", {"cuenta": cuenta, "form": form, "pagos": pagos})
