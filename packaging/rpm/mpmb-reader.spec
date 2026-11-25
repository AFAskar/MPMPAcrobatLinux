%global debug_package %{nil}
%global _build_id_links none
%global __provides_exclude ^libpdfium\\.so.*$
%global __requires_exclude ^libpdfium\\.so.*$

Name:           mpmb-reader
Version:        %{?_version}%{!?_version:0.1.0}
Release:        1%{?dist}
Summary:        Native desktop reader for MPMB interactive PDF character sheets
License:        AGPL-3.0-or-later AND BSD-3-Clause
URL:            https://github.com/AFAskar/MPMPAcrobatLinux
ExclusiveArch:  x86_64

Requires:       zenity
Requires:       dejavu-sans-fonts

%description
MPMB Reader is a native Rust desktop application built to run original
MorePurpleMoreBetter (MPMB) interactive 5e/2024 PDF character sheets
without Adobe Acrobat Reader. Includes QuickJS form execution, lopdf
persistence, bundled PDFium rendering, and a themed Dark/Light UI.

%install
install -Dm755 "%{_binary_path}" "%{buildroot}%{_bindir}/mpmb-reader"
install -Dm644 "%{_pdfium_lib}" "%{buildroot}%{_libdir}/mpmb-reader/libpdfium.so"
install -Dm644 "%{_pdfium_license}" "%{buildroot}%{_licensedir}/mpmb-reader/LICENSE-PDFIUM.txt"
if [ -d "%{_pdfium_licenses_dir}" ]; then
  install -dm755 "%{buildroot}%{_licensedir}/mpmb-reader/licenses"
  cp -a "%{_pdfium_licenses_dir}/." "%{buildroot}%{_licensedir}/mpmb-reader/licenses/"
fi
install -Dm644 "%{_assets_dir}/io.github.afaskar.MpmbReader.desktop" \
  "%{buildroot}%{_datadir}/applications/io.github.afaskar.MpmbReader.desktop"
install -Dm644 "%{_assets_dir}/io.github.afaskar.MpmbReader.metainfo.xml" \
  "%{buildroot}%{_datadir}/metainfo/io.github.afaskar.MpmbReader.metainfo.xml"
install -Dm644 "%{_assets_dir}/io.github.afaskar.MpmbReader.svg" \
  "%{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.afaskar.MpmbReader.svg"

%files
%{_bindir}/mpmb-reader
%dir %{_libdir}/mpmb-reader
%{_libdir}/mpmb-reader/libpdfium.so
%license %{_licensedir}/mpmb-reader/LICENSE-PDFIUM.txt
%license %{_licensedir}/mpmb-reader/licenses
%{_datadir}/applications/io.github.afaskar.MpmbReader.desktop
%{_datadir}/metainfo/io.github.afaskar.MpmbReader.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/io.github.afaskar.MpmbReader.svg

%changelog
* Wed Nov 25 2026 AF_Askar <68832286+abo3skr2019@users.noreply.github.com> - 0.1.0-1
- Initial packaged RPM release with bundled PDFium and desktop integration.
