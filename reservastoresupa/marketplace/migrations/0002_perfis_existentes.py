from django.conf import settings
from django.db import migrations


def criar_perfis(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Perfil = apps.get_model("marketplace", "Perfil")
    Loja = apps.get_model("lojas", "Loja")
    db = schema_editor.connection.alias
    lojistas = set(Loja.objects.using(db).values_list("dono_id", flat=True))
    for user_id in User.objects.using(db).values_list("pk", flat=True).iterator():
        Perfil.objects.using(db).get_or_create(user_id=user_id, defaults={"papel": "lojista" if user_id in lojistas else "cliente"})


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0001_initial")]
    operations = [migrations.RunPython(criar_perfis, migrations.RunPython.noop)]
