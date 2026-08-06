Name:           liquid-devil-rgb
Version:        1.0.0
Release:        1%{?dist}
Summary:        Linux I2C RGB Lighting Control for PowerColor Radeon RX 7900 XTX Liquid Devil

License:        MIT
URL:            https://github.com/shanefagan/liquid_devil_linux_rgb
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-hatchling
Requires:       python3
Requires:       python3-click
Requires:       i2c-tools

%description
Reverse-engineered hardware protocol implementation for the PowerColor Radeon RX
7900 XTX Liquid Devil V2 I2C RGB microcontroller (0x22). Includes OpenRGB SDK
sync client for real-time PC lighting mirroring at 30 FPS.

%prep
%autosetup

%build
%py3_build

%install
%py3_install

%files
%license LICENSE
%doc README.md PROTOCOL.md
%{_bindir}/liquid-devil-rgb
%{python3_sitelib}/liquid_devil_rgb/
%{python3_sitelib}/liquid_devil_rgb-*.egg-info/

%changelog
* Thu Aug 06 2026 Shane Fagan <shane@performativenonsense.com> - 1.0.0-1
- Initial RPM release
