from django.db import migrations


def create_default_user(apps, schema_editor):
    """首次启动时创建默认 viewer 用户"""
    User = apps.get_model("accounts", "User")
    if not User.objects.filter(username="user").exists():
        User.objects.create_user(
            username="user",
            password="user",
            role="viewer",
            must_change_password=True,
        )


def remove_default_user(apps, schema_editor):
    """回滚时删除默认用户"""
    User = apps.get_model("accounts", "User")
    User.objects.filter(username="user").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_user, remove_default_user),
    ]
