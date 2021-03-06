# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

'''Views for the main navigation pages.
'''

import sys
import feedparser  # vendor-local
from django.core.urlresolvers import reverse
from django.http import (HttpResponsePermanentRedirect, Http404,
                         HttpResponseServerError)
from django.shortcuts import render, redirect
from django.utils.safestring import mark_safe
from django.template import RequestContext, loader
from django.conf import settings
from django.shortcuts import render
from django.views.defaults import page_not_found, server_error
from django.core.cache import cache
import django_arecibo.wrapper

from life.models import Locale


def handler404(request):
    if getattr(settings, 'ARECIBO_SERVER_URL', None):
        # Make a distinction between Http404 and Resolver404.
        # Http404 is an explicity exception raised from within the views which
        # might indicate the wrong usage of arguments to a view for example.
        # Resolver404 is an implicit exception that Django raises when it can't
        # resolve a URL to an appropriate view or handler.
        # We're not interested in sending Arecibo exceptions on URLs like
        # /blablalb/junk/junk
        # but we might be interested in /dashboard?from=20LL-02-31
        exception = sys.exc_info()[0]
        if isinstance(exception, Http404) or exception is Http404:
            django_arecibo.wrapper.post(request, 404)
    return page_not_found(request)


def handler500(request):
    if getattr(settings, 'ARECIBO_SERVER_URL', None):
        django_arecibo.wrapper.post(request, 500)
    # unlike the default django.views.default.server_error view function we
    # want one that passes a RequestContext so that we can have 500.html
    # template that uses '{% extends "base.html" %}' which depends on various
    # context variables to be set
    t = loader.get_template('500.html')
    return HttpResponseServerError(t.render(RequestContext(request)))


def index(request):
    limit = getattr(settings, 'HOMEPAGE_LOCALES_LIMIT', 10)

    locales_first_half, locales_second_half, locales_rest_count = \
      get_homepage_locales(limit / 2)

    feed_items = get_feed_items()

    options = {
      'feed_items': feed_items,
      'locales_first_half': locales_first_half,
      'locales_second_half': locales_second_half,
      'locales_rest_count': locales_rest_count,
    }
    return render(request, 'homepage/index.html', options)


def get_homepage_locales(split):
    # we're only going to show the `split+split-1` first locales
    # and in the interest to avoid excessive db queries, download
    # them all as a python list and split up accordingly
    locales = list(Locale.objects
                   .filter(name__isnull=False)
                   .order_by('name')
                   .values('name', 'code'))
    length = len(locales)
    if split * 2 > length:
        split = length / 2  # new minimum split
    first_half = locales[:split]
    second_half = locales[split:split * 2 - 1]
    rest_count = length - split * 2 + 1
    return first_half, second_half, rest_count


def get_feed_items(max_count=settings.HOMEPAGE_FEED_SIZE,
                   force_refresh=False):
    cache_key = 'feed_items:%s' % max_count
    if not force_refresh:
        items = cache.get(cache_key, None)
        if items is not None:
            return items

    parsed = feedparser.parse(settings.L10N_FEED_URL)

    items = []
    for item in parsed.entries:
        url = item['link']
        title = item['title']
        if url and title:
            items.append(dict(url=url, title=title))
            if len(items) >= max_count:
                break

    cache.set(cache_key, items, 60 * 60)
    return items


def teams(request):
    locs = Locale.objects.all().order_by('name')
    # This is an artifact of the addon trees
    # see https://bugzilla.mozilla.org/show_bug.cgi?id=701218
    locs = locs.exclude(code='en-US')
    return render(request, 'homepage/teams.html', {
                    'locales': locs,
                  })


def locale_team(request, code):
    try:
        loc = Locale.objects.get(code=code)
    except Locale.DoesNotExist:
        return redirect('homepage.views.teams')

    from shipping.views import teamsnippet as ship_snippet
    ship_div = mark_safe(ship_snippet(loc))

    from bugsy.views import teamsnippet as bug_snippet
    bug_div = mark_safe(bug_snippet(loc))

    name = loc.name or loc.code

    return render(request, 'homepage/locale-team.html', {
                    'locale': loc,
                    'locale_name': name,
                    'shipping': ship_div,
                    'bugs': bug_div,
                    'webdashboard_url': settings.WEBDASHBOARD_URL,
                  })

# redirects for moves within pushes app, and moving the diff view
# from shipping to pushes.
# XXX Revisit how long we need to keep those


def pushlog_redirect(request, path):
    return HttpResponsePermanentRedirect(
        reverse('pushes.views.pushlog.pushlog',
                kwargs={'repo_name': path}) + '?' + request.GET.urlencode())


def diff_redirect(request):
    return HttpResponsePermanentRedirect(
        reverse('pushes.views.diff') + '?' + request.GET.urlencode())
