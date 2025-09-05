# core/views_material_watch.py
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse
from .models import CourseMaterial

def material_watch(request, material_id: int):
    m = get_object_or_404(CourseMaterial, pk=material_id)

    # Si es un enlace de YouTube, redirige allí
    if m.kind == CourseMaterial.KIND_YOUTUBE and m.youtube_url:
        return redirect(m.youtube_url)

    # Si tiene archivo subido, redirige al archivo
    if m.file:
        try:
            return redirect(m.file.url)
        except Exception:
            pass

    return HttpResponse("This material has no file or URL.", status=404)
