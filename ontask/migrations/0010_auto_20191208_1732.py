# Generated by Django 2.2.8 on 2019-12-08 07:02

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('django_celery_beat', '0011_auto_20190508_0153'),
        ('ontask', '0009_auto_20191208_1729'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='scheduledoperation',
            name='task_uuid',
        ),
        migrations.AddField(
            model_name='scheduledoperation',
            name='task',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scheduled_operation', to='django_celery_beat.PeriodicTask'),
        ),
    ]
