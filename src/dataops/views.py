# -*- coding: utf-8 -*-


from builtins import object
from builtins import range
from builtins import str
from builtins import zip

import django_tables2 as tables
import pandas as pd
from celery.task.control import inspect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import redirect, render, reverse
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.cache import cache_page

import dataops.ops as ops
import dataops.pandas_db
from dataops import pandas_db
from dataops.forms import PluginInfoForm
from logs.models import Log
from ontask.permissions import is_instructor
from ontask.tasks import run_plugin
from workflow.ops import get_workflow
from .forms import RowForm, FIELD_PREFIX
from .models import PluginRegistry
from .plugin_manager import refresh_plugin_data, load_plugin


class PluginRegistryTable(tables.Table):
    """
    Table to render the list of plugins available for execution. The
    Operations column is inheriting from another class to centralise the
    customisation.
    """

    filename = tables.Column(verbose_name=_('Folder'))

    name = tables.Column(verbose_name=_('Name'))

    description_txt = tables.Column(verbose_name=_('Description'))

    last_exec = tables.DateTimeColumn(
        verbose_name=_('Last executed'),
        extra_context={''}
    )

    def __init__(self, *args, **kwargs):

        self.request = kwargs.get("request", None)

        super(PluginRegistryTable, self).__init__(*args, **kwargs)

    def render_name(self, record):
        if record.is_verified:
            return format_html(
                '<a href="{0}" ' +
                'data-toggle="tooltip" title="{1}">{2}',
                reverse('dataops:plugin_invoke', kwargs={'pk': record.id}),
                _('Execute the transformation'),
                record.name
            )

        return record.name

    def render_is_verified(self, record):
        if record.is_verified:
            return format_html('<span class="true">✔</span>')

        return render_to_string(
            'dataops/includes/partial_plugin_diagnose.html',
            context={'id': record.id},
            request=None
        )

    def render_last_exec(self, record):
        workflow = get_workflow(self.request)
        log_item = workflow.logs.filter(
            user=self.request.user,
            name=Log.PLUGIN_EXECUTE,
            payload__name=record.name
        ).order_by(F('created').desc()).first()
        if not log_item:
            return '--'
        return log_item.created

    class Meta(object):
        model = PluginRegistry

        fields = ('filename', 'name', 'description_txt', 'is_verified')

        sequence = ('filename', 'name', 'description_txt', 'is_verified',
                    'last_exec')

        attrs = {
            'class': 'table table-hover table-bordered shadow',
            'style': 'width: 100%;',
            'id': 'transform-table'
        }


@cache_page(60 * 15)
@user_passes_test(is_instructor)
def uploadmerge(request):
    # Get the workflow that is being used
    workflow = get_workflow(request)
    if not workflow:
        return redirect('home')

    return render(request,
                  'dataops/uploadmerge.html',
                  {'valuerange':
                       range(5) if workflow.has_table() else range(3)})


@user_passes_test(is_instructor)
def transform(request):
    # Get the workflow that is being used
    workflow = get_workflow(request)
    if not workflow:
        return redirect('home')

    # Traverse the plugin folder and refresh the db content.
    refresh_plugin_data(request, workflow)

    table = PluginRegistryTable(PluginRegistry.objects.all(),
                                orderable=False,
                                request=request)

    return render(request, 'dataops/transform.html', {'table': table})


@user_passes_test(is_instructor)
def diagnose(request, pk):
    """
    HTML request to show the diagnostics of a plugin that failed the
    verification tests.

    :param request: HTML request object
    :param pk: Primary key of the transform element
    :return:
    """

    # To include in the JSON response
    data = dict()

    # Action being used
    try:
        plugin = PluginRegistry.objects.get(id=pk)
    except ObjectDoesNotExist:
        data['form_is_valid'] = True
        data['html_redirect'] = reverse('dataops:transform')
        return JsonResponse(data)

    # Reload the plugin to get the messages stored in the right place.
    pinstance, msgs = load_plugin(plugin.filename)

    # If the new instance is now properly verified, simply redirect to the
    # transform page
    if pinstance:
        plugin.is_verified = True
        plugin.save()
        data['form_is_valid'] = True
        data['html_redirect'] = reverse('dataops:transform')

        return JsonResponse(data)

    # Get the diagnostics from the plugin and use it for rendering.
    data['html_form'] = render_to_string(
        'dataops/includes/partial_diagnostics.html',
        {'diagnostic_table': msgs},
        request=request)
    return JsonResponse(data)


@user_passes_test(is_instructor)
def row_update(request):
    """
    Receives a POST request to update a row in the data table
    :param request: Request object with all the data.
    :return:
    """

    # If there is no workflow object, go back to the index
    workflow = get_workflow(request)
    if not workflow:
        return redirect('home')

    # If the workflow has no data, something went wrong, go back to the
    # main dataops page
    if workflow.nrows == 0:
        return redirect('dataops:uploadmerge')

    # Get the pair key,value to fetch the row from the table
    update_key = request.GET.get('update_key', None)
    update_val = request.GET.get('update_val', None)

    if not update_key or not update_val:
        # Malformed request
        return render(request, 'error.html',
                      {'message': _('Unable to update table row')})

    # Get the rows from the table
    rows = pandas_db.execute_select_on_table(
        workflow.get_data_frame_table_name(),
        [update_key],
        [update_val],
        workflow.get_column_names()
    )

    row_form = RowForm(request.POST or None,
                       workflow=workflow,
                       initial_values=list(rows[0]))

    if request.method == 'GET' or not row_form.is_valid():
        return render(request,
                      'dataops/row_filter.html',
                      {'workflow': workflow,
                       'row_form': row_form,
                       'cancel_url': reverse('table:display')})

    # This is a valid POST request

    # Create the query to update the row
    set_fields = []
    set_values = []
    columns = workflow.get_columns()
    unique_names = [c.name for c in columns if c.is_key]
    unique_field = None
    unique_value = None
    log_payload = []
    for idx, col in enumerate(columns):
        value = row_form.cleaned_data[FIELD_PREFIX + '%s' % idx]
        set_fields.append(col.name)
        set_values.append(value)
        log_payload.append((col.name, str(value)))

        if not unique_field and col.name in unique_names:
            unique_field = col.name
            unique_value = value

    # If there is no unique key, something went wrong.
    if not unique_field:
        raise Exception(_('Key value not found when updating row'))

    pandas_db.update_row(workflow.get_data_frame_table_name(),
                         set_fields,
                         set_values,
                         [unique_field],
                         [unique_value])

    # Recompute all the values of the conditions in each of the actions
    for act in workflow.actions.all():
        act.update_n_rows_selected()

    # Log the event
    Log.objects.register(request.user,
                         Log.TABLEROW_UPDATE,
                         workflow,
                         {'id': workflow.id,
                          'name': workflow.name,
                          'new_values': log_payload})

    return redirect('table:display')


@user_passes_test(is_instructor)
def row_create(request):
    """
    Receives a POST request to create a new row in the data table
    :param request: Request object with all the data.
    :return:
    """

    # If there is no workflow object, go back to the index
    workflow = get_workflow(request)
    if not workflow:
        return redirect('home')

    # If the workflow has no data, the operation should not be allowed
    if workflow.nrows == 0:
        return redirect('dataops:uploadmerge')

    # Create the form
    form = RowForm(request.POST or None, workflow=workflow)

    if request.method == 'GET' or not form.is_valid():
        return render(request,
                      'dataops/row_create.html',
                      {'workflow': workflow,
                       'form': form,
                       'cancel_url': reverse('table:display')})

    # Create the query to update the row
    columns = workflow.get_columns()
    column_names = [c.name for c in columns]
    field_name = FIELD_PREFIX + '%s'
    row_vals = [form.cleaned_data[field_name % idx]
                for idx in range(len(columns))]

    # Load the existing df from the db
    df = pandas_db.load_from_db(workflow.get_data_frame_table_name())

    # Perform the row addition in the DF first
    # df2 = pd.DataFrame([[5, 6], [7, 8]], columns=list('AB'))
    # df.append(df2, ignore_index=True)
    new_row = pd.DataFrame([row_vals], columns=column_names)
    df = df.append(new_row, ignore_index=True)

    # Verify that the unique columns remain unique
    for ucol in [c for c in columns if c.is_key]:
        if not dataops.pandas_db.is_unique_column(df[ucol.name]):
            form.add_error(
                None,
                _('Repeated value in column {0}. It must be different '
                  'to maintain Key property').format(ucol.name)
            )
            return render(request,
                          'dataops/row_create.html',
                          {'workflow': workflow,
                           'form': form,
                           'cancel_url': reverse('table:display')})

    # Restore the dataframe to the DB
    ops.store_dataframe(df, workflow)

    # Recompute all the values of the conditions in each of the actions
    for act in workflow.actions.all():
        act.update_n_rows_selected()

    # Log the event
    log_payload = list(zip(column_names, [str(x) for x in row_vals]))
    Log.objects.register(request.user,
                         Log.TABLEROW_CREATE,
                         workflow,
                         {'id': workflow.id,
                          'name': workflow.name,
                          'new_values': log_payload})

    # Done. Back to the table view
    return redirect('table:display')


@user_passes_test(is_instructor)
def plugin_invoke(request, pk):
    """
    View provided as the first step to execute a plugin.
    :param request: HTTP request received
    :param pk: primary key of the plugin
    :return: Page offering to select the columns to invoke
    """

    # Verify that celery is running!
    celery_stats = None
    try:
        celery_stats = inspect().stats()
    except Exception:
        pass

    # If the stats are empty, celery is not running.
    if not celery_stats:
        messages.error(
            request,
            _('Unable to send emails due to a misconfiguration. '
              'Ask your system administrator to enable email queueing.'))
        return redirect(reverse('table:display'))

    # Get the workflow and the plugin information
    workflow = get_workflow(request)
    if not workflow:
        return redirect('home')
    try:
        plugin_info = PluginRegistry.objects.get(pk=pk)
    except PluginRegistry.DoesNotExist:
        return redirect('home')

    plugin_instance, msgs = load_plugin(plugin_info.filename)
    if plugin_instance is None:
        messages.error(
            request,
            _('Unable to instantiate plugin "{0}"').format(plugin_info.name)
        )
        return redirect('dataops:transform')

    if len(plugin_instance.input_column_names) > 0:
        # The plug in works with a fixed set of columns
        cnames = workflow.columns.all().values_list('name', flat=True)
        if not set(plugin_instance.input_column_names) < set(cnames):
            # The set of columns are not part of the workflow
            messages.error(
                request,
                _('Workflow does not have the correct columns to run this '
                  'plugin')
            )
            return redirect('dataops:transform')

    # create the form to select the columns and the corresponding dictionary
    form = PluginInfoForm(request.POST or None,
                          workflow=workflow,
                          plugin_instance=plugin_instance)

    # Set the basic elements in the context
    context = {
        'form': form,
        'output_column_fields': [x for x in list(form)
                                 if x.name.startswith(FIELD_PREFIX + 'output')],
        'parameters': [x for x in list(form)
                       if x.name.startswith(FIELD_PREFIX + 'parameter')],
        'pinstance': plugin_instance,
        'id': workflow.id
    }

    # If it is a GET request or non valid, render the form.
    if request.method == 'GET' or not form.is_valid():
        return render(request,
                      'dataops/plugin_info_for_run.html',
                      context)

    # POST is correct proceed with execution

    # Prepare the data to invoke the plugin, namely:
    # input_column_names (list)
    # output_column_names (list)
    # merge_key (string)
    # parameters (dictionary)

    # Take the list of inputs from the form if empty list is given.
    input_column_names = []
    if not plugin_instance.input_column_names:
        input_column_names = [c.name for c in form.cleaned_data['columns']]

    output_column_names = []
    if plugin_instance.output_column_names:
        # Process the output columns
        for idx, __ in enumerate(plugin_instance.output_column_names):
            new_cname = form.cleaned_data[FIELD_PREFIX + 'output_%s' % idx]
            output_column_names.append(new_cname)
    else:
        # Plugin instance has an empty set of output files, clone the input
        output_column_names = input_column_names[:]

    suffix = form.cleaned_data['out_column_suffix']
    if suffix:
        # A suffix has been provided, add it to the list of outputs
        output_column_names = [x + suffix for x in output_column_names]

    # Pack the parameters
    parameters = {}
    for idx, tpl in enumerate(plugin_instance.parameters):
        parameters[tpl[0]] = form.cleaned_data[
            FIELD_PREFIX + 'parameter_%s' % idx
            ]

    # Log the event with the status "preparing invocation"
    log_item = Log.objects.register(request.user,
                                    Log.PLUGIN_EXECUTE,
                                    workflow,
                                    {'id': plugin_info.id,
                                     'name': plugin_info.name,
                                     'input_column_names': input_column_names,
                                     'output_column_names': output_column_names,
                                     'parameters': parameters,
                                     'status': 'preparing execution'})

    # Call the plugin execution
    run_plugin(request.user.id,
    # run_plugin.delay(request.user.id,
                     workflow.id,
                     pk,
                     input_column_names,
                     output_column_names,
                     suffix,
                     form.cleaned_data['merge_key'],
                     parameters,
                     log_item.id)

    # Successful processing.
    return render(request,
                  'dataops/plugin_execution_report.html',
                  {'log_id': log_item.id})
