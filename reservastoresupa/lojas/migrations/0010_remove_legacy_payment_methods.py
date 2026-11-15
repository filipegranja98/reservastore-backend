from django.db import migrations

def remove_methods(apps, schema_editor):
    Loja=apps.get_model("lojas","Loja")
    for shop in Loja.objects.using(schema_editor.connection.alias).all():
        methods=[method for method in shop.meios_pagamento if method not in {"cartao_na_entrega","transferencia"}]
        if methods != shop.meios_pagamento:
            shop.meios_pagamento=methods
            shop.save(update_fields=["meios_pagamento"])

class Migration(migrations.Migration):
    dependencies=[("lojas","0009_loja_permite_entrega_loja_permite_retirada")]
    operations=[migrations.RunPython(remove_methods,migrations.RunPython.noop)]
