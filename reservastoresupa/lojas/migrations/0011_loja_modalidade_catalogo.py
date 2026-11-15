from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("lojas", "0010_remove_legacy_payment_methods")]
    operations = [migrations.AddField(
        model_name="loja", name="modalidade_catalogo",
        field=models.CharField(max_length=10, blank=True, default="",
            choices=[("produtos", "Loja de produtos"), ("servicos", "Prestador de serviços")],
            verbose_name="Perfil da loja", help_text="Se não selecionado, segue o tipo de loja já cadastrado."),
    )]
