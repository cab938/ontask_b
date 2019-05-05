# -*- coding: utf-8 -*-

"""Functions for Condition CRUD."""
from typing import Optional

from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, reverse
from django.template.loader import render_to_string
from django.utils.html import escape
from django.utils.translation import ugettext_lazy as _
from django.views import generic

from action.forms import ConditionForm, FilterForm
from action.models import Action, Condition
from dataops.formula_evaluation import (
    NodeEvaluation, evaluate_formula, get_variables,
)
from logs.models import Log
from ontask.decorators import get_workflow
from ontask.permissions import UserIsInstructor, is_instructor
from workflow.models import Workflow


def save_condition_form(
    request: HttpRequest,
    workflow: Workflow,
    form,
    template_name: str,
    action: Action,
    condition: Optional[Condition],
    is_filter: bool,
) -> JsonResponse:
    """
    Process the AJAX form to create and update conditions and filters.

    :param request: HTTP request

    :param workflow: workflow object where the action/condition is inserted

    :param form: Form being used to ask for the fields

    :param template_name: Template being used to render the form

    :param action: The action to which the condition is attached to

    :param condition: Condition object being manipulated or None if creating

    :param is_filter: The condition is a filter

    :return: JSON response
    """
    # Ajax response
    resp_data = {}

    # The condition is new if no value is given
    is_new = condition is None

    if is_new:
        condition_id = -1
    else:
        condition_id = condition.id

    # Context for rendering
    context = {
        'form': form,
        'action_id': action.id,
        'condition_id': condition_id,
        'add': is_new}

    # If the method is GET or the form is not valid, re-render the page.
    if request.method == 'GET' or not form.is_valid():
        resp_data['html_form'] = render_to_string(
            template_name,
            context,
            request=request)
        return JsonResponse(resp_data)

    # If the request has the 'action_content' field, update the action
    action_content = request.POST.get('action_content', None)
    if action_content:
        action.set_text_content(action_content)

    # Reset the counter of rows with all conditions false
    action.rows_all_false = None
    action.save()

    if is_filter:
        # Process the filter form
        # If this is a create filter operation, but the action has one,
        # flag the error
        if is_new and action.get_filter():
            # Should not happen. Go back to editing the action
            resp_data['html_redirect'] = ''
            return JsonResponse(resp_data)
    else:
        # Verify that the condition name does not exist yet (Uniqueness FIX)
        qs = action.conditions.filter(
            name=form.cleaned_data['name'],
            is_filter=False)
        if (is_new and qs.exists()) or \
            (not is_new and qs.filter(~Q(id=condition_id)).exists()):
            form.add_error(
                'name',
                _('A condition with that name already exists in this action'),
            )
            resp_data['html_form'] = render_to_string(
                template_name,
                context,
                request=request)
            return JsonResponse(resp_data)
        # New condition name does not collide with column name
        if form.cleaned_data['name'] in workflow.get_column_names():
            form.add_error(
                'name',
                _('A column name with that name already exists.'),
            )
            context = {
                'form': form,
                'action_id': action.id,
                'condition_id': condition_id,
                'add': is_new}
            resp_data['html_form'] = render_to_string(
                template_name,
                context,
                request=request)
            return JsonResponse(resp_data)

        # New condition name does not collide with attribute names
        if form.cleaned_data['name'] in list(workflow.attributes.keys()):
            form.add_error(
                'name',
                _('The workflow has an attribute with this name.'),
            )
            context = {
                'form': form,
                'action_id': action.id,
                'condition_id': condition_id,
                'add': is_new}
            resp_data['html_form'] = render_to_string(
                template_name,
                context,
                request=request)
            return JsonResponse(resp_data)

        # If condition name has changed, rename appearances in the content
        # field of the action.
        if form.old_name and 'name' in form.changed_data:
            # Performing string substitution in the content and saving
            # TODO: Review!
            replacing = '{{% if {0} %}}'
            action.text_content = action.text_content.replace(
                escape(replacing.format(form.old_name)),
                escape(replacing.format(condition.name)))
            action.save()

    # Proceed to update the DB
    if is_new:
        # Get the condition from the form, but don't commit as there are
        # changes pending.
        condition = form.save(commit=False)
        condition.action = action
        condition.is_filter = is_filter
        condition.save()
    else:
        condition = form.save()

    # Update the columns field
    condition.columns.set(workflow.columns.filter(
        name__in=get_variables(condition.formula),
    ))

    # Update the condition
    condition.save()

    if condition.is_filter:
        # This update must propagate to the rest of conditions
        condition.action.update_n_rows_selected()
        condition.refresh_from_db(fields='n_rows_selected')
    else:
        # Update the number of rows selected in the condition
        condition.update_n_rows_selected()

    # Log the event
    if is_new:
        if is_filter:
            log_type = Log.FILTER_CREATE
        else:
            log_type = Log.CONDITION_CREATE
    else:
        if is_filter:
            log_type = Log.FILTER_UPDATE
        else:
            log_type = Log.CONDITION_UPDATE

    # Log the event
    Log.objects.register(
        request.user,
        log_type,
        workflow,
        {
            'id': condition.id,
            'name': condition.name,
            'selected_rows': condition.n_rows_selected,
            'formula': evaluate_formula(
                condition.formula, NodeEvaluation.EVAL_TXT),
        })

    resp_data['html_redirect'] = ''
    return JsonResponse(resp_data)


class FilterCreateView(UserIsInstructor, generic.TemplateView):
    """Process AJAX request to create a filter through AJAX calls.

    It receives the action IDwhere the condition needs to be connected.
    """

    form_class = FilterForm

    template_name = 'action/includes/partial_filter_addedit.html'

    def get_context_data(self, **kwargs):
        """Add a flag to the context."""
        context = super().get_context_data(**kwargs)
        context['add'] = True
        return context

    def get(self, request, *args, **kwargs):
        """Process GET request to create a filter."""
        workflow = get_workflow(
            request,
            prefetch_related=['actions', 'columns'])
        if not workflow:
            return redirect('home')

        # Get the action that is being used
        action = workflow.actions.filter(
            pk=kwargs['pk'],
        ).filter(
            Q(workflow__user=request.user) | Q(workflow__shared=request.user),
        ).distinct().first()
        if not action:
            return redirect('home')

        form = self.form_class()
        return save_condition_form(
            request,
            workflow,
            form,
            self.template_name,
            action,
            None,  # no current condition object
            True)  # Is Filter

    def post(self, request, *args, **kwargs):
        """Process POST request to  create a filter."""
        workflow = get_workflow(
            request,
            prefetch_related=['actions', 'columns'])
        if not workflow:
            return redirect('home')

        # Get the action that is being used
        action = workflow.actions.filter(
            pk=kwargs['pk'],
        ).filter(
            Q(workflow__user=request.user) | Q(workflow__shared=request.user),
        ).first()
        if not action:
            return redirect('home')

        form = self.form_class(request.POST)
        return save_condition_form(
            request,
            workflow,
            form,
            self.template_name,
            action,
            None,  # No current condition object
            True)  # Is Filter


@user_passes_test(is_instructor)
def edit_filter(request: HttpRequest, pk: int) -> JsonResponse:
    """Edit the filter of an action through AJAX.

    :param request: HTTP request

    :param pk: condition ID

    :return: AJAX response
    """
    workflow = get_workflow(request, prefetch_related='columns')
    if not workflow:
        return JsonResponse({'html_redirect': reverse('home')})

    # Get the filter
    cond_filter = Condition.objects.filter(
        pk=pk,
    ).filter(
        Q(action__workflow__user=request.user)
        | Q(action__workflow__shared=request.user),
        action__workflow=workflow,
        is_filter=True,
    ).select_related('action').first()

    if not cond_filter:
        return redirect('home')

    # Create the filter and populate with existing data
    form = FilterForm(request.POST or None, instance=cond_filter)

    # Render the form with the Condition information
    return save_condition_form(
        request,
        workflow,
        form,
        'action/includes/partial_filter_addedit.html',
        cond_filter.action,
        cond_filter,  # Condition object
        True)  # It is a filter


@user_passes_test(is_instructor)
def delete_filter(request: HttpRequest, pk: int) -> JsonResponse:
    """Handle the AJAX request to delete a filter.

    :param request: AJAX request

    :param pk: Filter ID

    :return: AJAX response
    """
    workflow = get_workflow(request, prefetch_related='columns')
    if not workflow:
        return JsonResponse({'html_redirect': reverse('home')})

    # Get the filter
    cond_filter = Condition.objects.filter(
        pk=pk,
    ).filter(
        Q(action__workflow__user=request.user)
        | Q(action__workflow__shared=request.user),
        action__workflow=workflow,
        is_filter=True,
    ).select_related('action').first()

    if not cond_filter:
        return redirect('home')

    resp_data = {}

    if request.method == 'GET':
        resp_data['html_form'] = render_to_string(
            'action/includes/partial_filter_delete.html',
            {'id': cond_filter.id},
            request=request,
        )

        return JsonResponse(resp_data)

    # If the request has 'action_content', update the action
    action_content = request.POST.get('action_content', None)
    if action_content:
        cond_filter.action.set_text_content(action_content)
        cond_filter.action.save()

    # Log the event
    formula, fields = evaluate_formula(
        cond_filter.formula, NodeEvaluation.EVAL_SQL)

    Log.objects.register(
        request.user,
        Log.FILTER_DELETE,
        cond_filter.action.workflow,
        {
            'id': cond_filter.id,
            'name': cond_filter.name,
            'selected_rows': cond_filter.n_rows_selected,
            'formula': formula,
            'formula_fields': fields,
        },
    )

    # Get the action object for further processing
    action = cond_filter.action

    # Perform the delete operation
    cond_filter.delete()

    # Number of selected rows now needs to be updated in all remaining
    # conditions
    action.update_n_rows_selected()

    return JsonResponse({'html_redirect': ''})


class ConditionCreateView(UserIsInstructor, generic.TemplateView):
    """Handle AJAX requests to create a non-filter condition."""

    form_class = ConditionForm

    template_name = 'action/includes/partial_condition_addedit.html'

    def get(self, request, *args, **kwargs):
        """Process the GET request when creating a condition."""
        # Get the workflow
        workflow = get_workflow(request, prefetch_related='actions')
        if not workflow:
            return redirect('home')

        # Get the action that is being used
        action = workflow.actions.filter(
            pk=kwargs['pk'],
        ).filter(
            Q(workflow__user=request.user) | Q(workflow__shared=request.user),
        ).first()
        if not action:
            return redirect('home')

        form = self.form_class()
        return save_condition_form(
            request,
            workflow,
            form,
            self.template_name,
            action,
            None,
            False)  # Is it a filter?

    def post(self, request, *args, **kwargs):
        """Process the POST request when creating a condition."""
        # Get the workflow
        workflow = get_workflow(request, prefetch_related='actions')
        if not workflow:
            return redirect('home')

        # Get the action that is being used
        action = workflow.actions.filter(
            pk=kwargs['pk'],
        ).filter(
            Q(workflow__user=request.user) | Q(workflow__shared=request.user),
        ).first()
        if not action:
            return redirect('home')

        form = self.form_class(request.POST)

        return save_condition_form(
            request,
            workflow,
            form,
            self.template_name,
            action,
            None,
            False)


@user_passes_test(is_instructor)
def edit_condition(request: HttpRequest, pk: int) -> JsonResponse:
    """Handle the AJAX request to edit a condition.

    :param request: AJAX request

    :param pk: Condition ID

    :return: AJAX reponse
    """
    # Get the workflow
    workflow = get_workflow(request, prefetch_related='columns')
    if not workflow:
        return JsonResponse({'html_redirect': reverse('home')})

    # Get the condition
    condition = Condition.objects.filter(
        pk=pk,
    ).filter(
        Q(action__workflow__user=request.user)
        | Q(action__workflow__shared=request.user),
        is_filter=False,
        action__workflow=workflow,
    ).select_related('action').first()

    if not condition:
        return JsonResponse({'html_redirect': reverse('home')})

    form = ConditionForm(request.POST or None, instance=condition)

    # Render the form with the Condition information
    return save_condition_form(
        request,
        workflow,
        form,
        'action/includes/partial_condition_addedit.html',
        condition.action,
        condition,
        False)


@user_passes_test(is_instructor)
def delete_condition(request: HttpRequest, pk: int) -> JsonResponse:
    """Handle the AJAX request to delete a condition.

    :param request: HTTP request

    :param pk: condition or filter id

    :return: AJAX response to render
    """
    workflow = get_workflow(request, prefetch_related='columns')
    if not workflow:
        return JsonResponse({'html_redirect': reverse('home')})

    # Get the condition
    condition = Condition.objects.filter(
        pk=pk,
    ).filter(
        Q(action__workflow__user=request.user)
        | Q(action__workflow__shared=request.user),
        action__workflow=workflow,
        is_filter=False,
    ).select_related('action').first()
    if not condition:
        return JsonResponse({'html_redirect': reverse('home')})

    # Treat the two types of requests
    if request.method == 'POST':
        # If the request has the 'action_content', update the action
        action_content = request.POST.get('action_content', None)
        if action_content:
            condition.action.set_text_content(action_content)
            condition.action.save()

        formula, fields = evaluate_formula(
            condition.formula,
            NodeEvaluation.EVAL_SQL)

        Log.objects.register(
            request.user,
            Log.CONDITION_DELETE,
            condition.action.workflow,
            {'id': condition.id,
             'name': condition.name,
             'formula': formula,
             'formula_fields': fields})

        # Perform the delete operation
        condition.delete()

        # Reset the count of number of rows with all conditions false
        condition.action.rows_all_false = None

        return JsonResponse({'html_redirect': ''})

    return JsonResponse({
        'html_form': render_to_string(
            'action/includes/partial_condition_delete.html',
            {'condition_id': condition.id},
            request=request)
    })
