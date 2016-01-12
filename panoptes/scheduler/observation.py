import os.path

from astropy import units as u
from astropy.time import Time

from collections import OrderedDict

from ..utils.logger import get_logger
from ..utils.config import load_config
from ..utils import error


class Exposure(object):

    """ An individual exposure taken by an `Observation` """

    def __init__(self, exptime=120, filter_type=None, analyze=False, cameras=[]):

        self.exptime = exptime
        self.filter_type = filter_type
        self.analyze = analyze
        self.cameras = cameras

        self.images = OrderedDict()

        self._images_exist = False

        self._is_exposing = False
        self._exposed = False

    @property
    def complete(self):
        return not self.images_exist and not self.is_exposing

    @property
    def has_images(self):
        return len(self.images) > 0

    @property
    def is_exposing(self):
        return self._is_exposing

    @property
    def exposed(self):
        return self.images_exist

    @property
    def images_exist(self):
        """ Whether or not the images indicated by `self.images` exists.

        The `images` attribute is set when the exposure starts, so this is
        effectively a test for if the exposure has ended correctly.
        """
        self._exposed = all(os.path.exists(f) for f in self.images)

        return self._exposed

    def expose(self):
        """ Takes an exposure with each camera in `cameras`.

        Loop through each camera and take the corresponding `primary` or `secondary` type.
        """

        try:
            # One start_time for this round of exposures
            start_time = Time.now().isot

            obs_info = {}

            # Take a picture with each camera
            for cam_name, cam in self.cameras.items():
                # Start exposure
                img_file = cam.take_exposure(seconds=self.exptime)
                self._is_exposing = True

                obs_info = {
                    'name': cam_name,
                    'camera_id': cam.uid,
                    'img_file': img_file,
                    'analyze': cam.is_primary and self.analyze,
                    'filter': self.filter_type,
                    'start_time': start_time,
                }
                self.logger.debug("{}".format(obs_info))
                self.images.append(img_file)

        except error.InvalidCommand as e:
            self.logger.warning("{} is already running a command.".format(cam.name))
            self._is_exposing = False
        except Exception as e:
            self.logger.warning("Problem with taking exposure: {}".format(e))
            self._is_exposing = False


class Observation(object):

    def __init__(self, obs_config=dict(), cameras=None):
        """An object which describes a single observation.

        Each observation can have a number of different `Exposure`s based on the config settings.
        For each type of exposure ('primary' or 'secondary') there are `[type]_nexp` `Exposure`
        objects created. Each of these `Exposure`s has a list of cameras. (See `Exposure` for details)

        Example::

              - analyze: false
                primary_exptime: 300
                primary_filter: null
                primary_nexp: 3
                secondary_exptime: 300
                secondary_filter: null
                secondary_nexp: 3

        Args:
            obs_config (dictionary): a dictionary describing the observation as read from
                the YAML file, see Example.
            cameras(list[panoptes.camera]): A list of `panoptes.camera` objects to use for
                this observation.

        """
        self.config = load_config()
        self.logger = get_logger(self)

        self.exposures = self._create_exposures(obs_config, cameras)
        self._current_exposure = 0


##################################################################################################
# Properties
##################################################################################################

    @property
    def current_exposure(self):
        primary = self.exposures['primary'][self._current_exposure]
        secondary = self.exposures['secondary'][self._current_exposure]

        return [primary, secondary]

    @property
    def has_exposures(self):
        """ Bool indicating whether or not any exposures are left """
        self.logger.debug("Checking if observation has exposures")

        is_complete = []

        for exp_type, exps in self.exposures.items():
            for exp in exps:
                self.logger.debug("{} {}".format(exp_type, exp.complete))
                is_complete.append(exp.complete)

        has_exposures = not all(is_complete)
        self.logger.debug("Observation has exposures: {}".format(has_exposures))

        return has_exposures

##################################################################################################
# Methods
##################################################################################################

    def get_next_exposure(self):
        """ Yields the next exposure """

        yield self.current_exposure
        self._current_exposure = self._current_exposure + 1

    def take_exposure(self):
        """ Take the next exposure """
        primary, secondary = self.get_next_exposure()
        try:
            primary.expose()
            secondary.expose()
        except Exception as e:
            self.logger.warning("Can't take exposure from Observation: {}".format(e))

    def estimate_duration(self, overhead=0 * u.s):
        """Method to estimate the duration of a single observation.

        A quick and dirty estimation of the time it takes to execute the
        observation.  Does not take overheads such as slewing, image readout,
        or image download in to consideration.

        Args:
            overhead (astropy.units.Quantity): The overhead time for the observation in
            units which are reducible to seconds.  This is the overhead which occurs
            for each exposure.

        Returns:
            astropy.units.Quantity: The duration (with units of seconds).
        """
        duration = max([(self.primary_exptime + overhead) * self.primary_nexp,
                        (self.secondary_exptime + overhead) * self.secondary_nexp])
        self.logger.debug('Observation duration estimated as {}'.format(duration))
        return duration

##################################################################################################
# Private Methods
##################################################################################################

    def _create_exposures(self, obs_config, cameras):
        self.logger.debug("Creating exposures")
        primary_exptime = obs_config.get('primary_exptime', 120) * u.s
        primary_filter = obs_config.get('primary_filter', None)
        primary_nexp = obs_config.get('primary_nexp', 1)
        analyze = obs_config.get('primary_analyze', False)

        primary_exposures = [Exposure(
            exptime=primary_exptime,
            filter_type=primary_filter,
            analyze=analyze,
            cameras=[c for c in cameras.values() if c.is_primary],
        ) for n in range(primary_nexp)]
        self.logger.debug("Primary exposures: {}".format(primary_exposures))

        # secondary_exptime (assumes units of seconds, defaults to 120 seconds)
        secondary_exptime = obs_config.get('secondary_exptime', 120) * u.s
        secondary_nexp = obs_config.get('secondary_nexp', primary_nexp)
        secondary_filter = obs_config.get('secondary_filter', None)

        secondary_exposures = [Exposure(
            exptime=secondary_exptime,
            filter_type=secondary_filter,
            analyze=False,
            cameras=[c for c in cameras.values() if not c.is_primary],
        ) for n in range(secondary_nexp)]
        self.logger.debug("Secondary exposures: {}".format(secondary_exposures))

        return {'primary': primary_exposures, 'secondary': secondary_exposures}
