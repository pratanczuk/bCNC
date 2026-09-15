"""Translate controller and transport failures into actionable user messages."""

import re
from PlotterPolicy import can_unlock

# grblHAL core alarms.h/errors.h; unknown and driver-specific codes use fallback guidance.
ALARM_GROUPS = {
    1: ('The plotter reached its travel limit', 'Check for an obstruction or a triggered limit switch. Restore the machine position before cutting again.'),
    2: ('This move is outside the working area', 'Check the origin, mat size and design position before trying again.'),
    3: ('The cut was interrupted', 'The machine may have lost its position. Inspect the material and restore the origin before another cut.'),
    4: ('A sensor check could not start', 'Check the probe or sensor state and wiring before repeating the operation.'),
    5: ('The expected sensor was not detected', 'Check the probe or sensor and its travel settings before repeating the operation.'),
    6: ('Finding the origin was interrupted', 'Check the machine, then repeat the homing procedure from Advanced settings.'),
    7: ('A cover opened during homing', 'Close the cover and check the machine before repeating the homing procedure.'),
    8: ('A limit switch stayed active', 'Check that the switch can release and the axis can move away from it.'),
    9: ('The origin switch was not found', 'Check the homing switch, wiring and travel settings.'),
    10: ('Emergency stop is active', 'Inspect the machine and resolve the cause. Release the emergency stop only when safe, then follow the machine’s reset procedure.'),
    11: ('The plotter needs its origin', 'Complete the homing procedure in Advanced settings, then position and confirm the mat.'),
    12: ('A limit switch is active', 'Check the switch and axis position. Resolve the cause before continuing.'),
    13: ('Sensor protection stopped the machine', 'Check the probe or sensor for unexpected contact before continuing.'),
    14: ('The tool did not become ready', 'Check the tool controller and firmware configuration. Review the spindle-related settings in Advanced settings.'),
    15: ('The axes could not finish alignment', 'Check both homing switches and axis movement before repeating alignment.'),
    16: ('The controller’s startup check failed', 'Review the controller diagnostics and hardware connections before using the machine.'),
    17: ('A motor reported a fault', 'Inspect the axis and motor driver. Resolve the fault before resetting the machine.'),
    18: ('The plotter could not find its origin', 'Check the homing switches and configuration before trying homing again.'),
    19: ('A controller device is not responding', 'Check the connected device and its communication wiring.'),
    20: ('An input/output device reported a fault', 'Check the controller’s expansion hardware and wiring.'),
    21: ('The controller could not read its settings', 'Review the saved machine settings in diagnostics before using the plotter.'),
    22: ('The controller received too much data', 'Review the connection and controller configuration before restarting the job.'),
}
ERROR_ALARMS = {13: 7, 45: 12, 46: 11, 49: 16, 50: 10, 51: 17}


def friendly_error(title, detail):
    raw = f'{title}\n{detail}'.lower()
    if title == 'Internal application error':
        return ('This action couldn’t finish',
                'Foil Studio encountered an unexpected problem. Review your design before trying again. If it repeats, save your work if possible and share the details for support.',
                'Review details', 'details')
    if 'restarted during mat handling' in raw:
        return ('The plotter restarted',
                'Mat movement was interrupted. Wait until the plotter is ready, check the mat, then load it again and confirm alignment.',
                'Review plotter', 'diagnostics')
    alarm = re.search(r'\balarm\s*:\s*(\d+)', raw)
    error = re.search(r'\berror\s*:\s*(\d+)', raw)
    if alarm:
        code = int(alarm.group(1))
        heading, message = ALARM_GROUPS.get(code, ('Your plotter needs attention',
            'The controller reported an unfamiliar alarm. Inspect the machine and review Advanced settings before continuing.'))
        return heading, message, 'Review plotter', 'diagnostics'
    if error:
        code = int(error.group(1))
        if code in ERROR_ALARMS:
            heading, message = ALARM_GROUPS[ERROR_ALARMS[code]]
            return heading, message, 'Review plotter', 'diagnostics'
        if code in (8, 9):
            return ('The plotter isn’t ready yet', 'Wait for motion to finish and resolve any active alarm before trying again.', 'Review plotter', 'diagnostics')
        if code in (15,):
            return ('This move is outside the working area', 'Check the origin and move the artwork inside the mat.', 'Arrange design', 'arrange')
        if code in (22, 43):
            return ('Check the cutting speed', 'Set a valid cutting speed for your plotter before starting again.', 'Check cut settings', 'settings')
        if code in (5, 7, 10, 12, 17, 52, 53, 55):
            return ('A machine setting needs attention', 'Review the controller configuration before repeating the operation.', 'Review plotter', 'diagnostics')
        return ('The plotter couldn’t use this command',
                'The command may not match this firmware or artwork. Review the details and controller configuration before trying again.',
                'Review details', 'details')
    if title in ('Tool sequence interrupted', 'Tool change needs attention'):
        return ('Check the tool sequence', detail.split('\nController:')[0], 'Review plotter', 'diagnostics')
    if title == 'Unsupported file type':
        return ('Choose a cutting design', 'Import SVG, DXF or a GRBL cut file. 3D mesh files are not supported by this plotter workspace.', 'Back to design', 'design')
    if title in ('Preview unavailable', 'Cannot open image') or any(word in title.lower() for word in ('import', 'file', 'save')):
        return ('We couldn’t open or prepare this artwork',
                'Check that the file is available and uses a supported format. Try another file or review the details.',
                'Review details', 'details')
    if title.lower() == 'empty gcode':
        return ('There’s nothing to cut yet', 'Add artwork or enable an object, then review the cut again.', 'Back to design', 'design')
    if title.lower() == 'already running':
        return ('A cut is already in progress', 'Wait for this cut to finish or stop it before starting another.', 'Review details', 'details')
    if title == 'Check cutting settings':
        return ('Check your cutting settings',
                'Use positive dimensions and speed, a blade offset of zero or more, and pressure between 0 and 1000.',
                'Check cut settings', 'settings')
    if 'socket://' in raw or 'tcp connection' in raw:
        if any(word in raw for word in ('name or service not known', 'getaddrinfo', 'name resolution', 'nodename nor servname')):
            return ('We can’t find that plotter on the network',
                    'Check the hostname and network connection. If the .local name does not resolve, try the plotter’s IP address.',
                    'Connection setup', 'connection')
        if any(word in raw for word in ('refused', 'errno 111', '10061')):
            return ('The plotter isn’t accepting a TCP connection',
                    'Check that its TCP service is enabled and that the port number is correct. Close any other app connected to the plotter, then try again.',
                    'Connection setup', 'connection')
        if any(word in raw for word in ('timed out', 'timeout', 'unreachable', 'no route')):
            return ('The network plotter isn’t responding',
                    'Check its power, hostname or IP address, and TCP port. Make sure your computer can reach the plotter’s network.',
                    'Connection setup', 'connection')
        if any(word in raw for word in ('lost', 'disconnected', 'reset by peer', 'closed', 'broken pipe')):
            return ('The network connection was interrupted',
                    'Check the plotter’s power and network, then reconnect. Inspect the material and confirm the mat position before another cut.',
                    'Reconnect plotter', 'connection')
        return ('We couldn’t connect to the network plotter',
                'Check the hostname or IP address and TCP port. Make sure the plotter is powered on and its TCP service is available.',
                'Connection setup', 'connection')
    connection = any(word in raw for word in ('connect', 'serial', 'could not open port', 'usb'))
    if connection:
        if any(word in raw for word in ('errno 2', 'no such file', 'cannot find', 'filenotfound')):
            return ('We can’t find your plotter',
                    'Check that it’s powered on and the USB cable is connected. Then choose its port again.',
                    'Choose plotter', 'connection')
        if any(word in raw for word in ('permission', 'access is denied', 'errno 13')):
            return ('Connection isn’t allowed',
                    'Your computer is blocking access to the plotter. Check its USB access permissions, then try connecting again.',
                    'Connection setup', 'connection')
        if any(word in raw for word in ('busy', 'already open', 'resource temporarily unavailable')):
            return ('The plotter may be in use',
                    'Close other cutting apps that could be connected to the plotter, then try again.',
                    'Try connecting', 'connection')
        if any(word in raw for word in ('lost', 'disconnected', 'removed')):
            return ('The connection was interrupted',
                    'Check the power and USB cable, then reconnect. Inspect the material and confirm the mat position before another cut.',
                    'Reconnect plotter', 'connection')
        return ('We couldn’t connect',
                'Check the power and USB cable. Choose the plotter’s port and try again.',
                'Connection setup', 'connection')
    if title == 'Unlock requested':
        return ('Waiting for your plotter',
                'Wait until it is ready. Check the origin and confirm the mat position before cutting.',
                'Review plotter', 'diagnostics')
    if any(word in raw for word in ('alarm', 'door', 'needs attention')):
        return ('Your plotter needs attention',
                'Check the blade, mat and any open cover. Resolve the cause before unlocking, then confirm the mat position again.',
                'Review plotter', 'diagnostics')
    if title == 'Cannot prepare cut':
        if 'outside' in raw or 'extend' in raw:
            return ('Your design needs more room',
                    'Move the design inward or make it smaller. Leave space around it for the blade offset and overcut.',
                    'Arrange design', 'arrange')
        return ('This design isn’t ready to cut',
                'Check the artwork and drag-knife settings, then review the cut again.',
                'Check cut settings', 'settings')
    if title == 'Nothing to separate':
        return ('These outlines are already separate',
                'Choose an object with several outlines, such as lettering or combined shapes.',
                'Back to design', 'design')
    if 'rejected' in raw or 'error:' in raw:
        return ('The plotter couldn’t follow a command',
                'Inspect the blade and material. Review the cut settings and artwork before starting again.',
                'Check cut settings', 'settings')
    return ('Something needs a quick check',
            'This action couldn’t finish. Open the details to find out more before trying again.',
            'Review details', 'details')
