/*
 * Carla Backend
 * Copyright (C) 2012 Filipe Coelho <falktx@falktx.com>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * For a full copy of the GNU General Public License see the COPYING file
 */

#include "carla_plugin.h"
#include "plugins/carla_native.h"

CARLA_BACKEND_START_NAMESPACE

struct NativePluginMidiData {
    uint32_t count;
    uint32_t* rindexes;
    CarlaEngineMidiPort** ports;

    NativePluginMidiData()
        : count(0),
          rindexes(nullptr),
          ports(nullptr) {}
};

class NativePluginScopedInitiliazer
{
public:
    NativePluginScopedInitiliazer()
    {
    }

    ~NativePluginScopedInitiliazer()
    {
        for (size_t i=0; i < descriptors.size(); i++)
        {
            const PluginDescriptor* const desc = descriptors[i];

            if (desc->_fini)
                desc->_fini((struct _PluginDescriptor*)desc);
        }

        descriptors.clear();
    }

    void initializeIfNeeded(const PluginDescriptor* const desc)
    {
        if (descriptors.empty() || std::find(descriptors.begin(), descriptors.end(), desc) == descriptors.end())
        {
            if (desc->_init)
                desc->_init((struct _PluginDescriptor*)desc);

            descriptors.push_back(desc);
        }
    }

private:
    std::vector<const PluginDescriptor*> descriptors;
};

static NativePluginScopedInitiliazer scopedInitliazer;

class NativePlugin : public CarlaPlugin
{
public:
    NativePlugin(CarlaEngine* const engine, const unsigned short id)
        : CarlaPlugin(engine, id)
    {
        qDebug("NativePlugin::NativePlugin()");

        m_type = PLUGIN_INTERNAL;

        descriptor = nullptr;
        handle     = nullptr;

        host.handle = this;
        host.get_buffer_size  = carla_host_get_buffer_size;
        host.get_sample_rate  = carla_host_get_sample_rate;
        host.get_time_info    = carla_host_get_time_info;
        host.write_midi_event = carla_host_write_midi_event;

        isProcessing = false;

        midiEventCount = 0;
        memset(midiEvents, 0, sizeof(::MidiEvent) * MAX_MIDI_EVENTS * 2);
    }

    ~NativePlugin()
    {
        qDebug("NativePlugin::~NativePlugin()");

        if (descriptor)
        {
            if (descriptor->deactivate && m_activeBefore)
            {
                if (handle)
                    descriptor->deactivate(handle);
                //if (h2)
                //    descriptor->deactivate(h2);
            }

            if (descriptor->cleanup)
            {
                if (handle)
                    descriptor->cleanup(handle);
                //if (h2)
                //    descriptor->cleanup(h2);
            }
        }
    }

    // -------------------------------------------------------------------
    // Information (base)

    PluginCategory category()
    {
        Q_ASSERT(descriptor);

        if (descriptor)
            return (PluginCategory)descriptor->category;

        return getPluginCategoryFromName(m_name);
    }

    // -------------------------------------------------------------------
    // Information (count)

    uint32_t midiInCount()
    {
        return mIn.count;
    }

    uint32_t midiOutCount()
    {
        return mOut.count;
    }

    uint32_t parameterScalePointCount(const uint32_t parameterId)
    {
        Q_ASSERT(descriptor);
        Q_ASSERT(parameterId < param.count);

        int32_t rindex = param.data[parameterId].rindex;

        if (descriptor && rindex < (int32_t)descriptor->portCount)
        {
            const PluginPort* const port = &descriptor->ports[rindex];

            if (port)
                return port->scalePointCount;
        }

        return 0;
    }

    // -------------------------------------------------------------------
    // Information (per-plugin data)

    double getParameterValue(const uint32_t parameterId)
    {
        Q_ASSERT(descriptor);
        Q_ASSERT(handle);
        Q_ASSERT(parameterId < param.count);

        if (descriptor && handle)
            return descriptor->get_parameter_value(handle, parameterId);

        return 0.0;
    }

    double getParameterScalePointValue(const uint32_t parameterId, const uint32_t scalePointId)
    {
        Q_ASSERT(descriptor);
        Q_ASSERT(parameterId < param.count);
        Q_ASSERT(scalePointId < parameterScalePointCount(parameterId));

        const int32_t rindex = param.data[parameterId].rindex;

        if (descriptor && rindex < (int32_t)descriptor->portCount)
        {
            const PluginPort* const port = &descriptor->ports[rindex];

            if (port && scalePointId < port->scalePointCount)
            {
                const PluginPortScalePoint* const scalePoint = &port->scalePoints[scalePointId];

                if (scalePoint)
                    return scalePoint->value;
            }
        }

        return 0.0;
    }

    void getLabel(char* const strBuf)
    {
        Q_ASSERT(descriptor);

        if (descriptor && descriptor->label)
            strncpy(strBuf, descriptor->label, STR_MAX);
        else
            CarlaPlugin::getLabel(strBuf);
    }

    void getMaker(char* const strBuf)
    {
        Q_ASSERT(descriptor);

        if (descriptor && descriptor->maker)
            strncpy(strBuf, descriptor->maker, STR_MAX);
        else
            CarlaPlugin::getMaker(strBuf);
    }

    void getCopyright(char* const strBuf)
    {
        Q_ASSERT(descriptor);

        if (descriptor && descriptor->copyright)
            strncpy(strBuf, descriptor->copyright, STR_MAX);
        else
            CarlaPlugin::getCopyright(strBuf);
    }

    void getRealName(char* const strBuf)
    {
        Q_ASSERT(descriptor);

        if (descriptor && descriptor->name)
            strncpy(strBuf, descriptor->name, STR_MAX);
        else
            CarlaPlugin::getRealName(strBuf);
    }

    void getParameterName(const uint32_t parameterId, char* const strBuf)
    {
        Q_ASSERT(descriptor);
        Q_ASSERT(parameterId < param.count);

        const int32_t rindex = param.data[parameterId].rindex;

        if (descriptor && rindex < (int32_t)descriptor->portCount)
        {
            const PluginPort* const port = &descriptor->ports[rindex];

            if (port && port->name)
            {
                strncpy(strBuf, port->name, STR_MAX);
                return;
            }
        }

        CarlaPlugin::getParameterName(parameterId, strBuf);
    }

    void getParameterText(const uint32_t parameterId, char* const strBuf)
    {
        Q_ASSERT(descriptor);
        Q_ASSERT(handle);
        Q_ASSERT(parameterId < param.count);

        if (descriptor && handle)
        {
            const int32_t rindex = param.data[parameterId].rindex;

            const char* const text = descriptor->get_parameter_text(handle, rindex);

            if (text)
            {
                strncpy(strBuf, text, STR_MAX);
                return;
            }
        }

        CarlaPlugin::getParameterText(parameterId, strBuf);
    }

    void getParameterUnit(const uint32_t parameterId, char* const strBuf)
    {
        Q_ASSERT(descriptor);
        Q_ASSERT(handle);
        Q_ASSERT(parameterId < param.count);

        if (descriptor && handle)
        {
            const int32_t rindex = param.data[parameterId].rindex;

            const char* const unit = descriptor->get_parameter_unit(handle, rindex);

            if (unit)
            {
                strncpy(strBuf, unit, STR_MAX);
                return;
            }
        }

        CarlaPlugin::getParameterUnit(parameterId, strBuf);
    }

    void getParameterScalePointLabel(const uint32_t parameterId, const uint32_t scalePointId, char* const strBuf)
    {
        Q_ASSERT(descriptor);
        Q_ASSERT(parameterId < param.count);
        Q_ASSERT(scalePointId < parameterScalePointCount(parameterId));

        int32_t rindex = param.data[parameterId].rindex;

        if (descriptor && rindex < (int32_t)descriptor->portCount)
        {
            const PluginPort* const port = &descriptor->ports[rindex];

            if (port && scalePointId < port->scalePointCount)
            {
                const PluginPortScalePoint* const scalePoint = &port->scalePoints[scalePointId];

                if (scalePoint && scalePoint->label)
                {
                    strncpy(strBuf, scalePoint->label, STR_MAX);
                    return;
                }
            }
        }

        CarlaPlugin::getParameterScalePointLabel(parameterId, scalePointId, strBuf);
    }

    // -------------------------------------------------------------------
    // Set data (plugin-specific stuff)

    void setParameterValue(const uint32_t parameterId, double value, const bool sendGui, const bool sendOsc, const bool sendCallback)
    {
        Q_ASSERT(descriptor);
        Q_ASSERT(handle);
        Q_ASSERT(parameterId < param.count);

        if (descriptor && handle)
            descriptor->set_parameter_value(handle, parameterId, fixParameterValue(value, param.ranges[parameterId]));

        CarlaPlugin::setParameterValue(parameterId, value, sendGui, sendOsc, sendCallback);
    }

    void setCustomData(const CustomDataType type, const char* const key, const char* const value, const bool sendGui)
    {
        Q_ASSERT(descriptor);
        Q_ASSERT(handle);
        Q_ASSERT(type == CUSTOM_DATA_STRING);
        Q_ASSERT(key);
        Q_ASSERT(value);

        if (type != CUSTOM_DATA_STRING)
            return qCritical("NativePlugin::setCustomData(%s, \"%s\", \"%s\", %s) - type is not string", CustomDataType2str(type), key, value, bool2str(sendGui));

        if (! key)
            return qCritical("NativePlugin::setCustomData(%s, \"%s\", \"%s\", %s) - key is null", CustomDataType2str(type), key, value, bool2str(sendGui));

        if (! value)
            return qCritical("Nativelugin::setCustomData(%s, \"%s\", \"%s\", %s) - value is null", CustomDataType2str(type), key, value, bool2str(sendGui));

        if (descriptor && handle)
            descriptor->set_custom_data(handle, key, value);

        CarlaPlugin::setCustomData(type, key, value, sendGui);
    }

    void setMidiProgram(int32_t index, const bool sendGui, const bool sendOsc, const bool sendCallback, const bool block)
    {
        Q_ASSERT(descriptor);
        Q_ASSERT(handle);
        Q_ASSERT(index >= -1 && index < (int32_t)midiprog.count);

        if (index < -1)
            index = -1;
        else if (index > (int32_t)midiprog.count)
            return;

        if (descriptor && handle && index >= 0)
        {
            if (x_engine->isOffline())
            {
                const CarlaEngine::ScopedLocker m(x_engine, block);
                descriptor->set_midi_program(handle, midiprog.data[index].bank, midiprog.data[index].program);
            }
            else
            {
                const ScopedDisabler m(this, block);
                descriptor->set_midi_program(handle, midiprog.data[index].bank, midiprog.data[index].program);
            }
        }

        CarlaPlugin::setMidiProgram(index, sendGui, sendOsc, sendCallback, block);
    }

    // -------------------------------------------------------------------
    // Set gui stuff

    void showGui(const bool yesNo)
    {
        Q_ASSERT(descriptor);

        if (descriptor && handle)
            descriptor->show_gui(handle, yesNo);
    }

    void idleGui()
    {
        // FIXME - this should not be called if there's no GUI!
        Q_ASSERT(descriptor);

        if (descriptor && descriptor->idle_gui && handle)
            descriptor->idle_gui(handle);
    }

    // -------------------------------------------------------------------
    // Plugin state

    void reload()
    {
        qDebug("NativePlugin::reload() - start");
        Q_ASSERT(descriptor);

        // Safely disable plugin for reload
        const ScopedDisabler m(this);

        if (x_client->isActive())
            x_client->deactivate();

        // Remove client ports
        removeClientPorts();

        // Delete old data
        deleteBuffers();

        uint32_t aIns, aOuts, mIns, mOuts, params, j;
        aIns = aOuts = mIns = mOuts = params = 0;

        const double sampleRate  = x_engine->getSampleRate();
        const uint32_t portCount = descriptor->portCount;

        for (uint32_t i=0; i < portCount; i++)
        {
            const PortType portType  = descriptor->ports[i].type;
            const uint32_t portHints = descriptor->ports[i].hints;

            if (portType == PORT_TYPE_AUDIO)
            {
                if (portHints & PORT_HINT_IS_OUTPUT)
                    aOuts += 1;
                else
                    aIns += 1;
            }
            else if (portType == PORT_TYPE_MIDI)
            {
                if (portHints & PORT_HINT_IS_OUTPUT)
                    mOuts += 1;
                else
                    mIns += 1;
            }
            else if (portType == PORT_TYPE_PARAMETER)
                params += 1;
        }

        if (aIns > 0)
        {
            aIn.ports    = new CarlaEngineAudioPort*[aIns];
            aIn.rindexes = new uint32_t[aIns];
        }

        if (aOuts > 0)
        {
            aOut.ports    = new CarlaEngineAudioPort*[aOuts];
            aOut.rindexes = new uint32_t[aOuts];
        }

        if (mIns > 0)
        {
            mIn.ports    = new CarlaEngineMidiPort*[mIns];
            mIn.rindexes = new uint32_t[mIns];
        }

        if (mOuts > 0)
        {
            mOut.ports    = new CarlaEngineMidiPort*[mOuts];
            mOut.rindexes = new uint32_t[mOuts];
        }

        if (params > 0)
        {
            param.data   = new ParameterData[params];
            param.ranges = new ParameterRanges[params];
        }

        const int portNameSize = CarlaEngine::maxPortNameSize() - 2;
        char portName[portNameSize];
        bool needsCtrlIn  = false;
        bool needsCtrlOut = false;

        for (uint32_t i=0; i < portCount; i++)
        {
            const PortType portType  = descriptor->ports[i].type;
            const uint32_t portHints = descriptor->ports[i].hints;

            if (portType == PORT_TYPE_AUDIO || portType == PORT_TYPE_MIDI)
            {
                if (carlaOptions.processMode != PROCESS_MODE_MULTIPLE_CLIENTS)
                {
                    strcpy(portName, m_name);
                    strcat(portName, ":");
                    strncat(portName, descriptor->ports[i].name, portNameSize/2);
                }
                else
                    strncpy(portName, descriptor->ports[i].name, portNameSize);
            }

            if (portType == PORT_TYPE_AUDIO)
            {
                if (portHints & PORT_HINT_IS_OUTPUT)
                {
                    j = aOut.count++;
                    aOut.ports[j]    = (CarlaEngineAudioPort*)x_client->addPort(CarlaEnginePortTypeAudio, portName, false);
                    aOut.rindexes[j] = i;
                    needsCtrlIn = true;
                }
                else
                {
                    j = aIn.count++;
                    aIn.ports[j]    = (CarlaEngineAudioPort*)x_client->addPort(CarlaEnginePortTypeAudio, portName, true);
                    aIn.rindexes[j] = i;
                }
            }
            else if (portType == PORT_TYPE_MIDI)
            {
                if (portHints & PORT_HINT_IS_OUTPUT)
                {
                    j = mOut.count++;
                    mOut.ports[j]    = (CarlaEngineMidiPort*)x_client->addPort(CarlaEnginePortTypeMIDI, portName, false);
                    mOut.rindexes[j] = i;
                }
                else
                {
                    j = mIn.count++;
                    mIn.ports[j]    = (CarlaEngineMidiPort*)x_client->addPort(CarlaEnginePortTypeMIDI, portName, true);
                    mIn.rindexes[j] = i;
                }
            }
            else if (portType == PORT_TYPE_PARAMETER)
            {
                j = param.count++;
                param.data[j].index  = j;
                param.data[j].rindex = i;
                param.data[j].hints  = 0;
                param.data[j].midiChannel = 0;
                param.data[j].midiCC = -1;

                double min, max, def, step, stepSmall, stepLarge;

                ::ParameterRanges ranges = { 0.0, 0.0, 1.0, 0.01, 0.0001, 0.1 };
                descriptor->get_parameter_ranges(handle, i, &ranges);

                // min value
                min = ranges.min;

                // max value
                min = ranges.max;

                if (min > max)
                    max = min;
                else if (max < min)
                    min = max;

                if (max - min == 0.0)
                {
                    qWarning("Broken plugin parameter: max - min == 0");
                    max = min + 0.1;
                }

                // default value
                def = ranges.def;

                if (def < min)
                    def = min;
                else if (def > max)
                    def = max;

                if (portHints & PORT_HINT_USES_SAMPLE_RATE)
                {
                    min *= sampleRate;
                    max *= sampleRate;
                    def *= sampleRate;
                    param.data[j].hints |= PARAMETER_USES_SAMPLERATE;
                }

                if (portHints & PORT_HINT_IS_BOOLEAN)
                {
                    step = max - min;
                    stepSmall = step;
                    stepLarge = step;
                    param.data[j].hints |= PARAMETER_IS_BOOLEAN;
                }
                else if (portHints & PORT_HINT_IS_INTEGER)
                {
                    step = 1.0;
                    stepSmall = 1.0;
                    stepLarge = 10.0;
                    param.data[j].hints |= PARAMETER_IS_INTEGER;
                }
                else
                {
                    double range = max - min;
                    step = range/100.0;
                    stepSmall = range/1000.0;
                    stepLarge = range/10.0;
                }

                if (portHints & PORT_HINT_IS_OUTPUT)
                {
                    param.data[j].type = PARAMETER_OUTPUT;
                    needsCtrlOut = true;
                }
                else
                {
                    param.data[j].type = PARAMETER_INPUT;
                    needsCtrlIn = true;
                }

                // extra parameter hints
                if (portHints & PORT_HINT_IS_ENABLED)
                    param.data[j].hints |= PARAMETER_IS_ENABLED;

                if (portHints & PORT_HINT_IS_AUTOMABLE)
                    param.data[j].hints |= PARAMETER_IS_AUTOMABLE;

                if (portHints & PORT_HINT_IS_LOGARITHMIC)
                    param.data[j].hints |= PARAMETER_IS_LOGARITHMIC;

                if (portHints & PORT_HINT_USES_SCALEPOINTS)
                    param.data[j].hints |= PARAMETER_USES_SCALEPOINTS;

                if (portHints & PORT_HINT_USES_CUSTOM_TEXT)
                    param.data[j].hints |= PARAMETER_USES_CUSTOM_TEXT;

                param.ranges[j].min = min;
                param.ranges[j].max = max;
                param.ranges[j].def = def;
                param.ranges[j].step = step;
                param.ranges[j].stepSmall = stepSmall;
                param.ranges[j].stepLarge = stepLarge;
            }
        }

        if (needsCtrlIn)
        {
            if (carlaOptions.processMode != PROCESS_MODE_MULTIPLE_CLIENTS)
            {
                strcpy(portName, m_name);
                strcat(portName, ":control-in");
            }
            else
                strcpy(portName, "control-in");

            param.portCin = (CarlaEngineControlPort*)x_client->addPort(CarlaEnginePortTypeControl, portName, true);
        }

        if (needsCtrlOut)
        {
            if (carlaOptions.processMode != PROCESS_MODE_MULTIPLE_CLIENTS)
            {
                strcpy(portName, m_name);
                strcat(portName, ":control-out");
            }
            else
                strcpy(portName, "control-out");

            param.portCout = (CarlaEngineControlPort*)x_client->addPort(CarlaEnginePortTypeControl, portName, false);
        }

        aIn.count   = aIns;
        aOut.count  = aOuts;
        mIn.count   = mIns;
        mOut.count  = mOuts;
        param.count = params;

        // plugin checks
        m_hints &= ~(PLUGIN_IS_SYNTH | PLUGIN_USES_CHUNKS | PLUGIN_CAN_DRYWET | PLUGIN_CAN_VOLUME | PLUGIN_CAN_BALANCE);

        if (aOuts > 0 && (aIns == aOuts || aIns == 1))
            m_hints |= PLUGIN_CAN_DRYWET;

        if (aOuts > 0)
            m_hints |= PLUGIN_CAN_VOLUME;

        if (aOuts >= 2 && aOuts%2 == 0)
            m_hints |= PLUGIN_CAN_BALANCE;

        m_hints |= getPluginHintsFromNative(descriptor->hints);

        reloadPrograms(true);

        x_client->activate();

        qDebug("NativePlugin::reload() - end");
    }

    void reloadPrograms(const bool init)
    {
        qDebug("NativePlugin::reloadPrograms(%s)", bool2str(init));
        uint32_t i, oldCount = midiprog.count;

        // Delete old programs
        if (midiprog.count > 0)
        {
            for (i=0; i < midiprog.count; i++)
            {
                if (midiprog.data[i].name)
                    free((void*)midiprog.data[i].name);
            }

            delete[] midiprog.data;
        }

        midiprog.count = 0;
        midiprog.data  = nullptr;

        // Query new programs
        midiprog.count = descriptor->midiProgramCount;

        if (midiprog.count > 0)
            midiprog.data = new midi_program_t[midiprog.count];

        // Update data
        for (i=0; i < midiprog.count; i++)
        {
            const MidiProgram* const mpDesc = &descriptor->midiPrograms[i];
            Q_ASSERT(mpDesc->program < 128);
            Q_ASSERT(mpDesc->name);

            midiprog.data[i].bank    = mpDesc->bank;
            midiprog.data[i].program = mpDesc->program;
            midiprog.data[i].name    = strdup(mpDesc->name);
        }

#ifndef BUILD_BRIDGE
        // Update OSC Names
        if (x_engine->isOscControllerRegisted())
        {
            x_engine->osc_send_control_set_midi_program_count(m_id, midiprog.count);

            for (i=0; i < midiprog.count; i++)
                x_engine->osc_send_control_set_midi_program_data(m_id, i, midiprog.data[i].bank, midiprog.data[i].program, midiprog.data[i].name);
        }
#endif

        if (init)
        {
            if (midiprog.count > 0)
                setMidiProgram(0, false, false, false, true);
        }
        else
        {
            x_engine->callback(CALLBACK_RELOAD_PROGRAMS, m_id, 0, 0, 0.0);

            // Check if current program is invalid
            bool programChanged = false;

            if (midiprog.count == oldCount+1)
            {
                // one midi program added, probably created by user
                midiprog.current = oldCount;
                programChanged   = true;
            }
            else if (midiprog.current >= (int32_t)midiprog.count)
            {
                // current midi program > count
                midiprog.current = 0;
                programChanged   = true;
            }
            else if (midiprog.current < 0 && midiprog.count > 0)
            {
                // programs exist now, but not before
                midiprog.current = 0;
                programChanged   = true;
            }
            else if (midiprog.current >= 0 && midiprog.count == 0)
            {
                // programs existed before, but not anymore
                midiprog.current = -1;
                programChanged   = true;
            }

            if (programChanged)
                setMidiProgram(midiprog.current, true, true, true, true);
        }
    }

    // -------------------------------------------------------------------
    // Plugin processing

    void process(float** const inBuffer, float** const outBuffer, const uint32_t frames, const uint32_t framesOffset)
    {
        uint32_t i, k;

        double aInsPeak[2]  = { 0.0 };
        double aOutsPeak[2] = { 0.0 };

        // reset MIDI
        midiEventCount = 0;
        memset(midiEvents, 0, sizeof(::MidiEvent) * MAX_MIDI_EVENTS * 2);

        CARLA_PROCESS_CONTINUE_CHECK;

        // --------------------------------------------------------------------------------------------------------
        // Input VU

        if (aIn.count > 0)
        {
            if (aIn.count == 1)
            {
                for (k=0; k < frames; k++)
                {
                    if (abs(inBuffer[0][k]) > aInsPeak[0])
                        aInsPeak[0] = abs(inBuffer[0][k]);
                }
            }
            else if (aIn.count > 1)
            {
                for (k=0; k < frames; k++)
                {
                    if (abs(inBuffer[0][k]) > aInsPeak[0])
                        aInsPeak[0] = abs(inBuffer[0][k]);

                    if (abs(inBuffer[1][k]) > aInsPeak[1])
                        aInsPeak[1] = abs(inBuffer[1][k]);
                }
            }
        }

        CARLA_PROCESS_CONTINUE_CHECK;

        // --------------------------------------------------------------------------------------------------------
        // Parameters Input [Automation]

        if (param.portCin && m_active && m_activeBefore)
        {
            bool allNotesOffSent = false;

            const CarlaEngineControlEvent* cinEvent;
            uint32_t time, nEvents = param.portCin->getEventCount();

            uint32_t nextBankId = 0;
            if (midiprog.current >= 0 && midiprog.count > 0)
                nextBankId = midiprog.data[midiprog.current].bank;

            for (i=0; i < nEvents; i++)
            {
                cinEvent = param.portCin->getEvent(i);

                if (! cinEvent)
                    continue;

                time = cinEvent->time - framesOffset;

                if (time >= frames)
                    continue;

                // Control change
                switch (cinEvent->type)
                {
                case CarlaEngineEventNull:
                    break;

                case CarlaEngineEventControlChange:
                {
                    double value;

                    // Control backend stuff
                    if (cinEvent->channel == m_ctrlInChannel)
                    {
                        if (MIDI_IS_CONTROL_BREATH_CONTROLLER(cinEvent->controller) && (m_hints & PLUGIN_CAN_DRYWET) > 0)
                        {
                            value = cinEvent->value;
                            setDryWet(value, false, false);
                            postponeEvent(PluginPostEventParameterChange, PARAMETER_DRYWET, 0, value);
                            continue;
                        }

                        if (MIDI_IS_CONTROL_CHANNEL_VOLUME(cinEvent->controller) && (m_hints & PLUGIN_CAN_VOLUME) > 0)
                        {
                            value = cinEvent->value*127/100;
                            setVolume(value, false, false);
                            postponeEvent(PluginPostEventParameterChange, PARAMETER_VOLUME, 0, value);
                            continue;
                        }

                        if (MIDI_IS_CONTROL_BALANCE(cinEvent->controller) && (m_hints & PLUGIN_CAN_BALANCE) > 0)
                        {
                            double left, right;
                            value = cinEvent->value/0.5 - 1.0;

                            if (value < 0.0)
                            {
                                left  = -1.0;
                                right = (value*2)+1.0;
                            }
                            else if (value > 0.0)
                            {
                                left  = (value*2)-1.0;
                                right = 1.0;
                            }
                            else
                            {
                                left  = -1.0;
                                right = 1.0;
                            }

                            setBalanceLeft(left, false, false);
                            setBalanceRight(right, false, false);
                            postponeEvent(PluginPostEventParameterChange, PARAMETER_BALANCE_LEFT, 0, left);
                            postponeEvent(PluginPostEventParameterChange, PARAMETER_BALANCE_RIGHT, 0, right);
                            continue;
                        }
                    }

                    // Control plugin parameters
                    for (k=0; k < param.count; k++)
                    {
                        if (param.data[k].midiChannel != cinEvent->channel)
                            continue;
                        if (param.data[k].midiCC != cinEvent->controller)
                            continue;
                        if (param.data[k].type != PARAMETER_INPUT)
                            continue;

                        if (param.data[k].hints & PARAMETER_IS_AUTOMABLE)
                        {
                            if (param.data[k].hints & PARAMETER_IS_BOOLEAN)
                            {
                                value = cinEvent->value < 0.5 ? param.ranges[k].min : param.ranges[k].max;
                            }
                            else
                            {
                                value = cinEvent->value * (param.ranges[k].max - param.ranges[k].min) + param.ranges[k].min;

                                if (param.data[k].hints & PARAMETER_IS_INTEGER)
                                    value = rint(value);
                            }

                            setParameterValue(k, value, false, false, false);
                            postponeEvent(PluginPostEventParameterChange, k, 0, value);
                        }
                    }

                    break;
                }

                case CarlaEngineEventMidiBankChange:
                    if (cinEvent->channel == m_ctrlInChannel)
                        nextBankId = rint(cinEvent->value);
                    break;

                case CarlaEngineEventMidiProgramChange:
                    if (cinEvent->channel == m_ctrlInChannel)
                    {
                        uint32_t nextProgramId = rint(cinEvent->value);

                        for (k=0; k < midiprog.count; k++)
                        {
                            if (midiprog.data[k].bank == nextBankId && midiprog.data[k].program == nextProgramId)
                            {
                                setMidiProgram(k, false, false, false, false);
                                postponeEvent(PluginPostEventMidiProgramChange, k, 0, 0.0);
                                break;
                            }
                        }
                    }
                    break;

                case CarlaEngineEventAllSoundOff:
                    if (cinEvent->channel == m_ctrlInChannel)
                    {
                        if (mIn.count > 0 && ! allNotesOffSent)
                            sendMidiAllNotesOff();

                        if (descriptor->deactivate)
                        {
                            descriptor->deactivate(handle);
                            //if (h2) ldescriptor->deactivate(h2);
                        }

                        if (descriptor->activate)
                        {
                            descriptor->activate(handle);
                            //if (h2) ldescriptor->activate(h2);
                        }

                        allNotesOffSent = true;
                    }
                    break;

                case CarlaEngineEventAllNotesOff:
                    if (cinEvent->channel == m_ctrlInChannel)
                    {
                        if (mIn.count > 0 && ! allNotesOffSent)
                            sendMidiAllNotesOff();

                        allNotesOffSent = true;
                    }
                    break;
                }
            }
        } // End of Parameters Input

        CARLA_PROCESS_CONTINUE_CHECK;

        // --------------------------------------------------------------------------------------------------------
        // MIDI Input

        if (mIn.count > 0 && m_active && m_activeBefore)
        {
            // ----------------------------------------------------------------------------------------------------
            // MIDI Input (External)

            {
                engineMidiLock();

                for (i=0; i < MAX_MIDI_EVENTS && midiEventCount < MAX_MIDI_EVENTS; i++)
                {
                    if (extMidiNotes[i].channel < 0)
                        break;

                    ::MidiEvent* const midiEvent = &midiEvents[midiEventCount];
                    memset(midiEvent, 0, sizeof(::MidiEvent));

                    midiEvent->data[0] = uint8_t(extMidiNotes[i].velo ? MIDI_STATUS_NOTE_ON : MIDI_STATUS_NOTE_OFF) + extMidiNotes[i].channel;
                    midiEvent->data[1] = extMidiNotes[i].note;
                    midiEvent->data[2] = extMidiNotes[i].velo;
                    midiEvent->size = 3;

                    extMidiNotes[i].channel = -1; // mark as invalid
                    midiEventCount += 1;
                }

                engineMidiUnlock();

            } // End of MIDI Input (External)

            CARLA_PROCESS_CONTINUE_CHECK;

            // ----------------------------------------------------------------------------------------------------
            // MIDI Input (System)

            for (i=0; i < mIn.count; i++)
            {
                if (! mIn.ports[i])
                    continue;

                const CarlaEngineMidiEvent* minEvent;
                uint32_t time, nEvents = mIn.ports[i]->getEventCount();

                for (k=0; k < nEvents && midiEventCount < MAX_MIDI_EVENTS; k++)
                {
                    minEvent = mIn.ports[i]->getEvent(k);

                    if (! minEvent)
                        continue;

                    time = minEvent->time - framesOffset;

                    if (time >= frames)
                        continue;

                    uint8_t status  = minEvent->data[0];
                    uint8_t channel = status & 0x0F;

                    // Fix bad note-off
                    if (MIDI_IS_STATUS_NOTE_ON(status) && minEvent->data[2] == 0)
                        status -= 0x10;

                    ::MidiEvent* const midiEvent = &midiEvents[midiEventCount];
                    memset(midiEvent, 0, sizeof(::MidiEvent));

                    midiEvent->portOffset = i;
                    midiEvent->time = minEvent->time;
                    midiEvent->size = minEvent->size;

                    if (MIDI_IS_STATUS_NOTE_OFF(status))
                    {
                        uint8_t note = minEvent->data[1];

                        midiEvent->data[0] = status;
                        midiEvent->data[1] = note;

                        postponeEvent(PluginPostEventNoteOff, channel, note, 0.0);
                    }
                    else if (MIDI_IS_STATUS_NOTE_ON(status))
                    {
                        uint8_t note = minEvent->data[1];
                        uint8_t velo = minEvent->data[2];

                        midiEvent->data[0] = status;
                        midiEvent->data[1] = note;
                        midiEvent->data[2] = velo;

                        postponeEvent(PluginPostEventNoteOn, channel, note, velo);
                    }
                    else if (MIDI_IS_STATUS_POLYPHONIC_AFTERTOUCH(status))
                    {
                        uint8_t note     = minEvent->data[1];
                        uint8_t pressure = minEvent->data[2];

                        midiEvent->data[0] = status;
                        midiEvent->data[1] = note;
                        midiEvent->data[2] = pressure;
                    }
                    else if (MIDI_IS_STATUS_AFTERTOUCH(status))
                    {
                        uint8_t pressure = minEvent->data[1];

                        midiEvent->data[0] = status;
                        midiEvent->data[1] = pressure;
                    }
                    else if (MIDI_IS_STATUS_PITCH_WHEEL_CONTROL(status))
                    {
                        uint8_t lsb = minEvent->data[1];
                        uint8_t msb = minEvent->data[2];

                        midiEvent->data[0] = status;
                        midiEvent->data[1] = lsb;
                        midiEvent->data[2] = msb;
                    }
                    else
                        continue;

                    midiEventCount += 1;
                }
            } // End of MIDI Input (System)

        } // End of MIDI Input

        CARLA_PROCESS_CONTINUE_CHECK;

        // --------------------------------------------------------------------------------------------------------
        // Plugin processing

        uint32_t midiEventCountBefore = midiEventCount;

        if (m_active)
        {
            if (! m_activeBefore)
            {
                if (mIn.count > 0 && m_ctrlInChannel >= 0 && m_ctrlInChannel < 16)
                {
                    memset(&midiEvents[0], 0, sizeof(::MidiEvent));
                    midiEvents[0].data[0] = MIDI_STATUS_CONTROL_CHANGE + m_ctrlInChannel;
                    midiEvents[0].data[1] = MIDI_CONTROL_ALL_SOUND_OFF;
                    midiEvents[0].size = 2;

                    memset(&midiEvents[1], 0, sizeof(::MidiEvent));
                    midiEvents[1].data[0] = MIDI_STATUS_CONTROL_CHANGE + m_ctrlInChannel;
                    midiEvents[1].data[1] = MIDI_CONTROL_ALL_NOTES_OFF;
                    midiEvents[1].size = 2;

                    midiEventCount = 2;
                }

                if (descriptor->activate)
                {
                    descriptor->activate(handle);
                    //if (h2) descriptor->activate(h2);
                }
            }

            isProcessing = true;
            descriptor->process(handle, inBuffer, outBuffer, frames, midiEventCountBefore, midiEvents);
            //if (h2) descriptor->process(h2, inBuffer, outBuffer, frames, midiEventCount, midiEvents);
            isProcessing = false;
        }
        else
        {
            if (m_activeBefore)
            {
                if (descriptor->deactivate)
                {
                    descriptor->deactivate(handle);
                    //if (h2) descriptor->deactivate(h2);
                }
            }
        }

        CARLA_PROCESS_CONTINUE_CHECK;

        // --------------------------------------------------------------------------------------------------------
        // Post-processing (dry/wet, volume and balance)

        if (m_active)
        {
            bool do_drywet  = (m_hints & PLUGIN_CAN_DRYWET) > 0 && x_dryWet != 1.0;
            bool do_volume  = (m_hints & PLUGIN_CAN_VOLUME) > 0 && x_volume != 1.0;
            bool do_balance = (m_hints & PLUGIN_CAN_BALANCE) > 0 && (x_balanceLeft != -1.0 || x_balanceRight != 1.0);

            double bal_rangeL, bal_rangeR;
            float oldBufLeft[do_balance ? frames : 0];

            for (i=0; i < aOut.count; i++)
            {
                // Dry/Wet
                if (do_drywet)
                {
                    for (k=0; k < frames; k++)
                    {
                        if (aOut.count == 1)
                            outBuffer[i][k] = (outBuffer[i][k]*x_dryWet)+(inBuffer[0][k]*(1.0-x_dryWet));
                        else
                            outBuffer[i][k] = (outBuffer[i][k]*x_dryWet)+(inBuffer[i][k]*(1.0-x_dryWet));
                    }
                }

                // Balance
                if (do_balance)
                {
                    if (i%2 == 0)
                        memcpy(&oldBufLeft, outBuffer[i], sizeof(float)*frames);

                    bal_rangeL = (x_balanceLeft+1.0)/2;
                    bal_rangeR = (x_balanceRight+1.0)/2;

                    for (k=0; k < frames; k++)
                    {
                        if (i%2 == 0)
                        {
                            // left output
                            outBuffer[i][k]  = oldBufLeft[k]*(1.0-bal_rangeL);
                            outBuffer[i][k] += outBuffer[i+1][k]*(1.0-bal_rangeR);
                        }
                        else
                        {
                            // right
                            outBuffer[i][k]  = outBuffer[i][k]*bal_rangeR;
                            outBuffer[i][k] += oldBufLeft[k]*bal_rangeL;
                        }
                    }
                }

                // Volume
                if (do_volume)
                {
                    for (k=0; k < frames; k++)
                        outBuffer[i][k] *= x_volume;
                }

                // Output VU
                for (k=0; i < 2 && k < frames; k++)
                {
                    if (abs(outBuffer[i][k]) > aOutsPeak[i])
                        aOutsPeak[i] = abs(outBuffer[i][k]);
                }
            }
        }
        else
        {
            // disable any output sound if not active
            for (i=0; i < aOut.count; i++)
                memset(outBuffer[i], 0.0f, sizeof(float)*frames);

            aOutsPeak[0] = 0.0;
            aOutsPeak[1] = 0.0;

        } // End of Post-processing

        CARLA_PROCESS_CONTINUE_CHECK;

        // --------------------------------------------------------------------------------------------------------
        // MIDI Output

        if (mOut.count > 0 && m_active)
        {
            uint8_t data[3] = { 0 };

            for (uint32_t i = midiEventCountBefore; i < midiEventCount; i++)
            {
                data[0] = midiEvents[i].data[0];
                data[1] = midiEvents[i].data[1];
                data[2] = midiEvents[i].data[2];

                // Fix bad note-off
                if (MIDI_IS_STATUS_NOTE_ON(data[0]) && data[2] == 0)
                    data[0] -= 0x10;

                const uint32_t portOffset = midiEvents[i].portOffset;

                if (portOffset < mOut.count)
                    mOut.ports[portOffset]->writeEvent(midiEvents[i].time, data, 3);
            }

        } // End of MIDI Output

        // --------------------------------------------------------------------------------------------------------
        // Control Output

        if (param.portCout && m_active)
        {
            double value, valueControl;

            for (k=0; k < param.count; k++)
            {
                if (param.data[k].type == PARAMETER_OUTPUT)
                {
                    value = descriptor->get_parameter_value(handle, param.data[k].rindex);

                    if (param.data[k].midiCC > 0)
                    {
                        valueControl = (value - param.ranges[k].min) / (param.ranges[k].max - param.ranges[k].min);
                        param.portCout->writeEvent(CarlaEngineEventControlChange, framesOffset, param.data[k].midiChannel, param.data[k].midiCC, valueControl);
                    }
                }
            }
        } // End of Control Output

        CARLA_PROCESS_CONTINUE_CHECK;

        // --------------------------------------------------------------------------------------------------------
        // Peak Values

        x_engine->setInputPeak(m_id, 0, aInsPeak[0]);
        x_engine->setInputPeak(m_id, 1, aInsPeak[1]);
        x_engine->setOutputPeak(m_id, 0, aOutsPeak[0]);
        x_engine->setOutputPeak(m_id, 1, aOutsPeak[1]);

        m_activeBefore = m_active;
    }

    // -------------------------------------------------------------------
    // Cleanup

    void removeClientPorts()
    {
        qDebug("NativePlugin::removeClientPorts() - start");

        for (uint32_t i=0; i < mIn.count; i++)
        {
            delete mIn.ports[i];
            mIn.ports[i] = nullptr;
        }

        for (uint32_t i=0; i < mOut.count; i++)
        {
            delete mOut.ports[i];
            mOut.ports[i] = nullptr;
        }

        CarlaPlugin::removeClientPorts();

        qDebug("NativePlugin::removeClientPorts() - end");
    }

    void initBuffers()
    {
        uint32_t i;

        for (i=0; i < mIn.count; i++)
        {
            if (mIn.ports[i])
                mIn.ports[i]->initBuffer(x_engine);
        }

        for (i=0; i < mOut.count; i++)
        {
            if (mOut.ports[i])
                mOut.ports[i]->initBuffer(x_engine);
        }

        CarlaPlugin::initBuffers();
    }

    void deleteBuffers()
    {
        qDebug("NativePlugin::deleteBuffers() - start");

        if (mIn.count > 0)
        {
            delete[] mIn.ports;
            delete[] mIn.rindexes;
        }

        if (mOut.count > 0)
        {
            delete[] mOut.ports;
            delete[] mOut.rindexes;
        }

        mIn.count = 0;
        mIn.ports = nullptr;
        mIn.rindexes = nullptr;

        mOut.count = 0;
        mOut.ports = nullptr;
        mOut.rindexes = nullptr;

        CarlaPlugin::deleteBuffers();

        qDebug("NativePlugin::deleteBuffers() - end");
    }

    // -------------------------------------------------------------------

    uint32_t handleGetBufferSize()
    {
        return x_engine->getBufferSize();
    }

    double handleGetSampleRate()
    {
        return x_engine->getSampleRate();
    }

    const TimeInfo* handleGetTimeInfo()
    {
        // TODO
        return nullptr;
    }

    bool handleWriteMidiEvent(MidiEvent* event)
    {
        Q_ASSERT(m_enabled);
        Q_ASSERT(mOut.count > 0);
        Q_ASSERT(isProcessing);
        Q_ASSERT(event);

        if (! m_enabled)
            return false;

        if (mOut.count == 0)
            return false;

        if (! isProcessing)
        {
            qCritical("NativePlugin::handleWriteMidiEvent(%p) - received MIDI out events outside audio thread, ignoring", event);
            return false;
        }

        if (midiEventCount >= MAX_MIDI_EVENTS*2)
            return false;

        memcpy(&midiEvents[midiEventCount], event, sizeof(::MidiEvent));
        midiEventCount += 1;

        return true;
    }

    static uint32_t carla_host_get_buffer_size(HostHandle handle)
    {
        Q_ASSERT(handle);
        return ((NativePlugin*)handle)->handleGetBufferSize();
    }

    static double carla_host_get_sample_rate(HostHandle handle)
    {
        Q_ASSERT(handle);
        return ((NativePlugin*)handle)->handleGetSampleRate();
    }

    static const TimeInfo* carla_host_get_time_info(HostHandle handle)
    {
        Q_ASSERT(handle);
        return ((NativePlugin*)handle)->handleGetTimeInfo();
    }

    static bool carla_host_write_midi_event(HostHandle handle, MidiEvent* event)
    {
        Q_ASSERT(handle);
        return ((NativePlugin*)handle)->handleWriteMidiEvent(event);
    }

    // -------------------------------------------------------------------

    static size_t getPluginCount()
    {
        return pluginDescriptors.size();
    }

    static const PluginDescriptor* getPlugin(size_t index)
    {
        Q_ASSERT(index < pluginDescriptors.size());

        if (index < pluginDescriptors.size())
            return pluginDescriptors[index];

        return nullptr;
    }

    static void registerPlugin(const PluginDescriptor* desc)
    {
        pluginDescriptors.push_back(desc);
    }

    // -------------------------------------------------------------------

    bool init(const char* const name, const char* const label)
    {
        // ---------------------------------------------------------------
        // get descriptor that matches label

        for (size_t i=0; i < pluginDescriptors.size(); i++)
        {
            descriptor = pluginDescriptors[i];

            if (! descriptor)
                break;
            if (strcmp(descriptor->label, label) == 0)
                break;

            descriptor = nullptr;
        }

        if (! descriptor)
        {
            setLastError("Invalid internal plugin");
            return false;
        }

        scopedInitliazer.initializeIfNeeded(descriptor);

        // ---------------------------------------------------------------
        // initialize plugin

        handle = descriptor->instantiate((struct _PluginDescriptor*)descriptor, &host);

        if (! handle)
        {
            setLastError("Plugin failed to initialize");
            return false;
        }

        // ---------------------------------------------------------------
        // get info

        if (name)
            m_name = x_engine->getUniqueName(name);
        else
            m_name = x_engine->getUniqueName(descriptor->name);

        // ---------------------------------------------------------------
        // register client

        x_client = x_engine->addClient(this);

        if (! x_client->isOk())
        {
            setLastError("Failed to register plugin client");
            return false;
        }

        return true;
    }

private:
    const PluginDescriptor* descriptor;
    PluginHandle handle;
    HostDescriptor host;

    bool isProcessing;

    NativePluginMidiData mIn;
    NativePluginMidiData mOut;

    uint32_t    midiEventCount;
    ::MidiEvent midiEvents[MAX_MIDI_EVENTS*2];

    static std::vector<const PluginDescriptor*> pluginDescriptors;
};

std::vector<const PluginDescriptor*> NativePlugin::pluginDescriptors;

CarlaPlugin* CarlaPlugin::newNative(const initializer& init)
{
    qDebug("CarlaPlugin::newNative(%p, \"%s\", \"%s\", \"%s\")", init.engine, init.filename, init.name, init.label);

    short id = init.engine->getNewPluginId();

    if (id < 0 || id > CarlaEngine::maxPluginNumber())
    {
        setLastError("Maximum number of plugins reached");
        return nullptr;
    }

    NativePlugin* const plugin = new NativePlugin(init.engine, id);

    if (! plugin->init(init.name, init.label))
    {
        delete plugin;
        return nullptr;
    }

    plugin->reload();
    plugin->registerToOsc();

    return plugin;
}

size_t CarlaPlugin::getNativePluginCount()
{
    return NativePlugin::getPluginCount();
}

const PluginDescriptor* CarlaPlugin::getNativePlugin(size_t index)
{
    return NativePlugin::getPlugin(index);
}

CARLA_BACKEND_END_NAMESPACE

void carla_register_native_plugin(const PluginDescriptor* desc)
{
    CarlaBackend::NativePlugin::registerPlugin(desc);
}