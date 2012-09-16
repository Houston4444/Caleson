# QtCreator project file

QT = core

CONFIG    = debug link_pkgconfig qt warn_on
PKGCONFIG = liblo gtk+-3.0

TARGET   = carla-bridge-lv2-gtk3
TEMPLATE = app
VERSION  = 0.5.0

SOURCES = \
    ../carla_bridge_osc.cpp \
    ../carla_bridge_ui-lv2.cpp \
    ../carla_bridge_toolkit-gtk3.cpp

HEADERS = \
    ../carla_bridge.h \
    ../carla_bridge_client.h \
    ../carla_bridge_osc.h \
    ../carla_bridge_toolkit.h \
    ../../carla-includes/carla_includes.h \
    ../../carla-includes/carla_lib_includes.h \
    ../../carla-includes/carla_osc_includes.h \
    ../../carla-includes/carla_lv2.h \
    ../../carla-includes/carla_midi.h \
    ../../carla-includes/lv2_rdf.h

INCLUDEPATH = .. \
    ../../carla-includes

LIBS    = \
    ../../carla-lilv/carla_lilv.a \
    ../../carla-rtmempool/carla_rtmempool.a

DEFINES  = QTCREATOR_TEST
DEFINES += BUILD_BRIDGE BUILD_BRIDGE_UI BRIDGE_LV2 BRIDGE_LV2_GTK3
DEFINES += DEBUG


QMAKE_CXXFLAGS *= -std=c++0x