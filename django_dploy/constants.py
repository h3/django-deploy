# -*- coding: utf-8 -*-/st

from __future__ import unicode_literals

import os

from django_dploy.utils import get_template


LOGGER = 'django_dploy'

EDITOR = os.environ.get('EDITOR','vim')

# Context templates

BASE_GLOBAL_CONTEXT = get_template('context_default.yml')
REMOTE_CONTEXT_TEMPLATE = get_template('context_remote.yml')

# Paths

BASE_PATH = os.path.dirname(__file__)
TEMPLATES_DIR = 'dploy/'

CONTEXT_CACHE = {}
