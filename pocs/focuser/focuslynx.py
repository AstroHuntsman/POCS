import serial
import time
from warnings import warn

import astropy.units as u

from pocs.focuser import AbstractFocuser

class Focuser(AbstractFocuser):
    """
    Focuser class for control of telescope focusers using the Optec FocusLynx focus controller.

    This includes the Starlight Instruments Focus Boss II controller, which is "powered by Optec"

    Args:
        name (str, optional): default 'FocusLynx Focuser'
        model (str, optional): default 'Focus Boss II'
        initial_position (int, optional): if given the focuser will drive to this encoder position
            following initialisation.
        focuser_number (int, optional): for focus controllers that support more than one focuser
            set this number to specify which focuser should be controlled by this object. Default 1
        min_position (int, optional): minimum allowed focuser position in encoder units, default 0
        max_position (int, optional): maximum allowed focuser position in encoder units. If not
            given the value will be taken from the focuser's internal config.

    Additional positional and keyword arguments are passed to the base class, AbstractFocuser. See
    that class for a complete list.
    """
    def __init__(self,
                 name='FocusLynx Focuser',
                 model='FA',
                 initial_position=None,
                 focuser_number=1,
                 min_position=0,
                 max_position=None,
                 *args, **kwargs):
        super().__init__(name=name, model=model, *args, **kwargs)
        self.logger.debug('Initialising FocusLynx focuser')

        try:
            self.connect()
        except (serial.SerialException, serial.SerialTimeoutException) as err:
            message = 'Error connecting to {} on {}: {}'.format(self.name, port, err)
            self.logger.error(message)
            warn(message)
            return

        self._focuser_number = focuser_number
        self._initialise()

        if min_position >= 0:
            self._min_position = int(min_position)
        else:
            self._min_position = 0
            message = "Specified min_position {} less than zero, ignoring!".format(min_position)
            warn(message)

        if max_position is not None:
            if max_position <= self._max_position:
                if max_position > self._min_position:
                    self._max_position = int(max_position)
                else:
                    raise ValueError('Max position must be greater than min position!')
            else:
                message = "Specified max_position {} greater than focuser max {}!".format(max_position,
                                                                                          self._max_position)
                warn(message)

        if initial_position is not None:
            self.position = initial_position

    def __del__(self):
        try:
            self._serial_port.close()
            self.logger.debug('Closed serial port {}'.format(self._port))
        except AttributeError:
            pass

    def __str__(self):
        return "{} {} ({}) on {}".format(self.name, self._focuser_number, self.uid, self.port)

##################################################################################################
# Properties
##################################################################################################

    @property
    def uid(self):
        """
        The user set 'nickname' of the focuser. Must be <= 16 characters
        """
        return self._focuser_config['Nickname']

    @uid.setter
    def uid(self, nickname):
        if len(nickname) > 16:
            self.logger.warning('Truncated nickname {} to {} (must be <= 16 characters)'.format(nickname,
                                                                                                nickname[:16]))
            nickname = nickname[:16]
        self._set_param('<F{:1d}SCNN{}>'.format(self._focuser_number, nickname))
        self._get_focuser_config()

    @property
    def is_connected(self):
        """
        Checks status of serial port to determine if connected.
        """
        connected = False
        if self._serial_port:
            connected = self._serial_port.isOpen()
        return connected

    @AbstractFocuser.position.getter
    def position(self):
        """
        Current focus position in encoder units
        """
        self._update_focuser_status()
        return self._position

    @property
    def min_position(self):
        """
        Position of close limit of focus travel, in encoder units
        """
        return self._min_position

    @property
    def max_position(self):
        """
        Position of far limit of focus travel, in encoder units
        """
        return self._max_position

    @property
    def firmware_version(self):
        """
        Firmware version of the focuser controller
        """
        return self._hub_info['Hub FVer']

    @property
    def hardware_version(self):
        """
        Device type code of the focuser
        """
        return self.model

    @property
    def temperature(self):
        """
        Current temperature of the focuser
        """
        self._update_focuser_status
        return self._temperature * u.Celsius

    @property
    def is_moving(self):
        """
        True if the focuser is currently moving
        """
        self._update_focuser_status()
        return self._is_moving

#################################################################################################
# Methods
##################################################################################################

    def connect(self):
        try:
            # Configure serial port.
            self._serial_port = serial.Serial(port=self.port,
                                              baudrate=115200,
                                              bytesize=serial.EIGHTBITS,
                                              parity=serial.PARITY_NONE,
                                              stopbits=serial.STOPBITS_ONE,
                                              timeout=1.0)

        except serial.SerialException as err:
            self._serial_port = None
            self.logger.critical('Could not open {}!'.format(self.port))
            raise err

        self.logger.debug('Established serial connection to {} on {}'.format(self.name, self.port))

    def move_to(self, position, blocking=True):
        """
        Move encoder to a new encoder position. Blocking by default, but if blocking=False is
        passed then will return immediately. If blocking=True returns actual position following
        move, otherwise returns target position
        """
        if position < self._min_position:
            message = 'Requested position {} less than min position, moving to {}!'.format(position,
                                                                                           self._min_position)
            self.logger.error(message)
            warn(message)
            position = self._min_position
        elif position > self._max_position:
            message = 'Requested position {} greater than max position, moving to {}!'.format(position,
                                                                                              self._max_position)
            self.logger.error(message)
            warn(message)
            position = self._max_position

        self.logger.debug('Moving focuser {} to {}'.format(self.uid, position))
        self._send_command('<F{:1d}MA{:06d}>'.format(self._focuser_number, position),
                           command_type='MOVE')

        if blocking:
            while self.is_moving:
                time.sleep(1)
            if self.position != self._target_position:
                message = "Focuser {} did not reach target position {}, now at {}!".format(self.uid,
                                                                                           self._target_position,
                                                                                           self._position)
                self.logger.warning(message)
                warn(message)
            return self._position
        else:
            return position

    def halt(self):
        """
        Causes the focuser to immediately stop any movements
        """
        self._send_command('<F{:1d}HALT>'.format(self._focuser_number), command_type='HALT')
        self.logger.warning("Focuser {} halted".format(self.uid))

##################################################################################################
# Private Methods
##################################################################################################

    def _initialise(self):
        self._get_hub_info()
        self._get_focuser_config()
        self._update_focuser_status()

        self.model = self._focuser_config['Dev Typ']
        self._max_position = int(self._focuser_config['Max Pos'])

        self.logger.info('{} initialised'.format(self))

    def _get_hub_info(self):
        self._hub_info = self._get_info('<FHGETHUBINFO>', 'HUB INFO')

    def _get_focuser_config(self):
        self._focuser_config = self._get_info('<F{:1d}GETCONFIG>'.format(self._focuser_number),
                                              'CONFIG{:1d}'.format(self._focuser_number))

    def _update_focuser_status(self):
        self._focuser_status = self._get_info('<F{:1d}GETSTATUS>'.format(self._focuser_number),
                                              'STATUS{:1d}'.format(self._focuser_number))
        self._position = int(self._focuser_status['Curr Pos'])
        self._target_position = int(self._focuser_status['Targ Pos'])
        self._is_moving = bool(int(self._focuser_status['IsMoving']))
        self._temperature = float(self._focuser_status['Temp(C)'])

    def _get_info(self, command_str, header_str):
        """
        Utility function for info type commands (multiline response, starting with "!" and ending
        with 'END').
        """
        try:
            info = self._send_command(command_str, command_type='GET INFO', header_str=header_str)
        except RuntimeError as err:
            message = "Error setting parameter using command '{}': {}".format(command_str, err)
            self.logger.error(message)
            warn(message)
            return None
        else:
            return info

    def _set_param(self, command_str):
        """
        Utility function for parameter setting commands. Expected response is 2 lines,
        '!' and 'SET'.
        """
        try:
            self._send_command(command_str, command_type='SET PARAM')
        except RuntimeError as err:
            message = "Error setting parameter using command '{}': {}".format(command_str, err)
            self.logger.error(message)
            warn(message)

    def _send_command(self, command_str, command_type, **kwargs):
        """
        Utility function that handles the common aspects of sending commands and
        parsing responses.
        """
        # Make sure we start with a clean slate
        self._serial_port.reset_output_buffer()
        self._serial_port.reset_input_buffer()
        # Send command
        self._serial_port.write(command_str.encode('ascii'))
        # Should always get '!' back unless there's an error
        response = str(self._serial_port.readline(), encoding='ascii').strip()
        if response != '!':
            raise RuntimeError(response)

        if command_type == 'GET INFO':
            # Expect header string, several lines of key = value, then 'END'
            assert str(self._serial_port.readline(),
                       encoding='ascii').strip() == kwargs['header_str']
            info = {}
            response = str(self._serial_port.readline(), encoding='ascii').strip()
            while response != 'END':
                key, value = (item.strip() for item in response.split('='))
                info[key] = value
                response = str(self._serial_port.readline(), encoding='ascii').strip()
            return info
        elif command_type == 'SET PARAM':
            assert str(self._serial_port.readline(), encoding='ascii').strip() == 'SET'
        elif command_type == 'MOVE':
            assert str(self._serial_port.readline(), encoding='ascii').strip() == 'M'
        elif command_type == 'HALT':
            assert str(self._serial_port.readline(), encoding='ascii').strip() == 'HALTED'
        else:
            raise ValueError('Invalid command type {}!'.format(command_type))

    def _fits_header(self, header):
        header = super()._fits_header(header)
        header.set('FOC-MOD', self.model, 'Focuser device type')
        header.set('FOC-ID', self.uid, 'Focuser nickname')
        header.set('FOC-HW', self.hardware_version, 'Focuser device type')
        header.set('FOC-FW', self.firmware_version, 'Focuser controller firmware version')
        header.set('FOC-TEMP', self.temperature, 'Focuser temperature (deg C)')
        return header
