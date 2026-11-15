from django.db import migrations, models


def mark_services(apps, schema_editor):
    TipoLoja = apps.get_model("lojas", "TipoLoja")
    for item in TipoLoja.objects.using(schema_editor.connection.alias).all():
        if item.nome.strip().casefold() in ("serviços", "servicos", "serviço", "servico"):
            item.modo_catalogo = "servicos"
            item.save(update_fields=["modo_catalogo"])


class Migration(migrations.Migration):
    dependencies = [("lojas", "0007_loja_email_contato_alter_loja_whatsapp")]
    operations = [
        migrations.AddField(model_name="tipoloja", name="modo_catalogo", field=models.CharField(choices=[("produtos", "Produtos"), ("servicos", "Serviços")], default="produtos", max_length=10)),
        migrations.RunPython(mark_services, migrations.RunPython.noop),
    ]
