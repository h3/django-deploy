# -*- coding: utf-8 -*-/st

from __future__ import unicode_literals

import os
import sys
import pprint

from fabric.api import run, task, execute, cd, sudo, hide
from fabric.operations import put
from fabric.colors import *  # noqa
from fabric.contrib import files

from django_dploy import env
from django_dploy.utils import (
    editor_input,
    get_context, ctx, get_project_dir, pip,
    manage
)

"""
$ fab on:beta rollback
$ fab on:prod deploy
"""


@task
def on(stage):
    env.stage = stage
    env.context = get_context()
    env.hosts = env.context['hosts']


@task
def print_context():
    print('-' * 80)
    print('Global context')
    print('-' * 80)
    print('\x1b[33m')
    pprint.pprint(env.context)
    print('\x1b[0m')
    print('-' * 80)


@task
def create_dirs():
    log('creating directories')
    with hide('output', 'running'):
        socket_dir = '/dev/shm/{}-run/'.format(ctx('django.project_name'))
        sudo('mkdir -p {}'.format(ctx('nginx.document_root')))
        sudo('mkdir -p {}'.format(ctx('django.static_root')))
        sudo('mkdir -p {}'.format(ctx('django.media_root')))
        sudo('mkdir -p {}'.format(ctx('logs.path')))
        sudo('mkdir -p {}'.format(socket_dir))
        sudo('chown -R {user}:{group} {path}'.format(
            user=ctx('system.user'), group=ctx('system.group'),
            path=ctx('logs.path')))
        sudo('chown -R {user}:{group} {path}'.format(
            user=ctx('system.user'), group=ctx('system.group'),
            path=ctx('nginx.document_root')))
        sudo('chown -R {user}:{group} {path}'.format(
            user=ctx('system.user'), group=ctx('system.group'),
            path=socket_dir))


@task
def checkout():
    project_dir = get_project_dir()
    branch = ctx('git.branch')

    with hide('running', 'stdout'):
        if files.exists(os.path.join(project_dir, '.git'), use_sudo=True):
            log('updating code')
            with cd(project_dir):
                sudo('git reset --hard')
                sudo('git pull')
                sudo('git checkout {}'.format(branch))
                sudo("find . -iname '*.pyc' | xargs rm -f")
        else:
            log('cloning code')
            with cd(ctx('nginx.document_root')):
                sudo('git clone -b {} {}'.format(
                    ctx('git.branch'), ctx('git.repository')))


@task
def install_requirements():
    log('installing requirements')
    with hide('running', 'stdout'):
        pip('install -qr requirements.pip')


@task
def update_requirements():
    log('installing/updating requirements')
    with hide('running', 'stdout'):
        pip('install -qUr requirements.pip')


@task
def setup_virtualenv():
    venv_root = ctx('virtualenv.root')
    venv_name = ctx('virtualenv.name')
    py_version = ctx('python.version')
    venv_path = os.path.join(venv_root, venv_name)
    with hide('running', 'stdout'):
        with cd(ctx('nginx.document_root')):
            if not files.exists(venv_path, use_sudo=True):
                sudo('virtualenv --python=python{version} {name}'.format(
                    version=py_version, name=venv_name))
                log('created virtualenv: {}'.format(venv_path))
                execute(install_requirements)


@task
def setup_django_settings():
    project_dir = get_project_dir()
    local_settings = '{stage}_settings.py'.format(stage=env.stage)

    # with hide('running', 'stdout'):
    if os.path.exists(os.path.join(TEMPLATES_DIR, local_settings)):
        _settings_dest = os.path.join(project_dir,
                                      ctx('django.project_name'),
                                      'local_settings.py')
        _context = {'ctx': ctx, 'project_dir': project_dir}
        files.upload_template(
            local_settings, _settings_dest, context=_context, use_jinja=True,
            template_dir=TEMPLATES_DIR, use_sudo=True, backup=False, mode=None)
        log('Configured django settings')
    else:
        log('ERROR: deploying to {}, but {}/{} does not exists.'.format(
                env.stage, TEMPLATES_DIR, local_settings), color=red)
        sys.exit(1)


@task
def django_migrate():
    with hide('running'):
        try:
            manage('migrate --noinput')
            log('django migrated')
        except FabricException as e:
            log('WARNING: had to fake migrations because of exception %s' % e,
                color=yellow)
            manage('migrate --noinput --fake')


@task
def django_collectstatic():
    with hide('running'):
        log('django collect static')
        manage('collectstatic --noinput --link -v 0')


@task
def django(cmd):
    log('django manage {}'.format(cmd))
    with hide('stdout'):
        manage(cmd)


@task
def setup_cron():
    # Cron doesn't like dots in filename
    filename = ctx('nginx.server_name').replace('.', '_')
    dest = os.path.join(ctx('cron.config_path'), filename)
    if os.path.exists(os.path.join(TEMPLATES_DIR, 'cron.template')):
        log('configuring cron')
        with hide('running', 'stdout'):
            files.upload_template(
                'cron.template', dest, context={'ctx': ctx}, use_jinja=True,
                template_dir=TEMPLATES_DIR, use_sudo=True, backup=False,
                mode=None)

            # We make sure the cron file always ends with a blank line,
            # otherwise it will be ignored by cron. Yeah, that's retarded.
            sudo("echo -en '\n' >> {}".format(dest))
            sudo('chown -R root:root {}'.format(dest))
            sudo('chmod 644 {}'.format(dest))


@task
def setup_uwsgi():
    log('configuring uwsgi')
    project_dir = get_project_dir()
    wsgi_file = os.path.join(project_dir, ctx('django.project_name'), 'wsgi.py')
    uwsgi_ini = os.path.join(project_dir, 'uwsgi.ini')
    context = {'ctx': ctx, 'project_dir': project_dir, 'wsgi_file': wsgi_file}
    log_file = '{}/uwsgi.log'.format(ctx('logs.path'))
    with hide('running', 'stdout'):
        sudo('touch {logfile}'.format(logfile=log_file))
        sudo('chown {user}:{group} {logfile}'.format(
            logfile=log_file, user=ctx('system.user'),
            group=ctx('system.group')))
        files.upload_template(
            'uwsgi.template', uwsgi_ini, context=context, use_jinja=True,
            template_dir=TEMPLATES_DIR, use_sudo=True, backup=False, mode=None)


@task
def setup_nginx():
    log('configuring nginx')

    ssl = False
    context = {
        'ctx': ctx,
        'ssl_with_dhparam': False,
        'ssl_cert': None,
        'ssl_key': None,
        'project_dir': get_project_dir(),
    }
    with hide('running', 'stdout'):

        if ctx('ssl.key') and ctx('ssl.cert'):
            ssl = True
            if files.exists(ctx('ssl.key'), use_sudo=True):
                context['ssl_key'] = ctx('ssl.key')
            if files.exists(ctx('ssl.cert'), use_sudo=True):
                context['ssl_cert'] = ctx('ssl.cert')
            if files.exists(ctx('ssl.dhparam'), use_sudo=True):
                context['ssl_with_dhparam'] = True
        if ssl:
            files.upload_template('nginx_ssl.template',
                                  ctx('nginx.config_path'),
                                  context=context, use_jinja=True,
                                  template_dir='dploy/', use_sudo=True,
                                  backup=False, mode=None)
        else:
            files.upload_template('nginx.template', ctx('nginx.config_path'),
                                  context=context, use_jinja=True,
                                  template_dir='dploy/', use_sudo=True,
                                  backup=False, mode=None)

        if files.exists(ctx('nginx.document_root'), use_sudo=True):
            sudo('chown -R {user}:{group} {path}'.format(
                path=ctx('nginx.document_root'), user=ctx('system.user'),
                group=ctx('system.group')))

        sudo('service nginx reload')


@task
def setup_supervisor():
    log('configuring supervisor')
    project_dir = get_project_dir()
    uwsgi_ini = os.path.join(project_dir, 'uwsgi.ini')
    context = {'project_dir': project_dir, 'uwsgi_ini': uwsgi_ini, 'ctx': ctx}
    with hide('running', 'stdout'):
        files.upload_template(
            'supervisor.template', ctx('supervisor.config_path'),
            context=context, use_jinja=True, template_dir='dploy/',
            use_sudo=True, backup=False, mode=None)
        sudo('supervisorctl reload')


@task
def check_services():
    log('checking services')
    checks = {
        'uwsgi': "ps aux | grep uwsgi | grep '{}' | grep '^www-data' | grep -v grep".format(ctx('nginx.server_name')),  # noqa
        'nginx': "ps aux | grep nginx | grep '^www-data' | grep -v grep",
        'supervisor': "ps aux | grep supervisord.conf | grep '^root' | grep -v grep",  # noqa
    }
    for check, cmd in checks.iteritems():
        try:
            label = ('%s...' % check).ljust(20)
            with hide('output', 'running'):
                run(cmd)
            log(' - {} [OK]'.format(label.ljust(80)), color=green)
        except Exception:
            log(' - {} [FAIL]'.format(label.ljust(80)), color=red)


@task
def install_packages():
    if ctx('system.packages'):
        log('installing system packages')
        with hide('running', 'stdout'):
            sudo('apt-get update && apt-get upgrade')
            sudo('apt-get install -qy {}'.format(ctx('system.packages')))


@task
def create_context():
    context = editor_input(initial=REMOTE_CONTEXT_TEMPLATE)
    tmpfile = '/tmp/context.tmp'
    upload_path = os.path.join('/root/.context',
                               ctx('django.project_name'),
                               '{}.yml'.format(env.stage))

    if os.path.exists(tmpfile):
        os.system('rm -f {}'.format(tmpfile))

    with open(tmpfile, 'w+') as fd:
        fd.write(context)

    sudo('mkdir -p {}'.format(os.path.dirname(upload_path)))
    put('/tmp/context.tmp', upload_path, use_sudo=True)
    os.system('rm -f {}'.format(tmpfile))


@task
def deploy():
    log('deploying')
    with hide('running', 'stdout'):
        execute(create_dirs)
        execute(checkout)
        execute(setup_virtualenv)
        execute(setup_django_settings)
        execute(django_migrate)
        execute(django_collectstatic)
        execute(setup_cron)
        execute(setup_uwsgi)
        execute(setup_supervisor)
        if ctx('nginx.hosts'):
            execute(setup_nginx, hosts=ctx('nginx.hosts'))
        else:
            execute(setup_nginx)
        execute(check_services)
