# -*- coding: utf-8 -*-
# Generated by Django 1.11.12 on 2018-05-22 07:04
from __future__ import unicode_literals

from django.db import migrations

from action.models import Action


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

        action.set_content(action.get_content())


class Migration(migrations.Migration):
    dependencies = [
        ('action', '0022_auto_20180621_1708'),
    ]

    operations = [
        migrations.RunPython(update_content_and_columns),
    ]
