"""Capa de inteligencia de negocio del Centro de Comando.

Cálculos puros a partir de datos reales de la empresa, separados de las
vistas (que solo orquestan) y de las plantillas (que solo presentan). Nada
aquí inventa información: cuando no hay datos suficientes para un cálculo,
la función lo dice explícitamente en vez de simular un resultado.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.humanize.templatetags.humanize import intcomma
from django.urls import reverse
from django.utils import timezone

MESES_ABREV = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}

# Peso de cada nivel de prioridad, usado para ordenar alertas y componer
# "Lo más importante hoy". Más alto = más urgente.
PESO_PRIORIDAD = {"critica": 4, "alta": 3, "media": 2, "baja": 1}


def money(value):
    return f"${intcomma(f'{value:.2f}')}"


def _primer_dia_mes(fecha):
    return fecha.replace(day=1)


def _mes_anterior(fecha):
    fin_mes_anterior = _primer_dia_mes(fecha) - timedelta(days=1)
    return _primer_dia_mes(fin_mes_anterior), fin_mes_anterior


# ===========================================================================
# Salud empresarial
# ===========================================================================

def calcular_salud_empresarial(empresa, hoy):
    """Indicador 0-100 calculado a partir de ventas, flujo de caja, cobranza,
    proyectos y margen. Cada componente se omite si no hay datos para
    calcularlo; si no queda ningún componente, devuelve None (el llamador
    debe mostrar el mensaje de "recopilando información", nunca un número
    inventado)."""
    from finanzas.models import CuentaPorCobrar
    from proyectos.models import Proyecto
    from ventas.models import Cotizacion, Venta

    ventas_confirmadas = Venta.objects.filter(empresa=empresa, estado=Venta.CONFIRMADA)
    total_cotizaciones = Cotizacion.objects.filter(empresa=empresa).count()
    total_proyectos = Proyecto.objects.filter(empresa=empresa).count()
    señales_disponibles = ventas_confirmadas.count() + total_cotizaciones + total_proyectos
    if señales_disponibles < 3:
        return None

    componentes = []

    # 1. Ventas: mes actual vs. mes anterior.
    inicio_mes = _primer_dia_mes(hoy)
    inicio_mes_ant, fin_mes_ant = _mes_anterior(hoy)
    ventas_mes = sum((v.total for v in ventas_confirmadas.filter(confirmada_en__date__gte=inicio_mes)), Decimal("0"))
    ventas_mes_ant = sum(
        (v.total for v in ventas_confirmadas.filter(
            confirmada_en__date__gte=inicio_mes_ant, confirmada_en__date__lte=fin_mes_ant,
        )), Decimal("0"),
    )
    if ventas_mes_ant > 0:
        variacion = (ventas_mes - ventas_mes_ant) / ventas_mes_ant
        score = max(Decimal("0"), min(Decimal("100"), Decimal("60") + variacion * 100))
        tendencia = "up" if variacion > Decimal("0.02") else ("down" if variacion < Decimal("-0.02") else "flat")
        componentes.append({"clave": "ventas", "etiqueta": "Ventas", "score": float(score), "tendencia": tendencia})
    elif ventas_mes > 0:
        componentes.append({"clave": "ventas", "etiqueta": "Ventas", "score": 70.0, "tendencia": "up"})

    # 2. Flujo de caja: balance del mes (ingresos de ventas - egresos de compras/nómina).
    from compras.models import Compra
    from rrhh.models import Nomina
    compras_mes = sum(
        (c.total for c in Compra.objects.filter(
            empresa=empresa, estado=Compra.CONFIRMADA, creado_en__date__gte=inicio_mes,
        )), Decimal("0"),
    )
    nomina_mes = sum(
        (n.total_pagar for n in Nomina.objects.filter(
            empresa=empresa, estado=Nomina.PROCESADA, creado_en__date__gte=inicio_mes,
        )), Decimal("0"),
    )
    egresos_mes = compras_mes + nomina_mes
    if ventas_mes > 0 or egresos_mes > 0:
        balance = ventas_mes - egresos_mes
        base = ventas_mes if ventas_mes > 0 else egresos_mes
        ratio = balance / base if base else Decimal("0")
        score = max(Decimal("0"), min(Decimal("100"), Decimal("60") + ratio * 80))
        tendencia = "up" if balance > 0 else ("down" if balance < 0 else "flat")
        componentes.append({"clave": "caja", "etiqueta": "Flujo de caja", "score": float(score), "tendencia": tendencia})

    # 3. Cobranza: proporción de cartera vencida sobre la cartera activa.
    cxc_activas = CuentaPorCobrar.objects.filter(empresa=empresa).exclude(estado=CuentaPorCobrar.ANULADA)
    total_cartera = sum((c.saldo_pendiente for c in cxc_activas), Decimal("0"))
    if total_cartera > 0:
        cxc_vencidas = cxc_activas.filter(
            fecha_vencimiento__lt=hoy, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
        )
        vencida = sum((c.saldo_pendiente for c in cxc_vencidas), Decimal("0"))
        pct_vencida = vencida / total_cartera
        score = max(Decimal("0"), Decimal("100") - pct_vencida * 150)
        tendencia = "down" if pct_vencida > Decimal("0.15") else "flat"
        componentes.append({"clave": "cobranza", "etiqueta": "Cobranza", "score": float(score), "tendencia": tendencia})

    # 4. Proyectos: proporción de obras activas que NO están sobre presupuesto.
    proyectos_activos = list(Proyecto.objects.filter(empresa=empresa, estado__in=Proyecto.ESTADOS_ACTIVOS))
    if proyectos_activos:
        en_riesgo = sum(1 for p in proyectos_activos if p.sobre_presupuesto)
        pct_ok = 1 - (en_riesgo / len(proyectos_activos))
        score = pct_ok * 100
        tendencia = "up" if pct_ok >= 0.8 else ("down" if pct_ok < 0.5 else "flat")
        componentes.append({"clave": "proyectos", "etiqueta": "Proyectos", "score": score, "tendencia": tendencia})

        # 5. Margen: promedio del margen de utilidad de las obras que ya tienen ingresos.
        margenes = [p.margen_utilidad for p in proyectos_activos if p.margen_utilidad is not None]
        if margenes:
            margen_prom = sum(margenes) / len(margenes)
            score = max(0.0, min(100.0, 50.0 + float(margen_prom)))
            tendencia = "up" if margen_prom > 15 else ("down" if margen_prom < 0 else "flat")
            componentes.append({"clave": "margen", "etiqueta": "Margen", "score": score, "tendencia": tendencia})

    if not componentes:
        return None

    score_final = round(sum(c["score"] for c in componentes) / len(componentes))
    if score_final >= 75:
        estado, color = "Saludable", "success"
    elif score_final >= 50:
        estado, color = "Estable", "warning"
    else:
        estado, color = "Requiere atención", "danger"

    return {"score": score_final, "estado": estado, "color": color, "componentes": componentes}


# ===========================================================================
# Requiere atención (alertas priorizadas)
# ===========================================================================

def construir_alertas(request):
    """Todo lo que requiere atención del usuario, con nivel de prioridad, para
    la campana de notificaciones, el dashboard y 'Lo más importante hoy'.
    Cada categoría se omite si el usuario no tiene acceso al módulo."""
    from finanzas.models import CuentaPorCobrar
    from proyectos.models import HitoProyecto, Proyecto
    from ventas.models import Cotizacion

    empresa = request.empresa
    hoy = timezone.localdate()
    alertas = []

    if request.user.has_module_perms("finanzas"):
        cxc_vencidas = CuentaPorCobrar.objects.filter(
            empresa=empresa,
            fecha_vencimiento__lt=hoy, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
        ).select_related("venta", "venta__cliente")
        for cuenta in cxc_vencidas:
            dias_vencida = (hoy - cuenta.fecha_vencimiento).days
            alertas.append({
                "tipo": "alert", "prioridad": "critica" if dias_vencida > 30 else "alta",
                "severidad": "danger", "icono": "bi-exclamation-triangle-fill",
                "titulo": "Factura vencida",
                "mensaje": f"Cliente {cuenta.venta.cliente} tiene una factura vencida por {money(cuenta.saldo_pendiente)}.",
                "url": reverse("finanzas:cxc_detalle", args=[cuenta.pk]), "accion": "Ver factura",
            })

    if request.user.has_module_perms("inventario"):
        from inventario.models import Producto
        productos_stock_bajo = [p for p in Producto.objects.filter(activo=True, empresa=empresa) if p.stock_bajo]
        if productos_stock_bajo:
            alertas.append({
                "tipo": "alert", "prioridad": "media",
                "severidad": "warning", "icono": "bi-box-seam",
                "titulo": "Stock bajo",
                "mensaje": f"{len(productos_stock_bajo)} producto(s) por debajo del stock mínimo.",
                "url": reverse("inventario:producto_lista"), "accion": "Ver inventario",
            })

    if request.user.has_module_perms("ventas"):
        cotizaciones_vencidas = Cotizacion.objects.filter(
            empresa=empresa, estado=Cotizacion.ENVIADA, fecha_validez__lt=hoy,
        ).select_related("cliente")
        for cot in cotizaciones_vencidas:
            dias_sin_actividad = (hoy - (cot.enviada_en.date() if cot.enviada_en else cot.creado_en.date())).days
            alertas.append({
                "tipo": "alert", "prioridad": "alta" if cot.total > 0 and dias_sin_actividad > 7 else "media",
                "severidad": "warning", "icono": "bi-file-earmark-text",
                "titulo": "Cotización sin seguimiento",
                "mensaje": (
                    f"Cotización {cot.numero} por {money(cot.total)} lleva {dias_sin_actividad} "
                    f"día{'s' if dias_sin_actividad != 1 else ''} sin actividad."
                ),
                "url": reverse("ventas:cotizacion_detalle", args=[cot.pk]), "accion": "Ver cotización",
            })

    if request.user.has_module_perms("proyectos"):
        hitos_vencidos = HitoProyecto.objects.filter(
            empresa=empresa, completado=False, fecha_objetivo__lt=hoy, proyecto__estado__in=Proyecto.ESTADOS_ACTIVOS,
        ).select_related("proyecto")
        for hito in hitos_vencidos:
            alertas.append({
                "tipo": "alert", "prioridad": "alta",
                "severidad": "warning", "icono": "bi-flag",
                "titulo": "Hito de obra vencido",
                "mensaje": f"'{hito.nombre}' de {hito.proyecto.nombre} venció sin completarse.",
                "url": reverse("proyectos:proyecto_detalle", args=[hito.proyecto_id]), "accion": "Ver proyecto",
            })

        proyectos_activos = Proyecto.objects.filter(empresa=empresa, estado__in=Proyecto.ESTADOS_ACTIVOS)
        for p in proyectos_activos:
            if p.sobre_presupuesto:
                exceso = p.gastado - p.presupuesto
                pct = round(float(exceso / p.presupuesto * 100)) if p.presupuesto else 0
                alertas.append({
                    "tipo": "alert", "prioridad": "critica" if pct > 15 else "alta",
                    "severidad": "danger", "icono": "bi-graph-up-arrow",
                    "titulo": "Proyecto en riesgo",
                    "mensaje": f"'{p.nombre}' presenta un costo ejecutado {pct}% superior al presupuesto.",
                    "url": reverse("proyectos:proyecto_detalle", args=[p.pk]), "accion": "Ver proyecto",
                })

    if request.user.has_module_perms("finanzas"):
        from finanzas.models import CuentaPorPagar
        proximos_7 = hoy + timedelta(days=7)
        cxp_proximas = CuentaPorPagar.objects.filter(
            empresa=empresa, estado__in=[CuentaPorPagar.PENDIENTE, CuentaPorPagar.PARCIAL],
        )
        # CuentaPorPagar no tiene fecha de vencimiento propia todavía: se informa el
        # total pendiente como recordatorio general, no como vencimiento puntual.
        total_cxp = sum((c.saldo_pendiente for c in cxp_proximas), Decimal("0"))
        if total_cxp > 0:
            alertas.append({
                "tipo": "alert", "prioridad": "baja",
                "severidad": "warning", "icono": "bi-wallet2",
                "titulo": "Pagos pendientes",
                "mensaje": f"Tienes {money(total_cxp)} en cuentas por pagar pendientes.",
                "url": reverse("finanzas:cxp_lista"), "accion": "Ver pagos",
            })

    alertas.sort(key=lambda a: PESO_PRIORIDAD.get(a["prioridad"], 0), reverse=True)
    return alertas


# ===========================================================================
# Oportunidades
# ===========================================================================

def detectar_oportunidades(request):
    """Situaciones favorables detectadas automáticamente: cotizaciones de alto
    valor en negociación, clientes que están comprando más, y proyectos con
    margen superior al promedio. Solo se reportan si hay datos reales que las
    respalden."""
    from proyectos.models import Proyecto
    from ventas.models import Cotizacion, Venta

    empresa = request.empresa
    hoy = timezone.localdate()
    oportunidades = []

    if request.user.has_module_perms("ventas"):
        cotizaciones_negociacion = Cotizacion.objects.filter(
            empresa=empresa, estado=Cotizacion.ENVIADA,
        ).select_related("cliente").order_by("-creado_en")
        for cot in cotizaciones_negociacion:
            if cot.total >= Decimal("50000000"):  # cotización de alto valor
                oportunidades.append({
                    "tipo": "opportunity", "icono": "bi-graph-up",
                    "titulo": "Cotización de alto valor",
                    "mensaje": f"Cliente {cot.cliente} tiene una cotización de {money(cot.total)} en negociación.",
                    "url": reverse("ventas:cotizacion_detalle", args=[cot.pk]), "accion": "Ver oportunidad",
                })

        # Clientes cuyas compras de este mes superan claramente las del mes anterior.
        inicio_mes = _primer_dia_mes(hoy)
        inicio_mes_ant, fin_mes_ant = _mes_anterior(hoy)
        ventas_confirmadas = Venta.objects.filter(empresa=empresa, estado=Venta.CONFIRMADA).select_related("cliente")
        por_cliente_mes, por_cliente_mes_ant = {}, {}
        for v in ventas_confirmadas.filter(confirmada_en__date__gte=inicio_mes):
            por_cliente_mes[v.cliente_id] = por_cliente_mes.get(v.cliente_id, Decimal("0")) + v.total
        for v in ventas_confirmadas.filter(confirmada_en__date__gte=inicio_mes_ant, confirmada_en__date__lte=fin_mes_ant):
            por_cliente_mes_ant[v.cliente_id] = por_cliente_mes_ant.get(v.cliente_id, Decimal("0")) + v.total
        for cliente_id, total_mes in por_cliente_mes.items():
            total_ant = por_cliente_mes_ant.get(cliente_id)
            if total_ant and total_mes >= total_ant * Decimal("1.3"):
                crecimiento = round(float((total_mes - total_ant) / total_ant * 100))
                cliente = ventas_confirmadas.filter(cliente_id=cliente_id).first().cliente
                oportunidades.append({
                    "tipo": "opportunity", "icono": "bi-arrow-up-circle",
                    "titulo": "Cliente con potencial",
                    "mensaje": f"Cliente {cliente} aumentó sus compras {crecimiento}% este mes.",
                    "url": reverse("ventas:cliente_detalle", args=[cliente_id]), "accion": "Ver cliente",
                })

    if request.user.has_module_perms("proyectos"):
        proyectos_activos = Proyecto.objects.filter(empresa=empresa, estado__in=Proyecto.ESTADOS_ACTIVOS)
        for p in proyectos_activos:
            if p.margen_utilidad is not None and p.margen_utilidad >= 20:
                oportunidades.append({
                    "tipo": "opportunity", "icono": "bi-trophy",
                    "titulo": "Proyecto rentable",
                    "mensaje": f"'{p.nombre}' presenta un margen del {p.margen_utilidad}%, superior al promedio.",
                    "url": reverse("proyectos:proyecto_detalle", args=[p.pk]), "accion": "Ver proyecto",
                })

    return oportunidades


# ===========================================================================
# Resumen ejecutivo automático
# ===========================================================================

def generar_resumen_ejecutivo(request, alertas, oportunidades):
    """Una síntesis en un par de frases, generada solo a partir de números
    reales ya calculados. Si no hay suficiente actividad, lo dice."""
    from ventas.models import Cotizacion, Venta

    empresa = request.empresa
    hoy = timezone.localdate()
    inicio_mes = _primer_dia_mes(hoy)
    inicio_mes_ant, fin_mes_ant = _mes_anterior(hoy)

    ventas_confirmadas = Venta.objects.filter(empresa=empresa, estado=Venta.CONFIRMADA)
    ventas_mes = sum((v.total for v in ventas_confirmadas.filter(confirmada_en__date__gte=inicio_mes)), Decimal("0"))
    ventas_mes_ant = sum(
        (v.total for v in ventas_confirmadas.filter(
            confirmada_en__date__gte=inicio_mes_ant, confirmada_en__date__lte=fin_mes_ant,
        )), Decimal("0"),
    )

    frases = []

    if ventas_mes_ant > 0:
        variacion = round(float((ventas_mes - ventas_mes_ant) / ventas_mes_ant * 100))
        verbo = "aumentaron" if variacion >= 0 else "cayeron"
        frases.append(f"Este mes las ventas {verbo} {abs(variacion)}% frente al mes anterior.")
    elif ventas_mes > 0:
        frases.append(f"Este mes se han confirmado ventas por {money(ventas_mes)}.")

    if request.user.has_module_perms("ventas"):
        en_negociacion = Cotizacion.objects.filter(empresa=empresa, estado=Cotizacion.ENVIADA)
        valor_negociacion = sum((c.total for c in en_negociacion), Decimal("0"))
        if valor_negociacion > 0:
            frases.append(f"Las cotizaciones en negociación representan {money(valor_negociacion)}.")

    criticas = [a for a in alertas if a["prioridad"] in ("critica", "alta")]
    if criticas:
        palabra = "situación" if len(criticas) == 1 else "situaciones"
        frases.append(
            f"Hay {len(criticas)} {palabra} que requiere{'n' if len(criticas) != 1 else ''} "
            "atención prioritaria: " + "; ".join(a["titulo"].lower() for a in criticas[:3]) + "."
        )

    if oportunidades:
        frases.append(f"Se detectaron {len(oportunidades)} oportunidad{'es' if len(oportunidades) != 1 else ''} comercial{'es' if len(oportunidades) != 1 else ''} o financiera{'s' if len(oportunidades) != 1 else ''}.")

    if not frases:
        return None
    return " ".join(frases)


# ===========================================================================
# Actividad reciente
# ===========================================================================

def construir_actividad_reciente(request, limite=8):
    """Línea de tiempo de lo último que pasó en el sistema, reconstruida a
    partir de las marcas de tiempo que ya existen en cada modelo (no hay un
    registro de auditoría dedicado: esto es lo mejor que se puede reconstruir
    sin inventar datos)."""
    from finanzas.models import PagoCliente
    from proyectos.models import Proyecto
    from ventas.models import Cotizacion, Venta

    empresa = request.empresa
    eventos = []

    if request.user.has_module_perms("ventas"):
        for v in Venta.objects.filter(empresa=empresa, facturada_en__isnull=False).select_related("cliente").order_by("-facturada_en")[:limite]:
            eventos.append({
                "cuando": v.facturada_en, "icono": "bi-receipt",
                "mensaje": f"Se facturó {v.numero_factura} a {v.cliente} por {money(v.total)}.",
                "url": reverse("ventas:venta_detalle", args=[v.pk]),
            })
        for cot in Cotizacion.objects.filter(empresa=empresa, estado=Cotizacion.ACEPTADA).select_related("cliente").order_by("-firmado_en")[:limite]:
            if cot.firmado_en:
                eventos.append({
                    "cuando": cot.firmado_en, "icono": "bi-pen",
                    "mensaje": f"Cotización {cot.numero} de {cot.cliente} fue aprobada.",
                    "url": reverse("ventas:cotizacion_detalle", args=[cot.pk]),
                })

    if request.user.has_module_perms("finanzas"):
        for pago in PagoCliente.objects.filter(empresa=empresa).select_related(
            "cuenta__venta__cliente", "registrado_por"
        ).order_by("-creado_en")[:limite]:
            quien = pago.registrado_por.get_full_name() or pago.registrado_por.get_username() if pago.registrado_por else "el sistema"
            eventos.append({
                "cuando": pago.creado_en, "icono": "bi-cash-coin",
                "mensaje": f"{pago.cuenta.venta.cliente} realizó un pago de {money(pago.monto)} (registrado por {quien}).",
                "url": reverse("finanzas:cxc_detalle", args=[pago.cuenta_id]),
            })

    if request.user.has_module_perms("proyectos"):
        for p in Proyecto.objects.filter(empresa=empresa).order_by("-creado_en")[:limite]:
            eventos.append({
                "cuando": p.creado_en, "icono": "bi-buildings",
                "mensaje": f"Se creó el proyecto '{p.nombre}'.",
                "url": reverse("proyectos:proyecto_detalle", args=[p.pk]),
            })

    eventos.sort(key=lambda e: e["cuando"], reverse=True)
    return eventos[:limite]


# ===========================================================================
# Lo más importante hoy
# ===========================================================================

def construir_lo_mas_importante(alertas, oportunidades, limite=5):
    """Los `limite` asuntos más urgentes del día, mezclando alertas (con su
    prioridad) y oportunidades relevantes, en un solo listado accionable."""
    items = []
    for a in alertas:
        items.append({
            "peso": PESO_PRIORIDAD.get(a["prioridad"], 0) + 10,  # las alertas pesan más que las oportunidades
            "icono": a["icono"], "severidad": a["severidad"],
            "mensaje": a["mensaje"], "url": a["url"], "accion": a["accion"],
        })
    for o in oportunidades:
        items.append({
            "peso": 5,
            "icono": o["icono"], "severidad": "success",
            "mensaje": o["mensaje"], "url": o["url"], "accion": o["accion"],
        })
    items.sort(key=lambda i: i["peso"], reverse=True)
    return items[:limite]
