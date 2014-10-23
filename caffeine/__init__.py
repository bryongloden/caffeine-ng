# Copyright (c) 2014 Hugo Osvaldo Barrera
# Copyright © 2009 The Caffeine Developers
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#


import gettext
import locale
import logging
import os
from os.path import join, abspath, dirname, pardir
from gi.repository import Gtk
from xdg.BaseDirectory import save_data_path
from . import procmanager


# http://stackoverflow.com/a/9350788/2587286
# http://stackoverflow.com/a/2860193/2587286
SCRIPT_PATH = os.path.dirname(os.path.realpath(__file__))
BASE_PATH = os.path.abspath(os.path.join(SCRIPT_PATH, os.pardir))
DATA_DIR = save_data_path('caffeine')
BASE_KEY = "net.launchpad.caffeine"

LOG_FILE = os.path.join(DATA_DIR, 'caffeine.log')
WHITELIST = os.path.join(DATA_DIR, 'whitelist.txt')

# Create an empty file if it doesn't exist.
if not os.path.isfile(WHITELIST):
    open(WHITELIST, "w").close()


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_FILE)
ch = logging.StreamHandler()
f = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(f)
ch.setFormatter(f)
logger.addHandler(fh)
logger.addHandler(ch)

_ProcMan = procmanager.ProcManager()


def get_ProcManager():
    return _ProcMan


IMAGE_PATH = join(BASE_PATH, 'share', 'caffeine', 'images')
GLADE_PATH = join(BASE_PATH, 'share', 'caffeine', 'glade')
ICON_PATH = join(BASE_PATH, 'share', 'icons')

_desktop_file = join(BASE_PATH, 'share', 'applications', 'caffeine.desktop')

FULL_ICON_PATH = join(IMAGE_PATH, "Full_Cup.svg")
EMPTY_ICON_PATH = join(IMAGE_PATH, "Empty_Cup.svg")

GENERIC_PROCESS_ICON_PATH = join(IMAGE_PATH, "application-x-executable.png")

ICON_NAME = 'caffeine'
icon_theme = Gtk.IconTheme.get_default()


def get_icon_pixbuf(size):
    global icon_theme
    global ICON_NAME

    iconInfo = icon_theme.lookup_icon(ICON_NAME, size,
                                      Gtk.IconLookupFlags.NO_SVG)

    if iconInfo:
        # icon is found
        base_size = iconInfo.get_base_size()
        if base_size != size:
            # No sizexsize icon in the users theme so use the default
            icon_theme = Gtk.IconTheme()
            icon_theme.set_search_path((ICON_PATH,))
    else:
        icon_theme.append_search_path(ICON_PATH)
        iconInfo = icon_theme.lookup_icon(ICON_NAME, size,
                                          Gtk.IconLookupFlags.NO_SVG)

    pixbuf = icon_theme.load_icon(ICON_NAME, size,
                                  Gtk.IconLookupFlags.NO_SVG)

    return pixbuf


def __init_translations():
    GETTEXT_DOMAIN = "caffeine"
    LOCALE_PATH = os.path.join(BASE_PATH, "share", "locale")

    locale.setlocale(locale.LC_ALL, '')

    for module in locale, gettext:
        module.bindtextdomain(GETTEXT_DOMAIN, LOCALE_PATH)
        module.textdomain(GETTEXT_DOMAIN)

__init_translations()

from .main import main
__all__ = ['main', 'WHITELIST', 'FULL_ICON_PATH', 'EMPTY_ICON_PATH',
           'GENERIC_PROCESS_ICON_PATH', 'GLADE_PATH', 'get_icon_pixbuf']
