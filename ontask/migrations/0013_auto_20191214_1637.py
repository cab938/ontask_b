# Generated by Django 2.2.8 on 2019-12-14 06:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ontask', '0012_auto_20191208_2140'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scheduledoperation',
            name='operation_type',
            field=models.CharField(choices=[('action_run_email', 'Execute scheduled email action'), ('action_run_canvas_email', 'Execute scheduled canvas email action'), ('action_runjson', 'Execute scheduled JSON action'), ('action_run_list', 'Execute scheduled JSON list action'), ('action_run_send_list', 'Execute scheduled send list action'), ('workflow_increase_track_count', 'Increase workflow track count.'), ('plugin_execute', 'Plugin executed'), ('workflow_update_lusers', 'Update list of workflow users')], max_length=1024),
        ),
    ]
