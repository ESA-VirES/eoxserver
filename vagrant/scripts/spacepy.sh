#!/bin/sh -e


# Install necessary dependencies
sudo yum -y install python-devel numpy scipy python-matplotlib  h5py \
				 libgfortran gcc-gfortran ncurses-devel ncurses-libs

sudo yum -y groupinstall "Development Tools"

sudo easy_install -q networkx

# CDF35 installation
# ------------------------------------------------------------------------------------------------------

# Download cdf35 to tmp for building
cd /tmp/

wget http://cdaweb.gsfc.nasa.gov/pub/software/cdf/dist/cdf35_0_2/linux/cdf35_0-dist-cdf.tar.gz
tar xvf cdf35_0-dist-cdf.tar.gz


cd cdf35_0-dist

make OS=linux ENV=gnu CURSES=yes FORTRAN=no UCOPTIONS=-O2 SHARED=yes all

# SpacePy  expects this cdf-stuff in /usr/local/cdf  but the make install (which will actually install it 
# in the cdf35_0-dist dir) has to be changed;
sudo make INSTALLDIR=/usr/local/cdf install

# To allow CDF command-line utilitites add to bashrc
cat >> /home/vagrant/.bashrc <<END
if [ -s /usr/local/cdf/bin/definitions.B ]; then
    source /usr/local/cdf/bin/definitions.B
fi
END

#modify entry in /usr/local/cdf/bin/definitions.B 
sudo sed -e 's/^setenv LD_LIBRARY_PATH$/export LD_LIBRARY_PAT/' -i /usr/local/cdf/bin/definitions.B 

source /usr/local/cdf/bin/definitions.B


# ffnet installation
# ------------------------------------------------------------------------------------------------------
sudo easy_install -q ffnet



# SpacePy installation
# ------------------------------------------------------------------------------------------------------

# Get SpacePy
cd /tmp/
wget http://heanet.dl.sourceforge.net/project/spacepy/spacepy/spacepy-0.1.4/spacepy-0.1.4.tar.gz
tar xvf spacepy-0.1.4.tar.gz
cd spacepy-0.1.4

#Configure and install
python setup.py build
sudo python setup.py install

python -c "import spacepy.toolbox; spacepy.toolbox.update()"