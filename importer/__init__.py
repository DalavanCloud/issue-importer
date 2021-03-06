#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

'''Does the main work to prepare and create a new issue.'''

import argparse
import json
import jsonschema
import os
import re
import requests

from config import REPO_PATH, OAUTH_TOKEN
from schema import schema
from termcolor import cprint
from textwrap import fill
from time import sleep

LABEL_VALIDATION_ERROR = '''
You attempted to create an issue with an unknown label. GitHub ignores unknown
labels when creating issues. Please email miket@mozilla.com if you feel like
this label should be added to the web-bugs issues repo. To ignore this type
of validation and proceed, try again using the --force option.
'''

REPO_URI = 'https://api.github.com/repos/{0}'.format(REPO_PATH)


def get_issue_body(json_data):
    '''Return the issue body in the proper format.'''
    body = u'''
**URL**: {0}
**Browser / Version**: {1}
**Operating System**: {2}

{3}'''
    return body.format(json_data['url'],
                       json_data['browser'],
                       json_data['os'],
                       json_data['body'])


def format_post_body(json_data):
    '''Create the POST "body" object.'''
    body = {'body': get_issue_body(json_data),
            'title': json_data['title'],
            'labels': json_data['labels']}
    return body


def api_post(uri, body, hooks=None):
    '''Generic method to create a resource at GitHub. `uri` will determine
    what gets created (currently either an issue or a comment).'''
    headers = {
        'Authorization': 'token {0}'.format(OAUTH_TOKEN),
        'User-Agent': 'Webcompat-Issue-Importer'
    }
    return requests.post(uri, data=json.dumps(body), headers=headers,
                         hooks=hooks)


def create_issue(json_data):
    '''Create a new GitHub issue by POSTing data to the issues API endpoint.
    If successful, the URL to the new issue is printed. Otherwise, the error
    code is printed.'''
    body = format_post_body(json_data)
    uri = '{0}/issues'.format(REPO_URI)
    r = api_post(uri, body)
    if r.status_code != 201:
        cprint('Something went wrong. Response: {0}. See '
               'developer.github.com/v3/ for troubleshooting.'.format(
                   r.status_code), 'red')
        return False
    else:
        cprint(r.json()['html_url'] + ' successfully imported', 'green')
        if len(json_data['comments']) > 0:
            cprint('Importing comments...', 'yellow')
            import_comments(r.json()['number'], json_data['comments'])
        return True


def import_comments(number, comments):
    '''Handles importing all comments from the comments array,
    ideally in order.'''
    def next_comment(response, *args, **kwargs):
        '''Callback to wait for a 201 before importing the next comment.'''
        if response.status_code == 201:
            cprint("{0} created".format(response.json()['html_url']), 'green')
            try:
                add_comment(number, comments.next())
            except StopIteration:
                cprint(u'All done. 🍪', 'green')

    def add_comment(issue_number, comment):
        '''Add a single comment.'''
        sleep(1)
        uri = '{0}/issues/{1}/comments'.format(REPO_URI, issue_number)
        body = {'body': comment}
        return api_post(uri, body, hooks=dict(response=next_comment))

    comments = iter(comments)
    add_comment(number, comments.next())


def get_as_json(issue_file):
    '''Return the contents of `issue_file` as a JSON object.'''
    try:
        # is `issue_file` a file object?
        r = json.load(issue_file)
    except AttributeError:
        # is `issue_file` a file name (string)?
        r = json.load(open(issue_file))
    return r


def validate_json(issue_file, skip_labels=False):
    '''Validate the structure of `file_name` against our JSON schema.'''
    json_data = get_as_json(issue_file)
    if not skip_labels:
        schema['properties']['labels']['items'].update(enum=get_labels())
    try:
        jsonschema.validate(json_data, schema)
        create_issue(json_data)
    except jsonschema.exceptions.ValidationError as e:
        cprint('JSON Schema validation failed:', 'white', 'on_red')
        print('\n')
        if e.path and e.path.popleft() == 'labels':
            print(fill(LABEL_VALIDATION_ERROR, width=80) + '\n')
            print(e.message)
        else:
            print(e)


def get_labels():
    '''Returns all labels in use for the given repo at REPO_URI.'''
    uri = '{0}/labels'.format(REPO_URI)
    r = requests.get(uri)
    labels = [label.get('name') for label in r.json()]
    return labels


def print_labels():
    '''Print all labels used by issues at REPO_URI.'''
    print('All labels: {0}'.format(get_labels()))
