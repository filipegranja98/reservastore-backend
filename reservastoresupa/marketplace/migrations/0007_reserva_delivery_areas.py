from decimal import Decimal
from django.db import migrations

NAMES = ('Condomínio Acácia', 'Condomínio Canela', 'Condomínio Carvalho', 'Condomínio Cerejeira', 'Condomínio Ébano', 'Condomínio Eucalipto', 'Condomínio Ipê', 'Condomínio Jacarandá', 'Condomínio Jaqueira', 'Condomínio Jatobá', 'Condomínio Jequitibá', 'Condomínio Laranjeira', 'Condomínio Macieira', 'Condomínio Pau-Brasil')

def seed(apps, schema_editor):
    Loja = apps.get_model("lojas", "Loja")
    Area = apps.get_model("marketplace", "AreaEntrega")
    alias = schema_editor.connection.alias
    for shop in Loja.objects.using(alias).iterator():
        for name in NAMES:
            area, created = Area.objects.using(alias).get_or_create(
                loja_id=shop.pk, condominio_normalizado=" ".join(name.casefold().split()),
                defaults={"condominio":name,"taxa":Decimal("0.00"),"ativa":True})
            if not created and not area.ativa:
                Area.objects.using(alias).filter(pk=area.pk).update(ativa=True)

class Migration(migrations.Migration):
    dependencies = [("marketplace", "0006_pedido_modalidade_alter_pedido_status"), ("lojas", "0009_loja_permite_entrega_loja_permite_retirada")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
