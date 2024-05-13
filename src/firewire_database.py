# List of Firewire interfaces with some ALSA support.
# this list has been taken from 
# https://github.com/alsa-project/snd-firewire-ctl-services

_DATABASE = """
snd-isight-ctl-service
    Apple iSight
snd-firewire-digi00x-ctl-service
    Digi 002
    Digi 002 Rack
    Digi 003
    Digi 003 Rack
    Digi 003 Rack+
snd-firewire-tascam-ctl-service
    Tascam FW-1884
    Tascam FW-1082
    Tascam FW-1804
    Tascam FE-8 (work without ALSA firewire-tascam driver)
snd-fireworks-ctl-service
    Mackie (Loud) Onyx 1200F
    Mackie (Loud) Onyx 400F
    Echo Audio Audiofire 12 (till Jul 2009)
    Echo Audio Audiofire 8 (till Jul 2009)
    Echo Audio Audiofire 12 (since Jul 2009)
    Echo Audio Audiofire 8 (since Jul 2009)
    Echo Audio Audiofire 2
    Echo Audio Audiofire 4
    Echo Audio Audiofire Pre8
    Gibson Robot Interface Pack (RIP) for Robot Guitar series
snd-firewire-motu-ctl-service
    MOTU 828
    MOTU 896
    MOTU Traveler
    MOTU 828mkII
    MOTU 896HD
    MOTU UltraLite
    MOTU 8pre
    MOTU 4pre
    MOTU AudioExpress
    MOTU 828mk3 (FireWire only)
    MOTU 828mk3 (Hybrid)
    MOTU 896mk3 (FireWire only)
    MOTU 896mk3 (Hybrid)
    MOTU UltraLite mk3 (FireWire only)
    MOTU UltraLite mk3 (Hybrid)
    MOTU Traveler mk3
    MOTU Track 16
snd-oxfw-ctl-service
    Tascam FireOne
    Apogee Duet FireWire
    Griffin FireWave
    Lacie FireWire Speakers
    Mackie Tapco Link.FireWire 4x6
snd-bebob-ctl-service
    Apogee Ensemble
    Behringer Firepower FCA610
    Digidesign Mbox 2 Pro
    Ego Systems Quatafire 610
    Focusrite Saffire
    Focusrite Saffire LE
    Focusrite Saffire Pro 10 i/o
    Focusrite Saffire Pro 26 i/o
    Icon Firexon
    M-Audio FireWire Solo
    M-Audio FireWire Audiophile
    M-Audio FireWire 410
    M-Audio FireWire 1814
    M-Audio Ozonic
    M-Audio ProFire LightBridge
    M-Audio ProjectMix I/O
    PreSonus Firebox
    PreSonus Firepod/FP10
    PreSonus Inspire 1394
    Roland Edirol FA-66
    Roland Edirol FA-101
    Stanton ScratchAmp in Final Scratch version 2
    TerraTec Aureon 7.1 FW
    TerraTec Phase 24 FW
    TerraTec Phase X24 FW
    TerraTec Phase 88 FW
    Yamaha Go 44
    Yamaha Go 46
snd-dice-ctl-service
    M-Audio ProFire 2626
    M-Audio ProFire 610
    Avid Mbox 3 Pro
    TC Electronic Konnekt 24d
    TC Electronic Konnekt 8
    TC Electronic Studio Konnekt 48
    TC Electronic Konnekt Live
    TC Electronic Desktop Konnekt 6
    TC Electronic Impact Twin
    TC Electronic Digital Konnekt x32
    Alesis MultiMix 8/12/16 FireWire
    Alesis iO 14
    Alesis iO 26
    Alesis MasterControl
    Lexicon I-ONIX FW810s
    Focusrite Saffire Pro 40
    Focusrite Liquid Saffire 56
    Focusrite Saffire Pro 24
    Focusrite Saffire Pro 24 DSP
    Focusrite Saffire Pro 14
    Focusrite Saffire Pro 26
    PreSonus FireStudio
    PreSonus FireStudio Project
    PreSonus FireStudio Tube
    PreSonus FireStudio Mobile
    Weiss Engineering ADC2
    Weiss Engineering Vesta
    Weiss Engineering DAC2, Minerva
    Weiss Engineering AFI1
    Weiss Engineering INT202, INT203, DAC1 FireWire option card
    Weiss Engineering DAC202, Maya
    Weiss Engineering MAN301
snd-fireface-ctl-service
    Fireface 800
    Fireface 400
    Fireface UCX
    Fireface 802
"""

def as_driver_interfaces() -> dict[str, list[str]]:
    driver_interfaces = dict[str, list[str]]()
    driver = ''
    
    for line in _DATABASE.splitlines():
        if not line.startswith(' '):
            driver = line.strip().replace('-ctl-service', '')
            continue
        
        if not driver:
            continue
        
        if driver_interfaces.get(driver) is None:
            driver_interfaces[driver] = list[str]()
            
        driver_interfaces[driver].append(line.strip())
        
    return driver_interfaces

DRIVER_INTERFACES = as_driver_interfaces()