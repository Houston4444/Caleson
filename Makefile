#!/usr/bin/make -f
# Makefile for Caleson #
# ---------------------- #
# Created by falkTX
#

PREFIX  = /usr/local
DESTDIR =

LINK   = ln -s
PYUIC ?= pyuic5
PYRCC ?= pyrcc5
PYLUPDATE ?= pylupdate5
LRELEASE ?= lrelease

# Detect X11 rules dir
ifeq "$(wildcard /etc/X11/Xsession.d/ )" ""
	X11_RC_DIR = $(DESTDIR)/etc/X11/xinit/xinitrc.d/
else
	X11_RC_DIR = $(DESTDIR)/etc/X11/Xsession.d/
endif

# -----------------------------------------------------------------------------------------------------------------------------------------
# Internationalization

I18N_LANGUAGES :=

# -----------------------------------------------------------------------------------------------------------------------------------------

all: RES UI locale

# -----------------------------------------------------------------------------------------------------------------------------------------
# Resources

RES: src/resources_rc.py

src/resources_rc.py: resources/resources.qrc
	$(PYRCC) $< -o $@

# -----------------------------------------------------------------------------------------------------------------------------------------
# Translations
locale: locale/caleson_en.qm locale/caleson_fr.qm
	
locale/%.qm: locale/%.ts
	$(LRELEASE) $< -qm $@

# -----------------------------------------------------------------------------------------------------------------------------------------
# UI code

UI: caleson tools

caleson: src/ui_caleson.py \
	src/ui_caleson_tb_alsa.py  \
	src/ui_caleson_rwait.py \
	src/ui_pulse_bridge.py

tools: \
	src/ui_logs.py \
	src/ui_settings_jack.py

src/ui_%.py: resources/ui/%.ui
	$(PYUIC) $< -o $@

# -----------------------------------------------------------------------------------------------------------------------------------------

clean:
	rm -f *~ src/*~ src/*.pyc src/ui_*.py src/resources_rc.py resources/locale/*.qm

# -----------------------------------------------------------------------------------------------------------------------------------------

debug:
	$(MAKE) DEBUG=true

# -----------------------------------------------------------------------------------------------------------------------------------------

install:
	# Create directories
	install -d $(DESTDIR)/etc/xdg/autostart/
	install -d $(DESTDIR)$(PREFIX)/bin/
	install -d $(DESTDIR)$(PREFIX)/share/applications/
	install -d $(DESTDIR)$(PREFIX)/share/icons/hicolor/16x16/apps/
	install -d $(DESTDIR)$(PREFIX)/share/icons/hicolor/48x48/apps/
	install -d $(DESTDIR)$(PREFIX)/share/icons/hicolor/128x128/apps/
	install -d $(DESTDIR)$(PREFIX)/share/icons/hicolor/256x256/apps/
	install -d $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/
	install -d $(DESTDIR)$(PREFIX)/share/caleson/
	install -d $(DESTDIR)$(PREFIX)/share/caleson/src/
	install -d $(DESTDIR)$(PREFIX)/share/caleson/pulse2jack/
	install -d $(DESTDIR)$(PREFIX)/share/caleson/pulse2loopback/
	install -d $(DESTDIR)$(PREFIX)/share/caleson/icons/
	install -d $(DESTDIR)$(PREFIX)/share/caleson/templates/
	install -d $(DESTDIR)$(PREFIX)/share/caleson/locale/
	install -d $(X11_RC_DIR)

	# Install script files and binaries
	install -m 755 \
		data/caleson \
		data/caleson-aloop-daemon \
		data/caleson-logs \
		data/caleson-pulse2jack \
		data/caleson-pulse2loopback \
		data/caleson-session-start \
		data/caleson-jacksettings \
		$(DESTDIR)$(PREFIX)/bin/

	# Install desktop files
	install -m 644 data/autostart/*.desktop $(DESTDIR)/etc/xdg/autostart/
	install -m 644 data/*.desktop           $(DESTDIR)$(PREFIX)/share/applications/

	# Install icons, 16x16
	install -m 644 resources/16x16/caleson.png    $(DESTDIR)$(PREFIX)/share/icons/hicolor/16x16/apps/

	# Install icons, 48x48
	install -m 644 resources/48x48/caleson.png    $(DESTDIR)$(PREFIX)/share/icons/hicolor/48x48/apps/

	# Install icons, 128x128
	install -m 644 resources/128x128/caleson.png  $(DESTDIR)$(PREFIX)/share/icons/hicolor/128x128/apps/

	# Install icons, 256x256
	install -m 644 resources/256x256/caleson.png  $(DESTDIR)$(PREFIX)/share/icons/hicolor/256x256/apps/

	# Install icons, scalable
	install -m 644 resources/scalable/caleson.svg $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/

	# Install main code
	install -m 644 src/*.py $(DESTDIR)$(PREFIX)/share/caleson/src/

	# Install translations
	install -m 644 locale/*.qm $(DESTDIR)$(PREFIX)/share/caleson/locale/

	# compile python files
	python3 -m compileall $(DESTDIR)$(PREFIX)/share/caleson/src/
	
	# Install addtional stuff for Caleson
	install -m 644 data/pulse2jack/*     $(DESTDIR)$(PREFIX)/share/caleson/pulse2jack/
	install -m 644 data/pulse2loopback/* $(DESTDIR)$(PREFIX)/share/caleson/pulse2loopback/
	install -m 755 data/61-caleson-session-inject $(X11_RC_DIR)

	# Adjust PREFIX value in script files
	sed -i "s?X-PREFIX-X?$(PREFIX)?" \
		$(DESTDIR)$(PREFIX)/bin/caleson \
		$(DESTDIR)$(PREFIX)/bin/caleson-aloop-daemon \
		$(DESTDIR)$(PREFIX)/bin/caleson-jacksettings \
		$(DESTDIR)$(PREFIX)/bin/caleson-logs \
		$(DESTDIR)$(PREFIX)/bin/caleson-pulse2jack \
		$(DESTDIR)$(PREFIX)/bin/caleson-pulse2loopback \
		$(DESTDIR)$(PREFIX)/bin/caleson-session-start \
		$(X11_RC_DIR)/61-caleson-session-inject

	# Delete old scripts
	rm -f $(X11_RC_DIR)/21caleson-session-inject
	rm -f $(X11_RC_DIR)/61caleson-session-inject
	rm -f $(X11_RC_DIR)/70caleson-plugin-paths
	rm -f $(X11_RC_DIR)/99caleson-session-start

# -----------------------------------------------------------------------------------------------------------------------------------------

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/caleson*
	rm -f $(DESTDIR)$(PREFIX)/share/applications/caleson.desktop
	rm -f $(DESTDIR)$(PREFIX)/share/icons/hicolor/*/apps/caleson.png
	rm -f $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/caleson.svg
	rm -f $(DESTDIR)/etc/xdg/autostart/caleson-session-start.desktop
	rm -f $(X11_RC_DIR)/61-caleson-session-inject
	rm -rf $(DESTDIR)$(PREFIX)/share/caleson/

	# Delete old scripts
	rm -f $(X11_RC_DIR)/21caleson-session-inject
	rm -f $(X11_RC_DIR)/61caleson-session-inject
	rm -f $(X11_RC_DIR)/70caleson-plugin-paths
	rm -f $(X11_RC_DIR)/99caleson-session-start
