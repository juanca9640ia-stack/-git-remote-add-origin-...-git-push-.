import calendar
import json
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import intcomma
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from comunicaciones.models import Comunicado
from compras.models import Compra, Proveedor
from documentos.models import Documento
from finanzas.models import CuentaPorCobrar, CuentaPorPagar
from inventario.models import Producto
from produccion.models import OrdenProduccion
from proyectos.models import HitoProyecto, Proyecto
from rrhh.models import Empleado
from ventas.models import Cliente, Cotizacion, Venta


def _money(value):
    return f"${intcomma(f'{value:.2f}')}"


MESES_ABREV = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}

MESES_COMPLETOS = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}

DIAS_SEMANA_ABREV = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

PERIODOS = {
    # clave -> (etiqueta, días hacia atrás desde hoy; None = desde el 1º del año)
    "semana": ("Última semana", 6),
    "mes": ("Este mes", None),
    "trimestre": ("Últimos 90 días", 89),
    "anio": ("Este año", None),
}


def _rango_periodo(periodo, hoy):
    """Devuelve (fecha_desde, agrupar_por_mes) para el periodo pedido."""
    if periodo == "semana":
        return hoy - timedelta(days=6), False
    if periodo == "trimestre":
        return hoy - timedelta(days=89), False
    if periodo == "anio":
        return hoy.replace(month=1, day=1), True
    # "mes" (por defecto)
    return hoy.replace(day=1), False


def _construir_alertas(request):
    """Todo lo que requiere atención del usuario, en un solo lugar: la campana
    de notificaciones del shellbar y el centro de alertas del dashboard
    comparten esta misma lista. Cada categoría se omite si el usuario no
    tiene acceso al módulo correspondiente."""
    empresa = request.empresa
    hoy = timezone.localdate()
    alertas = []

    if request.user.has_module_perms("finanzas"):
        cxc_vencidas = CuentaPorCobrar.objects.filter(
            empresa=empresa,
            fecha_vencimiento__lt=hoy, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
        )
        cxc_vencidas_count = cxc_vencidas.count()
        if cxc_vencidas_count:
            cxc_vencidas_total = sum((c.saldo_pendiente for c in cxc_vencidas), Decimal("0"))
            alertas.append({
                "severidad": "danger", "icono": "bi-exclamation-triangle-fill",
                "mensaje": f"{cxc_vencidas_count} factura(s) por cobrar vencida(s) por {_money(cxc_vencidas_total)}.",
                "url": reverse("finanzas:cxc_lista") + "?vencidas=1", "accion": "Ver vencidas",
            })

    if request.user.has_module_perms("inventario"):
        productos_stock_bajo = [p for p in Producto.objects.filter(activo=True, empresa=empresa) if p.stock_bajo]
        if productos_stock_bajo:
            alertas.append({
                "severidad": "warning", "icono": "bi-box-seam",
                "mensaje": f"{len(productos_stock_bajo)} producto(s) por debajo del stock mínimo.",
                "url": reverse("inventario:producto_lista"), "accion": "Ver inventario",
            })

    if request.user.has_module_perms("ventas"):
        cotizaciones_vencidas_count = Cotizacion.objects.filter(
            empresa=empresa, estado=Cotizacion.ENVIADA, fecha_validez__lt=hoy,
        ).count()
        if cotizaciones_vencidas_count:
            alertas.append({
                "severidad": "warning", "icono": "bi-file-earmark-text",
                "mensaje": f"{cotizaciones_vencidas_count} cotización(es) enviada(s) venció su vigencia sin respuesta.",
                "url": reverse("ventas:cotizacion_lista"), "accion": "Ver cotizaciones",
            })

    if request.user.has_module_perms("proyectos"):
        hitos_vencidos_count = HitoProyecto.objects.filter(
            empresa=empresa, completado=False, fecha_objetivo__lt=hoy, proyecto__estado__in=Proyecto.ESTADOS_ACTIVOS,
        ).count()
        if hitos_vencidos_count:
            alertas.append({
                "severidad": "warning", "icono": "bi-buildings",
                "mensaje": f"{hitos_vencidos_count} hito(s) de obra vencido(s) sin completar.",
                "url": reverse("proyectos:proyecto_lista"), "accion": "Ver proyectos",
            })
        proyectos_sobre_presupuesto = [
            p for p in Proyecto.objects.filter(empresa=empresa, estado__in=Proyecto.ESTADOS_ACTIVOS)
            if p.sobre_presupuesto
        ]
        if proyectos_sobre_presupuesto:
            alertas.append({
                "severidad": "danger", "icono": "bi-graph-up-arrow",
                "mensaje": f"{len(proyectos_sobre_presupuesto)} obra(s) sobrepasaron su presupuesto.",
                "url": reverse("proyectos:proyecto_lista"), "accion": "Ver proyectos",
            })

    return alertas


@login_required
def dashboard(request):
    if not (request.user.is_superuser or request.user.has_perm("core.ver_dashboard")):
        if request.user.has_perm("rrhh.marcar_propia_asistencia") or request.user.has_perm("rrhh.ver_propio_perfil"):
            return redirect("rrhh:mi_perfil")
        return render(request, "core/sin_acceso.html")

    empresa = request.empresa
    productos = Producto.objects.filter(activo=True, empresa=empresa)
    productos_stock_bajo = [p for p in productos if p.stock_bajo]
    valor_inventario = sum((p.valor_inventario for p in productos), Decimal("0"))

    hoy = timezone.localdate()
    periodo = request.GET.get("periodo", "mes")
    if periodo not in PERIODOS:
        periodo = "mes"
    fecha_desde, agrupar_por_mes = _rango_periodo(periodo, hoy)

    ventas_confirmadas = Venta.objects.filter(estado=Venta.CONFIRMADA, empresa=empresa)
    ventas_hoy = ventas_confirmadas.filter(confirmada_en__date=hoy)
    total_ventas_hoy = sum((v.total for v in ventas_hoy), Decimal("0"))
    ventas_periodo = ventas_confirmadas.filter(confirmada_en__date__gte=fecha_desde)
    total_ventas_mes = sum((v.total for v in ventas_periodo), Decimal("0"))

    compras_confirmadas = Compra.objects.filter(estado=Compra.CONFIRMADA, empresa=empresa)
    total_compras_mes = sum(
        (c.total for c in compras_confirmadas.filter(creado_en__date__gte=fecha_desde)), Decimal("0")
    )

    # Serie para el gráfico de ventas: por mes si el periodo es "Este año",
    # por día en cualquier otro caso. "total" es una propiedad calculada (no un
    # campo de BD, depende de las líneas), así que se agrupa en Python.
    serie_por_bucket = {}
    for v in ventas_periodo:
        fecha_v = timezone.localtime(v.confirmada_en).date()
        bucket = fecha_v.replace(day=1) if agrupar_por_mes else fecha_v
        serie_por_bucket[bucket] = serie_por_bucket.get(bucket, Decimal("0")) + v.total

    etiquetas, valores = [], []
    if agrupar_por_mes:
        cursor = fecha_desde.replace(day=1)
        while cursor <= hoy:
            etiquetas.append(MESES_ABREV[cursor.month])
            valores.append(float(serie_por_bucket.get(cursor, Decimal("0"))))
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    else:
        cursor = fecha_desde
        while cursor <= hoy:
            etiquetas.append(cursor.strftime("%d/%m"))
            valores.append(float(serie_por_bucket.get(cursor, Decimal("0"))))
            cursor += timedelta(days=1)

    cxc_activas = CuentaPorCobrar.objects.filter(empresa=empresa).exclude(estado=CuentaPorCobrar.ANULADA)
    cxp_activas = CuentaPorPagar.objects.filter(empresa=empresa).exclude(estado=CuentaPorPagar.ANULADA)
    total_por_cobrar = sum((c.saldo_pendiente for c in cxc_activas), Decimal("0"))
    total_por_pagar = sum((c.saldo_pendiente for c in cxp_activas), Decimal("0"))
    cxc_pendientes_count = cxc_activas.exclude(estado=CuentaPorCobrar.PAGADA).count()
    cxp_pendientes_count = cxp_activas.exclude(estado=CuentaPorPagar.PAGADA).count()

    cxc_vencidas = CuentaPorCobrar.objects.filter(
        empresa=empresa,
        fecha_vencimiento__lt=hoy, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
    )
    cxc_vencidas_count = cxc_vencidas.count()
    cxc_vencidas_total = sum((c.saldo_pendiente for c in cxc_vencidas), Decimal("0"))

    # Centro de alertas unificado: todo lo que requiere atención, en un solo lugar,
    # ordenado por severidad. Se comparte con la campana de notificaciones del shellbar.
    alertas = _construir_alertas(request)

    ordenes_planificadas = OrdenProduccion.objects.filter(
        estado=OrdenProduccion.PLANIFICADA, empresa=empresa
    ).count()
    empleados_activos = Empleado.objects.filter(activo=True, empresa=empresa).count()

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
        "total_clientes": Venta.objects.filter(empresa=empresa).values("cliente").distinct().count(),
        "total_por_cobrar": total_por_cobrar,
        "total_por_pagar": total_por_pagar,
        "cxc_pendientes_count": cxc_pendientes_count,
        "cxp_pendientes_count": cxp_pendientes_count,
        "cxc_vencidas_count": cxc_vencidas_count,
        "cxc_vencidas_total": cxc_vencidas_total,
        "alertas": alertas,
        "periodo": periodo,
        "periodos": [{"clave": k, "etiqueta": v[0]} for k, v in PERIODOS.items()],
        "periodo_etiqueta": PERIODOS[periodo][0],
        "chart_labels": json.dumps(etiquetas),
        "chart_values": json.dumps(valores),
        "ultimos_comunicados": Comunicado.objects.filter(empresa=empresa)[:3],
    }
    return render(request, "core/dashboard.html", context)


LIMITE_RESULTADOS_POR_CATEGORIA = 5


@login_required
def busqueda_global(request):
    """Búsqueda rápida (Ctrl+K / barra superior) a través de todos los módulos
    a los que el usuario tenga acceso. Devuelve resultados agrupados por
    categoría, en JSON, para el desplegable del shellbar."""
    q = request.GET.get("q", "").strip()
    empresa = request.empresa
    resultados = []

    if len(q) < 2:
        return JsonResponse({"resultados": resultados})

    if request.user.has_module_perms("ventas"):
        clientes = Cliente.objects.filter(empresa=empresa).filter(
            Q(nombre__icontains=q) | Q(documento__icontains=q)
        )[:LIMITE_RESULTADOS_POR_CATEGORIA]
        if clientes:
            resultados.append({
                "categoria": "Clientes", "icono": "bi-people",
                "items": [
                    {"titulo": c.nombre, "subtitulo": c.documento or "Sin documento",
                     "url": reverse("ventas:cliente_detalle", args=[c.pk])}
                    for c in clientes
                ],
            })

        ventas = Venta.objects.filter(empresa=empresa).select_related("cliente").filter(
            Q(numero__icontains=q) | Q(numero_factura__icontains=q)
        )[:LIMITE_RESULTADOS_POR_CATEGORIA]
        if ventas:
            resultados.append({
                "categoria": "Ventas", "icono": "bi-receipt",
                "items": [
                    {"titulo": v.numero, "subtitulo": str(v.cliente),
                     "url": reverse("ventas:venta_detalle", args=[v.pk])}
                    for v in ventas
                ],
            })

        cotizaciones = Cotizacion.objects.filter(empresa=empresa, numero__icontains=q).select_related(
            "cliente"
        )[:LIMITE_RESULTADOS_POR_CATEGORIA]
        if cotizaciones:
            resultados.append({
                "categoria": "Cotizaciones", "icono": "bi-file-earmark-text",
                "items": [
                    {"titulo": c.numero, "subtitulo": str(c.cliente),
                     "url": reverse("ventas:cotizacion_detalle", args=[c.pk])}
                    for c in cotizaciones
                ],
            })

    if request.user.has_module_perms("inventario"):
        productos = Producto.objects.filter(empresa=empresa).filter(
            Q(sku__icontains=q) | Q(nombre__icontains=q)
        )[:LIMITE_RESULTADOS_POR_CATEGORIA]
        if productos:
            resultados.append({
                "categoria": "Productos y servicios", "icono": "bi-box-seam",
                "items": [
                    {"titulo": p.nombre, "subtitulo": p.sku,
                     "url": reverse("inventario:producto_detalle", args=[p.pk])}
                    for p in productos
                ],
            })

    if request.user.has_module_perms("compras"):
        proveedores = Proveedor.objects.filter(empresa=empresa).filter(
            Q(nombre__icontains=q) | Q(nit__icontains=q)
        )[:LIMITE_RESULTADOS_POR_CATEGORIA]
        if proveedores:
            resultados.append({
                "categoria": "Proveedores", "icono": "bi-truck",
                "items": [
                    {"titulo": p.nombre, "subtitulo": p.nit or "Sin NIT",
                     "url": reverse("compras:proveedor_editar", args=[p.pk])}
                    for p in proveedores
                ],
            })

        compras = Compra.objects.filter(empresa=empresa, numero__icontains=q).select_related(
            "proveedor"
        )[:LIMITE_RESULTADOS_POR_CATEGORIA]
        if compras:
            resultados.append({
                "categoria": "Compras", "icono": "bi-cart-check",
                "items": [
                    {"titulo": c.numero, "subtitulo": str(c.proveedor),
                     "url": reverse("compras:compra_detalle", args=[c.pk])}
                    for c in compras
                ],
            })

    if request.user.has_module_perms("rrhh"):
        empleados = Empleado.objects.filter(empresa=empresa).filter(
            Q(nombre_completo__icontains=q) | Q(documento__icontains=q)
        )[:LIMITE_RESULTADOS_POR_CATEGORIA]
        if empleados:
            resultados.append({
                "categoria": "Empleados", "icono": "bi-person-badge",
                "items": [
                    {"titulo": e.nombre_completo, "subtitulo": e.cargo,
                     "url": reverse("rrhh:empleado_detalle", args=[e.pk])}
                    for e in empleados
                ],
            })

    if request.user.has_module_perms("proyectos"):
        proyectos = Proyecto.objects.filter(empresa=empresa).filter(
            Q(numero__icontains=q) | Q(nombre__icontains=q)
        )[:LIMITE_RESULTADOS_POR_CATEGORIA]
        if proyectos:
            resultados.append({
                "categoria": "Proyectos", "icono": "bi-buildings",
                "items": [
                    {"titulo": p.nombre, "subtitulo": p.numero,
                     "url": reverse("proyectos:proyecto_detalle", args=[p.pk])}
                    for p in proyectos
                ],
            })

    if request.user.has_module_perms("documentos"):
        documentos = Documento.objects.filter(empresa=empresa, titulo__icontains=q)[:LIMITE_RESULTADOS_POR_CATEGORIA]
        if documentos:
            resultados.append({
                "categoria": "Documentos", "icono": "bi-folder2-open",
                "items": [
                    {"titulo": d.titulo, "subtitulo": d.get_categoria_display(), "url": d.archivo.url}
                    for d in documentos
                ],
            })

    return JsonResponse({"resultados": resultados})


@login_required
def notificaciones(request):
    """Feed de la campana del shellbar: las mismas alertas del dashboard,
    disponibles desde cualquier pantalla."""
    return JsonResponse({"alertas": _construir_alertas(request)})


def _eventos_calendario(request, fecha_desde, fecha_hasta):
    """Fechas importantes de todos los módulos, en un solo lugar: hitos y
    entregas de obra, vencimientos de cartera y de cotizaciones. Cada
    categoría se omite si el usuario no tiene acceso al módulo."""
    empresa = request.empresa
    eventos_por_dia = {}

    def agregar(fecha, evento):
        if fecha_desde <= fecha <= fecha_hasta:
            eventos_por_dia.setdefault(fecha, []).append(evento)

    if request.user.has_module_perms("proyectos"):
        hitos = HitoProyecto.objects.filter(
            empresa=empresa, fecha_objetivo__gte=fecha_desde, fecha_objetivo__lte=fecha_hasta,
        ).select_related("proyecto")
        for hito in hitos:
            agregar(hito.fecha_objetivo, {
                "color": "success" if hito.completado else ("danger" if hito.vencido else "info"),
                "icono": "bi-flag", "titulo": f"Hito: {hito.nombre} ({hito.proyecto.nombre})",
                "url": reverse("proyectos:proyecto_detalle", args=[hito.proyecto_id]),
            })
        entregas = Proyecto.objects.filter(
            empresa=empresa, fecha_fin_estimada__gte=fecha_desde, fecha_fin_estimada__lte=fecha_hasta,
        ).exclude(estado__in=[Proyecto.FINALIZADO, Proyecto.CANCELADO])
        for proyecto in entregas:
            agregar(proyecto.fecha_fin_estimada, {
                "color": "primary", "icono": "bi-buildings", "titulo": f"Entrega estimada: {proyecto.nombre}",
                "url": reverse("proyectos:proyecto_detalle", args=[proyecto.pk]),
            })

    if request.user.has_module_perms("finanzas"):
        cxc = CuentaPorCobrar.objects.filter(
            empresa=empresa, fecha_vencimiento__gte=fecha_desde, fecha_vencimiento__lte=fecha_hasta,
            estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
        ).select_related("venta", "venta__cliente")
        hoy = timezone.localdate()
        for cuenta in cxc:
            agregar(cuenta.fecha_vencimiento, {
                "color": "danger" if cuenta.fecha_vencimiento < hoy else "warning",
                "icono": "bi-cash-coin", "titulo": f"Vence CxC {cuenta.venta.numero} · {cuenta.venta.cliente}",
                "url": reverse("finanzas:cxc_detalle", args=[cuenta.pk]),
            })

    if request.user.has_module_perms("ventas"):
        cotizaciones = Cotizacion.objects.filter(
            empresa=empresa, estado=Cotizacion.ENVIADA,
            fecha_validez__gte=fecha_desde, fecha_validez__lte=fecha_hasta,
        ).select_related("cliente")
        for cot in cotizaciones:
            agregar(cot.fecha_validez, {
                "color": "warning", "icono": "bi-file-earmark-text",
                "titulo": f"Vence cotización {cot.numero} · {cot.cliente}",
                "url": reverse("ventas:cotizacion_detalle", args=[cot.pk]),
            })

    return eventos_por_dia


@login_required
def calendario(request):
    if not (request.user.is_superuser or request.user.has_perm("core.ver_dashboard")):
        return render(request, "core/sin_acceso.html")

    hoy = timezone.localdate()
    try:
        anio = int(request.GET.get("anio", hoy.year))
        mes = int(request.GET.get("mes", hoy.month))
        primer_dia = date(anio, mes, 1)
    except (ValueError, TypeError):
        anio, mes, primer_dia = hoy.year, hoy.month, hoy.replace(day=1)

    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])
    cal = calendar.Calendar(firstweekday=0)  # semana empieza en lunes
    semanas_dias = cal.monthdatescalendar(anio, mes)  # incluye días de meses vecinos para completar semanas

    fecha_desde = semanas_dias[0][0]
    fecha_hasta = semanas_dias[-1][-1]
    eventos_por_dia = _eventos_calendario(request, fecha_desde, fecha_hasta)

    semanas = [
        [{"fecha": dia, "es_del_mes": dia.month == mes, "es_hoy": dia == hoy, "eventos": eventos_por_dia.get(dia, [])}
         for dia in semana]
        for semana in semanas_dias
    ]

    mes_anterior_anio, mes_anterior = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
    mes_siguiente_anio, mes_siguiente = (anio + 1, 1) if mes == 12 else (anio, mes + 1)

    return render(request, "core/calendario.html", {
        "semanas": semanas,
        "mes_nombre_largo": MESES_COMPLETOS.get(mes, ""),
        "dias_semana": DIAS_SEMANA_ABREV,
        "anio": anio, "mes": mes,
        "mes_anterior_anio": mes_anterior_anio, "mes_anterior": mes_anterior,
        "mes_siguiente_anio": mes_siguiente_anio, "mes_siguiente": mes_siguiente,
        "total_eventos": sum(len(v) for v in eventos_por_dia.values()),
    })
