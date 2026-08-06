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


@login_required
def resumen(request):
    total_por_cobrar = CuentaPorCobrar.objects.exclude(estado=CuentaPorCobrar.ANULADA).aggregate(
        total=Sum("saldo_pendiente")
    )["total"] or Decimal("0")
    total_por_pagar = CuentaPorPagar.objects.exclude(estado=CuentaPorPagar.ANULADA).aggregate(
        total=Sum("saldo_pendiente")
    )["total"] or Decimal("0")

    ventas_confirmadas = Venta.objects.filter(estado=Venta.CONFIRMADA)
    compras_confirmadas = Compra.objects.filter(estado=Compra.CONFIRMADA)
    nominas_procesadas = Nomina.objects.filter(estado=Nomina.PROCESADA)
    ingresos_totales = sum((v.total for v in ventas_confirmadas), Decimal("0"))
    egresos_totales = (
        sum((c.total for c in compras_confirmadas), Decimal("0"))
        + sum((n.total_pagar for n in nominas_procesadas), Decimal("0"))
    )

    cxc_pendientes_qs = CuentaPorCobrar.objects.filter(
        estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL]
    ).select_related("venta", "venta__cliente")
    cxc_pendientes = cxc_pendientes_qs[:8]
    cxp_pendientes = CuentaPorPagar.objects.filter(
        estado__in=[CuentaPorPagar.PENDIENTE, CuentaPorPagar.PARCIAL]
    ).select_related("compra", "compra__proveedor", "nomina")[:8]

    hoy = timezone.localdate()
    cxc_vencidas_qs = cxc_pendientes_qs.filter(fecha_vencimiento__lt=hoy)
    cxc_vencidas_count = cxc_vencidas_qs.count()
    cxc_vencidas_total = cxc_vencidas_qs.aggregate(total=Sum("saldo_pendiente"))["total"] or Decimal("0")

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
    }
    return render(request, "finanzas/resumen.html", context)


@login_required
def cxc_lista(request):
    cuentas = CuentaPorCobrar.objects.select_related("venta", "venta__cliente").all()
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
        CuentaPorCobrar.objects.exclude(estado=CuentaPorCobrar.ANULADA)
        .values("venta__cliente__id", "venta__cliente__nombre")
        .annotate(saldo=Sum("saldo_pendiente"))
        .filter(saldo__gt=0)
        .order_by("-saldo")
    )
    saldo_maximo = saldo_por_cliente[0]["saldo"] if saldo_por_cliente else Decimal("0")
    for fila in saldo_por_cliente:
        fila["porcentaje"] = int(fila["saldo"] / saldo_maximo * 100) if saldo_maximo else 0

    vencidas_qs = CuentaPorCobrar.objects.filter(
        fecha_vencimiento__lt=hoy, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
    )
    vencidas_count = vencidas_qs.count()
    vencidas_total = vencidas_qs.aggregate(total=Sum("saldo_pendiente"))["total"] or Decimal("0")

    return render(request, "finanzas/cxc_lista.html", {
        "cuentas": cuentas, "estado": estado,
        "clientes": Cliente.objects.filter(ventas__cuenta_por_cobrar__isnull=False).distinct().order_by("nombre"),
        "cliente_id": cliente_id, "solo_vencidas": solo_vencidas,
        "saldo_por_cliente": saldo_por_cliente,
        "vencidas_count": vencidas_count, "vencidas_total": vencidas_total,
    })


@login_required
def cxc_detalle(request, pk):
    cuenta = get_object_or_404(CuentaPorCobrar.objects.select_related("venta", "venta__cliente"), pk=pk)
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
    cuentas = CuentaPorPagar.objects.select_related("compra", "compra__proveedor", "nomina").all()
    estado = request.GET.get("estado", "")
    if estado:
        cuentas = cuentas.filter(estado=estado)
    return render(request, "finanzas/cxp_lista.html", {"cuentas": cuentas, "estado": estado})


@login_required
def cxp_detalle(request, pk):
    cuenta = get_object_or_404(
        CuentaPorPagar.objects.select_related("compra", "compra__proveedor", "nomina"), pk=pk
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
