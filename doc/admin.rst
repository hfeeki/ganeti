Ganeti administrator's guide
============================

Documents Ganeti version |version|

.. contents::

.. highlight:: text

Introduction
------------

Ganeti is a virtualization cluster management software. You are expected
to be a system administrator familiar with your Linux distribution and
the Xen or KVM virtualization environments before using it.

The various components of Ganeti all have man pages and interactive
help. This manual though will help you getting familiar with the system
by explaining the most common operations, grouped by related use.

After a terminology glossary and a section on the prerequisites needed
to use this manual, the rest of this document is divided in sections
for the different targets that a command affects: instance, nodes, etc.

.. _terminology-label:

Ganeti terminology
++++++++++++++++++

This section provides a small introduction to Ganeti terminology, which
might be useful when reading the rest of the document.

Cluster
~~~~~~~

A set of machines (nodes) that cooperate to offer a coherent, highly
available virtualization service under a single administration domain.

Node
~~~~

A physical machine which is member of a cluster.  Nodes are the basic
cluster infrastructure, and they don't need to be fault tolerant in
order to achieve high availability for instances.

Node can be added and removed (if they host no instances) at will from
the cluster. In a HA cluster and only with HA instances, the loss of any
single node will not cause disk data loss for any instance; of course,
a node crash will cause the crash of the its primary instances.

A node belonging to a cluster can be in one of the following roles at a
given time:

- *master* node, which is the node from which the cluster is controlled
- *master candidate* node, only nodes in this role have the full cluster
  configuration and knowledge, and only master candidates can become the
  master node
- *regular* node, which is the state in which most nodes will be on
  bigger clusters (>20 nodes)
- *drained* node, nodes in this state are functioning normally but the
  cannot receive new instances; the intention is that nodes in this role
  have some issue and they are being evacuated for hardware repairs
- *offline* node, in which there is a record in the cluster
  configuration about the node, but the daemons on the master node will
  not talk to this node; any instances declared as having an offline
  node as either primary or secondary will be flagged as an error in the
  cluster verify operation

Depending on the role, each node will run a set of daemons:

- the :command:`ganeti-noded` daemon, which control the manipulation of
  this node's hardware resources; it runs on all nodes which are in a
  cluster
- the :command:`ganeti-confd` daemon (Ganeti 2.1+) which runs on all
  nodes, but is only functional on master candidate nodes
- the :command:`ganeti-rapi` daemon which runs on the master node and
  offers an HTTP-based API for the cluster
- the :command:`ganeti-masterd` daemon which runs on the master node and
  allows control of the cluster

Instance
~~~~~~~~

A virtual machine which runs on a cluster. It can be a fault tolerant,
highly available entity.

An instance has various parameters, which are classified in three
categories: hypervisor related-parameters (called ``hvparams``), general
parameters (called ``beparams``) and per network-card parameters (called
``nicparams``). All these parameters can be modified either at instance
level or via defaults at cluster level.

Disk template
~~~~~~~~~~~~~

The are multiple options for the storage provided to an instance; while
the instance sees the same virtual drive in all cases, the node-level
configuration varies between them.

There are four disk templates you can choose from:

diskless
  The instance has no disks. Only used for special purpose operating
  systems or for testing.

file
  The instance will use plain files as backend for its disks. No
  redundancy is provided, and this is somewhat more difficult to
  configure for high performance.

plain
  The instance will use LVM devices as backend for its disks. No
  redundancy is provided.

drbd
  .. note:: This is only valid for multi-node clusters using DRBD 8.0+

  A mirror is set between the local node and a remote one, which must be
  specified with the second value of the --node option. Use this option
  to obtain a highly available instance that can be failed over to a
  remote node should the primary one fail.

IAllocator
~~~~~~~~~~

A framework for using external (user-provided) scripts to compute the
placement of instances on the cluster nodes. This eliminates the need to
manually specify nodes in instance add, instance moves, node evacuate,
etc.

In order for Ganeti to be able to use these scripts, they must be place
in the iallocator directory (usually ``lib/ganeti/iallocators`` under
the installation prefix, e.g. ``/usr/local``).

“Primary” and “secondary” concepts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

An instance has a primary and depending on the disk configuration, might
also have a secondary node. The instance always runs on the primary node
and only uses its secondary node for disk replication.

Similarly, the term of primary and secondary instances when talking
about a node refers to the set of instances having the given node as
primary, respectively secondary.

Tags
~~~~

Tags are short strings that can be attached to either to cluster itself,
or to nodes or instances. They are useful as a very simplistic
information store for helping with cluster administration, for example
by attaching owner information to each instance after it's created::

  gnt-instance add … instance1
  gnt-instance add-tags instance1 owner:user2

And then by listing each instance and its tags, this information could
be used for contacting the users of each instance.

Jobs and OpCodes
~~~~~~~~~~~~~~~~

While not directly visible by an end-user, it's useful to know that a
basic cluster operation (e.g. starting an instance) is represented
internall by Ganeti as an *OpCode* (abbreviation from operation
code). These OpCodes are executed as part of a *Job*. The OpCodes in a
single Job are processed serially by Ganeti, but different Jobs will be
processed (depending on resource availability) in parallel.

For example, shutting down the entire cluster can be done by running the
command ``gnt-instance shutdown --all``, which will submit for each
instance a separate job containing the “shutdown instance” OpCode.


Prerequisites
+++++++++++++

You need to have your Ganeti cluster installed and configured before you
try any of the commands in this document. Please follow the
:doc:`install` for instructions on how to do that.

Instance management
-------------------

Adding an instance
++++++++++++++++++

The add operation might seem complex due to the many parameters it
accepts, but once you have understood the (few) required parameters and
the customisation capabilities you will see it is an easy operation.

The add operation requires at minimum five parameters:

- the OS for the instance
- the disk template
- the disk count and size
- the node specification or alternatively the iallocator to use
- and finally the instance name

The OS for the instance must be visible in the output of the command
``gnt-os list`` and specifies which guest OS to install on the instance.

The disk template specifies what kind of storage to use as backend for
the (virtual) disks presented to the instance; note that for instances
with multiple virtual disks, they all must be of the same type.

The node(s) on which the instance will run can be given either manually,
via the ``-n`` option, or computed automatically by Ganeti, if you have
installed any iallocator script.

With the above parameters in mind, the command is::

  gnt-instance add \
    -n TARGET_NODE:SECONDARY_NODE \
    -o OS_TYPE \
    -t DISK_TEMPLATE -s DISK_SIZE \
    INSTANCE_NAME

The instance name must be resolvable (e.g. exist in DNS) and usually
points to an address in the same subnet as the cluster itself.

The above command has the minimum required options; other options you
can give include, among others:

- The memory size (``-B memory``)

- The number of virtual CPUs (``-B vcpus``)

- Arguments for the NICs of the instance; by default, a single-NIC
  instance is created. The IP and/or bridge of the NIC can be changed
  via ``--nic 0:ip=IP,bridge=BRIDGE``

See the manpage for gnt-instance for the detailed option list.

For example if you want to create an highly available instance, with a
single disk of 50GB and the default memory size, having primary node
``node1`` and secondary node ``node3``, use the following command::

  gnt-instance add -n node1:node3 -o debootstrap -t drbd \
    instance1

There is a also a command for batch instance creation from a
specification file, see the ``batch-create`` operation in the
gnt-instance manual page.

Regular instance operations
+++++++++++++++++++++++++++

Removal
~~~~~~~

Removing an instance is even easier than creating one. This operation is
irreversible and destroys all the contents of your instance. Use with
care::

  gnt-instance remove INSTANCE_NAME

Startup/shutdown
~~~~~~~~~~~~~~~~

Instances are automatically started at instance creation time. To
manually start one which is currently stopped you can run::

  gnt-instance startup INSTANCE_NAME

While the command to stop one is::

  gnt-instance shutdown INSTANCE_NAME

.. warning:: Do not use the Xen or KVM commands directly to stop
   instances. If you run for example ``xm shutdown`` or ``xm destroy``
   on an instance Ganeti will automatically restart it (via the
   :command:`ganeti-watcher` command which is launched via cron).

Querying instances
~~~~~~~~~~~~~~~~~~

There are two ways to get information about instances: listing
instances, which does a tabular output containing a given set of fields
about each instance, and querying detailed information about a set of
instances.

The command to see all the instances configured and their status is::

  gnt-instance list

The command can return a custom set of information when using the ``-o``
option (as always, check the manpage for a detailed specification). Each
instance will be represented on a line, thus making it easy to parse
this output via the usual shell utilities (grep, sed, etc.).

To get more detailed information about an instance, you can run::

  gnt-instance info INSTANCE

which will give a multi-line block of information about the instance,
it's hardware resources (especially its disks and their redundancy
status), etc. This is harder to parse and is more expensive than the
list operation, but returns much more detailed information.


Export/Import
+++++++++++++

You can create a snapshot of an instance disk and its Ganeti
configuration, which then you can backup, or import into another
cluster. The way to export an instance is::

  gnt-backup export -n TARGET_NODE INSTANCE_NAME


The target node can be any node in the cluster with enough space under
``/srv/ganeti`` to hold the instance image. Use the ``--noshutdown``
option to snapshot an instance without rebooting it. Note that Ganeti
only keeps one snapshot for an instance - any previous snapshot of the
same instance existing cluster-wide under ``/srv/ganeti`` will be
removed by this operation: if you want to keep them, you need to move
them out of the Ganeti exports directory.

Importing an instance is similar to creating a new one, but additionally
one must specify the location of the snapshot. The command is::

  gnt-backup import -n TARGET_NODE \
    --src-node=NODE --src-dir=DIR INSTANCE_NAME

By default, parameters will be read from the export information, but you
can of course pass them in via the command line - most of the options
available for the command :command:`gnt-instance add` are supported here
too.

Import of foreign instances
+++++++++++++++++++++++++++

There is a possibility to import a foreign instance whose disk data is
already stored as LVM volumes without going through copying it: the disk
adoption mode.

For this, ensure that the original, non-managed instance is stopped,
then create a Ganeti instance in the usual way, except that instead of
passing the disk information you specify the current volumes::

  gnt-instance add -t plain -n HOME_NODE ... \
    --disk 0:adopt=lv_name INSTANCE_NAME

This will take over the given logical volumes, rename them to the Ganeti
standard (UUID-based), and without installing the OS on them start
directly the instance. If you configure the hypervisor similar to the
non-managed configuration that the instance had, the transition should
be seamless for the instance. For more than one disk, just pass another
disk parameter (e.g. ``--disk 1:adopt=...``).

Instance HA features
--------------------

.. note:: This section only applies to multi-node clusters

.. _instance-change-primary-label:

Changing the primary node
+++++++++++++++++++++++++

There are three ways to exchange an instance's primary and secondary
nodes; the right one to choose depends on how the instance has been
created and the status of its current primary node. See
:ref:`rest-redundancy-label` for information on changing the secondary
node. Note that it's only possible to change the primary node to the
secondary and vice-versa; a direct change of the primary node with a
third node, while keeping the current secondary is not possible in a
single step, only via multiple operations as detailed in
:ref:`instance-relocation-label`.

Failing over an instance
~~~~~~~~~~~~~~~~~~~~~~~~

If an instance is built in highly available mode you can at any time
fail it over to its secondary node, even if the primary has somehow
failed and it's not up anymore. Doing it is really easy, on the master
node you can just run::

  gnt-instance failover INSTANCE_NAME

That's it. After the command completes the secondary node is now the
primary, and vice-versa.

Live migrating an instance
~~~~~~~~~~~~~~~~~~~~~~~~~~

If an instance is built in highly available mode, it currently runs and
both its nodes are running fine, you can at migrate it over to its
secondary node, without downtime. On the master node you need to run::

  gnt-instance migrate INSTANCE_NAME

The current load on the instance and its memory size will influence how
long the migration will take. In any case, for both KVM and Xen
hypervisors, the migration will be transparent to the instance.

Moving an instance (offline)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If an instance has not been create as mirrored, then the only way to
change its primary node is to execute the move command::

  gnt-instance move -n NEW_NODE INSTANCE

This has a few prerequisites:

- the instance must be stopped
- its current primary node must be on-line and healthy
- the disks of the instance must not have any errors

Since this operation actually copies the data from the old node to the
new node, expect it to take proportional to the size of the instance's
disks and the speed of both the nodes' I/O system and their networking.

Disk operations
+++++++++++++++

Disk failures are a common cause of errors in any server
deployment. Ganeti offers protection from single-node failure if your
instances were created in HA mode, and it also offers ways to restore
redundancy after a failure.

Preparing for disk operations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is important to note that for Ganeti to be able to do any disk
operation, the Linux machines on top of which Ganeti must be consistent;
for LVM, this means that the LVM commands must not return failures; it
is common that after a complete disk failure, any LVM command aborts
with an error similar to::

  # vgs
  /dev/sdb1: read failed after 0 of 4096 at 0: Input/output error
  /dev/sdb1: read failed after 0 of 4096 at 750153695232: Input/output
  error
  /dev/sdb1: read failed after 0 of 4096 at 0: Input/output error
  Couldn't find device with uuid
  't30jmN-4Rcf-Fr5e-CURS-pawt-z0jU-m1TgeJ'.
  Couldn't find all physical volumes for volume group xenvg.

Before restoring an instance's disks to healthy status, it's needed to
fix the volume group used by Ganeti so that we can actually create and
manage the logical volumes. This is usually done in a multi-step
process:

#. first, if the disk is completely gone and LVM commands exit with
   “Couldn't find device with uuid…” then you need to run the command::

    vgreduce --removemissing VOLUME_GROUP

#. after the above command, the LVM commands should be executing
   normally (warnings are normal, but the commands will not fail
   completely).

#. if the failed disk is still visible in the output of the ``pvs``
   command, you need to deactivate it from allocations by running::

    pvs -x n /dev/DISK

At this point, the volume group should be consistent and any bad
physical volumes should not longer be available for allocation.

Note that since version 2.1 Ganeti provides some commands to automate
these two operations, see :ref:`storage-units-label`.

.. _rest-redundancy-label:

Restoring redundancy for DRBD-based instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A DRBD instance has two nodes, and the storage on one of them has
failed. Depending on which node (primary or secondary) has failed, you
have three options at hand:

- if the storage on the primary node has failed, you need to re-create
  the disks on it
- if the storage on the secondary node has failed, you can either
  re-create the disks on it or change the secondary and recreate
  redundancy on the new secondary node

Of course, at any point it's possible to force re-creation of disks even
though everything is already fine.

For all three cases, the ``replace-disks`` operation can be used::

  # re-create disks on the primary node
  gnt-instance replace-disks -p INSTANCE_NAME
  # re-create disks on the current secondary
  gnt-instance replace-disks -s INSTANCE_NAME
  # change the secondary node, via manual specification
  gnt-instance replace-disks -n NODE INSTANCE_NAME
  # change the secondary node, via an iallocator script
  gnt-instance replace-disks -I SCRIPT INSTANCE_NAME
  # since Ganeti 2.1: automatically fix the primary or secondary node
  gnt-instance replace-disks -a INSTANCE_NAME

Since the process involves copying all data from the working node to the
target node, it will take a while, depending on the instance's disk
size, node I/O system and network speed. But it is (baring any network
interruption) completely transparent for the instance.

Re-creating disks for non-redundant instances
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 2.1

For non-redundant instances, there isn't a copy (except backups) to
re-create the disks. But it's possible to at-least re-create empty
disks, after which a reinstall can be run, via the ``recreate-disks``
command::

  gnt-instance recreate-disks INSTANCE

Note that this will fail if the disks already exists.

Conversion of an instance's disk type
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is possible to convert between a non-redundant instance of type
``plain`` (LVM storage) and redundant ``drbd`` via the ``gnt-instance
modify`` command::

  # start with a non-redundant instance
  gnt-instance add -t plain ... INSTANCE

  # later convert it to redundant
  gnt-instance stop INSTANCE
  gnt-instance modify -t drbd INSTANCE
  gnt-instance start INSTANCE

  # and convert it back
  gnt-instance stop INSTANCE
  gnt-instance modify -t plain INSTANCE
  gnt-instance start INSTANCE

The conversion must be done while the instance is stopped, and
converting from plain to drbd template presents a small risk, especially
if the instance has multiple disks and/or if one node fails during the
conversion procedure). As such, it's recommended (as always) to make
sure that downtime for manual recovery is acceptable and that the
instance has up-to-date backups.

Debugging instances
+++++++++++++++++++

Accessing an instance's disks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

From an instance's primary node you can have access to its disks. Never
ever mount the underlying logical volume manually on a fault tolerant
instance, or will break replication and your data will be
inconsistent. The correct way to access an instance's disks is to run
(on the master node, as usual) the command::

  gnt-instance activate-disks INSTANCE

And then, *on the primary node of the instance*, access the device that
gets created. For example, you could mount the given disks, then edit
files on the filesystem, etc.

Note that with partitioned disks (as opposed to whole-disk filesystems),
you will need to use a tool like :manpage:`kpartx(8)`::

  node1# gnt-instance activate-disks instance1
  …
  node1# ssh node3
  node3# kpartx -l /dev/…
  node3# kpartx -a /dev/…
  node3# mount /dev/mapper/… /mnt/
  # edit files under mnt as desired
  node3# umount /mnt/
  node3# kpartx -d /dev/…
  node3# exit
  node1#

After you've finished you can deactivate them with the deactivate-disks
command, which works in the same way::

  gnt-instance deactivate-disks INSTANCE

Note that if any process started by you is still using the disks, the
above command will error out, and you **must** cleanup and ensure that
the above command runs successfully before you start the instance,
otherwise the instance will suffer corruption.

Accessing an instance's console
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The command to access a running instance's console is::

  gnt-instance console INSTANCE_NAME

Use the console normally and then type ``^]`` when done, to exit.

Other instance operations
+++++++++++++++++++++++++

Reboot
~~~~~~

There is a wrapper command for rebooting instances::

  gnt-instance reboot instance2

By default, this does the equivalent of shutting down and then starting
the instance, but it accepts parameters to perform a soft-reboot (via
the hypervisor), a hard reboot (hypervisor shutdown and then startup) or
a full one (the default, which also de-configures and then configures
again the disks of the instance).

Instance OS definitions debugging
+++++++++++++++++++++++++++++++++

Should you have any problems with instance operating systems the command
to see a complete status for all your nodes is::

   gnt-os diagnose

.. _instance-relocation-label:

Instance relocation
~~~~~~~~~~~~~~~~~~~

While it is not possible to move an instance from nodes ``(A, B)`` to
nodes ``(C, D)`` in a single move, it is possible to do so in a few
steps::

  # instance is located on A, B
  node1# gnt-instance replace -n nodeC instance1
  # instance has moved from (A, B) to (A, C)
  # we now flip the primary/secondary nodes
  node1# gnt-instance migrate instance1
  # instance lives on (C, A)
  # we can then change A to D via:
  node1# gnt-instance replace -n nodeD instance1

Which brings it into the final configuration of ``(C, D)``. Note that we
needed to do two replace-disks operation (two copies of the instance
disks), because we needed to get rid of both the original nodes (A and
B).

Node operations
---------------

There are much fewer node operations available than for instances, but
they are equivalently important for maintaining a healthy cluster.

Add/readd
+++++++++

It is at any time possible to extend the cluster with one more node, by
using the node add operation::

  gnt-node add NEW_NODE

If the cluster has a replication network defined, then you need to pass
the ``-s REPLICATION_IP`` parameter to this option.

A variation of this command can be used to re-configure a node if its
Ganeti configuration is broken, for example if it has been reinstalled
by mistake::

  gnt-node add --readd EXISTING_NODE

This will reinitialise the node as if it's been newly added, but while
keeping its existing configuration in the cluster (primary/secondary IP,
etc.), in other words you won't need to use ``-s`` here.

Changing the node role
++++++++++++++++++++++

A node can be in different roles, as explained in the
:ref:`terminology-label` section. Promoting a node to the master role is
special, while the other roles are handled all via a single command.

Failing over the master node
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to promote a different node to the master role (for whatever
reason), run on any other master-candidate node the command::

  gnt-cluster master-failover

and the node you ran it on is now the new master. In case you try to run
this on a non master-candidate node, you will get an error telling you
which nodes are valid.

Changing between the other roles
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``gnt-node modify`` command can be used to select a new role::

  # change to master candidate
  gnt-node modify -C yes NODE
  # change to drained status
  gnt-node modify -D yes NODE
  # change to offline status
  gnt-node modify -O yes NODE
  # change to regular mode (reset all flags)
  gnt-node modify -O no -D no -C no NODE

Note that the cluster requires that at any point in time, a certain
number of nodes are master candidates, so changing from master candidate
to other roles might fail. It is recommended to either force the
operation (via the ``--force`` option) or first change the number of
master candidates in the cluster - see :ref:`cluster-config-label`.

Evacuating nodes
++++++++++++++++

There are two steps of moving instances off a node:

- moving the primary instances (actually converting them into secondary
  instances)
- moving the secondary instances (including any instances converted in
  the step above)

Primary instance conversion
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For this step, you can use either individual instance move
commands (as seen in :ref:`instance-change-primary-label`) or the bulk
per-node versions; these are::

  gnt-node migrate NODE
  gnt-node evacuate NODE

Note that the instance “move” command doesn't currently have a node
equivalent.

Both these commands, or the equivalent per-instance command, will make
this node the secondary node for the respective instances, whereas their
current secondary node will become primary. Note that it is not possible
to change in one step the primary node to another node as primary, while
keeping the same secondary node.

Secondary instance evacuation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For the evacuation of secondary instances, a command called
:command:`gnt-node evacuate` is provided and its syntax is::

  gnt-node evacuate -I IALLOCATOR_SCRIPT NODE
  gnt-node evacuate -n DESTINATION_NODE NODE

The first version will compute the new secondary for each instance in
turn using the given iallocator script, whereas the second one will
simply move all instances to DESTINATION_NODE.

Removal
+++++++

Once a node no longer has any instances (neither primary nor secondary),
it's easy to remove it from the cluster::

  gnt-node remove NODE_NAME

This will deconfigure the node, stop the ganeti daemons on it and leave
it hopefully like before it joined to the cluster.

Storage handling
++++++++++++++++

When using LVM (either standalone or with DRBD), it can become tedious
to debug and fix it in case of errors. Furthermore, even file-based
storage can become complicated to handle manually on many hosts. Ganeti
provides a couple of commands to help with automation.

Logical volumes
~~~~~~~~~~~~~~~

This is a command specific to LVM handling. It allows listing the
logical volumes on a given node or on all nodes and their association to
instances via the ``volumes`` command::

  node1# gnt-node volumes
  Node  PhysDev   VG    Name             Size Instance
  node1 /dev/sdb1 xenvg e61fbc97-….disk0 512M instance17
  node1 /dev/sdb1 xenvg ebd1a7d1-….disk0 512M instance19
  node2 /dev/sdb1 xenvg 0af08a3d-….disk0 512M instance20
  node2 /dev/sdb1 xenvg cc012285-….disk0 512M instance16
  node2 /dev/sdb1 xenvg f0fac192-….disk0 512M instance18

The above command maps each logical volume to a volume group and
underlying physical volume and (possibly) to an instance.

.. _storage-units-label:

Generalized storage handling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. versionadded:: 2.1

Starting with Ganeti 2.1, a new storage framework has been implemented
that tries to abstract the handling of the storage type the cluster
uses.

First is listing the backend storage and their space situation::

  node1# gnt-node list-storage
  Node  Name        Size Used   Free
  node1 /dev/sda7 673.8G   0M 673.8G
  node1 /dev/sdb1 698.6G 1.5G 697.1G
  node2 /dev/sda7 673.8G   0M 673.8G
  node2 /dev/sdb1 698.6G 1.0G 697.6G

The default is to list LVM physical volumes. It's also possible to list
the LVM volume groups::

  node1# gnt-node list-storage -t lvm-vg
  Node  Name  Size
  node1 xenvg 1.3T
  node2 xenvg 1.3T

Next is repairing storage units, which is currently only implemented for
volume groups and does the equivalent of ``vgreduce --removemissing``::

  node1# gnt-node repair-storage node2 lvm-vg xenvg
  Sun Oct 25 22:21:45 2009 Repairing storage unit 'xenvg' on node2 ...

Last is the modification of volume properties, which is (again) only
implemented for LVM physical volumes and allows toggling the
``allocatable`` value::

  node1# gnt-node modify-storage --allocatable=no node2 lvm-pv /dev/sdb1

Use of the storage commands
~~~~~~~~~~~~~~~~~~~~~~~~~~~

All these commands are needed when recovering a node from a disk
failure:

- first, we need to recover from complete LVM failure (due to missing
  disk), by running the ``repair-storage`` command
- second, we need to change allocation on any partially-broken disk
  (i.e. LVM still sees it, but it has bad blocks) by running
  ``modify-storage``
- then we can evacuate the instances as needed


Cluster operations
------------------

Beside the cluster initialisation command (which is detailed in the
:doc:`install` document) and the master failover command which is
explained under node handling, there are a couple of other cluster
operations available.

.. _cluster-config-label:

Standard operations
+++++++++++++++++++

One of the few commands that can be run on any node (not only the
master) is the ``getmaster`` command::

  node2# gnt-cluster getmaster
  node1.example.com
  node2#

It is possible to query and change global cluster parameters via the
``info`` and ``modify`` commands::

  node1# gnt-cluster info
  Cluster name: cluster.example.com
  Cluster UUID: 07805e6f-f0af-4310-95f1-572862ee939c
  Creation time: 2009-09-25 05:04:15
  Modification time: 2009-10-18 22:11:47
  Master node: node1.example.com
  Architecture (this node): 64bit (x86_64)
  …
  Tags: foo
  Default hypervisor: xen-pvm
  Enabled hypervisors: xen-pvm
  Hypervisor parameters:
    - xen-pvm:
        root_path: /dev/sda1
        …
  Cluster parameters:
    - candidate pool size: 10
      …
  Default instance parameters:
    - default:
        memory: 128
        …
  Default nic parameters:
    - default:
        link: xen-br0
        …

There various parameters above can be changed via the ``modify``
commands as follows:

- the hypervisor parameters can be changed via ``modify -H
  xen-pvm:root_path=…``, and so on for other hypervisors/key/values
- the "default instance parameters" are changeable via ``modify -B
  parameter=value…`` syntax
- the cluster parameters are changeable via separate options to the
  modify command (e.g. ``--candidate-pool-size``, etc.)

For detailed option list see the :manpage:`gnt-cluster(8)` man page.

The cluster version can be obtained via the ``version`` command::
  node1# gnt-cluster version
  Software version: 2.1.0
  Internode protocol: 20
  Configuration format: 2010000
  OS api version: 15
  Export interface: 0

This is not very useful except when debugging Ganeti.

Global node commands
++++++++++++++++++++

There are two commands provided for replicating files to all nodes of a
cluster and for running commands on all the nodes::

  node1# gnt-cluster copyfile /path/to/file
  node1# gnt-cluster command ls -l /path/to/file

These are simple wrappers over scp/ssh and more advanced usage can be
obtained using :manpage:`dsh(1)` and similar commands. But they are
useful to update an OS script from the master node, for example.

Cluster verification
++++++++++++++++++++

There are three commands that relate to global cluster checks. The first
one is ``verify`` which gives an overview on the cluster state,
highlighting any issues. In normal operation, this command should return
no ``ERROR`` messages::

  node1# gnt-cluster verify
  Sun Oct 25 23:08:58 2009 * Verifying global settings
  Sun Oct 25 23:08:58 2009 * Gathering data (2 nodes)
  Sun Oct 25 23:09:00 2009 * Verifying node status
  Sun Oct 25 23:09:00 2009 * Verifying instance status
  Sun Oct 25 23:09:00 2009 * Verifying orphan volumes
  Sun Oct 25 23:09:00 2009 * Verifying remaining instances
  Sun Oct 25 23:09:00 2009 * Verifying N+1 Memory redundancy
  Sun Oct 25 23:09:00 2009 * Other Notes
  Sun Oct 25 23:09:00 2009   - NOTICE: 5 non-redundant instance(s) found.
  Sun Oct 25 23:09:00 2009 * Hooks Results

The second command is ``verify-disks``, which checks that the instance's
disks have the correct status based on the desired instance state
(up/down)::

  node1# gnt-cluster verify-disks

Note that this command will show no output when disks are healthy.

The last command is used to repair any discrepancies in Ganeti's
recorded disk size and the actual disk size (disk size information is
needed for proper activation and growth of DRBD-based disks)::

  node1# gnt-cluster repair-disk-sizes
  Sun Oct 25 23:13:16 2009  - INFO: Disk 0 of instance instance1 has mismatched size, correcting: recorded 512, actual 2048
  Sun Oct 25 23:13:17 2009  - WARNING: Invalid result from node node4, ignoring node results

The above shows one instance having wrong disk size, and a node which
returned invalid data, and thus we ignored all primary instances of that
node.

Configuration redistribution
++++++++++++++++++++++++++++

If the verify command complains about file mismatches between the master
and other nodes, due to some node problems or if you manually modified
configuration files, you can force an push of the master configuration
to all other nodes via the ``redist-conf`` command::

  node1# gnt-cluster redist-conf
  node1#

This command will be silent unless there are problems sending updates to
the other nodes.


Cluster renaming
++++++++++++++++

It is possible to rename a cluster, or to change its IP address, via the
``rename`` command. If only the IP has changed, you need to pass the
current name and Ganeti will realise its IP has changed::

  node1# gnt-cluster rename cluster.example.com
  This will rename the cluster to 'cluster.example.com'. If
  you are connected over the network to the cluster name, the operation
  is very dangerous as the IP address will be removed from the node and
  the change may not go through. Continue?
  y/[n]/?: y
  Failure: prerequisites not met for this operation:
  Neither the name nor the IP address of the cluster has changed

In the above output, neither value has changed since the cluster
initialisation so the operation is not completed.

Queue operations
++++++++++++++++

The job queue execution in Ganeti 2.0 and higher can be inspected,
suspended and resumed via the ``queue`` command::

  node1~# gnt-cluster queue info
  The drain flag is unset
  node1~# gnt-cluster queue drain
  node1~# gnt-instance stop instance1
  Failed to submit job for instance1: Job queue is drained, refusing job
  node1~# gnt-cluster queue info
  The drain flag is set
  node1~# gnt-cluster queue undrain

This is most useful if you have an active cluster and you need to
upgrade the Ganeti software, or simply restart the software on any node:

#. suspend the queue via ``queue drain``
#. wait until there are no more running jobs via ``gnt-job list``
#. restart the master or another node, or upgrade the software
#. resume the queue via ``queue undrain``

.. note:: this command only stores a local flag file, and if you
   failover the master, it will not have effect on the new master.


Watcher control
+++++++++++++++

The :manpage:`ganeti-watcher` is a program, usually scheduled via
``cron``, that takes care of cluster maintenance operations (restarting
downed instances, activating down DRBD disks, etc.). However, during
maintenance and troubleshooting, this can get in your way; disabling it
via commenting out the cron job is not so good as this can be
forgotten. Thus there are some commands for automated control of the
watcher: ``pause``, ``info`` and ``continue``::

  node1~# gnt-cluster watcher info
  The watcher is not paused.
  node1~# gnt-cluster watcher pause 1h
  The watcher is paused until Mon Oct 26 00:30:37 2009.
  node1~# gnt-cluster watcher info
  The watcher is paused until Mon Oct 26 00:30:37 2009.
  node1~# ganeti-watcher -d
  2009-10-25 23:30:47,984:  pid=28867 ganeti-watcher:486 DEBUG Pause has been set, exiting
  node1~# gnt-cluster watcher continue
  The watcher is no longer paused.
  node1~# ganeti-watcher -d
  2009-10-25 23:31:04,789:  pid=28976 ganeti-watcher:345 DEBUG Archived 0 jobs, left 0
  2009-10-25 23:31:05,884:  pid=28976 ganeti-watcher:280 DEBUG Got data from cluster, writing instance status file
  2009-10-25 23:31:06,061:  pid=28976 ganeti-watcher:150 DEBUG Data didn't change, just touching status file
  node1~# gnt-cluster watcher info
  The watcher is not paused.
  node1~#

The exact details of the argument to the ``pause`` command are available
in the manpage.

.. note:: this command only stores a local flag file, and if you
   failover the master, it will not have effect on the new master.

Node auto-maintenance
+++++++++++++++++++++

If the cluster parameter ``maintain_node_health`` is enabled (see the
manpage for :command:`gnt-cluster`, the init and modify subcommands),
then the following will happen automatically:

- the watcher will shutdown any instances running on offline nodes
- the watcher will deactivate any DRBD devices on offline nodes

In the future, more actions are planned, so only enable this parameter
if the nodes are completely dedicated to Ganeti; otherwise it might be
possible to lose data due to auto-maintenance actions.

Removing a cluster entirely
+++++++++++++++++++++++++++

The usual method to cleanup a cluster is to run ``gnt-cluster destroy``
however if the Ganeti installation is broken in any way then this will
not run.

It is possible in such a case to cleanup manually most if not all traces
of a cluster installation by following these steps on all of the nodes:

1. Shutdown all instances. This depends on the virtualisation method
   used (Xen, KVM, etc.):

  - Xen: run ``xm list`` and ``xm destroy`` on all the non-Domain-0
    instances
  - KVM: kill all the KVM processes
  - chroot: kill all processes under the chroot mountpoints

2. If using DRBD, shutdown all DRBD minors (which should by at this time
   no-longer in use by instances); on each node, run ``drbdsetup
   /dev/drbdN down`` for each active DRBD minor.

3. If using LVM, cleanup the Ganeti volume group; if only Ganeti created
   logical volumes (and you are not sharing the volume group with the
   OS, for example), then simply running ``lvremove -f xenvg`` (replace
   'xenvg' with your volume group name) should do the required cleanup.

4. If using file-based storage, remove recursively all files and
   directories under your file-storage directory: ``rm -rf
   /srv/ganeti/file-storage/*`` replacing the path with the correct path
   for your cluster.

5. Stop the ganeti daemons (``/etc/init.d/ganeti stop``) and kill any
   that remain alive (``pgrep ganeti`` and ``pkill ganeti``).

6. Remove the ganeti state directory (``rm -rf /var/lib/ganeti/*``),
   replacing the path with the correct path for your installation.

On the master node, remove the cluster from the master-netdev (usually
``xen-br0`` for bridged mode, otherwise ``eth0`` or similar), by running
``ip a del $clusterip/32 dev xen-br0`` (use the correct cluster ip and
network device name).

At this point, the machines are ready for a cluster creation; in case
you want to remove Ganeti completely, you need to also undo some of the
SSH changes and log directories:

- ``rm -rf /var/log/ganeti /srv/ganeti`` (replace with the correct
  paths)
- remove from ``/root/.ssh`` the keys that Ganeti added (check the
  ``authorized_keys`` and ``id_dsa`` files)
- regenerate the host's SSH keys (check the OpenSSH startup scripts)
- uninstall Ganeti

Otherwise, if you plan to re-create the cluster, you can just go ahead
and rerun ``gnt-cluster init``.

Tags handling
-------------

The tags handling (addition, removal, listing) is similar for all the
objects that support it (instances, nodes, and the cluster).

Limitations
+++++++++++

Note that the set of characters present in a tag and the maximum tag
length are restricted. Currently the maximum length is 128 characters,
there can be at most 4096 tags per object, and the set of characters is
comprised by alphanumeric characters and additionally ``.+*/:-``.

Operations
++++++++++

Tags can be added via ``add-tags``::

  gnt-instance add-tags INSTANCE a b c
  gnt-node add-tags INSTANCE a b c
  gnt-cluster add-tags a b c


The above commands add three tags to an instance, to a node and to the
cluster. Note that the cluster command only takes tags as arguments,
whereas the node and instance commands first required the node and
instance name.

Tags can also be added from a file, via the ``--from=FILENAME``
argument. The file is expected to contain one tag per line.

Tags can also be remove via a syntax very similar to the add one::

  gnt-instance remove-tags INSTANCE a b c

And listed via::

  gnt-instance list-tags
  gnt-node list-tags
  gnt-cluster list-tags

Global tag search
+++++++++++++++++

It is also possible to execute a global search on the all tags defined
in the cluster configuration, via a cluster command::

  gnt-cluster search-tags REGEXP

The parameter expected is a regular expression (see
:manpage:`regex(7)`). This will return all tags that match the search,
together with the object they are defined in (the names being show in a
hierarchical kind of way)::

  node1# gnt-cluster search-tags o
  /cluster foo
  /instances/instance1 owner:bar


Job operations
--------------

The various jobs submitted by the instance/node/cluster commands can be
examined, canceled and archived by various invocations of the
``gnt-job`` command.

First is the job list command::

  node1# gnt-job list
  17771 success INSTANCE_QUERY_DATA
  17773 success CLUSTER_VERIFY_DISKS
  17775 success CLUSTER_REPAIR_DISK_SIZES
  17776 error   CLUSTER_RENAME(cluster.example.com)
  17780 success CLUSTER_REDIST_CONF
  17792 success INSTANCE_REBOOT(instance1.example.com)

More detailed information about a job can be found via the ``info``
command::

  node1# gnt-job info 17776
  Job ID: 17776
    Status: error
    Received:         2009-10-25 23:18:02.180569
    Processing start: 2009-10-25 23:18:02.200335 (delta 0.019766s)
    Processing end:   2009-10-25 23:18:02.279743 (delta 0.079408s)
    Total processing time: 0.099174 seconds
    Opcodes:
      OP_CLUSTER_RENAME
        Status: error
        Processing start: 2009-10-25 23:18:02.200335
        Processing end:   2009-10-25 23:18:02.252282
        Input fields:
          name: cluster.example.com
        Result:
          OpPrereqError
          [Neither the name nor the IP address of the cluster has changed]
        Execution log:

During the execution of a job, it's possible to follow the output of a
job, similar to the log that one get from the ``gnt-`` commands, via the
watch command::

  node1# gnt-instance add --submit … instance1
  JobID: 17818
  node1# gnt-job watch 17818
  Output from job 17818 follows
  -----------------------------
  Mon Oct 26 00:22:48 2009  - INFO: Selected nodes for instance instance1 via iallocator dumb: node1, node2
  Mon Oct 26 00:22:49 2009 * creating instance disks...
  Mon Oct 26 00:22:52 2009 adding instance instance1 to cluster config
  Mon Oct 26 00:22:52 2009  - INFO: Waiting for instance instance1 to sync disks.
  …
  Mon Oct 26 00:23:03 2009 creating os for instance instance1 on node node1
  Mon Oct 26 00:23:03 2009 * running the instance OS create scripts...
  Mon Oct 26 00:23:13 2009 * starting instance...
  node1#

This is useful if you need to follow a job's progress from multiple
terminals.

A job that has not yet started to run can be canceled::

  node1# gnt-job cancel 17810

But not one that has already started execution::

  node1# gnt-job cancel 17805
  Job 17805 is no longer waiting in the queue

There are two queues for jobs: the *current* and the *archive*
queue. Jobs are initially submitted to the current queue, and they stay
in that queue until they have finished execution (either successfully or
not). At that point, they can be moved into the archive queue, and the
ganeti-watcher script will do this automatically after 6 hours. The
ganeti-cleaner script will remove the jobs from the archive directory
after three weeks.

Note that only jobs in the current queue can be viewed via the list and
info commands; Ganeti itself doesn't examine the archive directory. If
you need to see an older job, either move the file manually in the
top-level queue directory, or look at its contents (it's a
JSON-formatted file).

Ganeti tools
------------

Beside the usual ``gnt-`` and ``ganeti-`` commands which are provided
and installed in ``$prefix/sbin`` at install time, there are a couple of
other tools installed which are used seldom but can be helpful in some
cases.

lvmstrap
++++++++

The ``lvmstrap`` tool, introduced in :ref:`configure-lvm-label` section,
has two modes of operation:

- ``diskinfo`` shows the discovered disks on the system and their status
- ``create`` takes all not-in-use disks and creates a volume group out
  of them

.. warning:: The ``create`` argument to this command causes data-loss!

cfgupgrade
++++++++++

The ``cfgupgrade`` tools is used to upgrade between major (and minor)
Ganeti versions. Point-releases are usually transparent for the admin.

More information about the upgrade procedure is listed on the wiki at
http://code.google.com/p/ganeti/wiki/UpgradeNotes.

There is also a script designed to upgrade from Ganeti 1.2 to 2.0,
called ``cfgupgrade12``.

cfgshell
++++++++

.. note:: This command is not actively maintained; make sure you backup
   your configuration before using it

This can be used as an alternative to direct editing of the
main configuration file if Ganeti has a bug and prevents you, for
example, from removing an instance or a node from the configuration
file.

.. _burnin-label:

burnin
++++++

.. warning:: This command will erase existing instances if given as
   arguments!

This tool is used to exercise either the hardware of machines or
alternatively the Ganeti software. It is safe to run on an existing
cluster **as long as you don't pass it existing instance names**.

The command will, by default, execute a comprehensive set of operations
against a list of instances, these being:

- creation
- disk replacement (for redundant instances)
- failover and migration (for redundant instances)
- move (for non-redundant instances)
- disk growth
- add disks, remove disk
- add NICs, remove NICs
- export and then import
- rename
- reboot
- shutdown/startup
- and finally removal of the test instances

Executing all these operations will test that the hardware performs
well: the creation, disk replace, disk add and disk growth will exercise
the storage and network; the migrate command will test the memory of the
systems. Depending on the passed options, it can also test that the
instance OS definitions are executing properly the rename, import and
export operations.

sanitize-config
+++++++++++++++

This tool takes the Ganeti configuration and outputs a "sanitized"
version, by randomizing or clearing:

- DRBD secrets and cluster public key (always)
- host names (optional)
- IPs (optional)
- OS names (optional)
- LV names (optional, only useful for very old clusters which still have
  instances whose LVs are based on the instance name)

By default, all optional items are activated except the LV name
randomization. When passing ``--no-randomization``, which disables the
optional items (i.e. just the DRBD secrets and cluster public keys are
randomized), the resulting file can be used as a safety copy of the
cluster config - while not trivial, the layout of the cluster can be
recreated from it and if the instance disks have not been lost it
permits recovery from the loss of all master candidates.

move-instance
+++++++++++++

See :doc:`separate documentation for move-instance <move-instance>`.

.. TODO: document cluster-merge tool


Other Ganeti projects
---------------------

There are two other Ganeti-related projects that can be useful in a
Ganeti deployment. These can be downloaded from the project site
(http://code.google.com/p/ganeti/) and the repositories are also on the
project git site (http://git.ganeti.org).

NBMA tools
++++++++++

The ``ganeti-nbma`` software is designed to allow instances to live on a
separate, virtual network from the nodes, and in an environment where
nodes are not guaranteed to be able to reach each other via multicasting
or broadcasting. For more information see the README in the source
archive.

ganeti-htools
+++++++++++++

The ``ganeti-htools`` software consists of a set of tools:

- ``hail``: an advanced iallocator script compared to Ganeti's builtin
  one
- ``hbal``: a tool for rebalancing the cluster, i.e. moving instances
  around in order to better use the resources on the nodes
- ``hspace``: a tool for estimating the available capacity of a cluster,
  so that capacity planning can be done efficiently

For more information and installation instructions, see the README file
in the source archive.

.. vim: set textwidth=72 :
.. Local Variables:
.. mode: rst
.. fill-column: 72
.. End:
