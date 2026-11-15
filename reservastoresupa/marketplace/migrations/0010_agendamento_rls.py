from django.db import migrations


def protect(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("ALTER TABLE marketplace_agendamento ENABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0009_agendamento")]
    operations = [migrations.RunPython(protect, migrations.RunPython.noop)]
