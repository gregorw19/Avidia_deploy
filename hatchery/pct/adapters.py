from django.core.exceptions import ValidationError
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from .models import Profile
import logging

logger = logging.getLogger(__name__)


class BCOnlySocialAccountAdapter(DefaultSocialAccountAdapter):
    """Restrict Google logins to @bc.edu accounts."""

    def validate_email(self, email):
        email = super().validate_email(email)

        if email and not email.lower().endswith("@bc.edu"):
            raise ValidationError("Please sign in with your @bc.edu email address.")

        return email
    
    def save_user(self, request, sociallogin, form=None):
        """Override to ensure Profile is created properly after user is saved."""
        try:
            user = super().save_user(request, sociallogin, form)
            # Ensure Profile exists for the user
            Profile.objects.get_or_create(user=user)
            return user
        except Exception as e:
            logger.error(f"Error saving user in social account adapter: {e}", exc_info=True)
            raise
