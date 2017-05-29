# -*- coding: utf-8 -*-/st

from __future__ import unicode_literals

import os
import sys
import yaml
import tempfile
import collections

from subprocess import call
from StringIO import StringIO
from jinja2 import Template

from django_dploy import env
from django_dploy.constants import EDITOR, CONTEXT_CACHE, BASE_GLOBAL_CONTEXT

from fabric.api import cd, sudo, get, hide
from fabric.colors import green, blue, cyan, yellow, red
from fabric.contrib import files


def log(i, color=green):
    p, s = (ctx('django.project_name'), env.stage)
    print('{}:{}> {}'.format(blue(p), cyan(s), color(i)))


def query_yes_no(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()  # noqa
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


def validate_yaml(string):
    try:
        yaml.load(string)
        return True
    except yaml.YAMLError as e:
        return {
            'problem': e.problem,
            'name': e.problem_mark.name,
            'column': e.problem_mark.column,
            'line': e.problem_mark.line,
        }


def editor_input(initial='', confirm=True):
    with tempfile.NamedTemporaryFile(suffix=".tmp") as tf:
        tf.write(initial)
        tf.flush()
        call([EDITOR, tf.name])
        tf.seek(0)
        out = tf.read()

    print('-' * 80)
    print('\n{}\n'.format(out))
    print('-' * 80)

    is_valid = validate_yaml(out)
    if is_valid is not True:
        print('YAML {name} error at line {line} column {column}: {problem}'.format(is_valid))  # noqa
        return editor_input(initial=out)
    elif not query_yes_no('Upload this context ?'):
        return editor_input(initial=out)
    else:
        return out


def update(orig_dict, new_dict):
    for key, val in new_dict.iteritems():
        if isinstance(val, collections.Mapping):
            tmp = update(orig_dict.get(key, {}), val)
            orig_dict[key] = tmp
        elif isinstance(val, list):
            orig_dict[key] = (orig_dict.get(key, []) + val)
        else:
            orig_dict[key] = new_dict[key]
    return orig_dict


def get_project_context():
    _f = os.path.join('dploy.yml')
    with open(_f, 'r') as fd:
        try:
            rs = yaml.load(fd)
        except yaml.YAMLError as e:
            print(e)
    return rs



def get_template(tpl):
    _f = os.path.join('templates/', tpl)
    with open(_f, 'r') as fd:
        try:
            rs = yaml.load(fd)
        except yaml.YAMLError as e:
            print(e)
    return rs


def get_stage_context(project_name, stage):
    rs = None
    with hide('running', 'stdout'):
        _path = '/root/.context/{project}/{stage}.yml'.format(**{
            'project': project_name,
            'stage': stage,
        })
        if not CONTEXT_CACHE.get(_path):
            if files.exists(_path, use_sudo=True):
                fd = StringIO()
                get(_path, fd, use_sudo=True)
                CONTEXT_CACHE[_path] = yaml.load(fd.getvalue())
                log('fetched context')
            else:
                log('Warning context file not found: {}'.format(_path),
                    color=yellow)
                CONTEXT_CACHE[_path] = {}
        rs = CONTEXT_CACHE.get(_path)
    return rs


def get_context():
    base_context = yaml.load(BASE_GLOBAL_CONTEXT)
    project_context = get_project_context()
    base_context = update(base_context, project_context.get('global'))
    base_context = update(base_context,
                          project_context.get('stages').get(env.stage))
    return base_context


def ctx(path):
    if path == 'stage':
        return env.stage
    elif path == 'project_dir':
        return get_project_dir()
    context = env.context
    if env.host_string:
        stage_ctx = get_stage_context(context['django']['project_name'],
                                      env.stage)
        if stage_ctx:
            context = update(context, stage_ctx)
    tokens = path.split('.')
    tokens.reverse()
    val = env.context
    while len(tokens):
        try:
            val = val.get(tokens.pop())
        except AttributeError:
            print(red('Configuration error: {}'.format(path)))
            sys.exit(1)
    if isinstance(val, str):
        return Template(val).render(**context)
    else:
        return val


def get_project_dir():
    return os.path.join(ctx('nginx.document_root'), ctx('git.dir'))


def venv(i):
    with cd(get_project_dir()):
        sudo('../{}/bin/{}'.format(
            ctx('virtualenv.name'), i))


def pip(i):
    venv('pip {}'.format(i))


def python(i):
    venv('python {}'.format(i))


def manage(i):
    python('manage.py {}'.format(i))
