from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from allauth.account.signals import user_logged_in
from allauth.socialaccount.signals import social_account_added
from .models import Profile, ActivityLog, Training, Certification, RoomReservation
from django.contrib import messages

User = get_user_model()

@receiver(post_save, sender=User)
def ensure_profile(sender, instance, **kwargs):
    profile, created = Profile.objects.get_or_create(user=instance)
    profile.save()

@receiver(user_logged_in)
def assign_role_on_login(request, user, **kwargs):
    """Handle role assignment for both regular and social login"""
    # Check for chosen_role in session
    role = request.session.get('chosen_role')
    if role:
        role = role.lower()  # Normalize to lowercase
        profile, _ = Profile.objects.get_or_create(user=user)
        
        # Check if user already has a role assigned
        if profile.role and profile.role.strip():
            existing_role = profile.role.lower()
            if existing_role != role:
                # User trying to login with different role - mark as error
                request.session['role_mismatch'] = True
                request.session['attempted_role'] = role
                request.session['existing_role'] = existing_role
            # If same role, do nothing - just keep existing role
        else:
            # No role yet, assign the new role
            profile.role = role
            profile.save()
        
        # Clean up session variable
        if 'chosen_role' in request.session:
            del request.session['chosen_role']
    
    # Log login activity
    try:
        ActivityLog.objects.create(
            user=user,
            action='login',
            description=f'{user.get_full_name() or user.username} logged in'
        )
    except Exception:
        pass  # Don't break login if logging fails

@receiver(social_account_added)
def assign_role_on_social_login(request, sociallogin, **kwargs):
    """Handle role assignment specifically for social account login"""
    try:
        # Check for chosen_role in session  
        role = request.session.get('chosen_role')
        if role:
            role = role.lower()  # Normalize to lowercase
            user = sociallogin.user
            if user and user.pk:
                profile, _ = Profile.objects.get_or_create(user=user)
                
                # Check if user already has a role assigned
                if profile.role and profile.role.strip():
                    existing_role = profile.role.lower()
                    if existing_role != role:
                        # User trying to login with different role - mark as error
                        request.session['role_mismatch'] = True
                        request.session['attempted_role'] = role
                        request.session['existing_role'] = existing_role
                    # If same role, do nothing - just keep existing role
                else:
                    # No role yet, assign the new role
                    profile.role = role
                    profile.save()
                
                # Clean up session variable
                if 'chosen_role' in request.session:
                    del request.session['chosen_role']
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in assign_role_on_social_login: {e}", exc_info=True)
        # Don't raise - let the login continue even if role assignment fails


@receiver(post_save, sender=Training)
def log_training_activity(sender, instance, created, **kwargs):
    """Log training booking activity"""
    if created and instance.student:
        try:
            ActivityLog.objects.create(
                user=instance.student.user,
                action='training',
                description=f'Booked training: {instance.name}'
            )
        except Exception:
            pass  # Don't break training creation if logging fails


@receiver(post_save, sender=Certification)
def log_certification_activity(sender, instance, created, **kwargs):
    """Log certification activity"""
    if created and instance.profile:
        try:
            ActivityLog.objects.create(
                user=instance.profile.user,
                action='certification',
                description=f'Added certification: {instance.type.name} Level {instance.level.level}'
            )
        except Exception:
            pass  # Don't break certification creation if logging fails


@receiver(post_save, sender=RoomReservation)
def log_reservation_activity(sender, instance, created, **kwargs):
    """Log reservation activity"""
    if created:
        try:
            ActivityLog.objects.create(
                user=instance.requester.user,
                action='reservation',
                description=f'Requested room reservation: {instance.get_room_display()}'
            )
        except Exception:
            pass  # Don't break reservation creation if logging fails
