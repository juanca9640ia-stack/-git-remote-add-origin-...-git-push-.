from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from inventario.models import Producto

from .forms import CompraForm, LineaCompraFormSet, ProveedorForm, ProveedorRapidoForm
from .models import Compra, Proveedor


def _precios_producto_json(empresa):
    return {str(p.pk): str(p.precio_costo) for p in Producto.objects.filter(activo=True, empresa=empresa)}


def _descripciones_producto_json(empresa):
    return {str(p.pk): p.descripcion for p in Producto.objects.filter(activo=True, empresa=empresa)}


@login_required
def proveedor_lista(request):
    query = request.GET.get("q", "")
    proveedores = Proveedor.objects.filter(empresa=request.empresa)
    if query:
        proveedores = proveedores.filter(Q(nombre__icontains=query) | Q(nit__icontains=query))
    return render(request, "compras/proveedor_lista.html", {"proveedores": proveedores, "query": query})


@login_required
def proveedor_form(request, pk=None):
    proveedor = get_object_or_404(Proveedor, pk=pk, empresa=request.empresa) if pk else None
    if request.method == "POST":
        form = ProveedorForm(request.POST, instance=proveedor)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.empresa = request.empresa
            obj.save()
            messages.success(request, f"Proveedor '{obj.nombre}' guardado correctamente.")
            return redirect("compras:proveedor_lista")
    else:
        form = ProveedorForm(instance=proveedor)
    return render(request, "compras/proveedor_form.html", {"form": form, "proveedor": proveedor})


@login_required
@require_POST
def proveedor_crear_rapido(request):
    """Crea un proveedor desde el modal de compras sin salir del formulario."""
    form = ProveedorRapidoForm(request.POST)
    if form.is_valid():
        proveedor = form.save(commit=False)
        proveedor.empresa = request.empresa
        proveedor.save()
        return JsonResponse({"ok": True, "id": proveedor.pk, "nombre": str(proveedor)})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
def compra_lista(request):
    compras = Compra.objects.select_related("proveedor", "responsable").filter(empresa=request.empresa)
    estado = request.GET.get("estado", "")
    if estado:
        compras = compras.filter(estado=estado)
    return render(request, "compras/compra_lista.html", {"compras": compras, "estado": estado})


@login_required
def compra_detalle(request, pk):
    compra = get_object_or_404(
        Compra.objects.select_related("proveedor", "responsable"), pk=pk, empresa=request.empresa
    )
    return render(request, "compras/compra_detalle.html", {"compra": compra})


@login_required
@transaction.atomic
def compra_crear(request):
    if request.method == "POST":
        form = CompraForm(request.POST, empresa=request.empresa)
        formset = LineaCompraFormSet(request.POST, form_kwargs={"empresa": request.empresa})
        if form.is_valid() and formset.is_valid():
            compra = form.save(commit=False)
            compra.empresa = request.empresa
            compra.responsable = request.user
            compra.save()
            formset.instance = compra
            formset.save()
            messages.success(request, f"Compra {compra.numero} creada como borrador. Confírmala para recibir la mercancía.")
            return redirect("compras:compra_detalle", pk=compra.pk)
    else:
        form = CompraForm(empresa=request.empresa)
        formset = LineaCompraFormSet(form_kwargs={"empresa": request.empresa})
    return render(request, "compras/compra_form.html", {
        "form": form, "formset": formset, "compra": None,
        "precios_producto": _precios_producto_json(request.empresa),
        "descripciones_producto": _descripciones_producto_json(request.empresa),
    })


@login_required
@transaction.atomic
def compra_editar(request, pk):
    compra = get_object_or_404(Compra, pk=pk, empresa=request.empresa)
    if not compra.editable:
        messages.error(request, "Esta compra ya no se puede editar.")
        return redirect("compras:compra_detalle", pk=compra.pk)

    if request.method == "POST":
        form = CompraForm(request.POST, instance=compra, empresa=request.empresa)
        formset = LineaCompraFormSet(request.POST, instance=compra, form_kwargs={"empresa": request.empresa})
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Compra actualizada.")
            return redirect("compras:compra_detalle", pk=compra.pk)
    else:
        form = CompraForm(instance=compra, empresa=request.empresa)
        formset = LineaCompraFormSet(instance=compra, form_kwargs={"empresa": request.empresa})
    return render(request, "compras/compra_form.html", {
        "form": form, "formset": formset, "compra": compra,
        "precios_producto": _precios_producto_json(request.empresa),
        "descripciones_producto": _descripciones_producto_json(request.empresa),
    })


@login_required
def compra_confirmar(request, pk):
    compra = get_object_or_404(Compra, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            compra.confirmar(usuario=request.user)
            messages.success(request, f"Compra {compra.numero} confirmada. Inventario actualizado.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("compras:compra_detalle", pk=compra.pk)


@login_required
def compra_anular(request, pk):
    compra = get_object_or_404(Compra, pk=pk, empresa=request.empresa)
    if request.method == "POST":
        try:
            compra.anular(usuario=request.user)
            messages.success(request, f"Compra {compra.numero} anulada. Stock retirado del inventario.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("compras:compra_detalle", pk=compra.pk)
