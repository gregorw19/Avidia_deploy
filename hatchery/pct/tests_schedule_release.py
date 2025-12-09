from datetime import date, datetime, time, timedelta
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from pct.models import (
    CertificationLevel,
    OpenHour,
    Profile,
    RoomReservation,
    ScheduleWeek,
    Semester,
    Shift,
    ShiftSwapRequest,
    Training,
)


class ScheduleReleaseTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        today = timezone.localdate()
        # pick the upcoming Monday (always in the future relative to today)
        self.week_start = today + timedelta(days=(7 - today.weekday()))

        self.staff_user = self.User.objects.create_user(username="staff", password="pass")
        self.staff_profile: Profile = self.staff_user.profile
        self.staff_profile.role = "staff"
        self.staff_profile.save()

        self.member_user = self.User.objects.create_user(username="member", password="pass")
        self.member_profile: Profile = self.member_user.profile
        self.member_profile.role = "team_member"
        self.member_profile.save()

        # Active semester covering the test window with full-day open hours.
        self.semester = Semester.objects.create(
            name="Test Semester",
            start_date=self.week_start - timedelta(days=7),
            end_date=self.week_start + timedelta(days=90),
            is_active=True,
        )
        for weekday in range(7):
            OpenHour.objects.create(
                semester=self.semester,
                weekday=weekday,
                open_time=time(0, 0),
                close_time=time(23, 59),
            )
        self.location = RoomReservation.RoomChoices.HATCH_FRONT

    def _make_shift(self):
        schedule_week = ScheduleWeek.objects.create(
            week_start=self.week_start,
            status=ScheduleWeek.Status.DRAFT,
            created_by=self.staff_profile,
        )
        start_dt = timezone.make_aware(datetime.combine(self.week_start, time(9, 0)))
        end_dt = timezone.make_aware(datetime.combine(self.week_start, time(12, 0)))
        shift = Shift.objects.create(
            schedule_week=schedule_week,
            title="Front desk",
            location=self.location,
            start=start_dt,
            end=end_dt,
            assigned_to=self.member_profile,
            min_staffing=1,
        )
        return schedule_week, shift

    def test_staff_can_publish_schedule_week(self):
        schedule_week, _ = self._make_shift()
        client = Client()
        client.force_login(self.staff_user)

        response = client.post(
            reverse("schedule-builder") + f"?week_start={self.week_start}", {"action": "publish"}
        )

        self.assertEqual(response.status_code, 302)
        schedule_week.refresh_from_db()
        self.assertEqual(schedule_week.status, ScheduleWeek.Status.PUBLISHED)
        self.assertIsNotNone(schedule_week.published_at)

    def test_team_member_only_sees_shifts_after_publish(self):
        schedule_week, shift = self._make_shift()

        member_client = Client()
        member_client.force_login(self.member_user)
        response = member_client.get(reverse("schedule") + f"?week_start={self.week_start}")
        self.assertEqual(list(response.context["my_shifts"]), [])

        staff_client = Client()
        staff_client.force_login(self.staff_user)
        staff_client.post(reverse("schedule-builder") + f"?week_start={self.week_start}", {"action": "publish"})
        schedule_week.refresh_from_db()
        self.assertEqual(schedule_week.status, ScheduleWeek.Status.PUBLISHED)

        response = member_client.get(reverse("schedule") + f"?week_start={self.week_start}")
        self.assertEqual(list(response.context["my_shifts"]), [shift])

    def test_non_staff_cannot_publish(self):
        schedule_week, _ = self._make_shift()
        member_client = Client()
        member_client.force_login(self.member_user)

        response = member_client.post(
            reverse("schedule-builder") + f"?week_start={self.week_start}", {"action": "publish"}
        )

        self.assertEqual(response.status_code, 302)
        schedule_week.refresh_from_db()
        self.assertEqual(schedule_week.status, ScheduleWeek.Status.DRAFT)
        self.assertIsNone(schedule_week.published_at)

    def test_team_member_can_signup_for_training(self):
        level_one = CertificationLevel.objects.create(level=1)
        training = Training.objects.create(
            name="Laser intro",
            machine="Glowforge Pro",
            level=level_one,
            staff=self.staff_profile,
        )

        member_client = Client()
        member_client.force_login(self.member_user)

        response = member_client.post(reverse("training-signup", args=[training.pk]))
        self.assertEqual(response.status_code, 302)

        training.refresh_from_db()
        self.assertEqual(training.student, self.member_profile)

    def test_training_signup_blocked_when_schedule_not_published(self):
        level_one = CertificationLevel.objects.create(level=1)
        schedule_week = ScheduleWeek.objects.create(
            week_start=self.week_start,
            status=ScheduleWeek.Status.DRAFT,
            created_by=self.staff_profile,
        )
        training_time = timezone.make_aware(datetime.combine(self.week_start, time(10, 0)))
        training = Training.objects.create(
            name="Laser intro",
            machine="Glowforge Pro",
            level=level_one,
            staff=self.staff_profile,
            time=training_time,
        )

        member_client = Client()
        member_client.force_login(self.member_user)

        response = member_client.post(reverse("training-signup", args=[training.pk]), follow=True)

        training.refresh_from_db()
        self.assertEqual(training.student, None)
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any("published" in message.message.lower() for message in messages_list))
        schedule_week.refresh_from_db()
        self.assertEqual(schedule_week.status, ScheduleWeek.Status.DRAFT)

    def test_training_signup_allowed_after_schedule_published(self):
        level_one = CertificationLevel.objects.create(level=1)
        ScheduleWeek.objects.create(
            week_start=self.week_start,
            status=ScheduleWeek.Status.PUBLISHED,
            created_by=self.staff_profile,
        )
        training_time = timezone.make_aware(datetime.combine(self.week_start, time(14, 0)))
        training = Training.objects.create(
            name="Laser intro",
            machine="Glowforge Pro",
            level=level_one,
            staff=self.staff_profile,
            time=training_time,
        )

        member_client = Client()
        member_client.force_login(self.member_user)

        response = member_client.post(reverse("training-signup", args=[training.pk]), follow=True)
        self.assertEqual(response.status_code, 200)

        training.refresh_from_db()
        self.assertEqual(training.student, self.member_profile)

    def test_calendar_hides_training_until_schedule_published(self):
        level_one = CertificationLevel.objects.create(level=1)
        schedule_week = ScheduleWeek.objects.create(
            week_start=self.week_start,
            status=ScheduleWeek.Status.DRAFT,
            created_by=self.staff_profile,
        )
        training_time = timezone.make_aware(datetime.combine(self.week_start, time(11, 0)))
        training = Training.objects.create(
            name="Laser intro",
            machine="Glowforge Pro",
            level=level_one,
            staff=self.staff_profile,
            time=training_time,
        )

        member_client = Client()
        member_client.force_login(self.member_user)

        response = member_client.get(reverse("events"))
        self.assertEqual(response.status_code, 200)
        events = json.loads(response.content)
        event_ids = [event.get("id") for event in events]
        self.assertNotIn(f"training-{training.id}", event_ids)

        schedule_week.status = ScheduleWeek.Status.PUBLISHED
        schedule_week.save(update_fields=["status"])

        response = member_client.get(reverse("events"))
        events = json.loads(response.content)
        event_ids = [event.get("id") for event in events]
        self.assertIn(f"training-{training.id}", event_ids)

    def test_team_member_cannot_exceed_20_hours_per_week(self):
        schedule_week = ScheduleWeek.objects.create(
            week_start=self.week_start,
            status=ScheduleWeek.Status.DRAFT,
            created_by=self.staff_profile,
        )

        def make_shift(day_offset, start_hour, end_hour):
            start_dt = timezone.make_aware(
                datetime.combine(self.week_start + timedelta(days=day_offset), time(start_hour, 0))
            )
            end_dt = timezone.make_aware(
                datetime.combine(self.week_start + timedelta(days=day_offset), time(end_hour, 0))
            )
            return Shift.objects.create(
                schedule_week=schedule_week,
                title="Front desk",
                location=self.location,
                start=start_dt,
                end=end_dt,
                assigned_to=self.member_profile,
                min_staffing=1,
            )

        make_shift(0, 8, 17)  # 9 hours
        make_shift(1, 8, 17)  # 9 hours, total 18

        with self.assertRaises(ValidationError):
            make_shift(2, 9, 14)  # Adds 5 hours -> 23 total, should fail

    def test_swap_approval_respects_weekly_hour_cap(self):
        schedule_week = ScheduleWeek.objects.create(
            week_start=self.week_start,
            status=ScheduleWeek.Status.DRAFT,
            created_by=self.staff_profile,
        )

        def make_shift(day_offset, start_hour, end_hour, assignee):
            start_dt = timezone.make_aware(
                datetime.combine(self.week_start + timedelta(days=day_offset), time(start_hour, 0))
            )
            end_dt = timezone.make_aware(
                datetime.combine(self.week_start + timedelta(days=day_offset), time(end_hour, 0))
            )
            return Shift.objects.create(
                schedule_week=schedule_week,
                title="Front desk",
                location=self.location,
                start=start_dt,
                end=end_dt,
                assigned_to=assignee,
                min_staffing=1,
            )

        make_shift(0, 8, 17, self.member_profile)
        make_shift(1, 8, 17, self.member_profile)

        other_user = self.User.objects.create_user(username="other", password="pass")
        other_profile: Profile = other_user.profile
        other_profile.role = "team_member"
        other_profile.save()

        swap_shift = make_shift(2, 9, 13, other_profile)  # 4 hours
        swap_request = ShiftSwapRequest.objects.create(
            shift=swap_shift,
            requester=other_profile,
            proposed_to=self.member_profile,
        )

        staff_client = Client()
        staff_client.force_login(self.staff_user)
        response = staff_client.post(
            reverse("schedule-builder") + f"?week_start={self.week_start}",
            {"action": "approve_swap", "swap_id": swap_request.pk},
            follow=True,
        )

        swap_shift.refresh_from_db()
        swap_request.refresh_from_db()

        self.assertEqual(swap_shift.assigned_to, other_profile)
        self.assertEqual(swap_request.status, ShiftSwapRequest.Status.PENDING)
        messages_list = list(response.wsgi_request._messages)
        self.assertTrue(any("20 hours" in message.message for message in messages_list))
