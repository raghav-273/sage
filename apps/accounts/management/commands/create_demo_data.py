# apps/accounts/management/commands/create_demo_data.py
"""
Creates realistic demo data for SAGE demonstrations.

Run once before the demo:
    docker compose exec web python manage.py create_demo_data

Creates:
  - 3 pending registration applications (for admin approval demo)
  - 3 demo users with different roles (reviewer, document manager, engineer)
  - Clears any stale lockout/rate-limit cache entries

Safe to run multiple times — uses get_or_create throughout.
"""

from django.contrib.auth.hashers import make_password
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

User = get_user_model()


DEMO_REGISTRATIONS = [
    {
        "username": "araj.singh",
        "email": "araj.singh@rdso.gov.in",
        "first_name": "Araj",
        "last_name": "Singh",
        "department": "Track Engineering",
        "designation": "Junior Engineer",
        "employee_id": "RDSO/TE/2024/041",
        "reason_for_access": (
            "I am a Junior Engineer in the Track Engineering directorate working on "
            "evaluation of rail joint specifications for the Mumbai-Ahmedabad HSRC project. "
            "I need access to SAGE to efficiently cross-reference RDSO track standards "
            "and verify material specifications without manual PDF searches."
        ),
        "password": "DemoPass2024!",
    },
    {
        "username": "priya.mehta",
        "email": "priya.mehta@rdso.gov.in",
        "first_name": "Priya",
        "last_name": "Mehta",
        "department": "Rolling Stock",
        "designation": "Section Engineer",
        "employee_id": "RDSO/RS/2023/018",
        "reason_for_access": (
            "Section Engineer in Rolling Stock directorate. Currently preparing compliance "
            "documentation for the Vande Bharat coach specification review. "
            "SAGE will help me retrieve specific clause references quickly during "
            "design approval meetings with vendors."
        ),
        "password": "DemoPass2024!",
    },
    {
        "username": "kiran.nair",
        "email": "kiran.nair@rdso.gov.in",
        "first_name": "Kiran",
        "last_name": "Nair",
        "department": "Signal and Telecommunications",
        "designation": "Research Officer",
        "employee_id": "RDSO/ST/2022/007",
        "reason_for_access": (
            "Research Officer in the S&T directorate conducting a literature survey on "
            "Kavach system integration specifications. Need cross-document search capability "
            "to identify conflicts between signalling standards and track geometry requirements "
            "for high-speed corridors."
        ),
        "password": "DemoPass2024!",
    },
]

DEMO_USERS = [
    {
        "username": "dr.sharma",
        "email": "sharma.rdso@gmail.com",
        "first_name": "Rajiv",
        "last_name": "Sharma",
        "role": "reviewer",
        "department": "Research Division",
        "designation": "Senior Research Officer",
        "employee_id": "RDSO/RD/2019/003",
        "password": "Demo@Reviewer1",
    },
    {
        "username": "doc.manager",
        "email": "docmanager.rdso@gmail.com",
        "first_name": "Sunita",
        "last_name": "Verma",
        "role": "document_manager",
        "department": "IT Division",
        "designation": "Document Controller",
        "employee_id": "RDSO/IT/2021/011",
        "password": "Demo@DocMgr1",
    },
    {
        "username": "eng.demo",
        "email": "engineer.rdso@gmail.com",
        "first_name": "Vikram",
        "last_name": "Patel",
        "role": "engineer",
        "department": "Bridge Engineering",
        "designation": "Assistant Research Officer",
        "employee_id": "RDSO/BR/2023/029",
        "password": "Demo@Eng1234",
    },
]


class Command(BaseCommand):
    help = "Creates realistic demo data for SAGE demonstrations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-registrations",
            action="store_true",
            help="Delete existing PENDING_APPROVAL registrations before creating new ones",
        )

    def handle(self, *args, **options):
        from apps.accounts.models import AccountRegistration, Role, UserProfile
        from django.core.cache import cache

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== SAGE Demo Data Setup ===\n"))

        # Clear cache (removes any lockouts from testing)
        cache.clear()
        self.stdout.write(self.style.SUCCESS("  Cache cleared (login lockouts reset)"))

        # --- Pending Registrations ---
        self.stdout.write(self.style.MIGRATE_HEADING("\n  Creating pending registrations..."))

        if options["clear_registrations"]:
            deleted, _ = AccountRegistration.objects.filter(
                status=AccountRegistration.Status.PENDING_APPROVAL
            ).delete()
            self.stdout.write(f"  Cleared {deleted} existing pending registrations")

        created_regs = 0
        for reg_data in DEMO_REGISTRATIONS:
            existing = AccountRegistration.objects.filter(
                username=reg_data["username"]
            ).first()
            if existing:
                self.stdout.write(f"    SKIP  {reg_data['username']} (already exists: {existing.status})")
                continue

            AccountRegistration.objects.create(
                username=reg_data["username"],
                email=reg_data["email"],
                first_name=reg_data["first_name"],
                last_name=reg_data["last_name"],
                department=reg_data["department"],
                designation=reg_data["designation"],
                employee_id=reg_data["employee_id"],
                reason_for_access=reg_data["reason_for_access"],
                password_hash=make_password(reg_data["password"]),
                status=AccountRegistration.Status.PENDING_APPROVAL,
                verified_at=timezone.now(),
            )
            created_regs += 1
            self.stdout.write(
                self.style.SUCCESS(f"    CREATED  {reg_data['username']} ({reg_data['department']})")
            )

        self.stdout.write(
            self.style.SUCCESS(f"\n  {created_regs} pending registrations created")
        )

        # --- Demo Users ---
        self.stdout.write(self.style.MIGRATE_HEADING("\n  Creating demo user accounts..."))

        for user_data in DEMO_USERS:
            role = Role.objects.filter(name=user_data["role"]).first()
            if not role:
                self.stdout.write(
                    self.style.WARNING(f"    SKIP  Role '{user_data['role']}' not found — run migrations first")
                )
                continue

            user, created = User.objects.get_or_create(
                username=user_data["username"],
                defaults={
                    "email": user_data["email"],
                    "first_name": user_data["first_name"],
                    "last_name": user_data["last_name"],
                    "is_active": True,
                },
            )

            if created:
                user.set_password(user_data["password"])
                user.save()

            # Profile is created by signal — ensure role and metadata
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.department = user_data["department"]
            profile.designation = user_data["designation"]
            profile.employee_id = user_data["employee_id"]
            profile.save(update_fields=["role", "department", "designation", "employee_id"])

            status = "CREATED" if created else "UPDATED"
            self.stdout.write(
                self.style.SUCCESS(
                    f"    {status}  {user_data['username']} / {user_data['password']} "
                    f"  [{role.display_name}]  ({user_data['department']})"
                )
            )

        # --- Summary ---
        pending_count = AccountRegistration.objects.filter(
            status=AccountRegistration.Status.PENDING_APPROVAL
        ).count()
        user_count = User.objects.filter(is_active=True).count()

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Demo Data Summary ==="))
        self.stdout.write(f"  Pending registrations:  {pending_count}")
        self.stdout.write(f"  Active user accounts:   {user_count}")
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("  Demo login credentials:"))
        self.stdout.write("  ┌──────────────────┬──────────────────────┬──────────────────────┐")
        self.stdout.write("  │ Username         │ Password             │ Role                 │")
        self.stdout.write("  ├──────────────────┼──────────────────────┼──────────────────────┤")
        for u in DEMO_USERS:
            role_obj = Role.objects.filter(name=u["role"]).first()
            role_display = role_obj.display_name if role_obj else u["role"]
            self.stdout.write(
                f"  │ {u['username']:<16} │ {u['password']:<20} │ {role_display:<20} │"
            )
        self.stdout.write("  └──────────────────┴──────────────────────┴──────────────────────┘")
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("  Pending registrations waiting for approval:"))
        for r in DEMO_REGISTRATIONS:
            reg = AccountRegistration.objects.filter(username=r["username"]).first()
            if reg:
                self.stdout.write(
                    f"    {reg.username:<20} ({reg.department}) — {reg.get_status_display()}"
                )
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("  Demo data setup complete.\n"))