# -*- coding: utf-8 -*-
#
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


from gi.repository import GObject, Notify
import os
import os.path
import subprocess

import dbus
import threading

from . import applicationinstance

import caffeine
from . import utils
import logging

from gettext import gettext as _

logging.basicConfig(level=logging.INFO)
os.chdir(os.path.abspath(os.path.dirname(__file__)))


class Caffeine(GObject.GObject):

    def __init__(self):

        GObject.GObject.__init__(self)

        # object to manage processes to activate for.
        self.ProcMan = caffeine.get_ProcManager()

        # Status string.
        self.status_string = ""

        # Makes sure that only one instance of Caffeine is run for
        # each user on the system.
        self.pid_name = '/tmp/caffeine' + str(os.getuid()) + '.pid'
        self.appInstance = \
            applicationinstance.ApplicationInstance(self.pid_name)

        # This variable is set to a string describing the type of screensaver
        # and powersaving systems used on this computer. It is detected when
        # the user first attempts to inhibit the screensaver and powersaving,
        # and can be set to one of the following values: "Gnome", "KDE",
        # "XSS+DPMS" or "DPMS".
        self.screensaverAndPowersavingType = None

        # Set to True when the detection routine is in progress
        self.attemptingToDetect = False

        self.dbusDetectionTimer = None
        self.dbusDetectionFailures = 0

        # Set to True when sleep seems to be prevented from the perspective of
        # the user.  This does not necessarily mean that sleep really is
        # prevented, because the detection routine could be in progress.
        self.sleepAppearsPrevented = False

        # Set to True when sleep mode has been successfully inhibited somehow.
        # This should match up with "self.sleepAppearsPrevented" most of the
        # time.
        self.sleepIsPrevented = False

        self.preventedForProcess = False
        self.preventedForFlash = False

        self.screenSaverCookie = None
        self.powerManagementCookie = None
        self.timer = None
        self.inhibit_id = None

        self.note = None

        # FIXME: add capability to xdg-screensaver to report timeout.
        GObject.timeout_add(10000, self._check_for_process)

        print(self.status_string)

    def _check_for_process(self):
        activate = False
        for proc in self.ProcMan.get_process_list():
            if utils.isProcessRunning(proc):

                activate = True

                if self.preventedForProcess or not self.getActivated():
                    logging.info("Caffeine has detected that the process '" +
                                 proc + "' is running, and will auto-activate")
                    self.setActivated(True)
                    self.preventedForProcess = True
                else:
                    logging.info("Caffeine has detected that the process '" +
                                 proc + "' is running, but will NOT auto-" +
                                 "-activate as Caffeine has already been " +
                                 "activated for a different reason.")

        # No process in the list is running, deactivate.
        if not activate and self.preventedForProcess:
            logging.info("Caffeine had previously auto-activated for a " +
                         "process, but that process is no longer running; " +
                         "deactivating...")
            self.setActivated(False)

        return True

    def quit(self):
        """Cancels any timer thread running
        so the program can quit right away.
        """
        if self.timer:
            self.timer.cancel()

        if self.dbusDetectionTimer:
            self.dbusDetectionTimer.cancel()

    def _notify(self, message, icon, title="Caffeine"):
        """Easy way to use pynotify"""
        try:

            Notify.init("Caffeine")
            if self.note:
                self.note.update(title, message, icon)
            else:
                self.note = Notify.Notification(title, message, icon)

            # Notify OSD doesn't seem to work when sleep is prevented
            if self.screenSaverCookie is not None and self.sleepIsPrevented:
                self.ssProxy.UnInhibit(self.screenSaverCookie)

            self.note.show()

            if self.screenSaverCookie is not None and self.sleepIsPrevented:
                self.screenSaverCookie = \
                    self.ssProxy.Inhibit("Caffeine",
                                         "User has requested that Caffeine " +
                                         "disable the screen saver")

        except Exception as e:
            logging.error("Exception occurred:\n" + " " + str(e))
            logging.error("Exception occurred attempting to display " +
                          "message:\n" + message)
        finally:
            return False

    def getActivated(self):
        return self.sleepAppearsPrevented

    def timedActivation(self, time, note=True):
        """Calls toggleActivated after the number of seconds
        specified by time has passed.
        """
        message = (_("Timed activation set; ") +
                   _("Caffeine will prevent powersaving for the next ") +
                   str(time))

        logging.info("Timed activation set for " + str(time))

        if self.status_string == "":
            self.status_string = _("Activated for ")+str(time)
            self.emit("activation-toggled", self.getActivated(),
                      self.status_string)

        self.setActivated(True, note)

        if note:
            self._notify(message, caffeine.FULL_ICON_PATH)

        # and deactivate after time has passed.
        # Stop already running timer
        if self.timer:
            logging.info("Previous timed activation cancelled due to a " +
                         "second timed activation request (was set for " +
                         str(self.timer.interval) + " or " +
                         str(time)+" seconds )")
            self.timer.cancel()

        self.timer = threading.Timer(time, self._deactivate, args=[note])
        self.timer.name = "Active"
        self.timer.start()

    def _deactivate(self, note):
        self.timer.name = "Expired"
        self.toggleActivated(note=note)

    def setActivated(self, activate, note=True):
        if self.getActivated() != activate:
            self.toggleActivated(note)

    def toggleActivated(self, note=True):
        """This function toggles the inhibition of the screensaver and
        powersaving features of the current computer, detecting the the type of
        screensaver and powersaving in use, if it has not been detected
        already."""

        self.preventedForProcess = False
        self.preventedForFlash = False

        if self.sleepAppearsPrevented:
            # sleep prevention was on now turn it off

            self.sleepAppearsPrevented = False
            logging.info("Caffeine is now dormant; powersaving is re-enabled")
            self.status_string = \
                _("Caffeine is dormant; powersaving is enabled")

            # If the user clicks on the full coffee-cup to disable
            # sleep prevention, it should also
            # cancel the timer for timed activation.

            if self.timer is not None and self.timer.name != "Expired":
                message = (_("Timed activation cancelled (was set for ") +
                           str(self.timer.interval) + ")")

                logging.info("Timed activation cancelled (was set for " +
                             str(self.timer.interval) + ")")

                if note:
                    self._notify(message, caffeine.EMPTY_ICON_PATH)

                self.timer.cancel()
                self.timer = None

            elif self.timer is not None and self.timer.name == "Expired":
                message = (str(self.timer.interval) +
                           _(" have elapsed; powersaving is re-enabled"))

                logging.info("Timed activation period (" +
                             str(self.timer.interval) +
                             ") has elapsed")

                if note:
                    self._notify(message, caffeine.EMPTY_ICON_PATH)

                self.timer = None

        else:
            self.sleepAppearsPrevented = True

        self._performTogglingActions()

        if self.status_string == "":
            if self.screensaverAndPowersavingType is not None:
                self.status_string = (_("Caffeine is preventing powersaving " +
                                      "modes and screensaver activation ") +
                                      "(" + self.screensaverAndPowersavingType
                                      + ")")

        self.emit("activation-toggled", self.getActivated(),
                  self.status_string)
        self.status_string = ""

    def _detectScreensaverAndPowersavingType(self):
        """This method always runs when the first attempt to inhibit the
        screensaver and powersaving is made. It detects what
        screensaver/powersaving software is running.  After detection is
        complete, it will finish the inhibiting process."""

        logging.info("Attempting to detect screensaver/powersaving type... ("
                     + str(self.dbusDetectionFailures) +
                     " dbus failures so far)")
        bus = dbus.SessionBus()

        if 'org.gnome.SessionManager' in bus.list_names() and \
           utils.isProcessRunning("gnome-screensaver"):
            self.screensaverAndPowersavingType = "Gnome3"

        elif 'org.freedesktop.ScreenSaver' in bus.list_names() and \
             'org.freedesktop.PowerManagement.Inhibit' in bus.list_names():
            self.screensaverAndPowersavingType = "KDE"
        else:
            self.dbusDetectionFailures += 1
            if self.dbusDetectionFailures <= 3:
                self.dbusDetectionTimer = \
                    threading.Timer(10,
                                    self._detectScreensaverAndPowersavingType)
                self.dbusDetectionTimer.start()
                return
            else:
                # At this point, all attempts to connect to the relevant dbus
                # interfaces have failed.  This user must be using something
                # other than the Gnome or KDE screensaver programs.
                if utils.isProcessRunning("xscreensaver"):
                    self.screensaverAndPowersavingType = "XSS+DPMS"
                else:
                    self.screensaverAndPowersavingType = "DPMS"

        self.attemptingToDetect = False
        self.dbusDetectionFailures = 0
        self.dbusDetectionTimer = None

        logging.info("Successfully detected screensaver and powersaving type: "
                     + str(self.screensaverAndPowersavingType))

        if self.sleepAppearsPrevented != self.sleepIsPrevented:
            self._performTogglingActions()

    def _performTogglingActions(self):
        """This method performs the actions that affect the screensaver and
        powersaving."""
        if self.screensaverAndPowersavingType is None:
            if self.attemptingToDetect is False:
                self.attemptingToDetect = True
                self._detectScreensaverAndPowersavingType()
            return

        if self.screensaverAndPowersavingType == "Gnome":
            self._toggleGnome()
        if self.screensaverAndPowersavingType == "Gnome3":
            self._toggleGnome3()
        elif self.screensaverAndPowersavingType == "KDE":
            self._toggleKDE()
        elif self.screensaverAndPowersavingType == "XSS+DPMS":
            self._toggleXSSAndDPMS()
        elif self.screensaverAndPowersavingType == "DPMS":
            self._toggleDPMS()

        if self.sleepIsPrevented is False:
            logging.info("Caffeine is now preventing powersaving modes" +
                         " and screensaver activation (" +
                         self.screensaverAndPowersavingType + ")")

        self.sleepIsPrevented = not self.sleepIsPrevented

    def _toggleGnome3(self):
        """Toggle the screensaver and powersaving with the interfaces used by
        Gnome 3."""

        self._toggleDPMS()
        bus = dbus.SessionBus()
        self.susuProxy = bus.get_object('org.gnome.SessionManager',
                                        '/org/gnome/SessionManager')
        if self.sleepIsPrevented:
            if self.screenSaverCookie is not None:
                self.susuProxy.Uninhibit(self.screenSaverCookie)
        else:
            self.screenSaverCookie = \
                self.susuProxy.Inhibit("Caffeine", dbus.UInt32(0),
                                       "User has requested that Caffeine " +
                                       "disable the screen saver",
                                       dbus.UInt32(8))

    def _toggleKDE(self):
        """Toggle the screensaver and powersaving with the interfaces used by
        KDE."""

        self._toggleDPMS()
        bus = dbus.SessionBus()
        self.ssProxy = bus.get_object('org.freedesktop.ScreenSaver',
                                      '/ScreenSaver')
        pmProxy = bus.get_object('org.freedesktop.PowerManagement.Inhibit',
                                 '/org/freedesktop/PowerManagement/Inhibit')
        if self.sleepIsPrevented:
            if self.screenSaverCookie is not None:
                self.ssProxy.UnInhibit(self.screenSaverCookie)
            if self.powerManagementCookie is not None:
                pmProxy.UnInhibit(self.powerManagementCookie)
        else:
            self.powerManagementCookie = \
                pmProxy.Inhibit("Caffeine", "User has requested that " +
                                "Caffeine disable the powersaving modes")
            self.screenSaverCookie = \
                self.ssProxy.Inhibit("Caffeine", "User has requested " +
                                     "that Caffeine disable the screen saver")

    def _toggleXSSAndDPMS(self):
        self._toggleXSS()
        self._toggleDPMS()

    def _toggleDPMS(self):
        """Toggle the DPMS powersaving subsystem."""
        if self.sleepIsPrevented:
            subprocess.getoutput("xset +dpms")
            subprocess.getoutput("xset s on")
        else:
            subprocess.getoutput("xset -dpms")
            subprocess.getoutput("xset s off")

    def _toggleXSS(self):
        """Toggle whether XScreensaver is activated (powersaving is
        unaffected)"""

        if self.sleepIsPrevented:
            # sleep prevention was on now turn it off

            # If the user clicks on the full coffee-cup to disable
            # sleep prevention, it should also
            # cancel the timer for timed activation.

            if self.inhibit_id is not None:
                GObject.source_remove(self.inhibit_id)

        else:
            def deactivate():
                try:
                    subprocess.getoutput("xscreensaver-command -deactivate")
                except Exception as data:
                    logging.error("Exception occurred:\n" + data)
                return True

            # reset the idle timer every 50 seconds.
            self.inhibit_id = GObject.timeout_add(50000, deactivate)


# register a signal
GObject.signal_new("activation-toggled", Caffeine,
                   GObject.SignalFlags.RUN_FIRST, None, [bool, str])
