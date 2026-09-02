from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import Empresa
from inventario.models import Producto

from .forms import (
    ClienteForm, ClienteRapidoForm, CotizacionForm, CuentaCobroForm, LineaCotizacionFormSet, LineaVentaFormSet,
    VentaForm,
)
from .models import Cliente, Cotizacion, CuentaCobro, Venta


def _precios_producto_json():
    return {str(p.pk): str(p.precio_venta) for p in Producto.objects.filter(activo=True)}


def _descripciones_producto_json():
    return {str(p.pk): p.descripcion for p in Producto.objects.filter(activo=True)}


@login_required
def cliente_lista(request):
    query = request.GET.get("q", "")
    clientes = Cliente.objects.all()
    if query:
        clientes = clientes.filter(Q(nombre__icontains=query) | Q(documento__icontains=query))
    return render(request, "ventas/cliente_lista.html", {"clientes": clientes, "query": query})


@login_required
def cliente_form(request, pk=None):
    cliente = get_object_or_404(Cliente, pk=pk) if pk else None
    if request.method == "POST":
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            obj = form.save()
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
        cliente = form.save()
        return JsonResponse({"ok": True, "id": cliente.pk, "nombre": str(cliente)})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
def venta_lista(request):
    ventas = Venta.objects.select_related("cliente", "vendedor").all()
    estado = request.GET.get("estado", "")
    if estado:
        ventas = ventas.filter(estado=estado)
    return render(request, "ventas/venta_lista.html", {"ventas": ventas, "estado": estado})


@login_required
def venta_detalle(request, pk):
    venta = get_object_or_404(Venta.objects.select_related("cliente", "vendedor"), pk=pk)
    sugerencia_factura = ""
    if venta.estado == Venta.CONFIRMADA and not venta.numero_factura:
        sugerencia_factura = Venta.siguiente_numero_factura_sugerido()
    return render(request, "ventas/venta_detalle.html", {
        "venta": venta, "sugerencia_factura": sugerencia_factura,
    })


@login_required
@transaction.atomic
def venta_crear(request):
    if request.method == "POST":
        form = VentaForm(request.POST)
        formset = LineaVentaFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            venta = form.save(commit=False)
            venta.vendedor = request.user
            venta.save()
            formset.instance = venta
            formset.save()
            messages.success(request, f"Venta {venta.numero} creada como borrador. Confírmala para descontar inventario.")
            return redirect("ventas:venta_detalle", pk=venta.pk)
    else:
        form = VentaForm()
        formset = LineaVentaFormSet()
    return render(request, "ventas/venta_form.html", {
        "form": form, "formset": formset, "venta": None,
        "precios_producto": _precios_producto_json(),
        "descripciones_producto": _descripciones_producto_json(),
    })


@login_required
@transaction.atomic
def venta_editar(request, pk):
    venta = get_object_or_404(Venta, pk=pk)
    if not venta.editable:
        messages.error(request, "Esta venta ya no se puede editar.")
        return redirect("ventas:venta_detalle", pk=venta.pk)

    if request.method == "POST":
        form = VentaForm(request.POST, instance=venta)
        formset = LineaVentaFormSet(request.POST, instance=venta)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Venta actualizada.")
            return redirect("ventas:venta_detalle", pk=venta.pk)
    else:
        form = VentaForm(instance=venta)
        formset = LineaVentaFormSet(instance=venta)
    return render(request, "ventas/venta_form.html", {
        "form": form, "formset": formset, "venta": venta,
        "precios_producto": _precios_producto_json(),
        "descripciones_producto": _descripciones_producto_json(),
    })


@login_required
def venta_confirmar(request, pk):
    venta = get_object_or_404(Venta, pk=pk)
    if request.method == "POST":
        try:
            venta.confirmar(usuario=request.user)
            messages.success(request, f"Venta {venta.numero} confirmada. Inventario actualizado.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:venta_detalle", pk=venta.pk)


@login_required
def venta_anular(request, pk):
    venta = get_object_or_404(Venta, pk=pk)
    if request.method == "POST":
        try:
            venta.anular(usuario=request.user)
            messages.success(request, f"Venta {venta.numero} anulada. Stock devuelto al inventario.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:venta_detalle", pk=venta.pk)


@login_required
def venta_facturar(request, pk):
    venta = get_object_or_404(Venta, pk=pk)
    if request.method == "POST":
        try:
            venta.facturar(request.POST.get("numero_factura", ""))
            messages.success(request, f"Venta facturada con el número {venta.numero_factura}.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:venta_detalle", pk=venta.pk)


@login_required
def venta_corregir_factura(request, pk):
    venta = get_object_or_404(Venta, pk=pk)
    if request.method == "POST":
        try:
            venta.corregir_factura(request.POST.get("numero_factura", ""))
            messages.success(request, f"Número de factura corregido a {venta.numero_factura}.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:venta_detalle", pk=venta.pk)


@login_required
def cotizacion_lista(request):
    cotizaciones = Cotizacion.objects.select_related("cliente", "vendedor").all()
    estado = request.GET.get("estado", "")
    if estado:
        cotizaciones = cotizaciones.filter(estado=estado)
    return render(request, "ventas/cotizacion_lista.html", {"cotizaciones": cotizaciones, "estado": estado})


@login_required
def cotizacion_detalle(request, pk):
    cotizacion = get_object_or_404(Cotizacion.objects.select_related("cliente", "vendedor", "venta"), pk=pk)
    return render(request, "ventas/cotizacion_detalle.html", {"cotizacion": cotizacion})


@login_required
@transaction.atomic
def cotizacion_crear(request):
    if request.method == "POST":
        form = CotizacionForm(request.POST)
        formset = LineaCotizacionFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            cotizacion = form.save(commit=False)
            cotizacion.vendedor = request.user
            cotizacion.save()
            formset.instance = cotizacion
            formset.save()
            messages.success(request, f"Cotización {cotizacion.numero} creada como borrador.")
            return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)
    else:
        form = CotizacionForm()
        formset = LineaCotizacionFormSet()
    return render(request, "ventas/cotizacion_form.html", {
        "form": form, "formset": formset, "cotizacion": None,
        "precios_producto": _precios_producto_json(),
        "descripciones_producto": _descripciones_producto_json(),
    })


@login_required
@transaction.atomic
def cotizacion_editar(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    if not cotizacion.editable:
        messages.error(request, "Esta cotización ya no se puede editar.")
        return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)

    if request.method == "POST":
        form = CotizacionForm(request.POST, instance=cotizacion)
        formset = LineaCotizacionFormSet(request.POST, instance=cotizacion)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Cotización actualizada.")
            return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)
    else:
        form = CotizacionForm(instance=cotizacion)
        formset = LineaCotizacionFormSet(instance=cotizacion)
    return render(request, "ventas/cotizacion_form.html", {
        "form": form, "formset": formset, "cotizacion": cotizacion,
        "precios_producto": _precios_producto_json(),
        "descripciones_producto": _descripciones_producto_json(),
    })


@login_required
def cotizacion_marcar_enviada(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    if request.method == "POST":
        try:
            cotizacion.marcar_enviada()
            messages.success(request, f"Cotización {cotizacion.numero} marcada como enviada.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)


@login_required
def cotizacion_marcar_aceptada(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    if request.method == "POST":
        try:
            cotizacion.marcar_aceptada(firmado_por=request.POST.get("firmado_por", "").strip())
            messages.success(request, f"Cotización {cotizacion.numero} firmada y aceptada.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)


@login_required
def cotizacion_marcar_rechazada(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    if request.method == "POST":
        try:
            cotizacion.marcar_rechazada()
            messages.success(request, f"Cotización {cotizacion.numero} marcada como rechazada.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)


@login_required
def cotizacion_convertir_venta(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    if request.method == "POST":
        try:
            venta = cotizacion.convertir_a_venta(usuario=request.user)
            messages.success(request, f"Cotización {cotizacion.numero} convertida en la venta {venta.numero}.")
            return redirect("ventas:venta_detalle", pk=venta.pk)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cotizacion_detalle", pk=cotizacion.pk)


@login_required
def cotizacion_imprimir(request, pk):
    cotizacion = get_object_or_404(
        Cotizacion.objects.select_related("cliente", "vendedor").prefetch_related("lineas__producto"), pk=pk
    )
    return render(request, "ventas/cotizacion_pdf.html", {
        "cotizacion": cotizacion, "empresa": Empresa.get_solo(),
    })


@login_required
def cuenta_cobro_lista(request):
    cuentas = CuentaCobro.objects.select_related("cliente").all()
    estado = request.GET.get("estado", "")
    if estado:
        cuentas = cuentas.filter(estado=estado)
    return render(request, "ventas/cuenta_cobro_lista.html", {"cuentas": cuentas, "estado": estado})


@login_required
def cuenta_cobro_detalle(request, pk):
    cuenta = get_object_or_404(CuentaCobro.objects.select_related("cliente", "venta", "creado_por"), pk=pk)
    return render(request, "ventas/cuenta_cobro_detalle.html", {"cuenta": cuenta})


@login_required
def cuenta_cobro_form(request, pk=None):
    cuenta = get_object_or_404(CuentaCobro, pk=pk) if pk else None
    if cuenta and not cuenta.editable:
        messages.error(request, "Esta cuenta de cobro ya no se puede editar.")
        return redirect("ventas:cuenta_cobro_detalle", pk=cuenta.pk)

    if request.method == "POST":
        form = CuentaCobroForm(request.POST, instance=cuenta)
        if form.is_valid():
            obj = form.save(commit=False)
            if not cuenta:
                obj.creado_por = request.user
            obj.save()
            messages.success(request, f"Cuenta de cobro '{obj.numero}' guardada correctamente.")
            return redirect("ventas:cuenta_cobro_detalle", pk=obj.pk)
    else:
        form = CuentaCobroForm(instance=cuenta)
    return render(request, "ventas/cuenta_cobro_form.html", {"form": form, "cuenta": cuenta})


@login_required
def cuenta_cobro_emitir(request, pk):
    cuenta = get_object_or_404(CuentaCobro, pk=pk)
    if request.method == "POST":
        try:
            cuenta.emitir()
            messages.success(request, f"Cuenta de cobro {cuenta.numero} emitida.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cuenta_cobro_detalle", pk=cuenta.pk)


@login_required
def cuenta_cobro_marcar_pagada(request, pk):
    cuenta = get_object_or_404(CuentaCobro, pk=pk)
    if request.method == "POST":
        try:
            cuenta.marcar_pagada()
            messages.success(request, f"Cuenta de cobro {cuenta.numero} marcada como pagada.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cuenta_cobro_detalle", pk=cuenta.pk)


@login_required
def cuenta_cobro_anular(request, pk):
    cuenta = get_object_or_404(CuentaCobro, pk=pk)
    if request.method == "POST":
        try:
            cuenta.anular()
            messages.success(request, f"Cuenta de cobro {cuenta.numero} anulada.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("ventas:cuenta_cobro_detalle", pk=cuenta.pk)


@login_required
def cuenta_cobro_imprimir(request, pk):
    cuenta = get_object_or_404(CuentaCobro.objects.select_related("cliente", "venta"), pk=pk)
    return render(request, "ventas/cuenta_cobro_pdf.html", {
        "cuenta": cuenta, "empresa": Empresa.get_solo(),
    })
