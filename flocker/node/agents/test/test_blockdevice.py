"""
Tests for ``flocker.node.agents.blockdevice``.
"""
from uuid import uuid4

from zope.interface.verify import verifyObject

from ..blockdevice import (
    BlockDeviceDeployer, LoopbackBlockDeviceAPI, IBlockDeviceAPI,
    BlockDeviceVolume, UnknownVolume, AlreadyAttachedVolume,
)

from ..._deploy import IDeployer, NodeState
from ....control import Dataset, Manifestation

from twisted.trial.unittest import SynchronousTestCase


class BlockDeviceDeployerTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceDeployer``.
    """
    def test_interface(self):
        """
        ``BlockDeviceDeployer`` instances provide ``IDeployer``.
        """
        api = LoopbackBlockDeviceAPI.from_path(self.mktemp())
        self.assertTrue(
            verifyObject(
                IDeployer,
                BlockDeviceDeployer(
                    hostname=b'192.0.2.123',
                    block_device_api=api
                )
            )
        )


class BlockDeviceDeployerDiscoverLocalStateTests(SynchronousTestCase):
    """
    Tests for ``BlockDeviceDeployer.discover_local_state``.
    """
    def setUp(self):
        self.expected_hostname = b'192.0.2.123'
        self.api = LoopbackBlockDeviceAPI.from_path(self.mktemp())
        self.deployer = BlockDeviceDeployer(
            hostname=self.expected_hostname,
            block_device_api=self.api
        )

    def assertDiscoveredState(self, deployer, expected_manifestations):
        """
        Assert that the manifestations on the state object returned by
        ``deployer.discover_local_state`` equals the given list of
        manifestations.

        :param IDeployer deployer: The object to use to discover the state.
        :param list expected_manifestations: The ``Manifestation``\ s expected
            to be discovered.

        :raise: A test failure exception if the manifestations are not what is
            expected.
        """
        discovering = deployer.discover_local_state()
        state = self.successResultOf(discovering)
        self.assertEqual(
            NodeState(
                hostname=deployer.hostname,
                running=(),
                not_running=(),
                manifestations=expected_manifestations,
            ),
            state
        )

    def test_no_devices(self):
        """
        ``BlockDeviceDeployer.discover_local_state`` returns a ``NodeState``
        with empty ``manifestations`` if the ``api`` reports no locally
        attached volumes.
        """
        self.assertDiscoveredState(self.deployer, [])

    def test_one_device(self):
        """
        ``BlockDeviceDeployer.discover_local_state`` returns a ``NodeState``
        with one ``manifestations`` if the ``api`` reports one locally
        attached volumes.
        """
        new_volume = self.api.create_volume(size=1234)
        attached_volume = self.api.attach_volume(
            new_volume.blockdevice_id, self.expected_hostname
        )
        expected_dataset = Dataset(dataset_id=attached_volume.blockdevice_id)
        expected_manifestation = Manifestation(dataset=expected_dataset, primary=True)
        self.assertDiscoveredState(self.deployer, [expected_manifestation])

    def test_only_remote_device(self):
        """
        ``BlockDeviceDeployer.discover_local_state`` does not consider remotely
        attached volumes.
        """
        new_volume = self.api.create_volume(size=1234)
        self.api.attach_volume(new_volume.blockdevice_id, b'some.other.host')
        self.assertDiscoveredState(self.deployer, [])

    def test_only_unattached_devices(self):
        """
        ``BlockDeviceDeployer.discover_local_state`` does not consider
        unattached volumes.
        """
        self.api.create_volume(size=1234)
        self.assertDiscoveredState(self.deployer, [])


class IBlockDeviceAPITestsMixin(object):
    """
    """
    def test_interface(self):
        """
        ``api`` instances provide ``IBlockDeviceAPI``.
        """
        self.assertTrue(
            verifyObject(IBlockDeviceAPI, self.api)
        )

    def test_list_volume_empty(self):
        """
        ``list_volumes`` returns an empty ``list`` if no block devices have
        been created.
        """
        self.assertEqual([], self.api.list_volumes())

    def test_created_is_listed(self):
        """
        ``create_volume`` returns a ``BlockVolume`` that is returned by
        ``list_volumes``.
        """
        new_volume = self.api.create_volume(size=1000)
        self.assertIn(new_volume, self.api.list_volumes())

    def test_attach_unknown_volume(self):
        """
        An attempt to attach an unknown ``BlockDeviceVolume`` raises
        ``UnknownVolume``.
        """
        self.assertRaises(
            UnknownVolume,
            self.api.attach_volume,
            blockdevice_id=bytes(uuid4()),
            host=b'192.0.2.123'
        )

    def test_attach_attached_volume(self):
        """
        An attempt to attach an already attached ``BlockDeviceVolume`` raises
        ``AlreadyAttachedVolume``.
        """
        host = b'192.0.2.123'
        new_volume = self.api.create_volume(size=1234)
        attached_volume = self.api.attach_volume(new_volume.blockdevice_id, host=host)

        self.assertRaises(
            AlreadyAttachedVolume,
            self.api.attach_volume,
            blockdevice_id=attached_volume.blockdevice_id,
            host=host
        )

    def test_attach_elsewhere_attached_volume(self):
        """
        An attempt to attach a ``BlockDeviceVolume`` already attached to
        another host raises ``AlreadyAttachedVolume``.
        """
        new_volume = self.api.create_volume(size=1234)
        attached_volume = self.api.attach_volume(new_volume.blockdevice_id, host=b'192.0.2.123')

        self.assertRaises(
            AlreadyAttachedVolume,
            self.api.attach_volume,
            blockdevice_id=attached_volume.blockdevice_id,
            host=b'192.0.2.124'
        )

    def test_attach_unattached_volume(self):
        """
        An unattached ``BlockDeviceVolume`` can be attached.
        """
        expected_host = b'192.0.2.123'
        new_volume = self.api.create_volume(size=1000)
        expected_volume = BlockDeviceVolume(
            blockdevice_id=new_volume.blockdevice_id,
            size=new_volume.size,
            host=expected_host,
        )
        attached_volume = self.api.attach_volume(
            blockdevice_id=new_volume.blockdevice_id,
            host=expected_host
        )
        self.assertEqual(expected_volume, attached_volume)

    def test_attached_volume_listed(self):
        """
        An attached ``BlockDeviceVolume`` is listed.
        """
        expected_host = b'192.0.2.123'
        new_volume = self.api.create_volume(size=1000)
        expected_volume = BlockDeviceVolume(
            blockdevice_id=new_volume.blockdevice_id,
            size=new_volume.size,
            host=expected_host,
        )
        self.api.attach_volume(
            blockdevice_id=new_volume.blockdevice_id,
            host=expected_host
        )
        self.assertEqual([expected_volume], self.api.list_volumes())


def make_iblockdeviceapi_tests(blockdevice_api_factory):
    """
    """
    class Tests(IBlockDeviceAPITestsMixin, SynchronousTestCase):
        """
        """
        def setUp(self):
            self.api = blockdevice_api_factory(test_case=self)

    return Tests


def loopbackblockdeviceapi_for_test(test_case):
    """
    """
    root_path = test_case.mktemp()
    return LoopbackBlockDeviceAPI.from_path(root_path=root_path)


class LoopbackBlockDeviceAPITests(
        make_iblockdeviceapi_tests(blockdevice_api_factory=loopbackblockdeviceapi_for_test)
):
    """
    Interface adherence Tests for ``LoopbackBlockDeviceAPI``.
    """


class LoopbackBlockDeviceAPIImplementationTests(SynchronousTestCase):
    """
    Implementation specific tests for ``LoopbackBlockDeviceAPI``.
    """
    def test_list_unattached_volumes(self):
        """
        ``list_volumes`` returns a ``BlockVolume`` for each unattached volume
        file.
        """
        expected_size = 1234
        api = loopbackblockdeviceapi_for_test(test_case=self)
        blockdevice_volume = BlockDeviceVolume(
            blockdevice_id=bytes(uuid4()),
            size=expected_size,
            host=None,
        )
        (api
         .root_path.child('unattached')
         .child(blockdevice_volume.blockdevice_id)
         .setContent(b'x' * expected_size))
        self.assertEqual([blockdevice_volume], api.list_volumes())


    def test_list_attached_volumes(self):
        """
        ``list_volumes`` returns a ``BlockVolume`` for each attached volume
        file.
        """
        expected_size = 1234
        expected_host = b'192.0.2.123'
        api = loopbackblockdeviceapi_for_test(test_case=self)
        blockdevice_volume = BlockDeviceVolume(
            blockdevice_id=bytes(uuid4()),
            size=expected_size,
            host=expected_host,
        )

        host_dir = api.root_path.child('attached').child(expected_host)
        host_dir.makedirs()
        (host_dir
         .child(blockdevice_volume.blockdevice_id)
         .setContent(b'x' * expected_size))
        self.assertEqual([blockdevice_volume], api.list_volumes())