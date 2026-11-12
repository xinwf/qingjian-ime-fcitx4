# Linux Fcitx4 适配

Fcitx4 插件与 Fcitx5 插件并列，复用同一个 Rust Server、Linux IPC 协议和 socket 传输代码。Fcitx4 插件在 C++ 壳中注册 `FcitxIMClass`，把按键、候选点击、翻页、焦点和预编辑映射到 Server；输入与排序逻辑仍在 Core。

## 构建与安装

X11 选区备用读取还需要 `libx11-dev` 和 `libxres-dev`。

Ubuntu 22.04 使用 `fcitx-libs-dev`（Fcitx4 4.2.9.8）、`nlohmann-json3-dev`、OpenSSL 开发包及 Rust 1.96；无需 Fcitx5 或 Qt6。`apps/linux/scripts/install.sh --fcitx4` 编译 Server 和插件，装到用户目录。插件库放在 `<prefix>/lib/fcitx/`，配置放在 `$XDG_CONFIG_HOME/fcitx/addon/`，配置中使用插件绝对路径。输入法图标同时放在 `$XDG_CONFIG_HOME/fcitx/imicon/qingjian.png` 和 `$XDG_DATA_HOME/icons/hicolor/48x48/apps/fcitx-qingjian.png`，分别供经典面板和托盘组件查找；只安装 `qingjian.png` 应用图标时，托盘组件会回退到 Fcitx 图标。默认 Fcitx5 安装流程不变；卸载继续按安装清单清理。

系统级安装走本机原生 deb：`apps/linux/packaging/build-local.sh` 在 glibc 低于容器包要求的老发行版（如 Ubuntu 20.04）上编出 `qingjian_*.deb` 与 `qingjian-fcitx4_*.deb`，用 `sudo apt install ./target/linux-pkg/out/qingjian_*.deb ./target/linux-pkg/out/qingjian-fcitx4_*.deb` 装上，见 [linux-packaging.md](linux-packaging.md)。deb 把插件放 `/usr/lib/<多架构>/fcitx/`、addon 描述放 `/usr/share/fcitx/addon/`，此时 `Library=fcitx-qingjian.so` 用裸库名（用户级安装才改成绝对路径）；装完 `fcitx -r`，`fcitx-remote -m qingjian` 应返回 `fcitx-qingjian`。设置程序是 `/usr/bin/qingjian-settings`（应用菜单「青简设置」），改的是 `~/.config/qingjian/config.toml`，保存后热加载；Fcitx4 插件自身没有内嵌设置面板，托盘里的「设置」是框架或搜狗的，不随当前输入法切换。

`python3 apps/linux/scripts/files.py` 的哈希读取按块处理，兼容 Ubuntu 22.04 自带的 Python 3.10。安装后需在 Fcitx4 配置中启用「青简」，并手动启动 Server。

## 框架差异

- Fcitx4 通过每个输入上下文的数据槽保存 Server 会话编号；候选列表由框架拥有并释放，因此候选的文本、注记和私有点击数据都交给 Fcitx4 管理。
- 候选分页使用 `FcitxCandidateWordSetOverridePaging` 转发给 Server；候选展示回执也发给 Server。组句期间每 80 ms 查询一次本地模型重排结果。
- Fcitx4 只有 `CAPACITY_PASSWORD`，没有 Fcitx5 的 `Sensitive` 和 `Disable` 对应标记。普通敏感字段无法可靠识别；用户文档给出了关闭输入日志与学习的办法。
- `[predict]` 的开关、地址、模型和密钥在保存后由 Server 热加载，旧云请求与翻译评审作废。
- 云联想由共用 Linux Server 提供；Fcitx4 默认面板从 Poll 接收云端候选和整句，在候选注记与辅助行加 ☁。密码框不发云请求，未标记的其他敏感输入框仍有上述识别限制。
- 前后文只在 `CAPACITY_SURROUNDING_TEXT` 可用时读取；`FcitxInstanceGetSurroundingText` 返回的字符串由插件释放，cursor/anchor 是 Unicode 字符位置。共用截取器跳过选区，只取两侧最多 80 字，再经 `LinuxEvent::Key` 发给 Server。
- 选区翻译由 Server 按 `[shortcut] translate_selection` 判断按键，返回 `RequestSelection` 后插件读取最多 500 字选区并回复 `LinuxEvent::Selection`。评审时默认面板显示「翻译中…」或译文，轮询直到有结果；提交前再次核对选区文字和位置。
- Chrome 等没有 `CAPACITY_SURROUNDING_TEXT` 的 X11 应用改读 PRIMARY；XRes 只接受与当前焦点窗口同属一个 X11 客户端的选区，等待最多 100 ms，UTF-8 格式和长度不合规时拒绝。提交前会重新读取并比对选中文字，应用能提供光标位置时还会比对位置。
- `OnClose(CET_LostFocus)` 表示框架已处理客户端预编辑；插件把这个事实告诉 Server，防止重复上屏。

## 皮肤

Fcitx4 的候选窗由 classic-ui 绘制，皮肤从 `/usr/share/fcitx/skin/<id>/fcitx_skin.conf` 读。
青简自己的 `theme.json` 是 Rust 渲染器的格式，进不了这个框架，但配色、字号、边距能映射过去：
`apps/linux/fcitx4/skin/generate.py` 生成五套皮肤，`qingjian-fcitx4` 把它们装到
`/usr/share/fcitx/skin/`：

| 目录 | 显示名 | 底色 |
| --- | --- | --- |
| `qingjian-light` | 简白 | 白底黑字，与青简渲染器的浅色一致 |
| `qingjian-dark` | 深黑 | 黑底白字，与青简渲染器的深色一致 |
| `qingjian` | 青简绿 | 原主题 `accent #94be52` 铺成淡绿底、深绿字 |
| `qingjian-orange` | 青简橙 | 暖橙底、深棕字 |
| `qingjian-blue` | 青简蓝 | 晴蓝底、深蓝字 |

切换走托盘「皮肤」菜单（写 `SkinType` 后 `ReloadConfig`），也可以直接改
`~/.config/fcitx/conf/fcitx-classic-ui.config` 的 `SkinType=qingjian`。改了颜色或尺寸后重跑
`python3 apps/linux/fcitx4/skin/generate.py` 再打包。

能映射的是字体、字号、各类候选字的颜色、输入窗/状态栏/菜单的圆角背景与边距、翻页箭头和托盘图标；
映射不了的是青简渲染器里的逐候选布局、内联注记排版、阴影/模糊、动效和主题装饰图形——classic-ui
只有一张背景图加一组文字颜色，候选按框架固定布局排。

## 托盘图标

Fcitx4 自带的 `fcitx-notificationitem` 在输入法未激活（英文模式）时显示的是启用列表第一个输入法的图标；装了搜狗拼音后，搜狗的 `fcitx-sogoupinyinhdm` / `hxm` 还会 hook `com.canonical.dbusmenu`，把右键菜单换成搜狗的，`Event` 被截走，菜单里的「切换皮肤 / 切换输入法」没反应，「属性设置」落到 `sogoupinyin-configtool`。

`apps/linux/fcitx4/tray/qingjian_tray.py` 是独立的 Python 托盘守护进程（装成 `qingjian-tray`），不复用 Fcitx4 的托盘模块：

- 图标按 `~/.config/fcitx/profile` 的 `IMName` 选，不受激活状态影响；青简 `fcitx-qingjian`、搜狗 `fcitx-sogoupinyin`、知意 `fcitx`，其他输入法回退 `input-keyboard`。
- 菜单：`青简设置`（启动 `/usr/bin/qingjian-settings`）、`输入法`（D-Bus `SetCurrentIM` + `ActivateIM`）、`中 / 英切换`（`ToggleIM`）、`皮肤`（写 `fcitx-classic-ui.config` 的 `SkinType` 后 `ReloadConfig`；列出 default / dark / classic 与随包的简白、深黑、青简绿、青简橙、青简蓝）、`重新启动 Fcitx4`、`退出托盘`。
- 用 `python3-gi` + `gir1.2-appindicator3-0.1`；`python3-dbus` 用来走 Fcitx4 的 D-Bus 接口，没有时回退 `fcitx-remote` 命令。
- 锁屏时 GNOME 会撤掉 `org.kde.StatusNotifierWatcher`，脚本监听它重新出现并重设 `Status`，解锁后自动注册。

`qingjian-tray --setup` 在 `~/.config/fcitx/addon/` 写 `fcitx-notificationitem`、`fcitx-sogoupinyinhdm`、`fcitx-sogoupinyinhxm` 三个 `Enabled=False` 覆盖并重启 Fcitx4；`--undo-setup` 删除它们并重启，恢复 Fcitx4 自带托盘。deb 装 `/usr/bin/qingjian-tray` 与 `/etc/xdg/autostart/qingjian-tray.desktop`，装完在用户会话执行一次 `--setup`。

本机 Ubuntu 20.04.6 / Fcitx4 4.2.9.7 上验过：SNI 导出 `Id=qingjian-tray`、`IconName=fcitx-qingjian`；点菜单「知意」/「青简」时 `IMName` 与图标跟着变（`fcitx` ↔ `fcitx-qingjian`）；点「dark」写入 `SkinType=dark` 并重载。本机上 `fcitx-remote -s sogoupinyin` 也切不过去，菜单点「搜狗拼音」无效是搜狗输入法自己的状态，与托盘无关。`SkinType=qingjian` / `qingjian-dark` 也验过：候选窗分别是白底与 `#1e1e1e` 圆角卡片，首候选橙色、序号灰色，`ni'hao` 的候选列表正常显示。

换一个窗口输入法就被重置成列表里别的输入法时，改 Fcitx4 的全局配置 `~/.config/fcitx/config`：`[Program] ShareStateAmongWindow=All`（缺省 `No` 表示每个窗口独立，新窗口回到 `IMName` / 启用列表的第一个）。这是 Fcitx4 自己按窗口管理输入状态的行为，与托盘插件无关；`All` 让所有窗口共享当前输入法。

## 本机验证

Ubuntu 22.04、Fcitx4 4.2.9.8、GTK3：在隔离的 Xvfb 和私有 D-Bus 会话中加载插件，`fcitx-remote -m qingjian` 返回 `fcitx-qingjian`；GTK3 文本框切换到青简，输入 `nihao`、空格，得到「你好」。同一文本框设为密码模式时输入原样上屏为 `nihao `。真实桌面上的 Chrome 输入框选中「你好」后按 `Ctrl + Super + T`，出现「翻译中…」，译文返回后按 Enter 成功替换选区。Qt5 等其他应用尚未验证。

系统级 deb 也在 Ubuntu 20.04.6 / Fcitx4 4.2.9.7 上验过：`fcitx -r` 后 `fcitx-remote -m qingjian` 返回 `fcitx-qingjian`，Server 由 `postinst` 自动起到 active，插件 `ldd` 无 `not found`，GTK3 输入框里 `nihao` + 空格上屏「你好」。
