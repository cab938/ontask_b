# -*- coding: utf-8 -*-

"""Classes and functions to show connections to regular users."""
from typing import Optional

from django.contrib.auth.decorators import user_passes_test
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import ugettext as _

from ontask import models
from ontask.core import get_workflow, is_instructor
from ontask.dataops import services


@user_passes_test(is_instructor)
@get_workflow()
def sql_connection_index(
    request: HttpRequest,
    workflow: Optional[models.Workflow] = None,
) -> HttpResponse:
    """Render a page showing a table with the available SQL connections.

    :param request: HTML request
    :param workflow: Current workflow being used
    :return: HTML response
    """
    del workflow
    table = services.sql_connection_select_table('dataops:sqlupload_start')
    return render(
        request,
        'dataops/connections.html',
        {'table': table, 'is_sql': True, 'title': _('SQL Connections')})


@user_passes_test(is_instructor)
@get_workflow()
def athena_connection_instructor_index(
    request: HttpRequest,
    workflow: Optional[models.Workflow],
) -> HttpResponse:
    """Render a page showing a table with the available Athena connections.

    :param request: HTML request
    :param workflow: Current workflow being used
    :return: HTML response
    """
    del workflow
    return render(
        request,
        'dataops/connections.html',
        {
            'table': services.create_athena_connection_runtable(),
            'is_athena': True,
            'title': _('Athena Connections')})
