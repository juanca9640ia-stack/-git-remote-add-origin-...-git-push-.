from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ComunicadoForm
from .models import Comunicado


@login_required
def comunicado_lista(request):
    """Cartelera interna: visible para todos los usuarios autenticados de la
    empresa, publicar/eliminar requiere permiso (o ser el autor)."""
    puede_publicar = request.user.has_perm("comunicaciones.add_comunicado")

    if request.method == "POST":
        if not puede_publicar:
            messages.error(request, "No tienes permiso para publicar comunicados.")
            return redirect("comunicaciones:comunicado_lista")
        form = ComunicadoForm(request.POST)
        if form.is_valid():
            comunicado = form.save(commit=False)
            comunicado.empresa = request.empresa
            comunicado.publicado_por = request.user
            comunicado.save()
            messages.success(request, "Comunicado publicado.")
            return redirect("comunicaciones:comunicado_lista")
    else:
        form = ComunicadoForm()

    comunicados = Comunicado.objects.filter(empresa=request.empresa).select_related("publicado_por")
    return render(request, "comunicaciones/comunicado_lista.html", {
        "comunicados": comunicados, "form": form, "puede_publicar": puede_publicar,
    })


@login_required
@require_POST
def comunicado_eliminar(request, pk):
    comunicado = get_object_or_404(Comunicado, pk=pk, empresa=request.empresa)
    puede_eliminar = (
        request.user.has_perm("comunicaciones.delete_comunicado") or comunicado.publicado_por_id == request.user.id
    )
    if not puede_eliminar:
        messages.error(request, "No tienes permiso para eliminar este comunicado.")
        return redirect("comunicaciones:comunicado_lista")
    comunicado.delete()
    messages.success(request, "Comunicado eliminado.")
    return redirect("comunicaciones:comunicado_lista")
