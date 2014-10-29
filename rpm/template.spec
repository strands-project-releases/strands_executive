Name:           ros-hydro-scipoptsuite
Version:        0.0.3
Release:        0%{?dist}
Summary:        ROS scipoptsuite package

Group:          Development/Libraries
License:        ZIB Academic License
URL:            http://scip.zib.de
Source0:        %{name}-%{version}.tar.gz

Requires:       gmp-devel
Requires:       ncurses-devel
Requires:       zlib-devel
BuildRequires:  gmp-devel
BuildRequires:  ncurses-devel
BuildRequires:  ros-hydro-catkin
BuildRequires:  zlib-devel

%description
This installs version 3.0.2 of SCIP optimisation suite.

%prep
%setup -q

%build
# In case we're installing to a non-standard location, look for a setup.sh
# in the install tree that was dropped by catkin, and source it.  It will
# set things like CMAKE_PREFIX_PATH, PKG_CONFIG_PATH, and PYTHONPATH.
if [ -f "/opt/ros/hydro/setup.sh" ]; then . "/opt/ros/hydro/setup.sh"; fi
mkdir -p build && cd build
%cmake .. \
        -UINCLUDE_INSTALL_DIR \
        -ULIB_INSTALL_DIR \
        -USYSCONF_INSTALL_DIR \
        -USHARE_INSTALL_PREFIX \
        -ULIB_SUFFIX \
        -DCMAKE_INSTALL_PREFIX="/opt/ros/hydro" \
        -DCMAKE_PREFIX_PATH="/opt/ros/hydro" \
        -DSETUPTOOLS_DEB_LAYOUT=OFF \
        -DCATKIN_BUILD_BINARY_PACKAGE="1" \

make %{?_smp_mflags}

%install
# In case we're installing to a non-standard location, look for a setup.sh
# in the install tree that was dropped by catkin, and source it.  It will
# set things like CMAKE_PREFIX_PATH, PKG_CONFIG_PATH, and PYTHONPATH.
if [ -f "/opt/ros/hydro/setup.sh" ]; then . "/opt/ros/hydro/setup.sh"; fi
cd build
make %{?_smp_mflags} install DESTDIR=%{buildroot}

%files
/opt/ros/hydro

%changelog
* Wed Oct 29 2014 Nick Hawes <n.a.hawes@cs.bham.ac.uk> - 0.0.3-0
- Autogenerated by Bloom

* Wed Oct 29 2014 Nick Hawes <n.a.hawes@cs.bham.ac.uk> - 0.0.1-2
- Autogenerated by Bloom

* Fri Oct 24 2014 Nick Hawes <n.a.hawes@cs.bham.ac.uk> - 0.0.1-1
- Autogenerated by Bloom

* Fri Oct 24 2014 Nick Hawes <n.a.hawes@cs.bham.ac.uk> - 0.0.1-0
- Autogenerated by Bloom

