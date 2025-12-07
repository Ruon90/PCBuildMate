from django.core.management.base import BaseCommand, CommandError

from django.contrib.auth import get_user_model

from calculator.models import UserBuild


class Command(BaseCommand):
    help = (
        "Clear saved UserBuilds. Use --all to delete all builds or --user <username> "
        "to delete builds for a specific user. Use --yes to skip confirmation."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            dest="all",
            help="Delete all UserBuilds",
        )
        parser.add_argument(
            "--user",
            type=str,
            dest="username",
            help="Delete builds for username",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            dest="yes",
            help="Confirm without prompt",
        )

    def handle(self, *args, **options):
        if not options.get("all") and not options.get("username"):
            raise CommandError("Provide --all or --user <username>")

        qs = UserBuild.objects.none()

        if options.get("all"):
            qs = UserBuild.objects.all()
        else:
            User = get_user_model()
            try:
                user = User.objects.get(username=options.get("username"))
            except User.DoesNotExist:
                raise CommandError(f'User "{options.get("username")}" does not exist')
            qs = UserBuild.objects.filter(user=user)

        count = qs.count()
        if count == 0:
            self.stdout.write("No builds to delete.")
            return

        if not options.get("yes"):
            confirm = input(f"About to delete {count} build(s). Type YES to confirm: ")
            if confirm != "YES":
                self.stdout.write("Aborted.")
                return

        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} build(s)."))
