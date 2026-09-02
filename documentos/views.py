from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import DocumentoForm
from .models import Documento


@login_required
def documento_lista(request):
    documentos = Documento.objects.select_related("proyecto", "cliente", "subido_por").filter(
        empresa=request.empresa
    )

    categoria = request.GET.get("categoria", "")
    if categoria:
        documentos = documentos.filter(categoria=categoria)

    query = request.GET.get("q", "")
    if query:
        documentos = documentos.filter(titulo__icontains=query)

    proyecto_id = request.GET.get("proyecto", "")
    if proyecto_id:
        documentos = documentos.filter(proyecto_id=proyecto_id)

    return render(request, "documentos/documento_lista.html", {
        "documentos": documentos, "categoria": categoria, "query": query, "proyecto_id": proyecto_id,
        "total_documentos": Documento.objects.filter(empresa=request.empresa).count(),
    })


@login_required
def documento_subir(request):
    if request.method == "POST":
        form = DocumentoForm(request.POST, request.FILES, empresa=request.empresa)
        if form.is_valid():
            documento = form.save(commit=False)
            documento.empresa = request.empresa
            documento.subido_por = request.user
            documento.save()
            messages.success(request, f"Documento '{documento.titulo}' subido correctamente.")
            if documento.proyecto_id:
                return redirect("proyectos:proyecto_detalle", pk=documento.proyecto_id)
            return redirect("documentos:documento_lista")
    else:
        proyecto_id = request.GET.get("proyecto")
        initial = {"proyecto": proyecto_id} if proyecto_id else {}
        form = DocumentoForm(empresa=request.empresa, initial=initial)
    return render(request, "documentos/documento_form.html", {"form": form})


@login_required
@require_POST
def documento_eliminar(request, pk):
    documento = get_object_or_404(Documento, pk=pk, empresa=request.empresa)
    proyecto_id = documento.proyecto_id
    titulo = documento.titulo
    documento.delete()
    messages.success(request, f"Documento '{titulo}' eliminado.")
    if proyecto_id:
        return redirect("proyectos:proyecto_detalle", pk=proyecto_id)
    return redirect("documentos:documento_lista")
