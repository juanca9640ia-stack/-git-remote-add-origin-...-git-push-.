from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from core.models import Empresa, GrupoEmpresa, PerfilUsuario
from finanzas.models import PagoCliente, PagoProveedor
from inventario.models import MovimientoInventario
from rrhh.models import Nomina

from .forms import (
    APARTADOS_ROL, CambiarPasswordForm, EmpresaAltaForm, EmpresaForm, RolForm, UsuarioCrearForm, UsuarioEditarForm,
    permisos_de_apartado,
)

LIMITE_POR_FUENTE = 60
LIMITE_TOTAL = 150


def _es_superadmin_plataforma(request):
    perfil = getattr(request.user, "perfil", None)
    return bool(perfil and perfil.es_superadmin_plataforma)


@login_required
def cambiar_empresa(request):
    """Selector de empresa activa, solo para superadministradores de la plataforma."""
    if not _es_superadmin_plataforma(request):
        messages.error(request, "No tienes permiso para cambiar de empresa.")
        return redirect("dashboard")

    if request.method == "POST":
        empresa = get_object_or_404(Empresa, pk=request.POST.get("empresa_id"))
        request.session["empresa_activa_id"] = empresa.pk
        messages.success(request, f"Ahora estás viendo los datos de '{empresa.nombre}'.")
        return redirect("dashboard")

    return render(request, "administracion/cambiar_empresa.html", {
        "empresas": Empresa.objects.filter(activa=True).order_by("nombre"),
    })


@login_required
def empresa_lista(request):
    """Listado de todas las empresas de la plataforma, solo para su superadministrador."""
    if not _es_superadmin_plataforma(request):
        messages.error(request, "No tienes permiso para administrar empresas.")
        return redirect("dashboard")
    empresas = Empresa.objects.annotate(total_usuarios=Count("usuarios")).order_by("nombre")
    return render(request, "administracion/empresa_lista.html", {"empresas": empresas})


@login_required
def empresa_alta(request):
    """Fase 0.3: da de alta una empresa nueva con su primer usuario administrador."""
    if not _es_superadmin_plataforma(request):
        messages.error(request, "No tienes permiso para dar de alta una empresa.")
        return redirect("dashboard")

    if request.method == "POST":
        form = EmpresaAltaForm(request.POST)
        if form.is_valid():
            empresa, admin = form.guardar()
            messages.success(
                request,
                f"Empresa '{empresa.nombre}' creada, con '{admin.username}' como su primer administrador.",
            )
            return redirect("administracion:empresa_lista")
    else:
        form = EmpresaAltaForm()
    return render(request, "administracion/empresa_alta.html", {"form": form})


@staff_member_required(login_url="login")
def empresa_editar(request):
    empresa = request.empresa
    if request.method == "POST":
        form = EmpresaForm(request.POST, request.FILES, instance=empresa)
        if form.is_valid():
            form.save()
            messages.success(request, "Datos de la empresa actualizados.")
            return redirect("administracion:empresa_editar")
    else:
        form = EmpresaForm(instance=empresa)
    return render(request, "administracion/empresa_form.html", {"form": form})


@staff_member_required(login_url="login")
def usuario_lista(request):
    query = request.GET.get("q", "")
    usuarios = User.objects.filter(perfil__empresa=request.empresa).prefetch_related("groups")
    if query:
        usuarios = usuarios.filter(Q(username__icontains=query) | Q(email__icontains=query))
    return render(request, "administracion/usuario_lista.html", {"usuarios": usuarios, "query": query})


@staff_member_required(login_url="login")
def usuario_crear(request):
    if request.method == "POST":
        form = UsuarioCrearForm(request.POST, empresa=request.empresa)
        if form.is_valid():
            usuario = form.save()
            PerfilUsuario.objects.get_or_create(usuario=usuario, defaults={"empresa": request.empresa})
            messages.success(request, f"Usuario '{usuario.username}' creado correctamente.")
            return redirect("administracion:usuario_lista")
    else:
        form = UsuarioCrearForm(empresa=request.empresa)
    return render(request, "administracion/usuario_form.html", {"form": form, "usuario": None})


@staff_member_required(login_url="login")
def usuario_editar(request, pk):
    usuario = get_object_or_404(User, pk=pk, perfil__empresa=request.empresa)
    if request.method == "POST":
        form = UsuarioEditarForm(request.POST, instance=usuario, empresa=request.empresa)
        if form.is_valid():
            if usuario == request.user and not form.cleaned_data["is_active"]:
                messages.error(request, "No puedes desactivar tu propia cuenta.")
            elif usuario == request.user and not form.cleaned_data["is_staff"]:
                messages.error(request, "No puedes quitarte a ti mismo el acceso de administración.")
            else:
                form.save()
                messages.success(request, "Usuario actualizado.")
                return redirect("administracion:usuario_lista")
    else:
        form = UsuarioEditarForm(instance=usuario, empresa=request.empresa)
    return render(request, "administracion/usuario_form.html", {"form": form, "usuario": usuario})


@staff_member_required(login_url="login")
def usuario_toggle_activo(request, pk):
    usuario = get_object_or_404(User, pk=pk, perfil__empresa=request.empresa)
    if request.method == "POST":
        if usuario == request.user:
            messages.error(request, "No puedes desactivar tu propia cuenta.")
        else:
            usuario.is_active = not usuario.is_active
            usuario.save(update_fields=["is_active"])
            estado = "activado" if usuario.is_active else "desactivado"
            messages.success(request, f"Usuario '{usuario.username}' {estado}.")
    return redirect("administracion:usuario_lista")


@staff_member_required(login_url="login")
def usuario_cambiar_password(request, pk):
    usuario = get_object_or_404(User, pk=pk, perfil__empresa=request.empresa)
    if request.method == "POST":
        form = CambiarPasswordForm(request.POST, usuario=usuario)
        if form.is_valid():
            usuario.set_password(form.cleaned_data["password1"])
            usuario.save(update_fields=["password"])
            messages.success(request, f"Contraseña de '{usuario.username}' actualizada.")
            return redirect("administracion:usuario_lista")
    else:
        form = CambiarPasswordForm(usuario=usuario)
    return render(request, "administracion/usuario_password_form.html", {"form": form, "usuario": usuario})


@staff_member_required(login_url="login")
def auditoria_lista(request):
    movimientos = (
        MovimientoInventario.objects.filter(empresa=request.empresa)
        .select_related("producto", "usuario").order_by("-creado_en")[:LIMITE_POR_FUENTE]
    )
    pagos_cliente = (
        PagoCliente.objects.filter(empresa=request.empresa)
        .select_related("registrado_por", "cuenta__venta").order_by("-creado_en")[:LIMITE_POR_FUENTE]
    )
    pagos_proveedor = (
        PagoProveedor.objects.filter(empresa=request.empresa)
        .select_related("registrado_por", "cuenta__compra", "cuenta__nomina").order_by("-creado_en")[:LIMITE_POR_FUENTE]
    )
    nominas_procesadas = (
        Nomina.objects.filter(estado=Nomina.PROCESADA, empresa=request.empresa)
        .select_related("procesada_por").order_by("-procesada_en")[:LIMITE_POR_FUENTE]
    )

    eventos = []
    for m in movimientos:
        eventos.append({
            "fecha": m.creado_en, "usuario": m.usuario, "modulo": "Inventario",
            "accion": f"{m.get_tipo_display()} · {m.producto.sku} x{m.cantidad} ({m.get_motivo_display()})",
            "referencia": m.referencia,
        })
    for p in pagos_cliente:
        eventos.append({
            "fecha": p.creado_en, "usuario": p.registrado_por, "modulo": "Finanzas",
            "accion": f"Pago recibido de cliente: ${p.monto} ({p.get_metodo_display()})",
            "referencia": p.cuenta.venta.numero,
        })
    for p in pagos_proveedor:
        eventos.append({
            "fecha": p.creado_en, "usuario": p.registrado_por, "modulo": "Finanzas",
            "accion": f"Pago realizado a proveedor: ${p.monto} ({p.get_metodo_display()})",
            "referencia": p.cuenta.origen,
        })
    for n in nominas_procesadas:
        eventos.append({
            "fecha": n.procesada_en, "usuario": n.procesada_por, "modulo": "RR.HH.",
            "accion": f"Nómina procesada: ${n.total_pagar}",
            "referencia": n.periodo,
        })

    eventos.sort(key=lambda e: e["fecha"], reverse=True)
    return render(request, "administracion/auditoria_lista.html", {"eventos": eventos[:LIMITE_TOTAL]})


@staff_member_required(login_url="login")
def rol_lista(request):
    # Roles compartidos de plataforma (sin empresa vinculada, ej. "Ventas", "Administración")
    # + los roles personalizados que creó esta empresa.
    grupos = (
        Group.objects.filter(Q(empresa_vinculo__isnull=True) | Q(empresa_vinculo__empresa=request.empresa))
        .annotate(total_usuarios=Count("user")).order_by("name")
    )
    propios = set(GrupoEmpresa.objects.filter(empresa=request.empresa).values_list("grupo_id", flat=True))
    for grupo in grupos:
        # Un rol compartido de plataforma (Ventas, Administración, ...) no se puede
        # editar ni eliminar desde aquí, solo asignar.
        grupo.es_propio = grupo.pk in propios
    return render(request, "administracion/rol_lista.html", {"grupos": grupos})


@staff_member_required(login_url="login")
def rol_form(request, pk=None):
    grupo = get_object_or_404(Group, pk=pk, empresa_vinculo__empresa=request.empresa) if pk else None
    permisos_actuales = set()
    if grupo:
        permisos_actuales = set(grupo.permissions.values_list("id", flat=True))

    if request.method == "POST":
        form = RolForm(request.POST)
        if form.is_valid():
            nombre = form.cleaned_data["nombre"]
            duplicados = Group.objects.filter(name=nombre)
            if grupo:
                duplicados = duplicados.exclude(pk=grupo.pk)
            if duplicados.exists():
                form.add_error("nombre", "Ya existe un rol con ese nombre (los nombres de rol son únicos en toda la plataforma).")
            else:
                if grupo is None:
                    grupo = Group.objects.create(name=nombre)
                    GrupoEmpresa.objects.create(grupo=grupo, empresa=request.empresa)
                else:
                    grupo.name = nombre
                    grupo.save(update_fields=["name"])

                permisos_ids = set()
                for clave, _etiqueta, spec in APARTADOS_ROL:
                    if form.cleaned_data[clave]:
                        permisos_ids.update(permisos_de_apartado(spec).values_list("id", flat=True))
                grupo.permissions.set(permisos_ids)
                messages.success(request, f"Rol '{grupo.name}' guardado correctamente.")
                return redirect("administracion:rol_lista")
    else:
        initial = {"nombre": grupo.name if grupo else ""}
        for clave, _etiqueta, spec in APARTADOS_ROL:
            ids_apartado = set(permisos_de_apartado(spec).values_list("id", flat=True))
            initial[clave] = bool(ids_apartado) and ids_apartado.issubset(permisos_actuales)
        form = RolForm(initial=initial)

    return render(request, "administracion/rol_form.html", {"form": form, "grupo": grupo, "modulos": APARTADOS_ROL})


@staff_member_required(login_url="login")
def rol_eliminar(request, pk):
    grupo = get_object_or_404(Group, pk=pk, empresa_vinculo__empresa=request.empresa)
    if request.method == "POST":
        nombre = grupo.name
        grupo.delete()
        messages.success(request, f"Rol '{nombre}' eliminado.")
    return redirect("administracion:rol_lista")
