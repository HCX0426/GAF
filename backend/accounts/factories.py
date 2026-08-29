"""factory_boy factories for the accounts app."""

import factory

from accounts.models import GameAccount, User
from gamestate.models import GameProfile


class UserFactory(factory.django.DjangoModelFactory):
    """Factory for generating test users."""

    class Meta:
        model = User
        django_get_or_create = ("username",)
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = factory.Sequence(lambda n: f"First{n}")
    last_name = factory.Sequence(lambda n: f"Last{n}")
    role = User.Role.VIEWER
    must_change_password = False
    password = factory.PostGenerationMethodCall("set_password", "testpass123")


class AdminUserFactory(UserFactory):
    """Convenience factory for admin users."""

    role = User.Role.ADMIN


class OperatorUserFactory(UserFactory):
    """Convenience factory for operator users."""

    role = User.Role.OPERATOR


class GameAccountFactory(factory.django.DjangoModelFactory):
    """Factory for generating test game accounts."""

    class Meta:
        model = GameAccount
        skip_postgeneration_save = True

    owner = factory.SubFactory(UserFactory)
    username = factory.Sequence(lambda n: f"game_user_{n}")
    # P3: game_name 字段已退役 — 唯一游戏维度 = game_profile (profile 名由 username 派生, 避免中间属性污染 kwargs)
    game_profile = factory.LazyAttribute(
        lambda o: GameProfile.objects.get_or_create(game_name=f"Game {o.username}")[0]
    )
    encrypted_password = factory.Sequence(lambda n: f"encrypted_{n}")
    login_method = "password"
    server_region = "CN"
