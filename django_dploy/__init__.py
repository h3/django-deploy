# -*- coding: utf-8 -*-/st

from __future__ import unicode_literals

from fabric.api import env

from django_dploy.exceptions import FabricException


env.abort_exception = FabricException
env.use_ssh_config = True
