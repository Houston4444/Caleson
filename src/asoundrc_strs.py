
ASOUNDRC_ALOOP = """# ------------------------------------------------------
# Custom asoundrc file for use with snd-aloop and JACK
#
# use it like this:
# env JACK_SAMPLE_RATE=44100 JACK_PERIOD_SIZE=1024 alsa_in (...)
#

# ------------------------------------------------------
# playback device
pcm.aloopPlayback {
  type dmix
  ipc_key 1
  ipc_key_add_uid true
  slave {
    pcm "hw:Loopback,0,0"
    format S32_LE
    rate {
      @func igetenv
      vars [ JACK_SAMPLE_RATE ]
      default 44100
    }
    period_size {
      @func igetenv
      vars [ JACK_PERIOD_SIZE ]
      default 1024
    }
    buffer_size 4096
  }
}

# capture device
pcm.aloopCapture {
  type dsnoop
  ipc_key 2
  ipc_key_add_uid true
  slave {
    pcm "hw:Loopback,0,1"
    format S32_LE
    rate {
      @func igetenv
      vars [ JACK_SAMPLE_RATE ]
      default 44100
    }
    period_size {
      @func igetenv
      vars [ JACK_PERIOD_SIZE ]
      default 1024
    }
    buffer_size 4096
  }
}

# duplex device
pcm.aloopDuplex {
  type asym
  playback.pcm "aloopPlayback"
  capture.pcm "aloopCapture"
}

# ------------------------------------------------------
# default device
pcm.!default {
  type plug
  slave.pcm "aloopDuplex"
}

# ------------------------------------------------------
# alsa_in -j alsa_in -dcloop -q 1
pcm.cloop {
  type dsnoop
  ipc_key 3
  ipc_key_add_uid true
  slave {
    pcm "hw:Loopback,1,0"
    channels 2
    format S32_LE
    rate {
      @func igetenv
      vars [ JACK_SAMPLE_RATE ]
      default 44100
    }
    period_size {
      @func igetenv
      vars [ JACK_PERIOD_SIZE ]
      default 1024
    }
    buffer_size 32768
  }
}

# ------------------------------------------------------
# alsa_out -j alsa_out -dploop -q 1
pcm.ploop {
  type plug
  slave.pcm "hw:Loopback,1,1"
}"""

ASOUNDRC_ALOOP_CHECK = ASOUNDRC_ALOOP.split("pcm.aloopPlayback", 1)[0]

ASOUNDRC_JACK = """pcm.!default {
    type plug
    slave { pcm "jack" }
}

pcm.jack {
    type jack
    playback_ports {
        0 system:playback_1
        1 system:playback_2
    }
    capture_ports {
        0 system:capture_1
        1 system:capture_2
    }
}

ctl.mixer0 {
    type hw
    card 0
}"""

ASOUNDRC_PULSE = """pcm.!default {
    type plug
    slave { pcm "pulse" }
}

pcm.pulse {
    type pulse
}

ctl.mixer0 {
    type hw
    card 0
}"""
