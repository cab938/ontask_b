# -*- coding: utf-8 -*-


from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _


class SchedulerConfig(AppConfig):
    name = 'ontask.scheduler'
    verbose_name = _('Task Scheduler')