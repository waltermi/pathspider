Installation
============

Debian GNU/Linux
----------------

PATHspider is packaged for Debian and packages are made available for the
testing and stable-backports distributions. If you are running Debian stable,
ensure that you have `enabled the stable-backports repository
<https://backports.debian.org/Instructions/>`_ in your apt sources.

To install PATHspider, simply run:

.. code-block:: shell

  sudo apt install pathspider

Source
------

If you are working from the source distribution (e.g. cloned git repository)
then you will need to install the required dependencies. On Debian GNU/Linux,
assuming you have the stable-backports repository enabled if you are running
stable:

.. code-block:: shell

  sudo apt build-dep pathspider

.. note:: This will install both the runtime and the build dependencies required
          for PATHspider, its testsuite and its documentation.

On other platforms, you may install the dependencies required via pip:

.. code-block:: shell

 pip install -r requirements.txt

If you wish to build the documentation from source or to use the testsuite, and
you are installing your dependencies via pip, you will also need the following
dependencies:

.. code-block:: shell

 pip install -r requirements_dev.txt

With the dependencies installed, you can install PATHspider with:

.. code-block:: shell

 python3 setup.py install
