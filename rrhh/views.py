from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import Empresa

from .forms import (
    AsistenciaForm, DepartamentoForm, DetalleNominaFormSet, EmpleadoForm, NominaForm, PrestamoForm,
)
from .models import Asistencia, Departamento, DetalleNomina, Empleado, Nomina, Prestamo


@login_required
def resumen(request):
    empleados_activos = Empleado.objects.filter(activo=True)
    hoy = timezone.localdate()
    asistencias_hoy = Asistencia.objects.filter(fecha=hoy)
    presentes_hoy = asistencias_hoy.filter(estado__in=[Asistencia.PRESENTE, Asistencia.TARDANZA]).count()
    ausentes_hoy = asistencias_hoy.filter(estado=Asistencia.AUSENTE).count()
    sin_registrar_hoy = empleados_activos.count() - asistencias_hoy.count()

    ultima_nomina = Nomina.objects.first()

    context = {
        "total_empleados": empleados_activos.count(),
        "presentes_hoy": presentes_hoy,
        "ausentes_hoy": ausentes_hoy,
        "sin_registrar_hoy": sin_registrar_hoy,
        "ultima_nomina": ultima_nomina,
    }
    return render(request, "rrhh/resumen.html", context)


@login_required
def departamento_lista(request):
    departamentos = Departamento.objects.all()
    if request.method == "POST":
        form = DepartamentoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Departamento creado.")
            return redirect("rrhh:departamento_lista")
    else:
        form = DepartamentoForm()
    return render(request, "rrhh/departamento_lista.html", {"departamentos": departamentos, "form": form})


@login_required
def empleado_lista(request):
    query = request.GET.get("q", "")
    empleados = Empleado.objects.select_related("departamento").all()
    if query:
        empleados = empleados.filter(Q(nombre_completo__icontains=query) | Q(documento__icontains=query))
    return render(request, "rrhh/empleado_lista.html", {"empleados": empleados, "query": query})


@login_required
def empleado_form(request, pk=None):
    empleado = get_object_or_404(Empleado, pk=pk) if pk else None
    if request.method == "POST":
        form = EmpleadoForm(request.POST, instance=empleado)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Empleado '{obj.nombre_completo}' guardado correctamente.")
            return redirect("rrhh:empleado_detalle", pk=obj.pk)
    else:
        form = EmpleadoForm(instance=empleado)
    return render(request, "rrhh/empleado_form.html", {"form": form, "empleado": empleado})


@login_required
def empleado_detalle(request, pk):
    empleado = get_object_or_404(Empleado.objects.select_related("departamento"), pk=pk)
    asistencias = empleado.asistencias.all()[:30]
    prestamos = empleado.prestamos.all()
    return render(
        request, "rrhh/empleado_detalle.html",
        {"empleado": empleado, "asistencias": asistencias, "prestamos": prestamos},
    )


@login_required
def asistencia_lista(request):
    fecha = request.GET.get("fecha") or timezone.localdate().isoformat()
    empleados = Empleado.objects.filter(activo=True).select_related("departamento")
    asistencias = {a.empleado_id: a for a in Asistencia.objects.filter(fecha=fecha)}

    filas = [{"empleado": emp, "asistencia": asistencias.get(emp.id)} for emp in empleados]

    return render(request, "rrhh/asistencia_lista.html", {"filas": filas, "fecha": fecha})


@login_required
def asistencia_marcar_entrada(request, empleado_id):
    empleado = get_object_or_404(Empleado, pk=empleado_id)
    if request.method == "POST":
        hoy = timezone.localdate()
        asistencia, creada = Asistencia.objects.get_or_create(
            empleado=empleado, fecha=hoy,
            defaults={"hora_entrada": timezone.localtime().time(), "estado": Asistencia.PRESENTE},
        )
        if not creada:
            messages.error(request, f"{empleado} ya tiene asistencia registrada hoy.")
        else:
            messages.success(request, f"Entrada registrada para {empleado}.")
    return redirect("rrhh:asistencia_lista")


@login_required
def asistencia_marcar_salida(request, empleado_id):
    empleado = get_object_or_404(Empleado, pk=empleado_id)
    if request.method == "POST":
        hoy = timezone.localdate()
        try:
            asistencia = Asistencia.objects.get(empleado=empleado, fecha=hoy)
            asistencia.marcar_salida()
            messages.success(request, f"Salida registrada para {empleado}.")
        except Asistencia.DoesNotExist:
            messages.error(request, f"{empleado} no tiene entrada registrada hoy.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("rrhh:asistencia_lista")


@login_required
def asistencia_registrar(request, empleado_id):
    empleado = get_object_or_404(Empleado, pk=empleado_id)
    fecha = request.GET.get("fecha") or timezone.localdate().isoformat()
    instancia = Asistencia.objects.filter(empleado=empleado, fecha=fecha).first()

    if request.method == "POST":
        form = AsistenciaForm(request.POST, instance=instancia)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.empleado = empleado
            obj.save()
            messages.success(request, f"Asistencia de {empleado} actualizada.")
            return redirect("rrhh:asistencia_lista")
    else:
        form = AsistenciaForm(instance=instancia, initial={"fecha": fecha})

    return render(request, "rrhh/asistencia_form.html", {"form": form, "empleado": empleado})


@login_required
def nomina_lista(request):
    nominas = Nomina.objects.all()
    return render(request, "rrhh/nomina_lista.html", {"nominas": nominas})


@login_required
@transaction.atomic
def nomina_crear(request):
    if request.method == "POST":
        form = NominaForm(request.POST)
        if form.is_valid():
            nomina = Nomina.objects.create(periodo=form.cleaned_data["periodo"])
            nomina.generar_detalles()
            messages.success(request, f"Nómina {nomina.periodo} creada con {nomina.detalles.count()} empleado(s).")
            return redirect("rrhh:nomina_detalle", pk=nomina.pk)
    else:
        form = NominaForm()
    return render(request, "rrhh/nomina_form.html", {"form": form})


@login_required
@transaction.atomic
def nomina_detalle(request, pk):
    nomina = get_object_or_404(Nomina, pk=pk)
    if nomina.editable:
        for detalle in nomina.detalles.select_related("empleado"):
            detalle.recalcular_dias_trabajados()
    if request.method == "POST" and nomina.editable:
        formset = DetalleNominaFormSet(request.POST, instance=nomina)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Nómina actualizada.")
            return redirect("rrhh:nomina_detalle", pk=nomina.pk)
    else:
        formset = DetalleNominaFormSet(instance=nomina, queryset=nomina.detalles.select_related("empleado"))
    return render(request, "rrhh/nomina_detalle.html", {"nomina": nomina, "formset": formset})


@login_required
def nomina_procesar(request, pk):
    nomina = get_object_or_404(Nomina, pk=pk)
    if request.method == "POST":
        try:
            nomina.procesar(usuario=request.user)
            messages.success(request, f"Nómina {nomina.periodo} procesada. Ya puedes generar los recibos de pago.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
    return redirect("rrhh:nomina_detalle", pk=nomina.pk)


@login_required
def detalle_nomina_recibo(request, pk):
    detalle = get_object_or_404(
        DetalleNomina.objects.select_related("empleado", "empleado__departamento", "nomina"), pk=pk
    )
    empresa = Empresa.get_solo()
    return render(request, "rrhh/recibo_nomina.html", {"detalle": detalle, "empresa": empresa})


@login_required
def prestamo_lista(request):
    prestamos = Prestamo.objects.select_related("empleado").all()
    return render(request, "rrhh/prestamo_lista.html", {"prestamos": prestamos})


@login_required
def prestamo_crear(request):
    if request.method == "POST":
        form = PrestamoForm(request.POST)
        if form.is_valid():
            prestamo = form.save(commit=False)
            prestamo.otorgado_por = request.user
            prestamo.save()
            messages.success(request, f"Préstamo de ${prestamo.monto} registrado para {prestamo.empleado}.")
            return redirect("rrhh:prestamo_detalle", pk=prestamo.pk)
    else:
        form = PrestamoForm()
    return render(request, "rrhh/prestamo_form.html", {"form": form})


@login_required
def prestamo_detalle(request, pk):
    prestamo = get_object_or_404(Prestamo.objects.select_related("empleado"), pk=pk)
    abonos = prestamo.abonos.select_related("nomina")
    abonado = prestamo.monto - prestamo.saldo_pendiente
    return render(
        request, "rrhh/prestamo_detalle.html",
        {"prestamo": prestamo, "abonos": abonos, "abonado": abonado},
    )
