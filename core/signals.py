# core/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import Profile, MaterialProgress

User = get_user_model()

@receiver(post_save, sender=User)
def create_profile_and_assign(sender, instance, created, **kwargs):
    if not created:
        return
    # crea perfil si no existe
    Profile.objects.get_or_create(user=instance)
    # import tardío para evitar ciclos
    from .services.assignments import assign_by_rules
    assign_by_rules(instance)

@receiver(post_save, sender=MaterialProgress)
def update_enrollment_progress(sender, instance, **kwargs):
    course = getattr(getattr(instance, "material", None), "course", None)
    if not course:
        return
    # import tardío para evitar ciclos
    from .services.assignments import recompute_enrollment_progress_for
    recompute_enrollment_progress_for(instance.user, course)
