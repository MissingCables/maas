# Copyright 2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the proxyconfig."""

__all__ = []

import os

from crochet import wait_for
from django.conf import settings
from fixtures import EnvironmentVariableFixture
from maasserver import proxyconfig
from maasserver.testing.factory import factory
from maasserver.testing.testcase import (
    MAASServerTestCase,
    MAASTransactionServerTestCase,
)
from maasserver.utils.orm import transactional
from maasserver.utils.threads import deferToDatabase
from maastesting.matchers import (
    MockCalledOnceWith,
    MockNotCalled,
)
from testtools.matchers import (
    Contains,
    FileContains,
    Not,
)
from twisted.internet.defer import inlineCallbacks


wait_for_reactor = wait_for(30)  # 30 seconds.


class TestGetConfigDir(MAASServerTestCase):
    """Tests for `maasserver.proxyconfig.get_proxy_config_dir`."""

    def test_returns_default(self):
        self.assertEquals(
            "/var/lib/maas", proxyconfig.get_proxy_config_dir())

    def test_env_overrides_default(self):
        os.environ['MAAS_PROXY_CONFIG_DIR'] = factory.make_name('env')
        self.assertEquals(
            os.environ['MAAS_PROXY_CONFIG_DIR'],
            proxyconfig.get_proxy_config_dir())
        del(os.environ['MAAS_PROXY_CONFIG_DIR'])


class TestProxyUpdateConfig(MAASTransactionServerTestCase):
    """Tests for `maasserver.proxyconfig`."""

    def setUp(self):
        super(TestProxyUpdateConfig, self).setUp()
        self.tmpdir = self.make_dir()
        self.service_monitor = self.patch(proxyconfig, "service_monitor")
        self.useFixture(
            EnvironmentVariableFixture('MAAS_PROXY_CONFIG_DIR', self.tmpdir))

    @transactional
    def make_subnet(self, allow_proxy=True):
        return factory.make_Subnet(allow_proxy=allow_proxy)

    @wait_for_reactor
    @inlineCallbacks
    def test__only_enabled_subnets_are_present(self):
        self.patch(settings, "PROXY_CONNECT", True)
        disabled = yield deferToDatabase(self.make_subnet, allow_proxy=False)
        enabled = yield deferToDatabase(self.make_subnet)
        yield proxyconfig.proxy_update_config(reload_proxy=False)
        # enabled's cidr must be present
        matcher = Contains("acl localnet src %s" % enabled.cidr)
        self.assertThat(
            "%s/%s" % (self.tmpdir, proxyconfig.MAAS_PROXY_CONF_NAME),
            FileContains(matcher=matcher))
        # disabled's cidr must not be present
        matcher = Not(Contains("acl localnet src %s" % disabled.cidr))
        self.assertThat(
            "%s/%s" % (self.tmpdir, proxyconfig.MAAS_PROXY_CONF_NAME),
            FileContains(matcher=matcher))

    @wait_for_reactor
    @inlineCallbacks
    def test__calls_reloadService(self):
        self.patch(settings, "PROXY_CONNECT", True)
        yield deferToDatabase(self.make_subnet)
        yield proxyconfig.proxy_update_config()
        self.assertThat(
            self.service_monitor.reloadService,
            MockCalledOnceWith("proxy", if_on=True))

    @wait_for_reactor
    @inlineCallbacks
    def test__doesnt_call_reloadService_when_PROXY_CONNECT_False(self):
        self.patch(settings, "PROXY_CONNECT", False)
        yield deferToDatabase(self.make_subnet)
        yield proxyconfig.proxy_update_config()
        self.assertThat(
            self.service_monitor.reloadService,
            MockNotCalled())

    @wait_for_reactor
    @inlineCallbacks
    def test__doesnt_call_reloadService_when_reload_proxy_False(self):
        self.patch(settings, "PROXY_CONNECT", True)
        yield deferToDatabase(self.make_subnet)
        yield proxyconfig.proxy_update_config(reload_proxy=False)
        self.assertThat(
            self.service_monitor.reloadService,
            MockNotCalled())
