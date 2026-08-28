"""import_routine command — convert routine.json to a TaskChain (TD-110 Phase 3, TD-113)."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from gamestate.models import GameProfile
from pipeline.services import RoutineImportError, convert_routine_to_chain


class Command(BaseCommand):
    help = (
        'Import a GameProfile\'s routine.json and convert it to a TaskChain '
        'with PIPELINE nodes (TD-110 Phase 3 + TD-113). The routine file '
        'path is read from GameProfile.routine_path — no path argument. '
        'Idempotent: re-running on the same game_profile replaces existing '
        'chain nodes.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--game-profile',
            type=int,
            required=True,
            help='GameProfile ID to read routine_path from and bind the TaskChain to',
        )
        parser.add_argument(
            '--user',
            type=str,
            default=None,
            help='Username to record as created_by (optional)',
        )

    def handle(self, *args, **options):
        game_profile_id = options['game_profile']
        username = options.get('user')

        try:
            game_profile = GameProfile.objects.get(pk=game_profile_id)
        except GameProfile.DoesNotExist as exc:
            raise CommandError(
                f'GameProfile id={game_profile_id} not found'
            ) from exc

        user = None
        if username:
            user_model = get_user_model()
            try:
                user = user_model.objects.get(username=username)
            except user_model.DoesNotExist as exc:
                raise CommandError(f'User "{username}" not found') from exc

        try:
            chain = convert_routine_to_chain(
                game_profile=game_profile,
                user=user,
            )
        except RoutineImportError as e:
            raise CommandError(str(e)) from e

        node_count = chain.chain_nodes.count()
        self.stdout.write(self.style.SUCCESS(
            f'Successfully imported routine [{game_profile.routine_path}] → '
            f'TaskChain [{chain.name}] (id={chain.id}, '
            f'game_profile={game_profile.game_name}, '
            f'nodes={node_count}, is_default={chain.is_default})'
        ))
