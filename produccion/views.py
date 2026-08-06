from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ComponenteBOMFormSet, ListaMaterialesForm, OrdenProduccionForm
from .models import ListaMateriales, OrdenProduccion


@login_required
def bom_lista(request):
    listas = ListaMateriales.objects.select_related("producto").all()
    return render(request, "produccion/bom_lista.html", {"listas": listas})


@login_required
@transaction.atomic
def bom_crear(request):
    if request.method == "POST":
        form = ListaMaterialesForm(request.POST)
        formset = ComponenteBOMFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            lista = form.save()
            formset.instance = lista
            formset.save()
            messages.success(request, f"Lista de materiales de '{lista.producto}' creada correctamente.")
            return redirect("produccion:bom_lista")
    else:
        form = ListaMaterialesForm()
        formset = ComponenteBOMFormSet()
    return render(request, "produccion/bom_form.html", {"form": form, "formset": formset, "lista": None})


@login_required
@transaction.atomic
def bom_editar(request, pk):
    lista = get_object_or_404(ListaMateriales, pk=pk)
    if request.method == "POST":
        form = ListaMaterialesForm(request.POST, instance=lista)
        formset = ComponenteBOMFormSet(request.POST, instance=lista)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Lista de materiales actualizada.")
            return redirect("produccion:bom_lista")
    else:
        form = ListaMaterialesForm(instance=lista)
        formset = ComponenteBOMFormSet(instance=lista)
    return render(request, "produccion/bom_form.html", {"form": form, "formset": formset, "lista": lista})


@login_required
def orden_lista(request):
    ordenes = OrdenProduccion.objects.select_related("producto", "responsable").all()
    estado = request.GET.get("estado", "")
    if estado:
        ordenes = ordenes.filter(estado=estado)
    return render(request, "produccion/orden_lista.html", {"ordenes": ordenes, "estado": estado})


@login_required
def orden_detalle(request, pk):
    orden = get_object_or_404(OrdenProduccion.objects.select_related("producto", "responsable"), pk=pk)
    componentes = orden.componentes.select_related("insumo")
    return render(request, "produccion/orden_detalle.html", {"orden": orden, "componentes": componentes})


@login_required
@transaction.atomic
def orden_crear(request):
    if request.method == "POST":
        form = OrdenProduccionForm(request.POST)
        if form.is_valid():
            try:
                orden = form.save(commit=False)
                orden.responsable = request.user
                orden.save()
                orden.sincronizar_componentes_desde_receta()
                messages.success(request, f"Orden {orden.numero} creada. Complétala para producir y actualizar el inventario.")
                return redirect("produccion:orden_detalle", pk=orden.pk)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
    else:
        form = OrdenProduccionForm()
    return render(request, "produccion/orden_form.html", {"form": form, "orden": None})


@login_required
@transaction.atomic
def orden_editar(request, pk):
    orden = get_object_or_404(OrdenProduccion, pk=pk)
    if not orden.editable:
        messages.error(request, "Esta orden ya no se puede editar.")
        return redirect("produccion:orden_detalle", pk=orden.pk)

    if request.method == "POST":
        form = OrdenProduccionForm(request.POST, instance=orden)
        if form.is_valid():
            try:
                form.save()
                orden.sincronizar_componentes_desde_receta()
                messages.success(request, "Orden actualizada.")
                return redirect("produccion:orden_detalle", pk=orden.pk)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
    else:
        form = OrdenProduccionForm(instance=orden)
    return render(request, "produccion/orden_form.html", {"form": form, "orden": orden})


@login_required
def orden_completar(request, pk):
    orden = get_object_or_404(OrdenProduccion, pk=pk)
    if request.method == "POST":
        try:
            orden.completar(usuario=request.user)
            messages.success(request, f"Orden {orden.numero} completada. Inventario actualizado.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("produccion:orden_detalle", pk=orden.pk)


@login_required
def orden_anular(request, pk):
    orden = get_object_or_404(OrdenProduccion, pk=pk)
    if request.method == "POST":
        try:
            orden.anular(usuario=request.user)
            messages.success(request, f"Orden {orden.numero} anulada. Inventario revertido.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("produccion:orden_detalle", pk=orden.pk)
