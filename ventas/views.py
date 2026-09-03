from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from inventario.models import Producto

from .forms import (
    ClienteForm, ClienteRapidoForm, CotizacionForm, CuentaCobroForm, LineaCotizacionFormSet, LineaVentaFormSet,
    VentaForm,
)
from .models import Cliente, Cotizacion, CuentaCobro, Venta


def _precios_producto_json(empresa):
    return {str(p.pk): str(p.precio_venta) for p in Producto.objects.filter(activo=True, empresa=empresa)}


def _descripciones_producto_json(empresa):
    return {str(p.pk): p.descripcion for p in Producto.objects.filter(activo=True, empresa=empresa)}


def _resolver_cotizacion_origen(request):
    """La cotización desde la que se está generando un documento: viene
    explícita en ?cotizacion=, o si no, se deduce del proyecto (?proyecto=)
    cuando esa obra nació de una cotización. Así, al facturar o generar una
    cuenta de cobro desde un proyecto, se copian sus datos automáticamente
    sin tener que volver a indicar la cotización."""
    cotizacion_id = request.GET.get("cotizacion")
    if cotizacion_id:
        return Cotizacion.objects.filter(pk=cotizacion_id, empresa=request.empresa).select_related("cliente").first()

    proyecto_id = request.GET.get("proyecto")
    if proyecto_id:
        return Cotizacion.objects.filter(
            proyecto_id=proyecto_id, empresa=request.empresa
        ).select_related("cliente").first()

    return None


def _concepto_desde_cotizacion(cotizacion):
    """Concepto de cuenta de cobro con las descripciones de cada línea de la
    cotización, no solo su número."""
    lineas = [
        f"- {l.producto.nombre}" + (f": {l.producto.descripcion}" if l.producto.descripcion else "") + f" (cant. {l.cantidad})"
        for l in cotizacion.lineas.select_related("producto")
    ]
    if lineas:
        return f"Según cotización {cotizacion.numero}:\n" + "\n".join(lineas)
    return f"Según cotización {cotizacion.numero}."


@login_required
def cliente_lista(request):
    query = request.GET.get("q", "")
    clientes = Cliente.objects.filter(empresa=request.empresa)
    if query:
        clientes = clientes.filter(Q(nombre__icontains=query) | Q(documento__icontains=query))
    return render(request, "ventas/cliente_lista.html", {"clientes": clientes, "query": query})


@login_required
def cliente_detalle(request, pk):
    """Vista 360°: todo lo que hay que saber de un cliente en una sola pantalla
    (compras, cotizaciones, proyectos, cartera, pagos, cuentas de cobro y documentos)."""
    from bitacora.models import Sede
    from finanzas.models import CuentaPorCobrar, PagoCliente

    cliente = get_object_or_404(Cliente, pk=pk, empresa=request.empresa)

    ventas = Venta.objects.filter(cliente=cliente, empresa=request.empresa).order_by("-creado_en")
    ventas_confirmadas = ventas.filter(estado=Venta.CONFIRMADA)
    total_facturado = sum((v.total for v in ventas_confirmadas), Decimal("0"))
    ultima_venta = ventas_confirmadas.first()

    cotizaciones = Cotizacion.objects.filter(cliente=cliente, empresa=request.empresa).order_by("-creado_en")
    cotizaciones_decididas = cotizaciones.filter(estado__in=[Cotizacion.ACEPTADA, Cotizacion.RECHAZADA]).count()
    cotizaciones_aceptadas = cotizaciones.filter(estado=Cotizacion.ACEPTADA).count()
    tasa_conversion = round(cotizaciones_aceptadas / cotizaciones_decididas * 100) if cotizaciones_decididas else None

    cxc = CuentaPorCobrar.objects.filter(venta__cliente=cliente, empresa=request.empresa).exclude(
        estado=CuentaPorCobrar.ANULADA
    )
    saldo_pendiente = cxc.aggregate(total=Sum("saldo_pendiente"))["total"] or Decimal("0")
    hoy = timezone.localdate()
    cxc_vencidas = cxc.filter(
        fecha_vencimiento__lt=hoy, estado__in=[CuentaPorCobrar.PENDIENTE, CuentaPorCobrar.PARCIAL],
    ).count()

    cuentas_cobro = CuentaCobro.objects.filter(cliente=cliente, empresa=request.empresa).order_by("-creado_en")

    pagos = PagoCliente.objects.filter(
        cuenta__venta__cliente=cliente, empresa=request.empresa
    ).select_related("cuenta__venta").order_by("-creado_en")

    context = {
        "cliente": cliente,
        "total_facturado": total_facturado,
        "ultima_venta": ultima_venta,
        "ventas": ventas[:10],
        "ventas_count": ventas.count(),
        "cotizaciones": cotizaciones[:10],
        "cotizaciones_count": cotizaciones.count(),
        "tasa_conversion": tasa_conversion,
        "saldo_pendiente": saldo_pendiente,
        "cxc_vencidas": cxc_vencidas,
        "cuentas_cobro": cuentas_cobro[:10],
        "documentos": cliente.documentos.all()[:10],
        "proyectos": cliente.proyectos.all()[:10],
        "proyectos_count": cliente.proyectos.count(),
        "pagos": pagos[:10],
        "sedes": Sede.objects.filter(cliente=cliente, empresa=request.empresa),
    }
    return render(request, "ventas/cliente_detalle.html", context)


@login_required
def cliente_form(request, pk=None):
    cliente = get_object_or_404(Cliente, pk=pk, empresa=request.empresa) if pk else None
    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.empresa = request.empresa
            obj.save()
            messages.success(request, f"Cliente '{obj.nombre}' guardado correctamente.")
            return redirect("ventas:cliente_lista")
    else:
        form = ClienteForm(instance=cliente)
    return render(request, "ventas/cliente_form.html", {"form": form, "cliente": cliente})


@login_required
@require_POST
def cliente_crear_rapido(request):
    """Crea un cliente desde el modal de ventas/cotizaciones sin salir del formulario."""
    form = ClienteRapidoForm(request.POST)
    if form.is_valid():
        cliente = form.save(commit=False)
        cliente.empresa = request.empresa
        cliente.save()
        return JsonResponse({"ok": True, "id": cliente.pk, "nombre": str(cliente)})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
def venta_lista(request):
    ventas = Venta.objects.select_related("cliente", "vendedor").filter(empresa=request.empresa)
    estado = request.GET.get("estado", "")
    if estado:
        ventas = ventas.filter(estado=estado)
    return render(request, "ventas/venta_lista.html", {"ventas": ventas, "estado": estado})


@login_required
def venta_detalle(request, pk):
    venta = get_object_or_404(
        Venta.objects.select_related("cliente", "vendedor"), pk=pk, empresa=request.empresa
    )
    sugerencia_factura = ""
    if venta.estado == Venta.CONFIRMADA and not venta.numero_factura:
        sugerencia_factura = Venta.siguiente_numero_factura_sugerido(request.empresa)
    return render(request, "ventas/venta_detalle.html", {
        "venta": venta, "sugerencia_factura": sugerencia_factura,
    })


@login_required
def venta_imprimir(request, pk):
    venta = get_object_or_404(
        Venta.objects.select_related("cliente", "vendedor", "proyecto").prefetch_related("lineas__producto"),
        pk=pk, empresa=request.empresa,
    )
    return render(request, "ventas/venta_pdf.html", {"venta": venta, "empresa": request.empresa})


@login_required
def elegir_documento(request):
    """Punto de entrada único para generar un documento de cobro: el sistema
    siempre pregunta primero qué tipo de documento se necesita, en vez de
    asumirlo. Se llega aquí desde una cotización, un proyecto, un cliente o
    directamente desde el menú de facturación."""
    cliente_id = request.GET.get("cliente", "")
    proyecto_id = request.GET.get("proyecto", "")
    cliente = Cliente.objects.filter(pk=cliente_id, empresa=request.empresa).first() if cliente_id else None

    parametros = ""
    if cliente_id:
        parametros += f"&cliente={cliente_id}"
    if proyecto_id:
        parametros += f"&proyecto={proyecto_id}"
    parametros = "?" + parametros[1:] if parametros else ""

    return render(request, "ventas/elegir_documento.html", {
        "cliente": cliente,
        "url_factura": reverse("ventas:venta_crear") + parametros,
        "url_cuenta_cobro": reverse("ventas:cuenta_cobro_crear") + parametros,
    })


@login_required
@transaction.atomic
def venta_crear(request):
    if request.method == "POST":
        form = VentaForm(request.POST, empresa=request.empresa)
        formset = LineaVentaFormSet(request.POST, form_kwargs={"empresa": request.empresa})
        if form.is_valid() and formset.is_valid():
            venta = form.save(commit=False)
            venta.empresa = request.empresa
            venta.vendedor = request.user
            venta.impuesto_porcentaje = Decimal("19")  # IVA de factura: siempre 19%, fijo.
            venta.save()
            formset.instance = venta
            formset.save()
            messages.success(request, f"Venta {venta.numero} creada como borrador. Confírmala para descontar inventario.")
            return redirect("ventas:venta_detalle", pk=venta.pk)
    else:
        # Al venir de "Generar factura" desde una cotización o desde un proyecto
        # que nació de una, se copian cliente, proyecto y líneas (con sus
        # descripciones) en vez de pedirlos de nuevo.
        cotizacion_origen = _resolver_cotizacion_origen(request)

        initial = {}
        if cotizacion_origen:
            initial["cliente"] = cotizacion_origen.cliente_id
            if cotizacion_origen.proyecto_id:
                initial["proyecto"] = cotizacion_origen.proyecto_id
        if request.GET.get("cliente"):
            initial["cliente"] = request.GET["cliente"]
        if request.GET.get("proyecto"):
            initial["proyecto"] = request.GET["proyecto"]
        form = VentaForm(empresa=request.empresa, initial=initial)

        lineas_iniciales = None
        if cotizacion_origen:
            lineas_iniciales = [
                {"producto": linea.producto_id, "cantidad": linea.cantidad, "precio_unitario": linea.precio_unitario}
                for linea in cotizacion_origen.lineas.all()
            ]
        formset = LineaVentaFormSet(form_kwargs={"empresa": request.empresa}, initial=lineas_iniciales)
    return render(request, "ventas/venta_form.html", {
        "form": form, "formset": formset, "venta": None,
        "precios_producto": _precios_producto_json(request.empresa),
        "descripciones_producto": _descripciones_producto_json(request.empresa),
    })


@login_required
@transaction.atomic
def venta_editar(request, pk):
    venta = get_object_or_404(Venta, pk=pk, empresa=request.empresa)
    if not venta.editable:
        messages.error(request, "Esta venta ya no se puede editar.")
        return redirect("ventas:venta_detalle", pk=venta.pk)

    if request.method == "POST":
        form = VentaForm(request.POST, instance=venta, empresa=request.empresa)
        formset = LineaVentaFormSet(request.POST, instance=venta, form_kwargs={"empresa": request.empresa})
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Venta actualizada.")
            return redirect("ventas:venta_detalle", pk=venta.pk)
    else:
        form = VentaForm(instance=venta, empresa=request.empresa)
        formset = LineaVentaFormSet(instance=venta, form_kwargs={"empresa": request.empresa})
    return render(request, "ventas/venta_form.html", {
        "form": form, "formset": formset, "venta": venta,
        "precios_producto": _precios_producto_json(request.empresa),
        "descripciones_producto": _descripciones_producto_json(request.empresa),
    })


@login_required
def venta_confirmar(request, pk):
    venta = get_object_or_404(Venta, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            venta.confirmar(usuario=request.user)
            messages.success(request, f"Venta {venta.numero} confirmada. Inventario actualizado.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:venta_detalle", pk=venta.pk)


@login_required
def venta_anular(request, pk):
    venta = get_object_or_404(Venta, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            venta.anular(usuario=request.user)
            messages.success(request, f"Venta {venta.numero} anulada. Stock devuelto al inventario.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:venta_detalle", pk=venta.pk)


@login_required
def venta_facturar(request, pk):
    venta = get_object_or_404(Venta, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            venta.facturar(request.POST.get("numero_factura", ""))
            messages.success(request, f"Venta facturada con el número {venta.numero_factura}.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:venta_detalle", pk=venta.pk)


@login_required
def venta_corregir_factura(request, pk):
    venta = get_object_or_404(Venta, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            venta.corregir_factura(request.POST.get("numero_factura", ""))
            messages.success(request, f"Número de factura corregido a {venta.numero_factura}.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:venta_detalle", pk=venta.pk)


@login_required
def cotizacion_lista(request):
    todas = Cotizacion.objects.filter(empresa=request.empresa)
    cotizaciones = todas.select_related("cliente", "vendedor", "venta")

    estado = request.GET.get("estado", "")
    if estado:
        cotizaciones = cotizaciones.filter(estado=estado)

    vendedor_id = request.GET.get("vendedor", "")
    if vendedor_id:
        cotizaciones = cotizaciones.filter(vendedor_id=vendedor_id)

    solo_convertidas = request.GET.get("convertidas") == "1"
    if solo_convertidas:
        cotizaciones = cotizaciones.filter(venta__isnull=False)

    # Embudo de ventas: cuántas cotizaciones hay en cada etapa, y qué tan
    # efectivo es el equipo comercial cerrando las que se deciden.
    conteos = {estado_clave: todas.filter(estado=estado_clave).count() for estado_clave, _ in Cotizacion.ESTADO_CHOICES}
    decididas = conteos[Cotizacion.ACEPTADA] + conteos[Cotizacion.RECHAZADA]
    tasa_conversion = round(conteos[Cotizacion.ACEPTADA] / decididas * 100) if decididas else None
    convertidas_count = todas.filter(venta__isnull=False).count()

    embudo = [
        {"etiqueta": "Borrador", "cantidad": conteos[Cotizacion.BORRADOR], "color": "warning"},
        {"etiqueta": "Enviada", "cantidad": conteos[Cotizacion.ENVIADA], "color": "info"},
        {"etiqueta": "Aceptada", "cantidad": conteos[Cotizacion.ACEPTADA], "color": "success"},
        {"etiqueta": "Rechazada", "cantidad": conteos[Cotizacion.RECHAZADA], "color": "danger"},
    ]
    embudo_maximo = max((e["cantidad"] for e in embudo), default=0) or 1

    vendedores = (
        Cotizacion.objects.filter(empresa=request.empresa, vendedor__isnull=False)
        .values("vendedor_id", "vendedor__username", "vendedor__first_name", "vendedor__last_name")
        .distinct().order_by("vendedor__username")
    )

    return render(request, "ventas/cotizacion_lista.html", {
        "cotizaciones": cotizaciones, "estado": estado,
        "vendedor_id": vendedor_id, "vendedores": vendedores,
        "solo_convertidas": solo_convertidas,
        "embudo": embudo, "embudo_maximo": embudo_maximo,
        "total_cotizaciones": todas.count(),
        "convertidas_count": convertidas_count,
        "decididas_count": decididas,
        "tasa_conversion": tasa_conversion,
    })


@login_required
def cotizacion_detalle(request, pk):
    cotizacion = get_object_or_404(
        Cotizacion.objects.select_related("cliente", "vendedor", "venta"), pk=pk, empresa=request.empresa
    )
    return render(request, "ventas/cotizacion_detalle.html", {"cotizacion": cotizacion})


@login_required
@transaction.atomic
def cotizacion_crear(request):
    if request.method == "POST":
        form = CotizacionForm(request.POST, empresa=request.empresa)
        formset = LineaCotizacionFormSet(request.POST, form_kwargs={"empresa": request.empresa})
        if form.is_valid() and formset.is_valid():
            cotizacion = form.save(commit=False)
            cotizacion.empresa = request.empresa
            cotizacion.vendedor = request.user
            cotizacion.save()
            formset.instance = cotizacion
            formset.save()
            messages.success(request, f"Cotización {cotizacion.numero} creada como borrador.")
            return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)
    else:
        form = CotizacionForm(empresa=request.empresa)
        formset = LineaCotizacionFormSet(form_kwargs={"empresa": request.empresa})
    return render(request, "ventas/cotizacion_form.html", {
        "form": form, "formset": formset, "cotizacion": None,
        "precios_producto": _precios_producto_json(request.empresa),
        "descripciones_producto": _descripciones_producto_json(request.empresa),
    })


@login_required
@transaction.atomic
def cotizacion_editar(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk, empresa=request.empresa)
    if not cotizacion.editable:
        messages.error(request, "Esta cotización ya no se puede editar.")
        return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)

    if request.method == "POST":
        form = CotizacionForm(request.POST, instance=cotizacion, empresa=request.empresa)
        formset = LineaCotizacionFormSet(
            request.POST, instance=cotizacion, form_kwargs={"empresa": request.empresa}
        )
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Cotización actualizada.")
            return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)
    else:
        form = CotizacionForm(instance=cotizacion, empresa=request.empresa)
        formset = LineaCotizacionFormSet(instance=cotizacion, form_kwargs={"empresa": request.empresa})
    return render(request, "ventas/cotizacion_form.html", {
        "form": form, "formset": formset, "cotizacion": cotizacion,
        "precios_producto": _precios_producto_json(request.empresa),
        "descripciones_producto": _descripciones_producto_json(request.empresa),
    })


@login_required
def cotizacion_marcar_enviada(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            cotizacion.marcar_enviada()
            messages.success(request, f"Cotización {cotizacion.numero} marcada como enviada.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)


@login_required
def cotizacion_marcar_aceptada(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            cotizacion.marcar_aceptada(firmado_por=request.POST.get("firmado_por", "").strip())
            messages.success(request, f"Cotización {cotizacion.numero} firmada y aceptada.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)


@login_required
def cotizacion_marcar_rechazada(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            cotizacion.marcar_rechazada()
            messages.success(request, f"Cotización {cotizacion.numero} marcada como rechazada.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)


@login_required
def cotizacion_convertir_venta(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            venta = cotizacion.convertir_a_venta(usuario=request.user)
            messages.success(request, f"Cotización {cotizacion.numero} convertida en la factura {venta.numero}.")
            return redirect("ventas:venta_detalle", pk=venta.pk)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)


@login_required
def cotizacion_convertir_proyecto(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            proyecto = cotizacion.convertir_a_proyecto(usuario=request.user)
            messages.success(request, f"Cotización {cotizacion.numero} convertida en el proyecto {proyecto.numero}.")
            return redirect("proyectos:proyecto_detalle", pk=proyecto.pk)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)


@login_required
def cotizacion_imprimir(request, pk):
    cotizacion = get_object_or_404(
        Cotizacion.objects.select_related("cliente", "vendedor").prefetch_related("lineas__producto"),
        pk=pk, empresa=request.empresa,
    )
    return render(request, "ventas/cotizacion_pdf.html", {
        "cotizacion": cotizacion, "empresa": request.empresa,
    })


@login_required
def cuenta_cobro_lista(request):
    cuentas = CuentaCobro.objects.select_related("cliente").filter(empresa=request.empresa)
    estado = request.GET.get("estado", "")
    if estado:
        cuentas = cuentas.filter(estado=estado)
    return render(request, "ventas/cuenta_cobro_lista.html", {"cuentas": cuentas, "estado": estado})


@login_required
def cuenta_cobro_detalle(request, pk):
    cuenta = get_object_or_404(
        CuentaCobro.objects.select_related("cliente", "venta", "creado_por"), pk=pk, empresa=request.empresa
    )
    return render(request, "ventas/cuenta_cobro_detalle.html", {"cuenta": cuenta})


@login_required
def cuenta_cobro_form(request, pk=None):
    cuenta = get_object_or_404(CuentaCobro, pk=pk, empresa=request.empresa) if pk else None
    if cuenta and not cuenta.editable:
        messages.error(request, "Esta cuenta de cobro ya no se puede editar.")
        return redirect("ventas:cuenta_cobro_detalle", pk=cuenta.pk)

    # Al venir de "Generar cuenta de cobro" desde una cotización o desde un
    # proyecto que nació de una, se copian sus datos en lugar de pedirlos de nuevo.
    cotizacion_origen = _resolver_cotizacion_origen(request) if not cuenta else None

    if request.method == "POST":
        form = CuentaCobroForm(request.POST, instance=cuenta, empresa=request.empresa)
        if form.is_valid():
            obj = form.save(commit=False)
            if not cuenta:
                obj.empresa = request.empresa
                obj.creado_por = request.user
                if cotizacion_origen:
                    obj.cotizacion = cotizacion_origen
            obj.save()
            messages.success(request, f"Cuenta de cobro '{obj.numero}' guardada correctamente.")
            return redirect("ventas:cuenta_cobro_detalle", pk=obj.pk)
    else:
        initial = {}
        if cotizacion_origen:
            initial = {
                "cliente": cotizacion_origen.cliente_id, "proyecto": cotizacion_origen.proyecto_id,
                "concepto": _concepto_desde_cotizacion(cotizacion_origen), "valor": cotizacion_origen.total,
            }
        elif request.GET.get("cliente") or request.GET.get("proyecto"):
            initial = {"cliente": request.GET.get("cliente"), "proyecto": request.GET.get("proyecto")}
        form = CuentaCobroForm(instance=cuenta, empresa=request.empresa, initial=initial)
    return render(request, "ventas/cuenta_cobro_form.html", {
        "form": form, "cuenta": cuenta, "cotizacion_origen": cotizacion_origen,
    })


@login_required
def cuenta_cobro_emitir(request, pk):
    cuenta = get_object_or_404(CuentaCobro, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            cuenta.emitir()
            messages.success(request, f"Cuenta de cobro {cuenta.numero} emitida.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cuenta_cobro_detalle", pk=cuenta.pk)


@login_required
def cuenta_cobro_marcar_pagada(request, pk):
    cuenta = get_object_or_404(CuentaCobro, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            cuenta.marcar_pagada()
            messages.success(request, f"Cuenta de cobro {cuenta.numero} marcada como pagada.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cuenta_cobro_detalle", pk=cuenta.pk)


@login_required
def cuenta_cobro_anular(request, pk):
    cuenta = get_object_or_404(CuentaCobro, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            cuenta.anular()
            messages.success(request, f"Cuenta de cobro {cuenta.numero} anulada.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cuenta_cobro_detalle", pk=cuenta.pk)


@login_required
def cuenta_cobro_imprimir(request, pk):
    cuenta = get_object_or_404(
        CuentaCobro.objects.select_related("cliente", "venta"), pk=pk, empresa=request.empresa
    )
    return render(request, "ventas/cuenta_cobro_pdf.html", {
        "cuenta": cuenta, "empresa": request.empresa,
    })
