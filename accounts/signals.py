"""
Auto-create a Profile for every User, so a User can never exist without one
(the failure mode that blocked the memberless super_admin). Superusers default
to super_admin; everyone else to member. Registration overrides the level
explicitly when it creates its own Profile, so this only fills the gap for
users created another way (createsuperuser, the admin, the shell).
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile
from .enums import AccessLevel


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if not created:
        return
    # Registration creates its own Profile in the same transaction; get_or_create
    # avoids clobbering it or raising on a race.
    level = AccessLevel.SUPER_ADMIN if instance.is_superuser else AccessLevel.MEMBER
    Profile.objects.get_or_create(
        user=instance, defaults={"access_level": level},
    )
