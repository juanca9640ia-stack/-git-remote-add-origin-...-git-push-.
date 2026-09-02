from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AsignacionForm, GastoForm, HitoForm, ProyectoForm
from .models import AsignacionEmpleado, GastoProyecto, HitoProyecto, Proyecto


@login_required
def proyecto_lista(request):
    proyectos = Proyecto.objects.select_related("cliente", "responsable").filter(empresa=request.empresa)

    estado = request.GET.get("estado", "")
    if estado:
        proyectos = proyectos.filter(estado=estado)

    query = request.GET.get("q", "")
    if query:
        proyectos = proyectos.filter(nombre__icontains=query)

    todos = Proyecto.objects.filter(empresa=request.empresa)
    en_curso_count = todos.filter(estado=Proyecto.EN_CURSO).count()
    presupuesto_total = sum((p.presupuesto for p in todos), Decimal("0"))
    gastado_total = sum((p.gastado for p in todos), Decimal("0"))

    return render(request, "proyectos/proyecto_lista.html", {
        "proyectos": proyectos, "estado": estado, "query": query,
        "total_proyectos": todos.count(), "en_curso_count": en_curso_count,
        "presupuesto_total": presupuesto_total, "gastado_total": gastado_total,
    })


@login_required
def proyecto_detalle(request, pk):
    proyecto = get_object_or_404(
        Proyecto.objects.select_related("cliente", "responsable"), pk=pk, empresa=request.empresa
    )
    return render(request, "proyectos/proyecto_detalle.html", {
        "proyecto": proyecto,
        "hitos": proyecto.hitos.all(),
        "gastos": proyecto.gastos.select_related("registrado_por")[:15],
        "asignaciones": proyecto.asignaciones.select_related("empleado").filter(activo=True),
        "hito_form": HitoForm(),
        "gasto_form": GastoForm(),
        "asignacion_form": AsignacionForm(empresa=request.empresa, proyecto=proyecto),
    })


@login_required
def proyecto_form(request, pk=None):
    proyecto = get_object_or_404(Proyecto, pk=pk, empresa=request.empresa) if pk else None
    if request.method == "POST":
        form = ProyectoForm(request.POST, instance=proyecto, empresa=request.empresa)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.empresa = request.empresa
            obj.save()
            messages.success(request, f"Proyecto '{obj.nombre}' guardado correctamente.")
            return redirect("proyectos:proyecto_detalle", pk=obj.pk)
    else:
        form = ProyectoForm(instance=proyecto, empresa=request.empresa)
    return render(request, "proyectos/proyecto_form.html", {"form": form, "proyecto": proyecto})


@login_required
@require_POST
def hito_crear(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk, empresa=request.empresa)
    form = HitoForm(request.POST)
    if form.is_valid():
        hito = form.save(commit=False)
        hito.empresa = request.empresa
        hito.proyecto = proyecto
        hito.save()
        messages.success(request, f"Hito '{hito.nombre}' agregado.")
    else:
        messages.error(request, "Revisa los datos del hito.")
    return redirect("proyectos:proyecto_detalle", pk=proyecto.pk)


@login_required
@require_POST
def hito_toggle(request, pk, hito_pk):
    proyecto = get_object_or_404(Proyecto, pk=pk, empresa=request.empresa)
    hito = get_object_or_404(HitoProyecto, pk=hito_pk, proyecto=proyecto)
    if hito.completado:
        hito.marcar_pendiente()
    else:
        hito.marcar_completado()
    return redirect("proyectos:proyecto_detalle", pk=proyecto.pk)


@login_required
@require_POST
def hito_eliminar(request, pk, hito_pk):
    proyecto = get_object_or_404(Proyecto, pk=pk, empresa=request.empresa)
    HitoProyecto.objects.filter(pk=hito_pk, proyecto=proyecto).delete()
    messages.success(request, "Hito eliminado.")
    return redirect("proyectos:proyecto_detalle", pk=proyecto.pk)


@login_required
@require_POST
def gasto_crear(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk, empresa=request.empresa)
    form = GastoForm(request.POST)
    if form.is_valid():
        gasto = form.save(commit=False)
        gasto.empresa = request.empresa
        gasto.proyecto = proyecto
        gasto.registrado_por = request.user
        gasto.save()
        messages.success(request, f"Gasto de {gasto.valor} registrado.")
    else:
        messages.error(request, "Revisa los datos del gasto.")
    return redirect("proyectos:proyecto_detalle", pk=proyecto.pk)


@login_required
@require_POST
def gasto_eliminar(request, pk, gasto_pk):
    proyecto = get_object_or_404(Proyecto, pk=pk, empresa=request.empresa)
    GastoProyecto.objects.filter(pk=gasto_pk, proyecto=proyecto).delete()
    messages.success(request, "Gasto eliminado.")
    return redirect("proyectos:proyecto_detalle", pk=proyecto.pk)


@login_required
@require_POST
def asignacion_crear(request, pk):
    proyecto = get_object_or_404(Proyecto, pk=pk, empresa=request.empresa)
    form = AsignacionForm(request.POST, empresa=request.empresa, proyecto=proyecto)
    if form.is_valid():
        asignacion = form.save(commit=False)
        asignacion.empresa = request.empresa
        asignacion.proyecto = proyecto
        asignacion.save()
        messages.success(request, f"{asignacion.empleado} asignado a la obra.")
    else:
        messages.error(request, "Revisa los datos de la asignación (¿el empleado ya está asignado?).")
    return redirect("proyectos:proyecto_detalle", pk=proyecto.pk)


@login_required
@require_POST
def asignacion_quitar(request, pk, asignacion_pk):
    proyecto = get_object_or_404(Proyecto, pk=pk, empresa=request.empresa)
    asignacion = get_object_or_404(AsignacionEmpleado, pk=asignacion_pk, proyecto=proyecto)
    asignacion.activo = False
    asignacion.save(update_fields=["activo"])
    messages.success(request, f"{asignacion.empleado} retirado de la obra.")
    return redirect("proyectos:proyecto_detalle", pk=proyecto.pk)
