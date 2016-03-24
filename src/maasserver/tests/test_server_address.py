# Copyright 2012-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the server_address module."""

__all__ = []

from collections import defaultdict
from random import randint

from maasserver import server_address
from maasserver.exceptions import UnresolvableHost
from maasserver.server_address import get_maas_facing_server_address
from maasserver.testing.config import RegionConfigurationFixture
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from netaddr import IPAddress


def make_hostname():
    return '%s.example.com' % factory.make_hostname()


class TestGetMAASFacingServerHost(MAASServerTestCase):

    def set_maas_url(self, hostname, with_port=False):
        """Set configured maas URL to be a (partly) random URL."""
        url = factory.make_simple_http_url(netloc=hostname, port=with_port)
        self.useFixture(RegionConfigurationFixture(maas_url=url))

    def test_get_maas_facing_server_host_returns_host_name(self):
        hostname = make_hostname()
        self.set_maas_url(hostname)
        self.assertEqual(
            hostname, server_address.get_maas_facing_server_host())

    def test_get_maas_facing_server_host_returns_ip_if_ip_configured(self):
        ip = factory.make_ipv4_address()
        self.set_maas_url(ip)
        self.assertEqual(ip, server_address.get_maas_facing_server_host())

    def test_get_maas_facing_server_host_returns_rack_maas_url(self):
        hostname = factory.make_hostname()
        maas_url = 'http://%s' % hostname
        rack = factory.make_RackController(url=maas_url)
        self.assertEqual(
            hostname, server_address.get_maas_facing_server_host(rack))

    def test_get_maas_facing_server_host_strips_out_port(self):
        hostname = make_hostname()
        self.set_maas_url(hostname, with_port=True)
        self.assertEqual(
            hostname, server_address.get_maas_facing_server_host())

    def test_get_maas_facing_server_host_parses_IPv6_address_in_URL(self):
        ip = factory.make_ipv6_address()
        self.set_maas_url('[%s]' % ip)
        self.assertEqual(
            str(ip), server_address.get_maas_facing_server_host())


class FakeResolveHostname:
    """Fake implementation for `resolve_hostname`.

    Makes `resolve_hostname` return the given IP addresses (always as
    `IPAddress`, even though you may pass them as text).  It will return just
    the IPv4 ones, or just the IPv6 ones, depending on which kind of address
    the caller requests.

    :ivar results_by_ip_version: Return values, as a dict mapping IP version
        to the set of results for that IP version.
    :ivar hostname: Host name that was passed by the last invocation.
    """

    def __init__(self, *addresses):
        self.hostname = None
        self.results_by_ip_version = defaultdict(set)
        for addr in addresses:
            addr = IPAddress(addr)
            self.results_by_ip_version[addr.version].add(addr)

    def __call__(self, hostname, ip_version):
        assert ip_version in (4, 6)
        self.hostname = hostname
        return self.results_by_ip_version[ip_version]


class TestGetMAASFacingServerAddress(MAASServerTestCase):

    def make_addresses(self):
        """Return a set of IP addresses, mixing IPv4 and IPv6."""
        return {
            factory.make_ipv4_address(),
            factory.make_ipv6_address(),
            }

    def patch_get_maas_facing_server_host(self, host=None):
        if host is None:
            host = make_hostname()
        patch = self.patch(server_address, 'get_maas_facing_server_host')
        patch.return_value = str(host)
        return patch

    def patch_resolve_hostname(self, addresses=None):
        if addresses is None:
            addresses = self.make_addresses()
        fake = FakeResolveHostname(*addresses)
        return self.patch(server_address, 'resolve_hostname', fake)

    def test__integrates_with_get_maas_facing_server_host(self):
        ip = factory.make_ipv4_address()
        maas_url = 'http://%s' % ip
        rack = factory.make_RackController(url=maas_url)
        self.assertEqual(
            str(ip),
            server_address.get_maas_facing_server_host(rack))

    def test__uses_IPv4_hostname_directly_if_ipv4_set(self):
        ip = factory.make_ipv4_address()
        self.patch_get_maas_facing_server_host(ip)
        fake_resolve = self.patch_resolve_hostname()
        result = get_maas_facing_server_address(ipv4=True)
        self.assertEqual(ip, result)
        self.assertIsNone(fake_resolve.hostname)

    def test__rejects_IPv4_hostname_if_ipv4_not_set(self):
        self.patch_get_maas_facing_server_host(factory.make_ipv4_address())
        fake_resolve = self.patch_resolve_hostname()
        self.assertRaises(
            UnresolvableHost,
            get_maas_facing_server_address, ipv4=False)
        self.assertIsNone(fake_resolve.hostname)

    def test__uses_IPv6_hostname_directly_if_ipv6_set(self):
        ip = factory.make_ipv6_address()
        self.patch_get_maas_facing_server_host(ip)
        fake_resolve = self.patch_resolve_hostname()
        result = get_maas_facing_server_address(ipv6=True)
        self.assertEqual(ip, result)
        self.assertIsNone(fake_resolve.hostname)

    def test__rejects_IPv6_hostname_if_ipv6_not_set(self):
        self.patch_get_maas_facing_server_host(factory.make_ipv6_address())
        fake_resolve = self.patch_resolve_hostname()
        self.assertRaises(
            UnresolvableHost,
            get_maas_facing_server_address, ipv6=False)
        self.assertIsNone(fake_resolve.hostname)

    def test__resolves_hostname(self):
        hostname = make_hostname()
        self.patch_get_maas_facing_server_host(hostname)
        ip = factory.make_ipv4_address()
        fake_resolve = self.patch_resolve_hostname([ip])
        result = get_maas_facing_server_address()
        self.assertEqual(str(ip), result)
        self.assertEqual(hostname, fake_resolve.hostname)

    def test__prefers_IPv4_if_ipv4_set(self):
        # If a server has mixed v4 and v6 addresses,
        # get_maas_facing_server_address() will return a v4 address
        # rather than a v6 one.
        v4_ip = factory.make_ipv4_address()
        v6_ip = factory.make_ipv6_address()
        self.patch_resolve_hostname([v4_ip, v6_ip])
        self.patch_get_maas_facing_server_host()
        self.assertEqual(
            str(v4_ip),
            get_maas_facing_server_address(ipv4=True, ipv6=True))

    def test__ignores_IPv4_if_ipv4_not_set(self):
        v4_ip = factory.make_ipv4_address()
        v6_ip = factory.make_ipv6_address()
        self.patch_resolve_hostname([v4_ip, v6_ip])
        self.patch_get_maas_facing_server_host()
        self.assertEqual(
            str(v6_ip),
            get_maas_facing_server_address(ipv4=False, ipv6=True))

    def test__falls_back_on_IPv6_if_ipv4_set_but_no_IPv4_address_found(self):
        v6_ip = factory.make_ipv6_address()
        self.patch_resolve_hostname([v6_ip])
        self.patch_get_maas_facing_server_host()
        self.assertEqual(
            str(v6_ip),
            get_maas_facing_server_address(ipv4=True, ipv6=True))

    def test__prefers_global_IPv6_over_link_local_IPv6(self):
        global_ipv6 = factory.make_ipv6_address()
        local_ipv6 = [
            'fe80::%d:9876:5432:10' % randint(0, 9999)
            for _ in range(5)
            ]
        self.patch_resolve_hostname([global_ipv6] + local_ipv6)
        self.patch_get_maas_facing_server_host()
        self.assertEqual(
            str(global_ipv6),
            get_maas_facing_server_address())

    def test__fails_if_neither_ipv4_nor_ipv6_set(self):
        self.patch_resolve_hostname()
        self.patch_get_maas_facing_server_host()
        self.assertRaises(
            UnresolvableHost,
            get_maas_facing_server_address, ipv4=False, ipv6=False)

    def test__raises_error_if_hostname_does_not_resolve(self):
        self.patch_resolve_hostname([])
        self.patch_get_maas_facing_server_host()
        self.assertRaises(
            UnresolvableHost,
            get_maas_facing_server_address)
