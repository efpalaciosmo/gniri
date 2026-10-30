#!/usr/bin/env bash
# Adapted from osbuild/image-builder's documented bootc-generic-iso contract.
set -euo pipefail
# osbuild runs tmpfiles with the build root's /usr mounted read-only. The base
# has a rule for this absent directory; create it before freezing the image.
install -d -m 0755 /usr/local/sbin
mapfile -t platform_packages < <(sed -e 's/#.*//' -e '/^[[:space:]]*$/d' /run/gniri-hardware-platform.txt)
dnf5 -y --refresh --setopt=keepcache=True --setopt=install_weak_deps=False upgrade
dnf5 -y --setopt=keepcache=True --setopt=install_weak_deps=False install \
    anaconda anaconda-install-img-deps anaconda-dracut \
    dracut-config-generic dracut-network net-tools grub2-efi-x64-cdboot \
    grub2-pc-modules plymouth default-fonts-core-sans default-fonts-other-sans \
    google-noto-sans-cjk-fonts xorrisofs squashfs-tools isomd5sum \
    "${platform_packages[@]}"
python3 /run/gniri-validate-hardware-platform.py /run/gniri-hardware-platform.txt
python3 /run/gniri-fix-anaconda.py
# Only this disposable installer environment follows Anaconda's permissive
# runtime model. Keep SELinux enabled so its policy remains available to bootc.
# This file is not copied into the separately built desktop payload.
sed -i 's/^SELINUX=.*/SELINUX=permissive/' /etc/selinux/config
grep -qx 'SELINUX=permissive' /etc/selinux/config
mkdir -p /boot/efi
cp -a /usr/lib/efi/*/*/EFI /boot/efi/
mkdir -p /usr/lib/image-builder/bootc
cat > /usr/lib/image-builder/bootc/iso.yaml <<'EOF'
label: Gniri-Installer
grub2:
  entries:
    - name: Install Gniri
      linux: /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=Gniri-Installer console=tty0 inst.graphical selinux=1 enforcing=0 rhgb quiet
      initrd: /images/pxeboot/initrd.img
EOF
printf 'install:x:0:0:root:/root:/usr/libexec/anaconda/run-anaconda\n' >> /etc/passwd
printf 'install::14438:0:99999:7:::\n' >> /etc/shadow
passwd -d root
mv /usr/share/anaconda/list-harddrives-stub /usr/bin/list-harddrives
mv /etc/yum.repos.d /etc/anaconda.repos.d
ln -sfn /usr/lib/systemd/system/anaconda.target /etc/systemd/system/default.target
if [[ -f /usr/lib/systemd/system-generators/systemd-gpt-auto-generator ]]; then
    rm /usr/lib/systemd/system-generators/systemd-gpt-auto-generator
fi
ln -sfn /usr/lib/systemd/system/anaconda-shell@.service /etc/systemd/system/autovt@.service
mkdir -p /usr/lib/systemd/logind.conf.d
printf '[Login]\nReserveVT=2\n' > /usr/lib/systemd/logind.conf.d/gniri-installer.conf
mkdir -p "$(realpath /root)"
# Lorax normally supplies this metadata. The generic ISO path does not run
# Lorax, so provide it to both Anaconda's runtime and its dracut cmdline hook.
python3 /run/gniri-write-buildstamp.py
kernel=$(find /usr/lib/modules -mindepth 2 -maxdepth 2 -name vmlinuz -printf '%h\n')
[[ -n $kernel && $kernel != *$'\n'* ]]
DRACUT_NO_XATTR=1 dracut --force --zstd --reproducible --no-hostonly \
    --include /.buildstamp /.buildstamp \
    --add anaconda "${kernel}/initramfs.img" "${kernel##*/}"
for unit in pipewire.service pipewire.socket; do
    mkdir -p "/etc/systemd/user/${unit}.d"
    printf '[Unit]\nConditionUser=\n' > "/etc/systemd/user/${unit}.d/allow-installer-root.conf"
done
