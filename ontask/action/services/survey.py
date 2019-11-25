# -*- coding: utf-8 -*-

"""Functions to process the survey run request."""

from typing import List, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from django.contrib import messages
import django_tables2 as tables
from django import http
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import ugettext_lazy as _

from ontask import models
from ontask.action.services.edit_manager import ActionEditManager
from ontask.action.services.manager import ActionRunManager
from ontask.action.services.manager_factory import action_process_factory
from ontask.core import DataTablesServerSidePaging, OperationsColumn
from ontask.dataops.sql import search_table
from ontask.visualizations.plotly import PlotlyHandler


class ColumnSelectedTable(tables.Table):
    """Table to render the columns selected for a given action in."""

    column__name = tables.Column(verbose_name=_('Name'))  # noqa: Z116
    column__description_text = tables.Column(  # noqa: Z116
        verbose_name=_('Description (shown to learners)'),
        default='',
    )
    changes_allowed = tables.BooleanColumn(
        verbose_name=_('Allow change?'),
        default=True)
    condition = tables.Column(  # noqa: Z116
        verbose_name=_('Condition'),
        empty_values=[-1],
    )

    # Template to render the extra column created dynamically
    ops_template = 'action/includes/partial_column_selected_operations.html'

    def __init__(self, *args, **kwargs):
        """Store the condition list."""
        self.condition_list = kwargs.pop('condition_list')
        super().__init__(*args, **kwargs)

    def render_column__name(self, record):  # noqa: Z116
        """Render as a link."""
        return format_html(
            '<a href="#questions" data-toggle="tooltip"'
            + ' class="js-workflow-question-edit" data-url="{0}"'
            + ' title="{1}">{2}</a>',
            reverse(
                'workflow:question_edit',
                kwargs={'pk': record['column__id']}),
            _('Edit the question'),
            record['column__name'],
        )

    def render_condition(self, record):
        """Render with template to select condition."""
        return render_to_string(
            'action/includes/partial_column_selected_condition.html',
            {
                'id': record['id'],
                'cond_selected': record['condition__name'],
                'conditions': self.condition_list,
            })

    def render_changes_allowed(self, record):
        """Render the boolean to allow changes."""
        return render_to_string(
            'action/includes/partial_question_changes_allowed.html',
            {
                'id': record['id'],
                'changes_allowed': record['changes_allowed'],
            })

    class Meta(object):
        """Define fields, sequence, attrs and row attrs."""

        fields = (
            'column__id',
            'column__name',
            'column__description_text',
            'changes_allowed',
            'condition',
            'operations')

        sequence = (
            'column__name',
            'column__description_text',
            'changes_allowed',
            'condition',
            'operations')

        attrs = {
            'class': 'table table-hover table-bordered',
            'style': 'width: 100%;',
            'id': 'column-selected-table',
        }

        row_attrs = {
            'class': lambda record: 'danger' if not record[
                'column__description_text'
            ] else '',
        }


def _create_link_to_survey_row(
    action_id: int,
    key_name: str,
    key_value,
) -> str:
    """Create the <a> Link element pointing to a survey row form.

    :param action_id: Action id with the survey information
    :param key_name:
    :param key_value:
    :return: HTML code with the <a> element
    """
    dst_url = reverse('action:run_survey_row', kwargs={'pk': action_id})
    url_parts = list(urlparse(dst_url))
    query = dict(parse_qs(url_parts[4]))
    query.update({'uatn': key_name, 'uatv': key_value})
    url_parts[4] = urlencode(query)

    return '<a href="{0}">{1}</a>'.format(
        urlunparse(url_parts), key_value,
    )


def _create_initial_qs(
    table_name,
    filter_formula,
    columns,
    dt_page,
):
    """Obtain the iniital QuerySet to select the right page.

    :param table_name: Workflow to get the table name
    :param filter_formula:
    :param columns: Workflow columns
    :param dt_page: datatables paging information
    :return: query set
    """
    # See if an order column has been given.
    order_col_name = None
    if dt_page.order_col is not None:
        order_col_name = columns[dt_page.order_col].name

    # Get the query set (including the filter in the action)
    qs = search_table(
        table_name,
        dt_page.search_value,
        columns_to_search=[col.name for col in columns],
        filter_formula=filter_formula,
        order_col_name=order_col_name,
        order_asc=dt_page.order_dir == 'asc',
    )

    return qs


def _create_table_qsdata(
    action_id: int,
    qs,
    dt_page: DataTablesServerSidePaging,
    columns: List[models.Column],
    key_idx: int,
) -> List:
    """Select the subset of the qs to be sent as qs data to the JSON request.

    :param action_id: Action id being processed
    :param qs: Query set from where to extract the data
    :param dt_page: Object with DataTable parameters to process the page
    :param columns: List of column
    :param key_idx: Index of the key column
    :return: Query set to return to DataTable JavaScript
    """
    final_qs = []
    item_count = 0
    for row in qs[dt_page.start:dt_page.start + dt_page.length]:
        item_count += 1

        # Render the first element (the key) as the link to the page to update
        # the content.
        row = list(row)
        row[key_idx] = _create_link_to_survey_row(
            action_id,
            columns[key_idx].name,
            row[key_idx],
        )

        # Add the row for rendering
        final_qs.append(row)

        if item_count == dt_page.length:
            # We reached the number or requested elements, abandon loop
            break

    return final_qs


def create_survey_table(
    workflow: models.Workflow,
    action: models.Action,
    dt_page: DataTablesServerSidePaging,
) -> http.JsonResponse:
    """Create the table with the survey entries for instructor.

    :param workflow: Workflow being processed
    :param action: Action representing the survey
    :param dt_page: Data tables server side paging object
    :return : JSon respnse
    """
    columns = [ccpair.column for ccpair in action.column_condition_pair.all()]
    query_set = _create_initial_qs(
        workflow.get_data_frame_table_name(),
        action.get_filter_formula(),
        columns,
        dt_page,
    )

    filtered = len(query_set)

    # Get the subset of the qs to show in the table
    query_set = _create_table_qsdata(
        action.id,
        query_set,
        dt_page,
        columns,
        next(idx for idx, col in enumerate(columns) if col.is_key),
    )

    return http.JsonResponse({
        'draw': dt_page.draw,
        'recordsTotal': workflow.nrows,
        'recordsFiltered': filtered,
        'data': query_set,
    })


class ActionManagerSurvey(ActionEditManager, ActionRunManager):
    """Class to serve running an email action."""

    def extend_edit_context(
        self,
        workflow: models.Workflow,
        action: models.Action,
        context: Dict,
    ) -> Optional[str]:
        """Get the context dictionary to render the GET request.

        :param workflow: Workflow being used
        :param action: Action being used
        :param context: Initial dictionary to extend
        :return: An error string or None if everything was correct.
        """
        self.add_conditions(action, context)
        self.add_conditions_to_clone(action, context)
        self.add_columns_show_stats(action, context)

        # All tuples (action, column, condition) to consider
        tuples = action.column_condition_pair.all()

        context.update({
            'column_selected_table': ColumnSelectedTable(
                tuples.filter(column__is_key=False).values(
                    'id',
                    'column__id',
                    'column__name',
                    'column__description_text',
                    'condition__name',
                    'changes_allowed'),
                orderable=False,
                extra_columns=[(
                    'operations',
                    OperationsColumn(
                        verbose_name='',
                        template_file=ColumnSelectedTable.ops_template,
                        template_context=lambda record: {
                            'id': record['column__id'],
                            'aid': action.id}),
                )],
                condition_list=context['conditions'],
            ),
            'columns_to_insert': workflow.columns.exclude(
                column_condition_pair__action=action,
            ).exclude(
                is_key=True,
            ).distinct().order_by('position'),
            'any_empty_description': tuples.filter(
                column__description_text='',
                column__is_key=False,
            ).exists(),
            'key_columns': workflow.get_unique_columns(),
            'key_selected': tuples.filter(column__is_key=True).first(),
            'has_no_key': tuples.filter(column__is_key=False).exists(),
        })

        return None

    def process_edit_request(
        self,
        request: http.HttpRequest,
        workflow: models.Workflow,
        action: models.Action) -> http.HttpResponse:
        """Process the action edit request."""

        context = self.get_render_context(action)
        extend_status = self.extend_edit_context(workflow, action, context)
        if extend_status:
            messages.error(request, extend_status)
            return redirect(reverse('action:index'))

        return render(request, self.edit_template, context)

    def process_run_request(
        self,
        operation_type: str,
        request: http.HttpRequest,
        action: models.Action,
        prev_url: str,
    ) -> http.HttpResponse:
        """Process a GET request."""
        # Render template with active columns.
        return render(
            request,
            self.run_template,
            {
                'columns': [
                    cc_pair.column
                    for cc_pair in action.column_condition_pair.all()
                    if cc_pair.column.is_active],
                'action': action})


action_process_factory.register_producer(
    models.Action.SURVEY,
    ActionManagerSurvey(
        edit_template='action/edit_in.html',
        run_template='action/run_survey.html',
        log_event=models.Log.ACTION_SURVEY_INPUT))
