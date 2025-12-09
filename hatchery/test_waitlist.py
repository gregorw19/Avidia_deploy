import os
import django
import unittest

# Configure Django before importing any models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hatchery.settings")
django.setup()

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.messages import get_messages
from django.utils import timezone
from pct.models import (
    Training,
    Profile,
    TrainingWaitlist,
    CertificationLevel,
    School,
    Major,
    Minor,
    CertificationType,
)

class TrainingWaitlistFlowTest(TestCase):
    def setUp(self):
        # Create users
        self.alice_user = User.objects.create_user(username="alice", password="password")
        self.bob_user = User.objects.create_user(username="bob", password="password")
        self.charlie_user = User.objects.create_user(username="charlie", password="password")
        self.staff_user = User.objects.create_user(username="staff", password="password")

        # Use auto-created profiles
        self.alice_profile = self.alice_user.profile
        self.bob_profile = self.bob_user.profile
        self.charlie_profile = self.charlie_user.profile
        self.staff_profile = self.staff_user.profile

        # Create required School/Major/Minor so Profile foreign keys are valid
        school = School.objects.create(school_name="MCAS")
        major = Major.objects.create(major_name="Computer Science", school=school)
        minor = Minor.objects.create(minor_name="Art History")

        # Attach majors/minors to profiles
        for profile in [self.alice_profile, self.bob_profile, self.charlie_profile, self.staff_profile]:
            profile.major1 = major
            profile.minor1 = minor
            profile.save()

        # Assign staff role
        self.staff_profile.role = "staff"
        self.staff_profile.save()

        # Create CertificationType and CertificationLevel (required for Training)
        cert_type = CertificationType.objects.create(name="Safety Training")
        cert_level = CertificationLevel.objects.create(level=1)

        # Create Training with required fields
        self.training = Training.objects.create(
            name="Test Training",
            machine="Laser Cutter",
            level=cert_level,
            certification_type=cert_type,
        )

        # Clients
        self.alice_client = Client()
        self.bob_client = Client()
        self.charlie_client = Client()
        self.staff_client = Client()
        self.alice_client.login(username="alice", password="password")
        self.bob_client.login(username="bob", password="password")
        self.charlie_client.login(username="charlie", password="password")
        self.staff_client.login(username="staff", password="password")

    def test_register_cancel_invite_flow(self):
        # Alice registers
        self.alice_client.post(reverse("register_training", args=[self.training.id]))
        self.training.refresh_from_db()
        self.assertEqual(self.training.student, self.alice_profile)

        # Bob joins waitlist
        self.bob_client.get(reverse("join_waitlist", args=[self.training.id]))
        waitlist_entry = TrainingWaitlist.objects.get(training=self.training, profile=self.bob_profile)
        self.assertEqual(waitlist_entry.status, "waiting")

        # Alice cancels, Bob invited
        self.alice_client.post(reverse("cancel_training", args=[self.training.id]))
        self.training.refresh_from_db()
        waitlist_entry.refresh_from_db()
        self.assertIsNone(self.training.student)
        self.assertEqual(waitlist_entry.status, "invited")

        # Bob confirms
        self.bob_client.post(reverse("confirm_training", args=[self.training.id, self.bob_profile.id]))
        self.training.refresh_from_db()
        waitlist_entry.refresh_from_db()
        self.assertEqual(self.training.student, self.bob_profile)
        self.assertEqual(waitlist_entry.status, "accepted")

    def test_decline_invitation(self):
        # Bob invited
        TrainingWaitlist.objects.create(training=self.training, profile=self.bob_profile, status="invited")

        # Bob declines
        self.bob_client.post(reverse("decline_training", args=[self.training.id, self.bob_profile.id]))
        entry = TrainingWaitlist.objects.get(training=self.training, profile=self.bob_profile)
        self.assertEqual(entry.status, "declined")

        # Slot empty
        self.training.refresh_from_db()
        self.assertIsNone(self.training.student)

        # Charlie joins waitlist
        self.charlie_client.get(reverse("join_waitlist", args=[self.training.id]))
        new_entry = TrainingWaitlist.objects.get(training=self.training, profile=self.charlie_profile)
        self.assertEqual(new_entry.status, "waiting")

    def test_duplicate_waitlist_entry(self):
        TrainingWaitlist.objects.create(training=self.training, profile=self.bob_profile)
        self.bob_client.get(reverse("join_waitlist", args=[self.training.id]))
        entries = TrainingWaitlist.objects.filter(training=self.training, profile=self.bob_profile)
        self.assertEqual(entries.count(), 1)


    def test_user_home_shows_waitlist_button(self):
        # Training is full and scheduled in the future
        self.training.time = timezone.now() + timezone.timedelta(days=1)
        self.training.student = self.alice_profile
        self.training.save()

        response = self.bob_client.get(reverse("user_home"), follow=True)

        # Bob joins waitlist
        self.bob_client.get(reverse("join_waitlist", args=[self.training.id]))
        entry = TrainingWaitlist.objects.get(training=self.training, profile=self.bob_profile)
        self.assertEqual(entry.status, "waiting")

        # HTML checks
        self.assertContains(response, "Full")
        self.assertContains(response, "Join Waitlist")
        self.assertTemplateUsed(response, "pct/user_home.html")

    def test_staff_home_shows_waitlist_button(self):
        # Training is full and scheduled in the future
        self.training.time = timezone.now() + timezone.timedelta(days=1)
        self.training.student = self.alice_profile
        self.training.save()

        response = self.staff_client.get(reverse("user_home"), follow=True)

        # HTML checks
        self.assertContains(response, "Full")
        self.assertContains(response, "Join Waitlist")
        self.assertTemplateUsed(response, "pct/staff_home.html")



if __name__ == "__main__":
    unittest.main()
