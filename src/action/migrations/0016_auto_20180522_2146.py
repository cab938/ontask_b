# -*- coding: utf-8 -*-
# Generated by Django 1.11.12 on 2018-05-22 12:16
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('action', '0015_condition_n_rows_selected_update'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='condition',
            options={},
        ),
        migrations.AlterUniqueTogether(
            name='condition',
            unique_together=set([]),
        ),
    ]