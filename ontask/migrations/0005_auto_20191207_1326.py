# Generated by Django 2.2.8 on 2019-12-07 02:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ontask', '0004_auto_20191206_2039'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='scheduledoperation',
            name='periodic_task',
        ),
        migrations.AddField(
            model_name='scheduledoperation',
            name='task id',
            field=models.CharField(blank=True, max_length=1024, null=True, verbose_name='Task identifier'),
        ),
    ]
