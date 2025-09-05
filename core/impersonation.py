# core/impersonation.py

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth import login, get_user_model
from django.conf import settings

User = get_user_model()

def _is_admin(user):
    # Permite a superusuarios; si tienes Profile.role, también acepta role=ADMIN
    try:
        return user.is_superuser or (hasattr(user, "profile") and getattr(user.profile, "role", "") == "ADMIN")
    except Exception:
        return user.is_superuser

@login_required
@user_passes_test(_is_admin)
def impersonate_start(request, user_id):
    # Bloquea anidamiento (si ya estás suplantando, primero detén)
    if request.session.get("impersonator_id"):
        messages.warning(request, "You are already impersonating. Stop first.")
        return redirect("dashboard")

    target = get_object_or_404(User, pk=user_id)

    # Seguridad: si el target es superusuario, solo un superusuario puede entrar como él
    if target.is_superuser and not request.user.is_superuser:
        messages.error(request, "You cannot impersonate a superuser.")
        return redirect("user_list")

    # Guarda quién es el verdadero admin y cambia sesión a target
    request.session["impersonator_id"] = request.user.id
    backend = settings.AUTHENTICATION_BACKENDS[0]
    login(request, target, backend=backend)
    messages.success(request, f"You are now impersonating: {target.username}")
    return redirect("dashboard")

@login_required
def impersonate_stop(request):
    orig_id = request.session.get("impersonator_id")
    if not orig_id:
        messages.info(request, "You are not impersonating anyone.")
        return redirect("dashboard")

    admin_user = get_object_or_404(User, pk=orig_id)
    backend = settings.AUTHENTICATION_BACKENDS[0]
    login(request, admin_user, backend=backend)
    try:
        del request.session["impersonator_id"]
    except KeyError:
        pass
    messages.success(request, "Impersonation ended. You're back as admin.")
    return redirect("dashboard")
