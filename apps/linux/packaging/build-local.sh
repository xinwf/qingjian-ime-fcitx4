#!/usr/bin/env bash
# 本机原生打 deb：Server、IBus 前端与 Fcitx4 插件都在当前 Debian/Ubuntu 上编，不用容器。
# 给老发行版（本机 glibc 比 build.sh 的容器低）用；只出 deb，不做 rpm / AppImage / 其它平台。
#
#   apps/linux/packaging/build-local.sh              两个包：qingjian 与 qingjian-fcitx4
#   QINGJIAN_SAMPLE=1 apps/linux/packaging/build-local.sh   没有产品数据时只带样例词库
#
# 前置：Rust（rust-toolchain.toml）、cmake、c++、pkg-config、python3、dpkg-dev，
# 以及 Fcitx4 插件的编译依赖（Ubuntu：sudo apt install fcitx-libs-dev libx11-dev libxres-dev
# nlohmann-json3-dev libssl-dev）。产物在 target/linux-pkg/out/，装法与限制见 docs/notes/linux-packaging.md。
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
work="$root/target/linux-pkg"
out="$work/out"
stage="$work/local-deb"

[[ -f /etc/debian_version ]] || { echo '只支持本机 Debian/Ubuntu（需要 dpkg-deb 与 dpkg-shlibdeps）' >&2; exit 1; }

missing=()
for tool in cargo cmake c++ pkg-config python3 git dpkg-deb dpkg-shlibdeps dpkg-architecture strip; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
for module in fcitx x11 xres openssl; do
  pkg-config --exists "$module" || missing+=("$module（pkg-config）")
done
if ((${#missing[@]})); then
  echo "缺少依赖：${missing[*]}" >&2
  echo 'Debian / Ubuntu：sudo apt install cmake g++ pkg-config dpkg-dev python3 fcitx-libs-dev libx11-dev libxres-dev nlohmann-json3-dev libssl-dev' >&2
  exit 1
fi

# 版本算法与 build.sh 一致：0.3.4-dev → 0.3.4~dev+git<短哈希>
cargo_version=$(sed -n 's/^version = "\(.*\)"/\1/p' "$root/apps/linux/server/Cargo.toml" | head -1)
upstream=${cargo_version%%-*}
git_rev=$(git -C "$root" rev-parse --short HEAD)
if [[ "$cargo_version" == *-dev ]]; then
  deb_version="${upstream}~dev+git${git_rev}"
else
  deb_version="$upstream"
fi
arch=$(dpkg --print-architecture)
multiarch=$(dpkg-architecture -qDEB_HOST_MULTIARCH)
echo "==> 版本 $cargo_version（$deb_version，$arch）"

echo '==> Rust：Server、IBus 前端与设置程序'
(cd "$root" && cargo build --release --locked -p qingjian-linux-server -p qingjian-linux-ibus -p qingjian-settings)
bin="$root/target/release"

# 默认编译器编不动时（老发行版上 g++ 9 的 C++20 支持不全），用 g++-10 再来一遍。
build_fcitx4() {
  local build=$1 compiler=${2:-} args=()
  [[ -z "$compiler" ]] || args=(-DCMAKE_CXX_COMPILER="$compiler")
  # 不把本机（可能带本地解压的依赖目录）的构建路径写进 .so 的 RPATH
  cmake -S "$root/apps/linux/fcitx4" -B "$build" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
    -DCMAKE_SKIP_BUILD_RPATH=ON "${args[@]}"
  cmake --build "$build" --parallel
}
fcitx4_build="$work/fcitx4-build"
echo '==> Fcitx4 插件'
if ! build_fcitx4 "$fcitx4_build" "${CXX:-}"; then
  if command -v g++-10 >/dev/null 2>&1; then
    echo '==> 默认 C++ 编译器构建失败，用 g++-10 重试'
    rm -rf "$fcitx4_build"
    build_fcitx4 "$fcitx4_build" g++-10
  else
    echo '插件构建失败；装 g++-10 后重试（sudo apt install g++-10）' >&2
    exit 1
  fi
fi
plugin="$fcitx4_build/fcitx-qingjian.so"
[[ -f "$plugin" ]] || { echo "没有构建出 $plugin" >&2; exit 1; }

echo '==> 随包资源'
resources="$work/resources"
sample_flag=()
[[ "${QINGJIAN_SAMPLE:-}" != 1 ]] || sample_flag=(--sample)
python3 "$root/apps/linux/scripts/files.py" resources "$resources" --root "$root" "${sample_flag[@]}"

rm -rf "$stage"
core="$stage/qingjian"
fcitx="$stage/qingjian-fcitx4"

# 与 build.sh 的 stage_core 同一套系统布局；Server 按可执行文件的上一层找 share/qingjian/resources
install -Dm755 "$bin/qingjian-linux-server" "$core/usr/bin/qingjian-linux-server"
install -Dm755 "$bin/qingjian-linux-ibus" "$core/usr/bin/qingjian-linux-ibus"
install -Dm755 "$bin/qingjian-settings" "$core/usr/bin/qingjian-settings"
mkdir -p "$core/usr/share/qingjian"
cp -r "$resources" "$core/usr/share/qingjian/resources"
mkdir -p "$core/usr/share/ibus/component"
"$bin/qingjian-linux-ibus" --ibus-xml /usr/bin/qingjian-linux-ibus > "$core/usr/share/ibus/component/qingjian.xml"
mkdir -p "$core/usr/lib/systemd/user"
sed 's|@EXEC@|/usr/bin/qingjian-linux-server|' "$root/apps/linux/scripts/qingjian-server.service.in" \
  > "$core/usr/lib/systemd/user/qingjian-server.service"
# 桌面项的 Exec 换到系统绝对路径，与 files.py 的用户级安装同一套写法
mkdir -p "$core/usr/share/applications"
sed 's|^Exec=qingjian-settings$|Exec=/usr/bin/qingjian-settings|' \
  "$root/apps/settings/linux/qingjian-settings.desktop" \
  > "$core/usr/share/applications/qingjian-settings.desktop"
for size in 16 22 24 32 48 64 128 256; do
  install -Dm644 "$root/assets/icon/linux/hicolor/${size}x${size}/apps/qingjian.png" \
    "$core/usr/share/icons/hicolor/${size}x${size}/apps/qingjian.png"
done
install -Dm644 "$root/LICENSE" "$core/usr/share/doc/qingjian/copyright"

# Fcitx4 从系统插件目录按裸库名找 .so，addon 描述文件不用改 Library=；图标两份分别给经典面板与托盘
install -Dm644 "$plugin" "$fcitx/usr/lib/$multiarch/fcitx/fcitx-qingjian.so"
install -Dm644 "$root/apps/linux/fcitx4/data/addon/fcitx-qingjian.conf" \
  "$fcitx/usr/share/fcitx/addon/fcitx-qingjian.conf"
install -Dm644 "$root/assets/icon/fcitx4.png" "$fcitx/usr/share/fcitx/imicon/qingjian.png"
install -Dm644 "$root/assets/icon/fcitx4.png" \
  "$fcitx/usr/share/icons/hicolor/48x48/apps/fcitx-qingjian.png"
# 青简的 Fcitx4 皮肤：classic-ui 从 /usr/share/fcitx/skin/<id>/ 读 fcitx_skin.conf，
# 托盘「皮肤」菜单里按目录名可切换（简白/深黑/青简绿/青简橙/青简蓝）
for skin in "$root"/apps/linux/fcitx4/skin/qingjian*/; do
  name=$(basename "$skin")
  mkdir -p "$fcitx/usr/share/fcitx/skin/$name"
  cp -a "$skin/." "$fcitx/usr/share/fcitx/skin/$name/"
done
install -Dm644 "$root/LICENSE" "$fcitx/usr/share/doc/qingjian-fcitx4/copyright"
# 托盘守护进程由桌面会话的 autostart 拉起；Exec 换到系统绝对路径
install -Dm755 "$root/apps/linux/fcitx4/tray/qingjian_tray.py" "$fcitx/usr/bin/qingjian-tray"
mkdir -p "$fcitx/etc/xdg/autostart"
sed 's|@TRAY@|/usr/bin/qingjian-tray|' "$root/apps/linux/fcitx4/tray/qingjian-tray.desktop.in" \
  > "$fcitx/etc/xdg/autostart/qingjian-tray.desktop"
strip --strip-unneeded "$core/usr/bin/qingjian-linux-server" "$core/usr/bin/qingjian-linux-ibus" \
  "$core/usr/bin/qingjian-settings" "$fcitx/usr/lib/$multiarch/fcitx/fcitx-qingjian.so"

# 动态库依赖从二进制推（libc6 的最低版本、Fcitx4 与 X11 的运行时库），不手写
shlibs() {
  local dir
  dir=$(mktemp -d)
  mkdir "$dir/debian"
  printf 'Source: qingjian\n\nPackage: qingjian\nArchitecture: any\n' > "$dir/debian/control"
  (cd "$dir" && dpkg-shlibdeps -O "$@" | sed -n 's/^shlibs:Depends=//p')
  rm -rf "$dir"
}

# 权限归一：宿主机 umask 是 002 时拷出来的是 664 / 775
normalize() {
  find "$1" -type d -exec chmod 755 {} +
  find "$1" -type f ! -path '*/usr/bin/*' -exec chmod 644 {} +
}

control() {
  local dir=$1 name=$2 depends=$3 extra=$4 summary=$5 description=$6
  mkdir -p "$dir/DEBIAN"
  cat > "$dir/DEBIAN/control" <<CONTROL
Package: $name
Version: $deb_version
Architecture: $arch
Maintainer: Qingjian <https://qingjian.app>
Installed-Size: $(du -sk --exclude=DEBIAN "$dir" | cut -f1)
Depends: $depends
${extra}Section: utils
Priority: optional
Homepage: https://qingjian.app
Description: $summary
$description
CONTROL
}

normalize "$core"
control "$core" qingjian \
  "$(shlibs "$core/usr/bin/qingjian-linux-server" "$core/usr/bin/qingjian-linux-ibus" "$core/usr/bin/qingjian-settings")" \
  $'Recommends: ibus | qingjian-fcitx4\n' \
  '青简输入法：Server、IBus 前端、设置程序与词库' \
  ' 跨平台拼音输入法。本包是引擎（Server，systemd 用户服务）、IBus 前端、设置程序与随包词库；
 用 Fcitx4 的再装 qingjian-fcitx4。设置从应用菜单「青简设置」打开，改的是用户目录的 config.toml。
 Server 装完就起；IBus 要重新登录一次（或 ibus restart）才看得到青简。'
# 装包脚本沿用 deb/assemble.sh 的逻辑：--global 只对之后起来的用户 systemd 实例生效，
# 注销再登录得快时实例不重起，所以已经登录的用户直接在正在跑的实例里重载并重启。
# 老 systemd（Ubuntu 20.04 的 245）上 root 用 -M 连别的用户实例会报
# "Cannot access user instance remotely"，所以先以该用户身份直连自己的 bus，-M 只作兜底。
cat > "$core/DEBIAN/postinst" <<'SCRIPT'
#!/bin/sh
set -e
if [ "$1" = configure ] && command -v systemctl >/dev/null 2>&1; then
  systemctl --global enable qingjian-server.service >/dev/null 2>&1 || true
  # 用户目录里的同名单元（源码安装的 install.sh 登记的）会盖过这个包的 Server：
  # 前端用这个包的、Server 用那边的，版本一错开就打不出字
  getent passwd | while IFS=: read -r name _ uid _ _ home _; do
    [ "$uid" -ge 1000 ] 2>/dev/null || continue
    if [ -f "$home/.config/systemd/user/qingjian-server.service" ]; then
      echo "注意：用户 $name 有自己的青简 Server 服务，会盖过这个包装的：" >&2
      echo "  $home/.config/systemd/user/qingjian-server.service" >&2
      echo "  以该用户卸掉那一份——源码安装的：apps/linux/scripts/uninstall.sh" >&2
    fi
  done
  user_systemctl() {
    uid=$1 user=$2
    shift 2
    if ! runuser -u "$user" -- env "XDG_RUNTIME_DIR=/run/user/$uid" \
        "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus" systemctl --user "$@" >/dev/null 2>&1; then
      systemctl --user -M "$user@" "$@" >/dev/null 2>&1 || true
    fi
  }
  loginctl list-users --no-legend 2>/dev/null | while read -r uid user _; do
    user_systemctl "$uid" "$user" daemon-reload
    user_systemctl "$uid" "$user" restart qingjian-server.service
  done
fi
SCRIPT
cat > "$core/DEBIAN/prerm" <<'SCRIPT'
#!/bin/sh
set -e
if [ "$1" = remove ] && command -v systemctl >/dev/null 2>&1; then
  systemctl --global disable qingjian-server.service >/dev/null 2>&1 || true
  user_systemctl() {
    uid=$1 user=$2
    shift 2
    if ! runuser -u "$user" -- env "XDG_RUNTIME_DIR=/run/user/$uid" \
        "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus" systemctl --user "$@" >/dev/null 2>&1; then
      systemctl --user -M "$user@" "$@" >/dev/null 2>&1 || true
    fi
  }
  loginctl list-users --no-legend 2>/dev/null | while read -r uid user _; do
    user_systemctl "$uid" "$user" stop qingjian-server.service
  done
fi
SCRIPT
chmod 755 "$core/DEBIAN/postinst" "$core/DEBIAN/prerm"

normalize "$fcitx"
control "$fcitx" qingjian-fcitx4 \
  "qingjian (= $deb_version), fcitx, python3, python3-gi, python3-dbus, gir1.2-appindicator3-0.1, $(shlibs "$fcitx/usr/lib/$multiarch/fcitx/fcitx-qingjian.so")" '' \
  '青简输入法的 Fcitx4 插件、托盘与皮肤' \
  ' 让 Fcitx4 能用青简；引擎在 qingjian 包里。装完重启 Fcitx4（fcitx -r），在配置工具里添加「青简」。
 托盘由 qingjian-tray 提供，在用户会话执行一次 qingjian-tray --setup 禁用 Fcitx4/搜狗自带的托盘模块。
 另带两套 classic-ui 皮肤（青简绿 / 青简绿·深色），在托盘「皮肤」菜单或 Fcitx 配置 → 外观里选。'
cat > "$fcitx/DEBIAN/postinst" <<'SCRIPT'
#!/bin/sh
if [ "$1" = configure ]; then
  echo '青简托盘：请在用户会话执行 qingjian-tray --setup（禁用冲突托盘模块并重启 Fcitx4）' >&2
fi
SCRIPT
chmod 755 "$fcitx/DEBIAN/postinst"

mkdir -p "$out"
rm -f "$out"/qingjian_*.deb "$out"/qingjian-fcitx4_*.deb
for dir in "$core" "$fcitx"; do
  dpkg-deb --root-owner-group -Zxz --build "$dir" \
    "$out/$(basename "$dir")_${deb_version}_${arch}.deb" >/dev/null
done
echo "==> 产物（$out）："
ls -lh "$out"/*.deb
