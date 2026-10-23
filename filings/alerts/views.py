import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods

from filings.models import AlertPreference, AlertDelivery, SavedSearch, IssuerWatch
from .service import preference


def cancel_pending(user_id):
    AlertDelivery.objects.filter(user_id=user_id,state__in=['pending','retry']).update(
        state='cancelled',last_error='Email alerts disabled',updated_at=timezone.now())


@login_required
@never_cache
@require_http_methods(['GET','POST'])
def preferences(request):
    pref = preference(request.user.pk)
    if request.method == 'POST':
        enabled = request.POST.get('enabled') == '1'
        with transaction.atomic():
            pref = AlertPreference.objects.select_for_update().get(pk=pref.pk)
            if enabled and not pref.email_enabled:
                # Old messages must not disable a newly resumed subscription.
                pref.unsubscribe_token = uuid.uuid4()
                SavedSearch.objects.filter(user=request.user).update(alerts_started_at=timezone.now())
                IssuerWatch.objects.filter(user=request.user).update(alerts_started_at=timezone.now())
            pref.email_enabled = enabled
            pref.save()
            if not enabled:
                cancel_pending(request.user.pk)
        messages.success(request,'Filing alert emails enabled.' if enabled else 'Filing alert emails paused.')
        return redirect('filings:alert_preferences')
    return render(request,'filings/alert_preferences.html',{'preference':pref,'robots':'noindex','page_title':'Filing email preferences — Form D Explorer'})


@login_required
@require_POST
def toggle_source(request,kind,pk):
    model = SavedSearch if kind=='search' else IssuerWatch
    preference(request.user.pk)
    with transaction.atomic():
        AlertPreference.objects.select_for_update().get(user=request.user)
        source=get_object_or_404(model.objects.select_for_update(),pk=pk,user=request.user)
        source.alerts_enabled = not source.alerts_enabled
        if source.alerts_enabled:
            source.alerts_started_at=timezone.now()
        source.save(update_fields=['alerts_enabled','alerts_started_at'])
    return redirect('filings:saved_search_list' if kind=='search' else 'filings:watchlist')


def opt_out(token):
    with transaction.atomic():
        pref=get_object_or_404(AlertPreference.objects.select_for_update(),unsubscribe_token=token)
        pref.email_enabled=False
        pref.save(update_fields=['email_enabled','updated_at'])
        cancel_pending(pref.user_id)


@never_cache
@require_http_methods(['GET','POST'])
def unsubscribe(request,token):
    # Link scanners can GET safely: only an explicit form POST changes preferences.
    get_object_or_404(AlertPreference,unsubscribe_token=token)
    if request.method=='POST':
        opt_out(token)
    response=render(request,'filings/alert_unsubscribe.html',{
        'done':request.method=='POST','page_title':'Unsubscribe from filing emails — Form D Explorer','robots':'noindex'})
    response['Referrer-Policy']='no-referrer'
    return response


@csrf_exempt
@never_cache
@require_POST
def unsubscribe_one_click(request,token):
    # RFC 8058: capability token authorizes opt-out only, never opt-in. No login
    # cookies, redirects or HTML confirmation are required by mailbox providers.
    if request.POST.get('List-Unsubscribe') != 'One-Click':
        return HttpResponseBadRequest('Expected one-click unsubscribe request')
    opt_out(token)
    response=HttpResponse('Unsubscribed',content_type='text/plain')
    response['Referrer-Policy']='no-referrer'
    return response
