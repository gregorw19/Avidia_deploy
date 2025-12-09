from django import forms
from datetime import datetime, timedelta
from .models import (
    Training,
    Profile,
    CertificationLevel,
    CertificationType,
    RoomReservation,
    Report,
    Availability,
    Shift,
    ShiftSwapRequest,
    Semester,
    Holiday,
    OpenHour,
)

MACHINE_CHOICES = [
    ("Prusa MK4", "Prusa MK4 (3D Printer)"),
    ("Bambu Lab X1 Carbon", "Bambu Lab X1 Carbon (3D Printer)"),
    ("Glowforge Pro", "Glowforge Pro (Laser Cutter)"),
    ("SawStop PCS", "SawStop PCS (Table Saw)"),
    ("Cricut Maker 3", "Cricut Maker 3 (Vinyl Cutter)"),
    ("Precision Matthews PM-1236", "Precision Matthews PM-1236 (Metal Lathe)"),
    ("Hakko FX-888D", "Hakko FX-888D (Soldering Station)"),
    ("Juki TL-2010Q", "Juki TL-2010Q (Textile Lab)"),
]

DATETIME_LOCAL_FORMAT = "%Y-%m-%dT%H:%M"

ROOM_CHOICES = [
    ("Second Floor", (
        (RoomReservation.RoomChoices.HATCH_FRONT, "Hatch Front"),
        (RoomReservation.RoomChoices.HATCH_BACK, "Hatch Back"),
    )),
    ("Third Floor", (
        (RoomReservation.RoomChoices.PROTO_STUDIO, "Prototyping Studio"),
        (RoomReservation.RoomChoices.PROTO_SHOP, "Prototyping Shop"),
    )),
]


def _active_semester_for_date(target_date):
    if not target_date:
        return None
    return (
        Semester.objects.filter(
            start_date__lte=target_date,
            end_date__gte=target_date,
            is_active=True,
        )
        .order_by("-start_date")
        .first()
    )


def _within_open_hours(semester, start_dt, end_dt):
    """Return True if the start/end fall within configured open hours for the weekday."""
    if not semester:
        return True
    weekday = start_dt.weekday()
    hours = semester.open_hours.filter(weekday=weekday)
    if not hours.exists():
        return False
    for window in hours:
        if window.open_time <= start_dt.time() and window.close_time >= end_dt.time():
            return True
    return False


def _is_holiday(semester, target_date):
    if not semester:
        return False
    return semester.holidays.filter(date=target_date).exists()

class TrainingForm(forms.ModelForm):
    machine = forms.ChoiceField(
        choices=[("", "Select a machine")] + MACHINE_CHOICES,
        required=True,
        help_text="Pick the machine students will train on.",
    )
    time_date = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date"},
        ),
        help_text="",
    )
    time_hour = forms.ChoiceField(
        choices=[('', 'Hour')] + [(str(i).zfill(2), str(i).zfill(2)) for i in range(24)],
        required=False,
        help_text="",
    )
    time_minute = forms.ChoiceField(
        choices=[('', 'Min')] + [(str(i).zfill(2), str(i).zfill(2)) for i in range(0, 60, 15)],
        required=False,
        help_text="Use local time; leave blank if the training time is still TBD.",
    )

    class Meta:
        model = Training
        fields = ("name", "machine", "certification_type", "level", "student", "staff")

    def __init__(self, *args, **kwargs):
        staff_user = kwargs.pop("staff_user", None)
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Profile.objects.filter(role__in=Profile.USER_ROLES)
        self.fields["student"].required = False
        self.fields["student"].help_text = "Leave blank to allow a student to sign up later."
        self.fields["staff"].queryset = Profile.objects.filter(role__in=["staff", "team_member"])
        self.fields["staff"].required = True
        self.fields["staff"].label_from_instance = lambda p: p.get_full_name()
        self.fields["student"].label_from_instance = lambda p: p.get_full_name()
        self.fields["level"].queryset = CertificationLevel.objects.order_by("level")
        self.fields["level"].label_from_instance = lambda level: f"L{level.level}"
        self.fields["certification_type"].queryset = CertificationType.objects.order_by("name")
        self.fields["certification_type"].required = False

        # If editing existing training, populate date/time fields
        if self.instance and self.instance.pk and self.instance.time:
            self.initial['time_date'] = self.instance.time.date()
            time_obj = self.instance.time.time()
            self.initial['time_hour'] = str(time_obj.hour).zfill(2)
            self.initial['time_minute'] = str(time_obj.minute).zfill(2)

        self.staff_profile = None
        if staff_user is not None:
            self.staff_profile = Profile.objects.filter(user=staff_user).first()
            if self.staff_profile and not self.instance.pk:
                self.fields["staff"].initial = self.staff_profile

        for field in self.fields.values():
            existing_classes = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing_classes + " form-input").strip()
    
    def clean(self):
        cleaned_data = super().clean()
        from django.utils import timezone
        from datetime import datetime, time
        
        time_date = cleaned_data.get("time_date")
        time_hour = cleaned_data.get("time_hour")
        time_minute = cleaned_data.get("time_minute")
        
        # Combine date and time into datetime object (optional field)
        if time_date and time_hour and time_minute:
            try:
                time_obj = time(int(time_hour), int(time_minute))
                time_datetime = datetime.combine(time_date, time_obj)
                cleaned_data["time"] = timezone.make_aware(time_datetime)
            except (ValueError, TypeError):
                self.add_error("time_hour", "Invalid time selected.")
                self.add_error("time_minute", "Invalid time selected.")
        elif time_date or time_hour or time_minute:
            # If any part is filled, all must be filled
            if not time_date:
                self.add_error("time_date", "Date is required if time is specified.")
            if not time_hour:
                self.add_error("time_hour", "Hour is required if time is specified.")
            if not time_minute:
                self.add_error("time_minute", "Minute is required if time is specified.")
        # If all are empty, time remains None (optional field)
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        # Set time from cleaned_data (set in clean method)
        if 'time' in self.cleaned_data:
            instance.time = self.cleaned_data['time']
        elif not self.cleaned_data.get('time_date') and not self.cleaned_data.get('time_hour') and not self.cleaned_data.get('time_minute'):
            # If all time fields are empty, set time to None
            instance.time = None
        if commit:
            instance.save()
        return instance


class RoomReservationForm(forms.ModelForm):
    room = forms.ChoiceField(choices=ROOM_CHOICES)
    start_date = forms.DateField(
        widget=forms.DateInput(
            attrs={"type": "date"},
        ),
        help_text="Choose the date for your reservation.",
    )
    start_time_hour = forms.ChoiceField(
        choices=[('', 'Hour')] + [(str(i).zfill(2), str(i).zfill(2)) for i in range(24)],
        required=False,
        help_text="",
    )
    start_time_minute = forms.ChoiceField(
        choices=[('', 'Min')] + [(str(i).zfill(2), str(i).zfill(2)) for i in range(0, 60, 15)],
        required=False,
        help_text="Choose when your reservation begins.",
    )
    end_date = forms.DateField(
        widget=forms.DateInput(
            attrs={"type": "date"},
        ),
        help_text="Choose the end date (must be same day).",
    )
    end_time_hour = forms.ChoiceField(
        choices=[('', 'Hour')] + [(str(i).zfill(2), str(i).zfill(2)) for i in range(24)],
        required=False,
        help_text="",
    )
    end_time_minute = forms.ChoiceField(
        choices=[('', 'Min')] + [(str(i).zfill(2), str(i).zfill(2)) for i in range(0, 60, 15)],
        required=False,
        help_text="Choose when your reservation ends.",
    )
    is_exclusive_request = forms.BooleanField(
        required=False,
        label="Exclusive classroom/station use",
        help_text="Select if you need the room blocked for a specific course or event.",
    )
    affiliation = forms.CharField(
        max_length=255,
        help_text="Tell us which class or organization needs the space.",
    )

    class Meta:
        model = RoomReservation
        fields = ("room", "affiliation", "is_exclusive_request")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If editing existing reservation, populate date/time fields
        if self.instance and self.instance.pk:
            if self.instance.start_time:
                self.initial['start_date'] = self.instance.start_time.date()
                start_time = self.instance.start_time.time()
                self.initial['start_time_hour'] = str(start_time.hour).zfill(2)
                self.initial['start_time_minute'] = str(start_time.minute).zfill(2)
            if self.instance.end_time:
                self.initial['end_date'] = self.instance.end_time.date()
                end_time = self.instance.end_time.time()
                self.initial['end_time_hour'] = str(end_time.hour).zfill(2)
                self.initial['end_time_minute'] = str(end_time.minute).zfill(2)
            self.initial.setdefault("is_exclusive_request", self.instance.is_exclusive_request)
        
        for field in self.fields.values():
            existing_classes = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing_classes + " form-input").strip()

    def clean(self):
        cleaned_data = super().clean()
        from django.utils import timezone
        from datetime import datetime, time
        
        start_date = cleaned_data.get("start_date")
        start_hour = cleaned_data.get("start_time_hour")
        start_minute = cleaned_data.get("start_time_minute")
        end_date = cleaned_data.get("end_date")
        end_hour = cleaned_data.get("end_time_hour")
        end_minute = cleaned_data.get("end_time_minute")
        
        # Combine date and time into datetime objects
        if start_date and start_hour and start_minute:
            try:
                start_time_obj = time(int(start_hour), int(start_minute))
                start_datetime = datetime.combine(start_date, start_time_obj)
                cleaned_data["start_time"] = timezone.make_aware(start_datetime)
            except (ValueError, TypeError):
                self.add_error("start_time_hour", "Invalid time selected.")
                self.add_error("start_time_minute", "Invalid time selected.")
        elif start_date or start_hour or start_minute:
            if not start_date:
                self.add_error("start_date", "Start date is required.")
            if not start_hour:
                self.add_error("start_time_hour", "Start hour is required.")
            if not start_minute:
                self.add_error("start_time_minute", "Start minute is required.")
        
        if end_date and end_hour and end_minute:
            try:
                end_time_obj = time(int(end_hour), int(end_minute))
                end_datetime = datetime.combine(end_date, end_time_obj)
                cleaned_data["end_time"] = timezone.make_aware(end_datetime)
            except (ValueError, TypeError):
                self.add_error("end_time_hour", "Invalid time selected.")
                self.add_error("end_time_minute", "Invalid time selected.")
        elif end_date or end_hour or end_minute:
            if not end_date:
                self.add_error("end_date", "End date is required.")
            if not end_hour:
                self.add_error("end_time_hour", "End hour is required.")
            if not end_minute:
                self.add_error("end_time_minute", "End minute is required.")
        
        start = cleaned_data.get("start_time")
        end = cleaned_data.get("end_time")
        
        if start and end:
            if end <= start:
                self.add_error("end_time_hour", "End time must be after the start time.")
                self.add_error("end_time_minute", "End time must be after the start time.")
            if start.date() != end.date():
                self.add_error("end_date", "Reservations must begin and end on the same day.")
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        # Set start_time and end_time from cleaned_data (set in clean method)
        if 'start_time' in self.cleaned_data:
            instance.start_time = self.cleaned_data['start_time']
        if 'end_time' in self.cleaned_data:
            instance.end_time = self.cleaned_data['end_time']
        if commit:
            instance.save()
        return instance


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ['title', 'category', 'description']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter report title'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 5,
                'placeholder': 'Describe the issue or concern...'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set default category to 'other'
        if not self.instance.pk:  # Only for new reports
            self.fields['category'].initial = 'other'


class AvailabilityForm(forms.ModelForm):
    skills = forms.ModelMultipleChoiceField(
        queryset=CertificationType.objects.order_by("name"),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-input"}),
        help_text="Pick certifications you can cover during this slot (optional).",
    )
    day = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "placeholder": "YYYY-MM-DD"}),
        input_formats=["%Y-%m-%d"],
        label="Date",
    )
    start_time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time", "placeholder": "HH:MM"}, format="%H:%M"),
        input_formats=["%H:%M"],
        label="Start time",
    )
    end_time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time", "placeholder": "HH:MM"}, format="%H:%M"),
        input_formats=["%H:%M"],
        label="End time",
    )

    class Meta:
        model = Availability
        fields = ("note", "skills")

    def __init__(self, *args, **kwargs):
        self.week = kwargs.pop("week", None)
        self.semester = kwargs.pop("semester", None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing_classes = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing_classes + " form-input").strip()
        # Keep the note field compact
        if "note" in self.fields:
            self.fields["note"].widget.attrs.setdefault("rows", 2)
            self.fields["note"].widget.attrs.setdefault("placeholder", "Optional note")
        # Pre-populate date fields to the selected week for convenience
        if self.instance and self.instance.pk:
            if self.instance.start:
                self.initial.setdefault("day", self.instance.start.date())
                self.initial.setdefault("start_time", self.instance.start.time().strftime("%H:%M"))
            if self.instance.end:
                self.initial.setdefault("end_time", self.instance.end.time().strftime("%H:%M"))
        elif self.week:
            self.initial.setdefault("day", self.week.week_start)

        if self.week:
            week_end = self.week.week_start + timedelta(days=6)
            self.fields["day"].widget.attrs["min"] = self.week.week_start
            self.fields["day"].widget.attrs["max"] = week_end

    def clean(self):
        cleaned_data = super().clean()
        from datetime import timedelta
        from django.utils import timezone
        day = cleaned_data.get("day")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if day and start_time:
            start_dt = datetime.combine(day, start_time)
            cleaned_data["start"] = timezone.make_aware(start_dt) if timezone.is_naive(start_dt) else start_dt
        if day and end_time:
            end_dt = datetime.combine(day, end_time)
            cleaned_data["end"] = timezone.make_aware(end_dt) if timezone.is_naive(end_dt) else end_dt

        start = cleaned_data.get("start")
        end = cleaned_data.get("end")

        if start and end and end <= start:
            self.add_error("end_time", "End must be after start time.")

        if self.week and start and end:
            week_start = self.week.week_start
            week_end = week_start + timedelta(days=7)
            if start.date() < week_start or end.date() >= week_end:
                self.add_error("day", "Availability must fall within the selected week.")

        # Enforce open hours/holidays for the active semester
        semester = self.semester or _active_semester_for_date(
            start.date() if start else end.date() if end else None
        )
        if semester and start and end:
            if _is_holiday(semester, start.date()):
                self.add_error(None, f"{start.date()} is marked as a holiday for {semester.name}.")
            elif not _within_open_hours(semester, start, end):
                self.add_error(None, f"This slot is outside the open hours for {semester.name}.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.start = self.cleaned_data.get("start")
        instance.end = self.cleaned_data.get("end")
        # carry semester context for view logic if needed
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ShiftForm(forms.ModelForm):
    location = forms.ChoiceField(
        choices=RoomReservation.RoomChoices.choices,
        widget=forms.Select(attrs={"class": "form-input"}),
    )
    required_certifications = forms.ModelMultipleChoiceField(
        queryset=CertificationType.objects.order_by("name"),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-input"}),
        help_text="Tag the certs needed for this shift (optional).",
    )
    start = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL_FORMAT),
        input_formats=[DATETIME_LOCAL_FORMAT],
    )
    end = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL_FORMAT),
        input_formats=[DATETIME_LOCAL_FORMAT],
    )

    class Meta:
        model = Shift
        fields = ("title", "location", "start", "end", "min_staffing", "assigned_to", "notes", "required_certifications")

    def __init__(self, *args, **kwargs):
        self.week = kwargs.pop("week", None)
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].required = False
        self.fields["assigned_to"].queryset = Profile.objects.filter(role__in=Profile.USER_ROLES + ("staff",))
        self.fields["assigned_to"].label_from_instance = lambda p: p.get_full_name()
        for field in self.fields.values():
            existing_classes = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing_classes + " form-input").strip()

    def clean(self):
        if self.week:
            # ensure the instance carries the selected week for validation/save
            self.instance.schedule_week = self.week
        cleaned_data = super().clean()
        from datetime import timedelta
        from django.utils import timezone

        start = cleaned_data.get("start")
        end = cleaned_data.get("end")
        if start and timezone.is_naive(start):
            start = timezone.make_aware(start)
            cleaned_data["start"] = start
        if end and timezone.is_naive(end):
            end = timezone.make_aware(end)
            cleaned_data["end"] = end

        if start and end and end <= start:
            self.add_error("end", "End must be after start time.")

        if self.week and start and end:
            week_start = self.week.week_start
            week_end = week_start + timedelta(days=7)
            if start.date() < week_start or end.date() >= week_end:
                self.add_error("start", "Shift must be scheduled within the selected week.")
                self.add_error("end", "Shift must be scheduled within the selected week.")

        semester = None
        if start and end:
            start_date = start.date()
            end_date = end.date()
            start_semester = _active_semester_for_date(start_date)
            end_semester = _active_semester_for_date(end_date)
            if not start_semester or not end_semester or start_semester.pk != end_semester.pk:
                self.add_error("start", "Shifts must start and end within an active semester.")
                self.add_error("end", "Shifts must start and end within an active semester.")
            else:
                semester = start_semester
                if end_date > semester.end_date or start_date < semester.start_date:
                    self.add_error("start", f"Shifts must be scheduled during {semester.name}.")
                    self.add_error("end", f"Shifts must be scheduled during {semester.name}.")
                elif _is_holiday(semester, start_date):
                    self.add_error(None, f"{start_date} is marked as a holiday for {semester.name}.")
                elif not _within_open_hours(semester, start, end):
                    self.add_error(None, f"This shift is outside the open hours for {semester.name}.")

        assignee = cleaned_data.get("assigned_to")
        if self.week and assignee and assignee.role == "team_member" and start and end:
            current_duration = Shift.weekly_assigned_duration(
                self.week, assignee, exclude_shift_id=self.instance.pk
            )
            projected_total = current_duration + (end - start)
            if projected_total > timedelta(hours=20):
                self.add_error(
                    "assigned_to",
                    f"{assignee.get_full_name()} would exceed 20 hours for this week.",
                )

        return cleaned_data


class SwapRequestForm(forms.ModelForm):
    class Meta:
        model = ShiftSwapRequest
        fields = ("proposed_to", "reason", "is_give_up")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proposed_to"].required = False
        self.fields["proposed_to"].queryset = Profile.objects.filter(role__in=Profile.USER_ROLES)
        for field in self.fields.values():
            existing_classes = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing_classes + " form-input").strip()


class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester
        fields = ("name", "start_date", "end_date", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make semester dates use native date pickers.
        for field_name in ("start_date", "end_date"):
            field = self.fields[field_name]
            field.widget.attrs["type"] = "date"
            field.widget.attrs.setdefault("placeholder", "YYYY-MM-DD")

        # Match the styling of other forms.
        for field_name in ("name", "start_date", "end_date"):
            existing_classes = self.fields[field_name].widget.attrs.get("class", "")
            self.fields[field_name].widget.attrs["class"] = (existing_classes + " form-input").strip()

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after the start date.")
        return cleaned_data


class OpenHourForm(forms.ModelForm):
    class Meta:
        model = OpenHour
        fields = ("semester", "weekday", "open_time", "close_time")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Style fields and use native time pickers.
        for name in ("semester", "weekday", "open_time", "close_time"):
            field = self.fields[name]
            existing_classes = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing_classes + " form-input").strip()

        for time_field in ("open_time", "close_time"):
            field = self.fields[time_field]
            field.widget.attrs["type"] = "time"
            field.widget.attrs.setdefault("placeholder", "HH:MM")
            field.help_text = "Enter time as HH:MM."

    def clean(self):
        cleaned_data = super().clean()
        open_time = cleaned_data.get("open_time")
        close_time = cleaned_data.get("close_time")
        if open_time and close_time and close_time <= open_time:
            self.add_error("close_time", "Close time must be after open time.")
        return cleaned_data


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ("semester", "date", "name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        date_field = self.fields["date"]
        date_field.widget.attrs["type"] = "date"
        date_field.widget.attrs.setdefault("placeholder", "YYYY-MM-DD")

        for field in self.fields.values():
            existing_classes = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing_classes + " form-input").strip()

    def clean(self):
        cleaned_data = super().clean()
        semester = cleaned_data.get("semester")
        date = cleaned_data.get("date")
        if semester and date:
            if date < semester.start_date or date > semester.end_date:
                self.add_error("date", "Holiday must fall within the semester dates.")
        return cleaned_data
