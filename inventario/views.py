import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AjusteInventarioForm, CategoriaForm, ProductoForm, ProductoRapidoForm
from .models import Categoria, MovimientoInventario, Producto, registrar_movimiento


@login_required
def producto_lista(request):
    query = request.GET.get("q", "")
    productos = Producto.objects.select_related("categoria").all()
    if query:
        productos = productos.filter(
            Q(sku__icontains=query) | Q(nombre__icontains=query)
        )
    solo_stock_bajo = request.GET.get("stock_bajo") == "1"
    if solo_stock_bajo:
        productos = [p for p in productos if p.stock_bajo]
    return render(request, "inventario/producto_lista.html", {
        "productos": productos,
        "query": query,
        "solo_stock_bajo": solo_stock_bajo,
    })


@login_required
def servicio_lista(request):
    query = request.GET.get("q", "")
    servicios = Producto.objects.filter(tipo=Producto.SERVICIO)
    if query:
        servicios = servicios.filter(Q(sku__icontains=query) | Q(nombre__icontains=query))
    return render(request, "inventario/servicio_lista.html", {"servicios": servicios, "query": query})


@login_required
def producto_detalle(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    movimientos = producto.movimientos.select_related("usuario")[:30]
    ajuste_form = AjusteInventarioForm()
    return render(request, "inventario/producto_detalle.html", {
        "producto": producto,
        "movimientos": movimientos,
        "ajuste_form": ajuste_form,
    })


@login_required
def producto_form(request, pk=None):
    producto = get_object_or_404(Producto, pk=pk) if pk else None
    if request.method == "POST":
        form = ProductoForm(request.POST, instance=producto)
        if form.is_valid():
            obj = form.save(commit=False)
            if not pk:
                obj.stock_actual = obj.stock_actual or 0
            obj.save()
            messages.success(request, f"Producto '{obj.nombre}' guardado correctamente.")
            return redirect("inventario:producto_detalle", pk=obj.pk)
    else:
        form = ProductoForm(instance=producto)
    return render(request, "inventario/producto_form.html", {"form": form, "producto": producto})


@login_required
@require_POST
def producto_crear_rapido(request):
    """Crea un producto o servicio desde el modal de ventas/cotizaciones/compras sin salir del formulario."""
    form = ProductoRapidoForm(request.POST)
    if form.is_valid():
        producto = form.save(commit=False)
        if not producto.sku:
            producto.sku = f"AUTO-{uuid.uuid4().hex[:8].upper()}"
        producto.save()
        return JsonResponse({
            "ok": True, "id": producto.pk, "nombre": str(producto),
            "descripcion": producto.descripcion,
            "precio_venta": str(producto.precio_venta), "precio_costo": str(producto.precio_costo),
        })
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@login_required
def producto_ajustar_stock(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == "POST":
        form = AjusteInventarioForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    registrar_movimiento(
                        producto=producto,
                        tipo=form.cleaned_data["tipo"],
                        cantidad=form.cleaned_data["cantidad"],
                        motivo=MovimientoInventario.MOTIVO_AJUSTE,
                        referencia=form.cleaned_data["referencia"],
                        usuario=request.user,
                    )
                messages.success(request, "Ajuste de inventario aplicado.")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        else:
            messages.error(request, "Revisa los datos del ajuste.")
    return redirect("inventario:producto_detalle", pk=producto.pk)


@login_required
def categoria_lista(request):
    categorias = Categoria.objects.all()
    if request.method == "POST":
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoría creada.")
            return redirect("inventario:categoria_lista")
    else:
        form = CategoriaForm()
    return render(request, "inventario/categoria_lista.html", {"categorias": categorias, "form": form})


@login_required
def movimiento_lista(request):
    movimientos = MovimientoInventario.objects.select_related("producto", "usuario")[:200]
    return render(request, "inventario/movimiento_lista.html", {"movimientos": movimientos})
