# 在本机（Ubuntu 20.04 + Fcitx4）原生构建并打 deb

## 背景

本机是 Ubuntu 20.04（glibc 2.31）+ 正在运行的 Fcitx4 4.2.9.7。仓库已有 Fcitx4 适配（`apps/linux/fcitx4`，源码安装），但现有 deb 打包（`apps/linux/packaging/build.sh`）全在 Ubuntu 22.04 / Debian 13 容器里编，产物要求 glibc ≥ 2.34，在本机跑不起来；且 deb 从未包含 fcitx4 插件。目标：在本机原生编译 Server + Fcitx4 插件，打成本机可安装使用的 deb。只管本机，不做 rpm / 其它发行版。

## 环境确认

- 本机 Ubuntu 20.04，glibc 2.31，Fcitx4 4.2.9.7 正在运行。
- 仓库已有 Fcitx4 适配：`apps/linux/fcitx4`，现有 `apps/linux/scripts/install.sh --fcitx4` 可源码安装。
- 现有发行包脚本 `apps/linux/packaging/build.sh` 使用 Ubuntu 22.04 / Debian 13 容器，且不包含 Fcitx4 插件。
- 本机未发现 rustup/cargo，需要安装 Rust 1.96.0。
- 本机缺少 Fcitx4 编译依赖 `fcitx-libs-dev`、`libxres-dev`；已确认有 cmake、nlohmann-json3-dev、libssl-dev、libx11-dev、libxres1、dpkg-dev、im-config 等相关依赖。
- 产品数据目录 `data/` 尚未拉取；完整打包需要先运行 `tools/release/data-fetch.sh`，否则使用 `QINGJIAN_SAMPLE=1` 仅打样例词库。
- 本机 v2rayA 正在运行；下载 Rust、Cargo 依赖及产品数据时需要先探测可用代理端口并设置 `http_proxy` / `https_proxy`。
- 没有发现用户级青简安装残留或同名 systemd 用户单元。

## 实现步骤

### 1. 环境准备

- 探测 v2rayA 可用 HTTP 代理端口，导出 `http_proxy` / `https_proxy`。
- 安装 rustup；进入仓库后按 `rust-toolchain.toml` 安装 Rust 1.96.0。
- 通过 apt 安装：
  - `fcitx-libs-dev`
  - `libxres-dev`
  - 其它缺失的构建依赖按实际报错补齐。
- 优先运行 `tools/release/data-fetch.sh` 拉取产品数据；若下载失败，使用 `QINGJIAN_SAMPLE=1` 构建样例包，并在结果中明确说明。

### 2. 新增本机原生打包脚本

新增：`apps/linux/packaging/build-local.sh`。

脚本要求：

- 只支持本机 Debian/Ubuntu 环境，不使用 Docker，不处理 rpm 或其它平台。
- 版本号沿用现有 `build.sh` 算法：`0.3.4-dev` 转为 `0.3.4~dev+git<短哈希>`。
- 原生构建 Rust Server 与 IBus 前端：

  ```bash
  cargo build --release --locked \
    -p qingjian-linux-server \
    -p qingjian-linux-ibus
  ```

- 原生构建 Fcitx4 插件：

  ```bash
  cmake -S apps/linux/fcitx4 \
    -B target/linux-pkg/fcitx4-build \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_TESTING=OFF
  cmake --build target/linux-pkg/fcitx4-build --parallel
  ```

- 构建产物：`fcitx-qingjian.so`。
- 使用 `apps/linux/scripts/files.py resources` 生成随包资源；支持 `QINGJIAN_SAMPLE=1`。
- 生成两个 deb：

#### `qingjian`

安装以下内容：

- `/usr/bin/qingjian-linux-server`
- `/usr/bin/qingjian-linux-ibus`
- `/usr/share/qingjian/resources/`
- `/usr/share/ibus/component/qingjian.xml`
- `/usr/lib/systemd/user/qingjian-server.service`
- `/usr/share/icons/hicolor/` 下的青简图标
- `/usr/share/doc/qingjian/copyright`

安装脚本沿用现有 `apps/linux/packaging/deb/assemble.sh`：

- `postinst` 执行 `systemctl --global enable qingjian-server.service`。
- 对已经登录的用户执行 `daemon-reload` 和 `restart`，避免必须重新登录。
- 检查并提示用户目录中可能覆盖系统包的同名青简 Server 服务。
- `prerm` 停止服务并取消全局启用。
- `Recommends: ibus | qingjian-fcitx4`。

#### `qingjian-fcitx4`

安装以下内容：

- `/usr/lib/x86_64-linux-gnu/fcitx/fcitx-qingjian.so`
- `/usr/share/fcitx/addon/fcitx-qingjian.conf`
- `/usr/share/fcitx/imicon/qingjian.png`
- `/usr/share/icons/hicolor/48x48/apps/fcitx-qingjian.png`
- `/usr/share/doc/qingjian-fcitx4/copyright`

Addon 配置使用现有的裸库名：

```ini
Library=fcitx-qingjian.so
```

这与 Fcitx4 系统插件目录的查找方式一致。

包依赖：

- `qingjian (= <版本>)`
- `fcitx`
- 通过 `dpkg-shlibdeps` 自动推导插件动态库依赖。

两个包都使用：

```bash
dpkg-deb --root-owner-group -Zxz --build
```

产物输出到：`target/linux-pkg/out/`。

如果本机默认 C++ 编译器不能构建插件，脚本支持使用 `g++-10` 重试。

### 3. 安装与验证

安装本机生成的两个包：

```bash
sudo apt install ./target/linux-pkg/out/qingjian_*.deb \
  ./target/linux-pkg/out/qingjian-fcitx4_*.deb
```

验证 Server：

```bash
systemctl --user status qingjian-server
qingjian-linux-ibus --check nihao
```

验证 Fcitx4 插件：

```bash
ldd /usr/lib/x86_64-linux-gnu/fcitx/fcitx-qingjian.so
fcitx -r
fcitx-remote -m qingjian
```

预期：

- `ldd` 没有 `not found`。
- `fcitx-remote -m qingjian` 返回 `fcitx-qingjian`。
- 在桌面输入框切换到「青简」，输入 `nihao` 后按空格，得到「你好」。

### 4. 文档同步

修改：

- `docs/notes/linux-packaging.md`：增加“本机原生打 deb（老发行版 / Fcitx4）”说明。
- `docs/notes/linux-fcitx4.md`：补充 deb 构建入口。
- `CLAUDE.md`：在 `apps/linux` 目录说明中补充 `build-local.sh`。

不修改 `docs/user/`，因为这次目标是本机定制构建，不处理其它平台发布说明。

### 5. 收尾

- 不自动提交代码。
- 若需要提交，使用 Conventional Commits，例如：

  ```text
  build(linux): 增加本机 Fcitx4 deb 打包
  ```

## 验证清单

1. 两个 deb 能安装且无依赖错误。
2. `qingjian-server` 用户服务处于 active 状态。
3. `qingjian-linux-ibus --check nihao` 能返回「你好」候选。
4. Fcitx4 插件动态库依赖完整。
5. `fcitx-remote -m qingjian` 返回 `fcitx-qingjian`。
6. 真机输入 `nihao` + 空格能上屏「你好」。
7. 可选：卸载两个包后，Server 停止、全局 systemd 启用项和已安装文件清理干净。
