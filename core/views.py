from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import intcomma
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from compras.models import Compra
from finanzas.models import CuentaPorCobrar, CuentaPorPagar
from inventario.models import Producto
from produccion.models import OrdenProduccion
from rrhh.models import Empleado
from ventas.models import Venta


def _money(value):
    return f"${intcomma(f'{value:.2f}')}"


@login_required
def dashboard(request):
    productos = Producto.objects.filter(activo=True)
    productos_stock_bajo = [p for p in productos if p.stock_bajo]
    valor_inventario = sum((p.valor_inventario for p in productos), Decimal("0"))

    hoy = timezone.localdate()
    ventas_confirmadas = Venta.objects.filter(estado=Venta.CONFIRMADA)
    ventas_hoy = ventas_confirmadas.filter(confirmada_en__date=hoy)
    total_ventas_hoy = sum((v.total for v in ventas_hoy), Decimal("0"))
    total_ventas_mes = sum(
        (v.total for v in ventas_confirmadas.filter(
            confirmada_en__year=hoy.year, confirmada_en__month=hoy.month
        )), Decimal("0")
    )

    compras_confirmadas = Compra.objects.filter(estado=Compra.CONFIRMADA)
    total_compras_mes = sum(
        (c.total for c in compras_confirmadas.filter(
            creado_en__year=hoy.year, creado_en__month=hoy.month
        )), Decimal("0")
    )

    cxc_activas = CuentaPorCobrar.objects.exclude(estado=CuentaPorCobrar.ANULADA)
    cxp_activas = CuentaPorPagar.objects.exclude(estado=CuentaPorPagar.ANULADA)
    total_por_cobrar = sum((c.saldo_pendiente for c in cxc_activas), Decimal("0"))
    total_por_pagar = sum((c.saldo_pendiente for c in cxp_activas), Decimal("0"))
    cxc_pendientes_count = cxc_activas.exclude(estado=CuentaPorCobrar.PAGADA).count()
    cxp_pendientes_count = cxp_activas.exclude(estado=CuentaPorPagar.PAGADA).count()

    cxc_vencidas = CuentaPorCobrar.objects.filter(
        fecha_vencimiento__lt=hoy, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
    )
    cxc_vencidas_count = cxc_vencidas.count()
    cxc_vencidas_total = sum((c.saldo_pendiente for c in cxc_vencidas), Decimal("0"))

    ordenes_planificadas = OrdenProduccion.objects.filter(estado=OrdenProduccion.PLANIFICADA).count()
    empleados_activos = Empleado.objects.filter(activo=True).count()

    tiles = [
        {
            "title": "Ventas", "icon": "bi-receipt", "color": "blue",
            "value": _money(total_ventas_mes), "label": "Ventas del mes",
            "url": reverse("ventas:venta_lista"),
        },
        {
            "title": "Compras", "icon": "bi-cart-check", "color": "teal",
            "value": _money(total_compras_mes), "label": "Compras del mes",
            "url": reverse("compras:compra_lista"),
        },
        {
            "title": "Inventario", "icon": "bi-box-seam", "color": "indigo",
            "value": _money(valor_inventario), "label": f"{len(productos_stock_bajo)} alerta(s) de stock bajo",
            "url": reverse("inventario:producto_lista"),
        },
        {
            "title": "Finanzas", "icon": "bi-graph-up-arrow", "color": "green",
            "value": _money(total_por_cobrar), "label": f"Por pagar: {_money(total_por_pagar)}",
            "url": reverse("finanzas:resumen"),
        },
        {
            "title": "Producción", "icon": "bi-gear-wide-connected", "color": "orange",
            "value": str(ordenes_planificadas), "label": "Órdenes planificadas",
            "url": reverse("produccion:orden_lista"),
        },
        {
            "title": "RR.HH.", "icon": "bi-person-badge", "color": "purple",
            "value": str(empleados_activos), "label": "Empleados activos",
            "url": reverse("rrhh:resumen"),
        },
    ]

    ultimas_ventas = ventas_confirmadas.select_related("cliente").order_by("-confirmada_en")[:5]

    context = {
        "tiles": tiles,
        "total_productos": productos.count(),
        "productos_stock_bajo": productos_stock_bajo,
        "valor_inventario": valor_inventario,
        "ventas_hoy_count": ventas_hoy.count(),
        "total_ventas_hoy": total_ventas_hoy,
        "total_ventas_mes": total_ventas_mes,
        "ultimas_ventas": ultimas_ventas,
        "total_clientes": Venta.objects.values("cliente").distinct().count(),
        "total_por_cobrar": total_por_cobrar,
        "total_por_pagar": total_por_pagar,
        "cxc_pendientes_count": cxc_pendientes_count,
        "cxp_pendientes_count": cxp_pendientes_count,
        "cxc_vencidas_count": cxc_vencidas_count,
        "cxc_vencidas_total": cxc_vencidas_total,
    }
    return render(request, "core/dashboard.html", context)
