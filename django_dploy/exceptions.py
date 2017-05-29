# -*- coding: utf-8 -*-/st

from __future__ import unicode_literals

import logging

from django_dploy.contants import LOGGER


log = logging.getLogger(LOGGER)


class FabricException(Exception):
    log.error('Exception: {}'.format(Exception))
