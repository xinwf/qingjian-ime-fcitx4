#!/usr/bin/env python3
# //! 青简 Fcitx4 托盘：自己注册 AppIndicator，按当前输入法换图标，菜单直达青简设置。
# //! Fcitx4 自带的 notificationitem 在未激活时会画成别的输入法图标，搜狗的 hdm/hxm 还会
# //! hook 掉 dbusmenu，所以这里不复用它们；用 --setup 禁用那三个模块后重启 Fcitx4 即可。
# //! 用法：qingjian-tray [--setup | --undo-setup | --check]
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import AppIndicator3, Gio, GLib, Gtk  # noqa: E402

try:
    import dbus
except ImportError:
    dbus = None

HOME = Path.home()
PROFILE = HOME / '.config/fcitx/profile'
CLASSIC_UI = HOME / '.config/fcitx/conf/fcitx-classic-ui.config'
ADDON_DIR = HOME / '.config/fcitx/addon'
SYSTEM_ADDON_DIR = Path('/usr/share/fcitx/addon')
SETTINGS = Path('/usr/bin/qingjian-settings')
OVERRIDES = ('fcitx-notificationitem', 'fcitx-sogoupinyinhdm', 'fcitx-sogoupinyinhxm')
SKINS = ('default', 'dark', 'classic',
         'qingjian-light', 'qingjian-dark', 'qingjian', 'qingjian-orange', 'qingjian-blue')
SKIN_NAMES = {
    'default': '默认',
    'dark': '深色',
    'classic': '经典',
    'qingjian-light': '简白',
    'qingjian-dark': '深黑',
    'qingjian': '青简绿',
    'qingjian-orange': '青简橙',
    'qingjian-blue': '青简蓝',
}
IM_NAMES = {'qingjian': '青简', 'sogoupinyin': '搜狗拼音', 'zhiyi': '知意输入法'}
IM_ICONS = {'qingjian': 'fcitx-qingjian', 'sogoupinyin': 'fcitx-sogoupinyin', 'zhiyi': 'fcitx'}
DEFAULT_ICON = 'input-keyboard'
FCITX_SERVICE = 'org.fcitx.Fcitx'
FCITX_PATH = '/inputmethod'
FCITX_INTERFACE = 'org.fcitx.Fcitx.InputMethod'
WATCHER_NAME = 'org.kde.StatusNotifierWatcher'

log = logging.getLogger('qingjian-tray')
_fcitx = None


def run(*command):
    try:
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=5, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        log.warning('command failed cmd=%s error=%s', command[0], error)


def launch(*command):
    try:
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError as error:
        log.warning('launch failed cmd=%s error=%s', command[0], error)


def fcitx():
    """Fcitx4 的 D-Bus 输入法接口；拿不到就回退到 fcitx-remote 命令。"""
    global _fcitx
    if dbus is None:
        return None
    if _fcitx is None:
        try:
            bus = dbus.SessionBus()
            _fcitx = dbus.Interface(bus.get_object(FCITX_SERVICE, FCITX_PATH), FCITX_INTERFACE)
        except dbus.DBusException as error:
            log.warning('fcitx dbus unavailable error=%s', error)
            return None
    return _fcitx


def d_bus_call(method, *args):
    # 每次重新 get_object：Fcitx4 重启后旧的连接名会失效，缓存 proxy 会一直报 ServiceUnknown
    if dbus is None:
        return None
    try:
        bus = dbus.SessionBus()
        interface = dbus.Interface(bus.get_object(FCITX_SERVICE, FCITX_PATH), FCITX_INTERFACE)
        return getattr(interface, method)(*args)
    except dbus.DBusException as error:
        log.warning('fcitx dbus call failed method=%s error=%s', method, error)
        return None


def profile_value(key):
    try:
        for line in PROFILE.read_text(encoding='utf-8', errors='replace').splitlines():
            if line.startswith(key + '='):
                return line.split('=', 1)[1]
    except OSError:
        pass
    return ''


def current_im():
    value = d_bus_call('GetCurrentIM')
    if value:
        return str(value)
    return profile_value('IMName').strip()


def current_state():
    value = d_bus_call('GetCurrentState')
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def enabled_ims():
    result = []
    for entry in profile_value('EnabledIMList').split(','):
        name, _, state = entry.partition(':')
        if state == 'True' and name and not name.startswith('fcitx-keyboard-'):
            result.append(name)
        if len(result) >= 10:
            break
    return result or ['qingjian']


def current_skin():
    try:
        for line in CLASSIC_UI.read_text(encoding='utf-8', errors='replace').splitlines():
            match = re.match(r'^#?SkinType=(\S+)', line)
            if match:
                return match.group(1)
    except OSError:
        pass
    return 'default'


def reload_config():
    if d_bus_call('ReloadConfig') is None:
        run('fcitx-remote', '-r')


def set_skin(skin):
    if skin not in SKINS:
        return
    lines = []
    try:
        lines = CLASSIC_UI.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        pass
    replaced = False
    output = []
    for line in lines:
        if re.match(r'^#?SkinType=', line):
            output.append('SkinType=' + skin)
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append('SkinType=' + skin)
    CLASSIC_UI.parent.mkdir(parents=True, exist_ok=True)
    CLASSIC_UI.write_text('\n'.join(output) + '\n', encoding='utf-8')
    reload_config()
    log.info('skin changed skin=%s', skin)


def switch_im(name):
    if d_bus_call('SetCurrentIM', name) is not None:
        d_bus_call('ActivateIM')
    else:
        run('fcitx-remote', '-o')
        run('fcitx-remote', '-s', name)
    log.info('switch im requested name=%s', name)


def setup_overrides():
    ADDON_DIR.mkdir(parents=True, exist_ok=True)
    for name in OVERRIDES:
        source = SYSTEM_ADDON_DIR / (name + '.conf')
        if not source.is_file():
            log.warning('addon description missing name=%s', name)
            continue
        content = re.sub(r'(?m)^Enabled=True$', 'Enabled=False',
                         source.read_text(encoding='utf-8', errors='replace'))
        (ADDON_DIR / (name + '.conf')).write_text(content, encoding='utf-8')
        log.info('addon disabled name=%s', name)
    launch('fcitx', '-r')
    print('已写入用户级配置并重启 Fcitx4，托盘由青简接管。')


def undo_overrides():
    for name in OVERRIDES:
        (ADDON_DIR / (name + '.conf')).unlink(missing_ok=True)
    launch('fcitx', '-r')
    print('已删除用户级配置并重启 Fcitx4，恢复 Fcitx4 自带托盘。')


class Tray:
    def __init__(self):
        self.last_im = None
        self.shown_im = None
        self.im_items = {}
        self.skin_items = {}
        self.indicator = AppIndicator3.Indicator.new(
            'qingjian-tray', IM_ICONS['qingjian'],
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_title('青简输入法')
        self.menu = Gtk.Menu()
        self.build_menu()
        self.indicator.set_menu(self.menu)
        self.refresh()
        GLib.timeout_add_seconds(1, self.refresh)
        # 锁屏时 GNOME 会撤掉 StatusNotifierWatcher，解锁后重新出现；重设状态触发注册
        Gio.bus_watch_name(Gio.BusType.SESSION, WATCHER_NAME,
                           Gio.BusNameWatcherFlags.NONE, self.on_watcher, None)

    def on_watcher(self, _connection, _name, owner):
        log.info('status notifier watcher appeared owner=%s', owner)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

    def build_menu(self):
        settings_item = Gtk.MenuItem(label='青简设置')
        settings_item.connect('activate', self.on_settings)
        self.menu.append(settings_item)
        self.menu.append(Gtk.SeparatorMenuItem())

        im_menu = Gtk.Menu()
        for name in enabled_ims():
            label = IM_NAMES.get(name, name)
            item = Gtk.MenuItem(label=label)
            item.connect('activate', self.on_switch_im, name)
            self.im_items[name] = (item, label)
            im_menu.append(item)
        im_root = Gtk.MenuItem(label='输入法')
        im_root.set_submenu(im_menu)
        self.menu.append(im_root)

        toggle = Gtk.MenuItem(label='中 / 英切换')
        toggle.connect('activate', self.on_toggle)
        self.menu.append(toggle)

        skin_menu = Gtk.Menu()
        for skin in SKINS:
            item = Gtk.MenuItem(label=SKIN_NAMES.get(skin, skin))
            item.connect('activate', self.on_skin, skin)
            self.skin_items[skin] = item
            skin_menu.append(item)
        skin_root = Gtk.MenuItem(label='皮肤')
        skin_root.set_submenu(skin_menu)
        self.menu.append(skin_root)

        self.menu.append(Gtk.SeparatorMenuItem())
        restart = Gtk.MenuItem(label='重新启动 Fcitx4')
        restart.connect('activate', self.on_restart)
        self.menu.append(restart)
        quit_item = Gtk.MenuItem(label='退出托盘')
        quit_item.connect('activate', self.on_quit)
        self.menu.append(quit_item)
        self.menu.show_all()

    def refresh(self):
        state = current_state()
        im = current_im()
        # 英文/未激活时 Fcitx4 可能把当前 IM 报成列表第一个（搜狗），
        # 保持最后一次激活时的输入法，图标才不会在切英文时跳回搜狗
        if state == 2 and im:
            self.last_im = im
        elif self.last_im is None:
            self.last_im = im or profile_value('IMName').strip()
        display = self.last_im or ''
        if display != self.shown_im:
            icon = IM_ICONS.get(display, DEFAULT_ICON)
            self.indicator.set_icon_full(icon, '青简输入法 · ' + (IM_NAMES.get(display, display) or '未知'))
            self.shown_im = display
            log.info('tray icon changed im=%s icon=%s state=%s', display, icon, state)
        for name, (item, label) in self.im_items.items():
            item.set_label(('● ' if name == display else '　 ') + label)
        skin = current_skin()
        for name, item in self.skin_items.items():
            item.set_label(('● ' if name == skin else '　 ') + SKIN_NAMES.get(name, name))
        return True

    def on_settings(self, _item):
        binary = str(SETTINGS) if SETTINGS.is_file() else 'qingjian-settings'
        launch(binary)

    def on_switch_im(self, _item, name):
        switch_im(name)

    def on_toggle(self, _item):
        if d_bus_call('ToggleIM') is None:
            run('fcitx-remote', '-t')

    def on_skin(self, _item, skin):
        set_skin(skin)

    def on_restart(self, _item):
        if d_bus_call('Restart') is None:
            launch('fcitx', '-r')

    def on_quit(self, _item):
        Gtk.main_quit()

    def run(self):
        Gtk.main()


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    args = sys.argv[1:]
    if args == ['--setup']:
        setup_overrides()
        return 0
    if args == ['--undo-setup']:
        undo_overrides()
        return 0
    if args == ['--check']:
        im = current_im()
        print('im=%s icon=%s state=%s skin=%s ims=%s dbus=%s dbus_im=%s' %
              (im, IM_ICONS.get(im, DEFAULT_ICON), current_state(), current_skin(),
               ','.join(enabled_ims()), bool(fcitx()), d_bus_call('GetCurrentIM')))
        return 0
    if args:
        print('用法：qingjian-tray [--setup | --undo-setup | --check]', file=sys.stderr)
        return 2
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        log.error('no display available')
        return 1
    Tray().run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
