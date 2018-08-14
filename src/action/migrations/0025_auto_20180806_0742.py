# -*- coding: utf-8 -*-
# Generated by Django 1.11.14 on 2018-08-05 22:12
from __future__ import unicode_literals

from django.db import migrations


def update_content_and_columns(apps, schema_editor):
    """
    Traverse all actions and update the content.

    :param apps:
    :param schema_editor:
    :return:
    """
    if schema_editor.connection.alias != 'default':
        return

    Action = apps.get_model('action', 'Action')
    for action in Action.objects.all():
        if not action.is_out:
            continue
   
  #     action.set_content(action.get_content())


class Migration(migrations.Migration):

    dependencies = [
        ('action', '0024_auto_20180630_1418'),
    ]

    operations = [
        migrations.RunPython(update_content_and_columns),
    ]